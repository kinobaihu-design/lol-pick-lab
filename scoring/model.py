"""The scoring model, step by step as in the brief (v0.38).

Reads the files the collector saves (see the README on the `data` branch) and returns
one dictionary with everything the website will need.
"""

import gzip
import json
import os
import re
import statistics
from datetime import datetime, timezone

from . import comfort as comfort_module
from . import config

# ---------------------------------------------------------------- reading files


def read_json(path):
    with open(path, "rb") as f:
        raw = f.read()
    if path.endswith(".gz"):
        raw = gzip.decompress(raw)
    return json.loads(raw)


def patch_order(name):
    return tuple(int(part) for part in name.split("."))


def list_patches(root):
    folder = os.path.join(root, "patches")
    names = [n for n in os.listdir(folder) if re.match(r"^\d+\.\d+$", n)] if os.path.isdir(folder) else []
    return sorted(names, key=patch_order)


class Patch:
    """One patch's totals. Counters are [games x2, wins x2, games x1, wins x1]."""

    def __init__(self, root, name):
        self.name = name
        self.root = root
        folder = os.path.join(root, "patches", name)
        self.summary = read_json(os.path.join(folder, "summary.json"))
        self.champions = read_json(os.path.join(folder, "champions.json"))
        self.weight = self.summary.get("double_weight", 2)
        self.average = self.summary["diamond_plus_average_win_rate"]   # percent
        participants = self.summary["participants"]
        self.participants_weighted = self.weight * participants[0] + participants[2]
        role = self.summary["roles"].get(config.LANE_ROLE, [0, 0, 0, 0])
        self.lane_games_weighted = self.weight * role[0] + role[2]

    def real(self, counter):
        return counter[0] + counter[2]

    def weighted(self, counter):
        return self.weight * counter[0] + counter[2], self.weight * counter[1] + counter[3]

    def players(self):
        return read_json(os.path.join(self.root, "patches", self.name, "players.json.gz"))


# ---------------------------------------------------------------- small helpers


def r(value, digits=2):
    return None if value is None else round(value, digits)


def percentile_points(values):
    """Rank 0-100 (lowest = 0, highest = 100, ties share the average rank).
    `values` is {key: number}. One value alone gets 50."""
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {k: 50.0 for k in values}
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    points, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        for k in range(i, j + 1):
            points[ordered[k][0]] = 100.0 * ((i + j) / 2) / (n - 1)
        i = j + 1
    return points


def spreads_from_average(score, mean, sd):
    """How many standard deviations ("spreads") the score is above the patch average
    (rounded to 2 decimals, as shown). No spread at all in the scores: everyone is 0."""
    return 0.0 if not sd else round((score - mean) / sd, 2)


def tier_of(spreads):
    """Tier from the spreads alone (model v0.36): S 1.5+, A 0.5+, B -0.5+, C -1.5+, else D."""
    for name, lowest in config.TIER_BOUNDARIES:
        if spreads >= lowest:
            return name
    return "D"


def win_rate_warning(win_rate_delta):
    """True when the win rate is 1.5% or more below the Diamond+ average (display only)."""
    return win_rate_delta <= config.WIN_RATE_WARNING_DELTA


DISPLAY_FIXES = {
    "MonkeyKing": "Wukong", "Nunu": "Nunu & Willump", "Renata": "Renata Glasc",
    "Velkoz": "Vel'Koz", "Khazix": "Kha'Zix", "Chogath": "Cho'Gath", "Leblanc": "LeBlanc",
    "DrMundo": "Dr. Mundo", "KSante": "K'Sante", "RekSai": "Rek'Sai", "Belveth": "Bel'Veth",
    "KogMaw": "Kog'Maw", "Kaisa": "Kai'Sa", "JarvanIV": "Jarvan IV",
}


def display_name(riot_name):
    """Readable name from Riot's internal one. The website will take real display
    names from Data Dragon; this is only for the score files and reports."""
    if riot_name in DISPLAY_FIXES:
        return DISPLAY_FIXES[riot_name]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", riot_name)


