"""Totals per patch, plus the collector's memory between runs.

Every counter is a list of 4 numbers:
    [games on double-weight servers, wins on double-weight servers,
     games on other servers,         wins on other servers]
Weighted games = 2 * c[0] + c[2], weighted wins = 2 * c[1] + c[3].
"""

import gzip
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone

from . import config

DETAIL_FILES = {"BOTTOM": "bottom.json.gz", "UTILITY": "utility.json.gz"}
PATCH_PATTERN = re.compile(r"^\d+\.\d+$")


class DataDamaged(Exception):
    """A saved file could not be read."""


def scramble(puuid):
    """Turn a Riot player ID into a short code that can't be looked up."""
    return hashlib.sha256(puuid.encode()).hexdigest()[:16]


def patch_from_version(version):
    """'16.19.712.4532' -> '16.19' (None if it doesn't look like a patch)."""
    patch = ".".join(str(version).split(".")[:2])
    return patch if PATCH_PATTERN.match(patch) else None


def patch_order(patch):
    return tuple(int(part) for part in patch.split("."))


def rune_key(perks):
    """One text key per full rune page: 'primary:4 runes|secondary:2 runes|shards'."""
    if not perks:
        return ""
    parts = []
    for style in perks.get("styles", [])[:2]:
        picks = ",".join(str(s.get("perk")) for s in style.get("selections", []))
        parts.append("%s:%s" % (style.get("style"), picks))
    shards = perks.get("statPerks") or {}
    parts.append(",".join(str(shards.get(k, 0)) for k in ("offense", "flex", "defense")))
    return "|".join(parts)


def compact_match(match, match_id, server):
    """Keep only what we need from a downloaded game (player IDs scrambled)."""
    info = match["info"]
    participants = info.get("participants", [])
    remake = info.get("gameDuration", 0) < config.MIN_GAME_SECONDS or any(
        p.get("gameEndedInEarlySurrender") for p in participants)
    bans = [b.get("championId", -1) for t in info.get("teams", []) for b in t.get("bans", [])]
    start_ms = info.get("gameStartTimestamp") or info.get("gameCreation") or time.time() * 1000
    players = []
    for p in participants:
        if not p.get("puuid"):
            continue
        players.append({
            "h": scramble(p["puuid"]),
            "c": p.get("championId"),
            "n": p.get("championName", ""),
            "pos": p.get("teamPosition") or "NONE",
            "team": p.get("teamId"),
            "win": bool(p.get("win")),
            "items": sorted({p.get("item%d" % i, 0) for i in range(6)} - {0}),
            "runes": rune_key(p.get("perks")),
        })
    return {
        "id": match_id,
        "server": server,
        "queue": info.get("queueId"),
        "patch": patch_from_version(info.get("gameVersion", "")),
        "remake": remake,
        "bans": sorted({c for c in bans if c and c > 0}),
        "players": players,
        "day": int(start_ms // 1000 // 86400),
    }


def bump(table, key, group, win):
    counter = table.get(key)
    if counter is None:
        counter = table[key] = [0, 0, 0, 0]
    counter[2 * group] += 1
    if win:
        counter[2 * group + 1] += 1


def win_rate(counter, weighted=True):
    weight = config.DOUBLE_WEIGHT if weighted else 1
    games = weight * counter[0] + counter[2]
    wins = weight * counter[1] + counter[3]
    return round(100 * wins / games, 3) if games else None


def new_patch():
    return {
        "games": [0, 0],          # games counted: [double-weight servers, other servers]
        "games_by_server": {},
        "participants": [0, 0, 0, 0],
        "roles": {},
        "champions": {},
        "detail": {role: {} for role in config.DETAIL_ROLES},
        "players": {},
    }


class Store:
    def __init__(self):
        self.patches = {}
        self.player_state = {s: {} for s in config.ALL_SERVERS}  # code -> [last check, hours to wait]
        self.processed = {s: {} for s in config.ALL_SERVERS}     # day -> set of game numbers
        self.processed_index = {s: set() for s in config.ALL_SERVERS}
        self.pending = {s: [] for s in config.ALL_SERVERS}
        self.seasons = {}  # "16" -> {"champions": set of IDs, "players": code -> counts}

    # ---- processed games ----

    def is_processed(self, match_id):
        server = config.server_of_match(match_id)
        return server is not None and _match_number(match_id) in self.processed_index[server]

    def mark_processed(self, match_id, day):
        server = config.server_of_match(match_id)
        number = _match_number(match_id)
        if server is None or number is None:
            return
        self.processed[server].setdefault(day, set()).add(number)
        self.processed_index[server].add(number)

    # ---- adding a game ----

    def add_match(self, rec, diamond_codes):
        """Add one game. Returns (outcome, list of Diamond+ players counted)."""
        if rec["queue"] != config.QUEUE_ID:
            return "not_ranked", []
        if rec["remake"]:
            return "remake", []
        if not rec["patch"]:
            return "unknown_patch", []
        counted = [p for p in rec["players"] if p["h"] in diamond_codes]
        if not counted:
            return "no_diamond", []

        patch = self.patches.setdefault(rec["patch"], new_patch())
        group = 0 if rec["server"] in config.DOUBLE_WEIGHT_SERVERS else 1
        patch["games"][group] += 1
        by_server = patch["games_by_server"]
        by_server[rec["server"]] = by_server.get(rec["server"], 0) + 1
        champions = patch["champions"]

        # Bans count once per game.
        for champ in rec["bans"]:
            _champion(champions, champ, "")["bans"][group] += 1

        for p in counted:
            win, pos, champ = p["win"], p["pos"], str(p["c"])
            entry = _champion(champions, p["c"], p["n"])
            bump(entry["roles"], pos, group, win)
            bump(patch["roles"], pos, group, win)
            patch["participants"][2 * group] += 1
            if win:
                patch["participants"][2 * group + 1] += 1

            tag = config.ROLE_TAGS.get(pos)
            player = patch["players"].setdefault(p["h"], {})
            _count(player, champ, win)
            if tag:
                _count(player, champ + ":" + tag, win)
            self._add_to_season(rec["patch"], p["h"], champ, tag, win, entry["roles"])

            if pos in config.DETAIL_ROLES:
                detail = patch["detail"][pos].setdefault(champ, {
                    "games": [0, 0, 0, 0], "items": {}, "runes": {}, "allies": {}, "enemies": {}})
                detail["games"][2 * group] += 1
                if win:
                    detail["games"][2 * group + 1] += 1
                for item in p["items"]:
                    bump(detail["items"], str(item), group, win)
                if p["runes"]:
                    bump(detail["runes"], p["runes"], group, win)
                for other in rec["players"]:
                    if other is p:
                        continue
                    side = "allies" if other["team"] == p["team"] else "enemies"
                    bump(detail[side], "%s:%s" % (other["c"], other["pos"]), group, win)
        return "counted", counted

    # ---- season totals (for the OTP rule) ----

    def _season(self, season):
        return self.seasons.setdefault(season, {"champions": set(), "players": {}})

    def _add_to_season(self, patch_name, code, champ, tag, win, roles):
        season = self._season(season_of(patch_name))
        player = season["players"].setdefault(code, {})
        _count(player, "all", win)
        if champ not in season["champions"] and _bot_or_support(roles):
            season["champions"].add(champ)  # stays for the rest of the season
        if champ in season["champions"]:
            _count(player, champ, win)
            if tag:
                _count(player, champ + ":" + tag, win)

    def _seed_seasons(self):
        """Build season totals from the patch files when a season has none yet,
        so nothing collected before season totals existed is lost."""
        by_season = {}
        for name in self.patches:
            by_season.setdefault(season_of(name), []).append(name)
        for season_name, names in by_season.items():
            if season_name in self.seasons:
                continue
            season = self._season(season_name)
            for name in names:
                for champ, entry in self.patches[name]["champions"].items():
                    if _bot_or_support(entry["roles"]):
                        season["champions"].add(champ)
            for name in names:
                for code, champs in self.patches[name]["players"].items():
                    player = season["players"].setdefault(code, {})
                    for key, (games, wins) in champs.items():
                        if ":" not in key:
                            _add(player, "all", games, wins)
                        if key.split(":")[0] in season["champions"]:
                            _add(player, key, games, wins)

    # ---- summaries ----

    def summary(self, name):
        patch = self.patches[name]
        return {
            "patch": name,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "games_counted": sum(patch["games"]),
            "games_weighted": config.DOUBLE_WEIGHT * patch["games"][0] + patch["games"][1],
            "diamond_plus_average_win_rate": win_rate(patch["participants"]),
            "diamond_plus_average_win_rate_unweighted": win_rate(patch["participants"], weighted=False),
            "role_average_win_rate": {r: win_rate(c) for r, c in sorted(patch["roles"].items())},
            "double_weight_servers": sorted(config.DOUBLE_WEIGHT_SERVERS),
            "double_weight": config.DOUBLE_WEIGHT,
            "games": patch["games"],
            "games_by_server": dict(sorted(patch["games_by_server"].items())),
            "participants": patch["participants"],
            "roles": patch["roles"],
        }

    # ---- saving and loading ----

    def save(self, root, run_info):
        """Write everything to `root`, then read it back to make sure it isn't damaged."""
        keep = sorted(self.patches, key=patch_order)[-config.KEEP_PATCHES:]
        for name in list(self.patches):
            if name not in keep:
                del self.patches[name]
        oldest_day = int(time.time() // 86400) - config.PROCESSED_KEEP_DAYS
        for server in config.ALL_SERVERS:
            for day in [d for d in self.processed[server] if d < oldest_day]:
                self.processed_index[server] -= self.processed[server].pop(day)

        patches_dir = os.path.join(root, "patches")
        os.makedirs(patches_dir, exist_ok=True)
        for name in os.listdir(patches_dir):
            if name not in self.patches:
                shutil.rmtree(os.path.join(patches_dir, name))
        for name, patch in self.patches.items():
            folder = os.path.join(patches_dir, name)
            _write(os.path.join(folder, "summary.json"), self.summary(name))
            _write(os.path.join(folder, "champions.json"), patch["champions"])
            for role, filename in DETAIL_FILES.items():
                _write(os.path.join(folder, filename), patch["detail"][role])
            _write(os.path.join(folder, "players.json.gz"), patch["players"])

        keep_seasons = sorted(self.seasons, key=int)[-config.KEEP_SEASONS:]
        for name in list(self.seasons):
            if name not in keep_seasons:
                del self.seasons[name]
        seasons_dir = os.path.join(root, "season")
        os.makedirs(seasons_dir, exist_ok=True)
        for name in os.listdir(seasons_dir):
            if name not in self.seasons:
                shutil.rmtree(os.path.join(seasons_dir, name))
        for name, season in self.seasons.items():
            _write(os.path.join(seasons_dir, name, "players.json.gz"),
                   {"champions": sorted(season["champions"], key=int), "players": season["players"]})

        state = os.path.join(root, "state")
        _write(os.path.join(state, "players.json.gz"), self.player_state)
        _write(os.path.join(state, "processed.json.gz"), {
            s: {str(day): sorted(nums) for day, nums in days.items()}
            for s, days in self.processed.items()})
        _write(os.path.join(state, "pending.json.gz"), self.pending)
        _write(os.path.join(root, "last_run.json"), run_info)
        with open(os.path.join(root, "README.md"), "w") as f:
            f.write(DATA_README)

        Store.load(root)  # raises DataDamaged if anything didn't save properly

    @classmethod
    def load(cls, root):
        store = cls()
        if not os.path.isdir(os.path.join(root, "state")):
            return store  # nothing saved yet
        try:
            state = os.path.join(root, "state")
            for server, codes in _read(os.path.join(state, "players.json.gz")).items():
                store.player_state.setdefault(server, {}).update(codes)
            for server, days in _read(os.path.join(state, "processed.json.gz")).items():
                for day, numbers in days.items():
                    store.processed.setdefault(server, {})[int(day)] = set(numbers)
                    store.processed_index.setdefault(server, set()).update(numbers)
            for server, ids in _read(os.path.join(state, "pending.json.gz")).items():
                store.pending.setdefault(server, []).extend(ids)
            patches_dir = os.path.join(root, "patches")
            for name in os.listdir(patches_dir) if os.path.isdir(patches_dir) else []:
                folder = os.path.join(patches_dir, name)
                summary = _read(os.path.join(folder, "summary.json"))
                patch = new_patch()
                for key in ("games", "games_by_server", "participants", "roles"):
                    patch[key] = summary[key]
                patch["champions"] = _read(os.path.join(folder, "champions.json"))
                for role, filename in DETAIL_FILES.items():
                    patch["detail"][role] = _read(os.path.join(folder, filename))
                patch["players"] = _read(os.path.join(folder, "players.json.gz"))
                store.patches[name] = patch
            seasons_dir = os.path.join(root, "season")
            for name in os.listdir(seasons_dir) if os.path.isdir(seasons_dir) else []:
                data = _read(os.path.join(seasons_dir, name, "players.json.gz"))
                store.seasons[name] = {"champions": set(data["champions"]), "players": data["players"]}
            store._seed_seasons()
        except Exception as error:
            raise DataDamaged("%s: %s" % (type(error).__name__, error))
        return store


def season_of(patch):
    """'16.19' -> '16'."""
    return patch.split(".")[0]


def _count(table, key, win):
    _add(table, key, 1, int(win))


def _add(table, key, games, wins):
    counter = table.get(key)
    if counter is None:
        counter = table[key] = [0, 0]
    counter[0] += games
    counter[1] += wins


def _bot_or_support(roles):
    """True when a champion is played enough in bot lane or support."""
    total = sum(c[0] + c[2] for c in roles.values())
    if total < config.SEASON_CHAMPION_MIN_GAMES:
        return False
    return any((roles.get(r) or [0, 0, 0, 0])[0] + (roles.get(r) or [0, 0, 0, 0])[2]
               >= config.SEASON_CHAMPION_MIN_SHARE * total for r in config.DETAIL_ROLES)


def _match_number(match_id):
    try:
        return int(match_id.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def _champion(champions, champ_id, name):
    entry = champions.get(str(champ_id))
    if entry is None:
        entry = champions[str(champ_id)] = {"name": name, "roles": {}, "bans": [0, 0]}
    elif name and not entry["name"]:
        entry["name"] = name
    return entry


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    if path.endswith(".gz"):
        text = gzip.compress(text, mtime=0)
    temp = path + ".tmp"
    with open(temp, "wb") as f:
        f.write(text)
    os.replace(temp, path)


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    if path.endswith(".gz"):
        raw = gzip.decompress(raw)
    return json.loads(raw)


DATA_README = """# LoL Pick Lab data

Written automatically by the collector (see the `main` branch). This branch is
replaced on every save, so it has no history. `data-backup` holds the previous
run's copy.

## patches/<patch>/
- `summary.json`: games counted, games per server, Diamond+ average win rate
  (weighted and unweighted), and average win rate per role.
- `champions.json`: per champion ID: name, games and wins per role, and bans.
  Bans count once per game: [games banned on double-weight servers, on other servers].
- `bottom.json.gz`, `utility.json.gz`: per ADC/support champion: games, final
  items, rune pages, and allies/enemies as "championId:role".
- `players.json.gz`: per scrambled player code, `[games, wins]` per champion ID
  (all roles), plus `"ID:B"` (bot lane) and `"ID:S"` (support) for games in
  those roles. Used for the "recent games" part of the OTP rule (current +
  previous patch). Real player IDs are never stored.

## season/<season>/players.json.gz
Running totals for the whole season (season 16 = patches 16.x), never pruned
during the season, for the "50 games this season" part of the OTP rule:
- `players`: per scrambled player code, `"all"` = `[games, wins]` across every
  champion, plus `[games, wins]` per champion ID and per `"ID:B"` / `"ID:S"`,
  only for bot-lane and support champions.
- `champions`: the bot-lane and support champion IDs counted this season (at
  least 200 games in a patch with at least 10% in bot lane or support; once in,
  they stay).
Games collected before season totals existed were copied in from the patch
files (without the bot/support split, which starts from that point).

Only Diamond+ players (from Riot's Diamond, Master, Grandmaster and Challenger
lists for ranked solo/duo) are counted.

## Counters
Every game/win counter is `[games x2, wins x2, games x1, wins x1]`. The x2 part
is LAN, NA, EUW and KR, the x1 part is every other server.
Weighted games = 2 * games x2 + games x1.

## state/
The collector's memory: when each player was last checked, which games were
already processed (last 14 days), and games waiting to be downloaded.
"""