def normalise(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def blend(current, previous, share):
    """Blend one number of this patch with last patch's. No last-patch value: this patch only."""
    if previous is None:
        return current
    if current is None:
        return previous
    return share * current + (1 - share) * previous


def this_patch_share(current_games, has_previous):
    if not has_previous:
        return 1.0
    return current_games / (current_games + config.BLEND_K)


# ---------------------------------------------------------------- stage 1: per-champion numbers


def lane_numbers(patch, champ, role):
    """Games, win rate, lane share for one champion in one role and one patch."""
    entry = patch.champions.get(champ)
    if not entry:
        return None
    counter = entry["roles"].get(role)
    if not counter or not (counter[0] + counter[2]):
        return None
    games_w, wins_w = patch.weighted(counter)
    total_real = sum(c[0] + c[2] for c in entry["roles"].values())
    return {
        "real": counter[0] + counter[2],
        "real_wins": counter[1] + counter[3],
        "win_rate": 100.0 * wins_w / games_w,
        "weighted": games_w,
        "lane_share": (counter[0] + counter[2]) / total_real,
        "total_real": total_real,
    }


def game_pick_rate(patch, weighted_games):
    """Share of games the champion appears in. Only Diamond+ players are stored (about 7.5 of
    the 10 per game), so the total number of games is estimated as participants / 10."""
    return weighted_games / (patch.participants_weighted / 10.0) if patch.participants_weighted else None


def lane_pick_rate(patch, numbers):
    if not numbers:
        return None
    if config.PICK_RATE_BASIS == "lane":
        return numbers["weighted"] / patch.lane_games_weighted if patch.lane_games_weighted else None
    return game_pick_rate(patch, numbers["weighted"])


def lane_candidates(current, previous):
    """Every champion that has bot-lane games, with this patch and last patch blended."""
    out = {}
    ids = set(current.champions) | (set(previous.champions) if previous else set())
    for champ in ids:
        cur = lane_numbers(current, champ, config.LANE_ROLE)
        prev = lane_numbers(previous, champ, config.LANE_ROLE) if previous else None
        if not cur and not prev:
            continue
        cur_real = cur["real"] if cur else 0
        has_prev = prev is not None
        share = this_patch_share(cur_real, has_prev)
        if not cur:
            share = 0.0
        # win rate: each patch is compared with its own Diamond+ average, then blended
        delta_cur = cur["win_rate"] - current.average if cur else None
        delta_prev = prev["win_rate"] - previous.average if prev else None
        delta = blend(delta_cur, delta_prev, share)
        pick_cur = lane_pick_rate(current, cur)
        pick_prev = lane_pick_rate(previous, prev) if previous else None
        name = (current.champions.get(champ, {}).get("name") or previous.champions.get(champ, {}).get("name")
                or "#%s" % champ)
        out[champ] = {
            "id": int(champ),
            "riot_name": name,
            "real_games": cur_real + (prev["real"] if prev else 0),
            "real_games_this_patch": cur_real,
            "real_games_last_patch": prev["real"] if prev else 0,
            "this_patch_share": share,
            "win_rate_delta": delta,
            "win_rate": current.average + delta,
            "pick_rate": blend(pick_cur, pick_prev, share),
            "lane_share": blend(cur["lane_share"] if cur else None, prev["lane_share"] if prev else None, share),
            # unweighted totals over both patches, for the OTP comparison
            "bot_games_raw": (cur["real"] if cur else 0) + (prev["real"] if prev else 0),
            "bot_wins_raw": (cur["real_wins"] if cur else 0) + (prev["real_wins"] if prev else 0),
        }
    return out


def failed_filters(c):
    """The reasons a champion misses the ranking, in plain words (empty when it passes)."""
    reasons = []
    if c["real_games"] < config.MIN_REAL_GAMES:
        reasons.append("under %d real games" % config.MIN_REAL_GAMES)
    if c["lane_share"] is None or c["lane_share"] < config.MIN_LANE_SHARE:
        reasons.append("bot-lane share under %g%%" % (100 * config.MIN_LANE_SHARE))
    if c["pick_rate"] is None or c["pick_rate"] < config.MIN_PICK_RATE:
        reasons.append("bot-lane pick rate under %g%%" % (100 * config.MIN_PICK_RATE))
    return reasons


def passes_filters(c):
    return (c["real_games"] >= config.MIN_REAL_GAMES
            and c["lane_share"] is not None and c["lane_share"] >= config.MIN_LANE_SHARE
            and c["pick_rate"] is not None and c["pick_rate"] >= config.MIN_PICK_RATE)


# ---------------------------------------------------------------- stage 2: OTP


def read_season_players(root, season_name):
    """Season totals per player code: from the 16 pieces (v1.1) or the old single file. {} if none is saved."""
    folder = os.path.join(root, "season", season_name)
    if os.path.exists(os.path.join(folder, "season.json")):
        players = {}
        for piece in "0123456789abcdef":
            players.update(read_json(os.path.join(folder, "players-%s.json.gz" % piece))["players"])
        return players
    legacy = os.path.join(folder, "players.json.gz")
    return read_json(legacy)["players"] if os.path.exists(legacy) else {}


def otp_numbers(root, patches, eligible_ids):
    """For each eligible champion: OTP players, their bot-lane games and wins (and, for display only,
    their games on it in every role).

    OTP rule: at least 55% of a player's recent ranked games (this patch + last patch,
    all champions and roles) are on the champion, and at least 50 games on it this
    season. The OTP's bot-lane games on the champion are what we measure.
    """
    wanted = set(eligible_ids)
    per_player = {}   # code -> [all games, {champ: [games, wins, bot games, bot wins]}]
    for patch in patches:
        for code, counts in patch.players().items():
            entry = per_player.setdefault(code, [0, {}])
            for key, (games, wins) in counts.items():
                if ":" in key:
                    champ, tag = key.split(":", 1)
                    if tag == "B" and champ in wanted:
                        row = entry[1].setdefault(champ, [0, 0, 0, 0])
                        row[2] += games
                        row[3] += wins
                    continue
                entry[0] += games
                if key in wanted:
                    row = entry[1].setdefault(key, [0, 0, 0, 0])
                    row[0] += games
                    row[1] += wins

    season_name = patches[-1].name.split(".")[0]
    season = read_season_players(root, season_name)

    result = {c: {"players": 0, "games": 0, "wins": 0, "all_role_games": 0} for c in wanted}
    for code, (total, champs) in per_player.items():
        if not total:
            continue
        for champ, row in champs.items():
            if row[0] / total < config.OTP_MIN_SHARE_OF_RECENT_GAMES:
                continue
            season_games = season.get(code, {}).get(champ, [0, 0])[0]
            if season_games < config.OTP_MIN_SEASON_GAMES:
                continue
            out = result[champ]
            out["players"] += 1
            out["games"] += row[2]
            out["wins"] += row[3]
            out["all_role_games"] += row[0]   # display only: games on it in every role
    return result


# ---------------------------------------------------------------- the whole model


def score_all(root, cards=None, now=None):
    cards = cards if cards is not None else comfort_module.load_cards()
    names = list_patches(root)
    if not names:
        raise SystemExit("No patch data found in %s" % root)
    patches = [Patch(root, n) for n in names[-2:]]
    current = patches[-1]
    previous = patches[-2] if len(patches) > 1 else None

    lane = lane_candidates(current, previous)
    passed = {k: v for k, v in lane.items() if passes_filters(v)}
    excluded_names = {normalise(n) for n in config.EXCLUDED_FROM_POOL}
    eligible = {k: v for k, v in passed.items() if normalise(v["riot_name"]) not in excluded_names}
    excluded = [{"id": v["id"], "name": display_name(v["riot_name"]), "real_games": v["real_games"],
                 "win_rate_delta": v["win_rate_delta"], "pick_rate": v["pick_rate"]}
                for k, v in passed.items() if k not in eligible]

    # --- Stats = 75% win rate points + 25% pick rate (ranked 0-100 among eligible champions)
    pick_points = percentile_points({k: v["pick_rate"] for k, v in eligible.items()})
    for k, v in eligible.items():
        wr_points = max(0.0, min(100.0, 50.0 + config.WIN_RATE_POINTS_PER_PERCENT * v["win_rate_delta"]))
        v["win_rate_points"] = wr_points
        v["pick_rate_points"] = pick_points[k]
        v["stats"] = config.STATS_WIN_RATE_SHARE * wr_points + config.STATS_PICK_RATE_SHARE * pick_points[k]
        v["meta_score"] = v["stats"]

    # --- OTP
    otp = otp_numbers(root, patches, eligible)
    deltas = {}
    for k, v in eligible.items():
        o = otp[k]
        v["otp_players"], v["otp_games"] = o["players"], o["games"]
        v["otp_games_all_roles"] = o["all_role_games"]
        if o["games"] > 0 and v["bot_games_raw"] > 0:
            v["otp_win_rate"] = 100.0 * o["wins"] / o["games"]
            v["overall_win_rate_raw"] = 100.0 * v["bot_wins_raw"] / v["bot_games_raw"]
            v["otp_delta"] = v["otp_win_rate"] - v["overall_win_rate_raw"]
            deltas[k] = v["otp_delta"]
        else:
            v["otp_win_rate"] = v["overall_win_rate_raw"] = v["otp_delta"] = None
    raw_points = percentile_points(deltas)
    for k, v in eligible.items():
        v["otp_raw_points"] = raw_points.get(k, 50.0)
        v["otp_reliability"] = v["otp_games"] / (v["otp_games"] + config.OTP_RELIABILITY_K)
        v["otp_points"] = 50.0 + (v["otp_raw_points"] - 50.0) * v["otp_reliability"]

    # --- Comfort and Pick Score for champions that have a card
    by_name = {normalise(c["riot_name"]): c for c in cards}
    carded = {}
    for k, v in eligible.items():
        card = by_name.get(normalise(v["riot_name"]))
        v["has_card"] = card is not None
        v["name"] = card["name"] if card else display_name(v["riot_name"])
        if card:
            carded[k] = card
    eligible_scores = [comfort_module.trait_score(c) for c in carded.values()]
    if len(eligible_scores) >= config.MIN_CARDS_FOR_TRAIT_AVERAGE:
        trait_average, trait_average_from = sum(eligible_scores) / len(eligible_scores), "eligible champions with a card"
    else:
        trait_average, trait_average_from = comfort_module.average_trait_score(cards), "all cards"

    for k, card in carded.items():
        v = eligible[k]
        parts = comfort_module.comfort(card, trait_average)
        v["comfort_parts"] = parts
        v["comfort"] = parts["comfort"]
        v["mastery"] = card["mastery"]
        v["traits"] = card.get("traits", {})
        v["main_type"] = card.get("main_type")
        v["kind"] = card.get("kind")
        v["pick_score"] = (config.WEIGHT_STATS * v["stats"] + config.WEIGHT_COMFORT * v["comfort"]
                           + config.WEIGHT_OTP * v["otp_points"])

    pick_list = sorted((v for v in eligible.values() if v["has_card"]), key=lambda v: -v["pick_score"])
    # Tiers: distance from this patch's average Pick Score, in standard deviations.
    scores_now = [v["pick_score"] for v in pick_list]
    tier_stats = {"average_pick_score": statistics.fmean(scores_now) if scores_now else None,
                  "spread": statistics.pstdev(scores_now) if len(scores_now) > 1 else 0.0,
                  "champions": len(scores_now),
                  "boundaries": {name: lowest for name, lowest in config.TIER_BOUNDARIES}}
    for v in pick_list:
        v["spreads"] = spreads_from_average(v["pick_score"], tier_stats["average_pick_score"], tier_stats["spread"])
        v["tier"] = tier_of(v["spreads"])
        v["win_rate_warning"] = win_rate_warning(v["win_rate_delta"])
    for i, v in enumerate(pick_list, 1):
        v["pick_rank"] = i
    # What each champion would score at Main (same Comfort and Pick Score code, only the mastery changes).
    for k, v in eligible.items():
        if v["has_card"]:
            v["pick_score_at_main"], v["best_tier_at_main"] = score_at_mastery(v, carded[k], trait_average, tier_stats, "main")
    meta_list = sorted(eligible.values(), key=lambda v: -v["meta_score"])
    for i, v in enumerate(meta_list, 1):
        v["meta_rank"] = i

    advisor = growth_advisor(eligible, carded, pick_list, trait_average, tier_stats)
    next_step, next_step_closest = next_step_list(eligible, carded, pick_list, trait_average, tier_stats)
    utopy, utopy_closest = utopy_list(eligible, carded, pick_list, trait_average, tier_stats)

    def clean(v):
        out = {k: v[k] for k in (
            "id", "riot_name", "name", "has_card", "real_games", "real_games_this_patch", "real_games_last_patch",
            "this_patch_share", "win_rate", "win_rate_delta", "pick_rate", "lane_share",
            "win_rate_points", "pick_rate_points", "stats", "meta_score", "meta_rank",
            "otp_players", "otp_games", "otp_games_all_roles", "otp_win_rate", "overall_win_rate_raw", "otp_delta",
            "otp_raw_points", "otp_reliability", "otp_points") if k in v}
        out["data_label"] = "Data: %d%% this patch" % round(100 * v["this_patch_share"])
        if v["has_card"]:
            out.update({k: v[k] for k in ("mastery", "traits", "main_type", "kind", "comfort", "comfort_parts", "pick_score", "pick_rank",
                                          "spreads", "tier", "win_rate_warning", "pick_score_at_main", "best_tier_at_main")})
        else:
            out["label"] = "no card yet"
        return out

    why_out = {}
    for k, v in lane.items():
        if k in eligible:
            continue
        reasons = failed_filters(v)
        if v["real_games"] >= 300:
            why_out[k] = {"name": display_name(v["riot_name"]), "real_games": v["real_games"],
                          "lane_share": v["lane_share"], "pick_rate": v["pick_rate"], "failed": reasons}

    ranked_names = {v["name"] for v in eligible.values() if v["has_card"]}
    cards_not_ranked = []
    for key, card in by_name.items():
        if card["name"] in ranked_names:
            continue
        cand = next((v for v in lane.values() if normalise(v["riot_name"]) == key), None)
        cards_not_ranked.append({"name": card["name"], "real_games": cand["real_games"] if cand else 0,
                                 "pick_rate": cand["pick_rate"] if cand else None,
                                 "failed": failed_filters(cand) if cand else ["no bot-lane games found"]})

    return {
        "model_version": config.MODEL_VERSION,
        "generated": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "patch": current.name,
        "previous_patch": previous.name if previous else None,
        "diamond_plus_average_win_rate": current.average,
        "diamond_plus_average_win_rate_previous_patch": previous.average if previous else None,
        "games_counted": {p.name: p.summary["games_counted"] for p in patches},
        "trait_average": trait_average,
        "trait_average_from": trait_average_from,
        "eligible_champions": len(eligible),
        "champions_with_card": len(pick_list),
        "champions_without_card": len(eligible) - len(pick_list),
        "cards_not_ranked": sorted(cards_not_ranked, key=lambda row: row["name"]),
        "pick_score_list": [clean(v) for v in pick_list],
        "meta_score_list": [clean(v) for v in meta_list],
        "needs_a_card": [clean(v) for v in meta_list if not v["has_card"]],
        "tier_stats": tier_stats,
        "excluded_by_pool_rule": excluded,
        "next_step_list": next_step,
        "next_step_closest": next_step_closest,
        "utopy_list": utopy,
        "utopy_closest": utopy_closest,
        "growth_advisor": advisor,
        "near_misses": sorted(why_out.values(), key=lambda row: (-row["real_games"], row["name"]))[:15],
    }


# ---------------------------------------------------------------- Growth advisor


def growth_advisor(eligible, carded, pick_list, trait_average, tier_stats):
    """Suggest champions that would beat the owner's current #3 pick at a target mastery.

    Only champions with a card (Comfort needs one). Never played and Below average are scored
    as if Good; Average and Good one level up. The tier at the target is read against the
    patch's current average and spread.
    """
    if len(pick_list) < config.GROWTH_BEAT_RANK:
        return []
    bar = pick_list[config.GROWTH_BEAT_RANK - 1]["pick_score"]
    scores = {v["id"]: v["pick_score"] for v in pick_list}

    suggestions = []
    for k, v in eligible.items():
        if not v["has_card"] or v["mastery"] == "main":
            continue
        current_mastery = v["mastery"]
        target = config.GROWTH_TARGET[current_mastery]
        new_comfort = comfort_module.comfort(carded[k], trait_average, target)["comfort"]
        before = v["pick_score"]
        kind = "New champion" if current_mastery == "never_played" else "Upgrade"
        after = (config.WEIGHT_STATS * v["stats"] + config.WEIGHT_COMFORT * new_comfort
                 + config.WEIGHT_OTP * v["otp_points"])
        if after <= bar or after <= before:
            continue
        others = [s for cid, s in scores.items() if cid != v["id"]]
        rank = 1 + sum(1 for s in others if s > after)
        tier = tier_of(spreads_from_average(after, tier_stats["average_pick_score"], tier_stats["spread"]))
        suggestions.append({
            "id": v["id"], "name": v["name"], "kind": kind,
            "current_mastery": current_mastery, "target_mastery": target,
            "pick_score_now": before, "pick_score_at_target": after, "gain": after - before,
            "would_rank": rank, "tier_at_target": tier,
        })
    suggestions.sort(key=lambda s: -s["pick_score_at_target"])
    return suggestions


def score_at_mastery(v, card, trait_average, tier_stats, mastery):
    """(Pick Score, tier) if the champion were played at `mastery`. Same code as the tier list; only the
    mastery changes. The tier is read against the patch's current average and spread."""
    new_comfort = comfort_module.comfort(card, trait_average, mastery)["comfort"]
    after = (config.WEIGHT_STATS * v["stats"] + config.WEIGHT_COMFORT * new_comfort
             + config.WEIGHT_OTP * v["otp_points"])
    spreads = spreads_from_average(after, tier_stats["average_pick_score"], tier_stats["spread"])
    return after, tier_of(spreads)


def next_step_list(eligible, carded, pick_list, trait_average, tier_stats):
    """"Next step to A or S": every carded champion now in B, C or D whose Pick Score ONE mastery step up
    (Never played -> Below average -> ... -> Main) would land in A or S. Returns (rows, closest).

    `closest` is the B, C or D champion nearest to the A line after one step (how many points short), or
    None; the page shows it when the list is empty. The ceiling at Main (`tier_at_main`) is information only
    and never decides who is listed. Nothing here changes a score.
    """
    if not pick_list:
        return [], None
    a_line = tier_stats["average_pick_score"] + dict(config.TIER_BOUNDARIES)["A"] * tier_stats["spread"]
    rows, closest = [], None
    for v in pick_list:
        if v["tier"] not in ("B", "C", "D") or v["mastery"] not in config.GROWTH_TARGET:
            continue
        k = next(key for key, e in eligible.items() if e is v)
        step = config.GROWTH_TARGET[v["mastery"]]
        after, tier = score_at_mastery(v, carded[k], trait_average, tier_stats, step)
        if tier in ("A", "S"):
            rows.append({"id": v["id"], "name": v["name"], "current_mastery": v["mastery"], "next_mastery": step,
                         "tier_now": v["tier"], "tier_next": tier,
                         "pick_score_now": v["pick_score"], "pick_score_next": after, "gain": after - v["pick_score"],
                         "tier_at_main": v["best_tier_at_main"]})
        elif closest is None or after > closest["pick_score_next"]:
            closest = {"id": v["id"], "name": v["name"], "next_mastery": step, "tier_now": v["tier"],
                       "pick_score_next": after, "points_short": a_line - after}
    rows.sort(key=lambda r: -r["pick_score_next"])
    return rows, (None if rows else closest)


def utopy_list(eligible, carded, pick_list, trait_average, tier_stats):
    """"Utopy picks" (v0.40): long-term goals. Every carded champion whose mastery is not Main and whose tier
    now is not S, whose Pick Score would reach S at Good or at Main. Returns (rows, closest).

    Same maths as the ceiling at Main: only this one champion's mastery changes, and it is compared with this
    patch's normal tier cutoffs (the other champions do not change). Only levels ABOVE the current mastery are
    tried. `steps` counts mastery steps from now to the first level that reaches S. Order: fewest steps, then
    the highest score at that first level. `closest` (when the list is empty) is the champion nearest to the S
    line at Main. Information only: nothing here changes a score or any other list.
    """
    if not pick_list:
        return [], None
    s_line = tier_stats["average_pick_score"] + dict(config.TIER_BOUNDARIES)["S"] * tier_stats["spread"]
    order = config.MASTERY_ORDER
    rows, closest = [], None
    for v in pick_list:
        if v["mastery"] == "main" or v["tier"] == "S":
            continue
        k = next(key for key, e in eligible.items() if e is v)
        here = order.index(v["mastery"])
        reaching = []                                           # (level, score) that land in S
        for level in config.UTOPY_LEVELS:
            if order.index(level) <= here:
                continue
            score, tier = score_at_mastery(v, carded[k], trait_average, tier_stats, level)
            if tier == "S":
                reaching.append({"level": level, "score": score})
        if reaching:
            first = reaching[0]
            rows.append({"id": v["id"], "name": v["name"], "current_mastery": v["mastery"], "tier_now": v["tier"],
                         "pick_score_now": v["pick_score"], "first_level": first["level"],
                         "steps": order.index(first["level"]) - here, "scores": reaching})
        else:
            main_score = score_at_mastery(v, carded[k], trait_average, tier_stats, "main")[0]
            if closest is None or main_score > closest["pick_score_at_main"]:
                closest = {"id": v["id"], "name": v["name"], "tier_now": v["tier"], "pick_score_at_main": main_score,
                           "points_short": s_line - main_score}
    rows.sort(key=lambda r: (r["steps"], -r["scores"][0]["score"]))
    return rows, (None if rows else closest)


def round_floats(value, digits=3):
    """Round every number in the result so the saved file is small and tidy."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, digits) for v in value]
    return value
