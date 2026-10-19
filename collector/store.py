"""Totals per patch, plus the collector's memory between runs.

Every counter is a list of 4 numbers:
    [games on double-weight servers, wins on double-weight servers,
     games on other servers,         wins on other servers]
Weighted games = 2 * c[0] + c[2], weighted wins = 2 * c[1] + c[3].
"""

import gzip
import hashlib
import hmac
import json
import os
import re
import resource
import shutil
import sys
import time
from datetime import datetime, timezone

from . import config

DETAIL_FILES = {"BOTTOM": "bottom.json.gz", "UTILITY": "utility.json.gz", "JUNGLE": "jungle.json.gz"}
PATCH_PATTERN = re.compile(r"^\d+\.\d+$")


MIN_PATCHES = 2  # cleanup never keeps fewer: the current and the previous patch

# Season totals are saved in 16 pieces (v1.1): season/<season>/players-<0-f>.json.gz, by the first character of the
# player code, plus season.json (champion list, conversion day). The old single file is still understood.
PIECES = "0123456789abcdef"
SEASON_FILE = "season.json"
LEGACY_SEASON_FILE = "players.json.gz"
PRECONVERSION_FILE = "players-preconversion.json.gz"
SEASON_FORMAT = 2


def _today():
    """Today as a day number (days since 1970). One place, so tests can set the date."""
    return int(time.time() // 86400)


def piece_of(code):
    first = code[:1].lower()
    return first if first and first in PIECES else "0"


def piece_name(piece):
    return "players-%s.json.gz" % piece


def new_season():
    return {"champions": set(), "players": {}, "seen": {}, "converted_day": None, "legacy": False}


def read_season(folder, today=None):
    """Season totals saved in `folder`: from the 16 pieces, or from the old single file (every player then counts
    as seen today). None when nothing is saved there. Raises on a missing or damaged piece."""
    meta_path = os.path.join(folder, SEASON_FILE)
    if os.path.exists(meta_path):
        meta = _read(meta_path)
        season = new_season()
        season["champions"] = set(meta["champions"])
        season["converted_day"] = meta.get("converted_day")
        for piece in PIECES:
            data = _read(os.path.join(folder, piece_name(piece)))
            season["players"].update(data["players"])
            season["seen"].update(data["seen"])
        return season
    legacy = os.path.join(folder, LEGACY_SEASON_FILE)
    if os.path.exists(legacy):
        data = _read(legacy)
        day = _today() if today is None else today
        season = new_season()
        season["champions"] = set(data["champions"])
        season["players"] = data["players"]
        season["seen"] = {code: day for code in data["players"]}
        season["legacy"] = True
        return season
    return None


def write_season(folder, season, today=None):
    """Write the 16 pieces and season.json. The old single file is not touched here."""
    day = _today() if today is None else today
    groups = {piece: {"players": {}, "seen": {}} for piece in PIECES}
    for code, counters in season["players"].items():
        group = groups[piece_of(code)]
        group["players"][code] = counters
        group["seen"][code] = season["seen"].setdefault(code, day)
    for piece, group in groups.items():
        _write(os.path.join(folder, piece_name(piece)), group)
    converted = season.get("converted_day")
    if converted is None and season.get("legacy"):
        converted = day
    _write(os.path.join(folder, SEASON_FILE), {
        "format": SEASON_FORMAT, "pieces": len(PIECES),
        "champions": sorted(season["champions"], key=int), "converted_day": converted})
    season["converted_day"] = converted


def finish_conversion(folder, season, today=None):
    """After the pieces were written and checked: rename the old single file so it is kept as a rollback copy,
    and delete that copy PRECONVERSION_KEEP_DAYS after the conversion."""
    day = _today() if today is None else today
    legacy = os.path.join(folder, LEGACY_SEASON_FILE)
    kept = os.path.join(folder, PRECONVERSION_FILE)
    if os.path.exists(legacy):
        if os.path.exists(kept):
            os.remove(legacy)
        else:
            os.replace(legacy, kept)
    season["legacy"] = False
    converted = season.get("converted_day")
    if os.path.exists(kept) and converted is not None and day >= converted + config.PRECONVERSION_KEEP_DAYS:
        os.remove(kept)


def season_fingerprint(season):
    """What must not change when a season is saved and read back."""
    games = wins = 0
    for counters in season["players"].values():
        for g, w in counters.values():
            games += g
            wins += w
    return (len(season["players"]), sorted(season["champions"], key=int), games, wins,
            sum(season["seen"].get(code, 0) for code in season["players"]) if season["seen"] else 0)


class DataDamaged(Exception):
    """A saved file could not be read."""


SECRET_ENV = "PLAYER_CODE_SALT"
CODES_FILE = "codes.json"
CODES_VERSION = "hmac-sha256-v1"
MIN_SECRET_LENGTH = 32


class MissingSecret(Exception):
    """The secret key for player codes is not set (or too short)."""


class CodesMismatch(Exception):
    """Saved data was made with other player codes than the current secret makes."""


def player_secret():
    secret = os.environ.get(SECRET_ENV, "").strip()
    if len(secret) < MIN_SECRET_LENGTH:
        raise MissingSecret("%s is missing or shorter than %d characters" % (SECRET_ENV, MIN_SECRET_LENGTH))
    return secret


def unsalted_code(puuid):
    """The old, public-lookup-able code. Only the first step of scramble(); never saved."""
    return hashlib.sha256(puuid.encode()).hexdigest()[:16]


def salted_code(old_code, secret=None):
    """Code saved in the data: HMAC-SHA256(secret, old code), shortened to 16 characters.
    Old saved codes are converted with this same function, so they keep matching."""
    key = (secret or player_secret()).encode()
    return hmac.new(key, old_code.encode(), hashlib.sha256).hexdigest()[:16]


def scramble(puuid):
    """Turn a Riot player ID into a short code that can't be looked up without the secret."""
    return salted_code(unsalted_code(puuid))


def secret_check(secret=None):
    """A short fingerprint of the secret, saved next to the data, to catch a wrong secret."""
    key = (secret or player_secret()).encode()
    return hmac.new(key, b"lol-pick-lab codes check", hashlib.sha256).hexdigest()[:12]


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
        self.seasons = {}  # "16" -> {"champions": set of IDs, "players": code -> counts, "seen": code -> day number}
        self.pruned_players = 0  # dropped as small and inactive in the last save

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
        return self.seasons.setdefault(season, new_season())

    def _add_to_season(self, patch_name, code, champ, tag, win, roles):
        season = self._season(season_of(patch_name))
        player = season["players"].setdefault(code, {})
        season["seen"][code] = _today()
        _count(player, "all", win)
        if champ not in season["champions"] and _site_role_champion(roles):
            # Joins for the rest of the season. Its earlier games (this one
            # included, since the patch file is updated first) are copied in.
            season["champions"].add(champ)
            self._copy_from_patches(season, season_of(patch_name), champ)
            return
        if champ in season["champions"]:
            _count(player, champ, win)
            if tag:
                _count(player, champ + ":" + tag, win)

    def _copy_from_patches(self, season, season_name, champ):
        keys = [champ] + [champ + ":" + tag for tag in config.ROLE_TAGS.values()]
        for name, patch in self.patches.items():
            if season_of(name) != season_name:
                continue
            for code, champs in patch["players"].items():
                if champ not in champs:
                    continue
                if code not in season["players"]:
                    continue   # dropped from the season file as small and inactive: not brought back
                player = season["players"][code]
                for key in keys:
                    if key in champs:
                        _add(player, key, *champs[key])

    def _seed_seasons(self):
        """Build season totals from the patch files when a season has none yet,
        so nothing collected before season totals existed is lost."""
        by_season = {}
        newest = max((season_of(n) for n in self.patches), key=int, default=None)
        for name in self.patches:
            if season_of(name) != newest:
                continue  # older seasons are not kept, so they are not rebuilt
            by_season.setdefault(season_of(name), []).append(name)
        for season_name, names in by_season.items():
            if season_name in self.seasons:
                continue
            season = self._season(season_name)
            for name in names:
                for champ, entry in self.patches[name]["champions"].items():
                    if _site_role_champion(entry["roles"]):
                        season["champions"].add(champ)
            for name in names:
                for code, champs in self.patches[name]["players"].items():
                    player = season["players"].setdefault(code, {})
                    for key, (games, wins) in champs.items():
                        if ":" not in key:
                            _add(player, "all", games, wins)
                        if key.split(":")[0] in season["champions"]:
                            _add(player, key, games, wins)

    def prune_seasons(self, today=None):
        """Drop players with SEASON_PRUNE_MAX_GAMES season games or fewer who haven't been seen for
        SEASON_PRUNE_AFTER_DAYS days. Returns how many were dropped."""
        day = _today() if today is None else today
        cutoff = day - config.SEASON_PRUNE_AFTER_DAYS
        dropped = 0
        for season in self.seasons.values():
            old = [code for code, counters in season["players"].items()
                   if counters.get("all", [0, 0])[0] <= config.SEASON_PRUNE_MAX_GAMES
                   and season["seen"].get(code, day) < cutoff]
            for code in old:
                del season["players"][code]
                season["seen"].pop(code, None)
            dropped += len(old)
        return dropped

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
        keep = sorted(self.patches, key=patch_order)[-max(config.KEEP_PATCHES, MIN_PATCHES):]
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
        ordered = sorted(self.patches, key=patch_order)
        with_players = ordered[-max(config.KEEP_PLAYER_PATCHES, MIN_PATCHES):]
        for name, patch in self.patches.items():
            folder = os.path.join(patches_dir, name)
            summary = self.summary(name)
            _write(os.path.join(folder, "summary.json"), summary)
            _write(os.path.join(folder, "champions.json"), patch["champions"])
            # The small archive is written for every patch and never cleaned up.
            _write(os.path.join(root, config.ARCHIVE_DIR, name, "summary.json"), summary)
            _write(os.path.join(root, config.ARCHIVE_DIR, name, "champions.json"), patch["champions"])
            for role, filename in DETAIL_FILES.items():
                _write(os.path.join(folder, filename), patch["detail"][role])
            players_path = os.path.join(folder, "players.json.gz")
            if name in with_players:
                _write(players_path, patch["players"])
            else:
                patch["players"] = {}
                if os.path.exists(players_path):
                    os.remove(players_path)

        keep_seasons = sorted(self.seasons, key=int)[-max(config.KEEP_SEASONS, 1):]
        for name in list(self.seasons):
            if name not in keep_seasons:
                del self.seasons[name]
        today = _today()
        self.pruned_players = self.prune_seasons(today)
        seasons_dir = os.path.join(root, "season")
        os.makedirs(seasons_dir, exist_ok=True)
        for name in os.listdir(seasons_dir):
            if name not in self.seasons:
                shutil.rmtree(os.path.join(seasons_dir, name))
        for name, season in self.seasons.items():
            write_season(os.path.join(seasons_dir, name), season, today)

        state = os.path.join(root, "state")
        _write(os.path.join(state, "players.json.gz"), self.player_state)
        _write(os.path.join(state, "processed.json.gz"), {
            s: {str(day): sorted(nums) for day, nums in days.items()}
            for s, days in self.processed.items()})
        _write(os.path.join(state, "pending.json.gz"), self.pending)
        _write(os.path.join(root, CODES_FILE), {"version": CODES_VERSION, "check": secret_check()})
        _write(os.path.join(root, "last_run.json"), run_info)
        with open(os.path.join(root, "README.md"), "w") as f:
            f.write(DATA_README)

        loaded = Store.load(root)  # raises DataDamaged if anything didn't save properly
        for name, season in self.seasons.items():
            # The season totals read back must be exactly what was written (also proves a conversion lost nothing).
            if season_fingerprint(loaded.seasons[name]) != season_fingerprint(season):
                raise DataDamaged("season %s changed while saving" % name)
        for name, season in self.seasons.items():
            finish_conversion(os.path.join(seasons_dir, name), season, today)

    @classmethod
    def load(cls, root):
        store = cls()
        if not os.path.isdir(os.path.join(root, "state")):
            return store  # nothing saved yet
        check_codes(root)
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
                    path = os.path.join(folder, filename)
                    # Patches saved before a role was added simply start empty for it.
                    patch["detail"][role] = _read(path) if os.path.exists(path) else {}
                players_path = os.path.join(folder, "players.json.gz")
                # Older patches no longer keep their player file.
                patch["players"] = _read(players_path) if os.path.exists(players_path) else {}
                store.patches[name] = patch
            seasons_dir = os.path.join(root, "season")
            for name in os.listdir(seasons_dir) if os.path.isdir(seasons_dir) else []:
                season = read_season(os.path.join(seasons_dir, name))
                if season is not None:
                    store.seasons[name] = season
            store._seed_seasons()
        except Exception as error:
            raise DataDamaged("%s: %s" % (type(error).__name__, error))
        return store


def check_codes(root):
    """Refuse data whose player codes were not made with the current secret."""
    path = os.path.join(root, CODES_FILE)
    try:
        saved = _read(path)
    except (OSError, ValueError):
        raise CodesMismatch("%s is missing: the data has not been converted to secret-key codes" % CODES_FILE)
    if saved.get("version") != CODES_VERSION or saved.get("check") != secret_check():
        raise CodesMismatch("the data was made with a different player-code secret")


def prune_scores(root):
    """Keep the newest KEEP_SCORE_FILES `scores/<patch>.json` files. `latest.json` and the
    newest patch's file are never removed."""
    folder = os.path.join(root, "scores")
    if not os.path.isdir(folder):
        return []
    names = [n[:-5] for n in os.listdir(folder) if n.endswith(".json") and PATCH_PATTERN.match(n[:-5])]
    names.sort(key=patch_order)
    old = names[:-max(config.KEEP_SCORE_FILES, MIN_PATCHES)]
    for name in old:
        os.remove(os.path.join(folder, name + ".json"))
    return old


def biggest_file(root):
    """(size in bytes, path relative to root) of the biggest file saved, or (0, None)."""
    best = (0, None)
    for folder, _, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            size = os.path.getsize(path)
            if size > best[0]:
                best = (size, os.path.relpath(path, root))
    return best


def size_report(root):
    """Lines for the run summary: the biggest file, with a clear warning at SIZE_WARNING_MB."""
    size, path = biggest_file(root)
    mb = size / 1_000_000
    line = "Biggest saved file: %s, %.1f MB (warning at %d MB)." % (path or "none", mb, config.SIZE_WARNING_MB)
    if mb >= config.SIZE_WARNING_MB:
        line = "WARNING: biggest saved file is %s, %.1f MB, at or over the %d MB warning line. Tell Alejandro." % (
            path, mb, config.SIZE_WARNING_MB)
    return line, mb >= config.SIZE_WARNING_MB


def total_size(root):
    return sum(os.path.getsize(os.path.join(folder, name)) for folder, _, files in os.walk(root) for name in files)


def season_report(root):
    """One line for the run summary: the season pieces and the biggest one."""
    sizes = []
    for folder, _, files in os.walk(os.path.join(root, "season")):
        for name in files:
            if name.startswith("players-") and name != PRECONVERSION_FILE and name.endswith(".json.gz"):
                sizes.append((os.path.getsize(os.path.join(folder, name)), name))
    if not sizes:
        return "Season totals: no pieces saved yet."
    biggest = max(sizes)
    return "Season totals: %d pieces, biggest %s %.1f MB, together %.1f MB." % (
        len(sizes), biggest[1], biggest[0] / 1_000_000, sum(size for size, _ in sizes) / 1_000_000)


def size_lines(root):
    """Lines for the run summary: biggest file (the 40 MB warning applies to it, so to each season piece too),
    the season pieces, and the size of everything saved. Returns (lines, warning)."""
    line, warn = size_report(root)
    return [line, season_report(root), "All saved data together: %.1f MB." % (total_size(root) / 1_000_000)], warn


def peak_memory_bytes(usage=None, platform=None):
    """Highest memory this process and its children (the scoring step) used, in bytes.
    Linux reports ru_maxrss in KB, macOS in bytes."""
    scale = 1 if (platform or sys.platform) == "darwin" else 1024
    if usage is not None:
        return usage * scale
    return max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss) * scale


def total_memory_bytes():
    """The machine's total memory (Linux /proc/meminfo, else sysconf). None if it can't be found."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def memory_report(season_players, peak=None, total=None):
    """Run-summary lines: peak memory, the runner's total memory, the season player count.
    Returns (lines, warning); the warning is on when the peak passes MEMORY_WARNING_SHARE of the total."""
    peak = peak_memory_bytes() if peak is None else peak
    total = total_memory_bytes() if total is None else total
    gb = lambda n: n / 1e9
    players = "Season totals hold %s players." % format(int(season_players), ",")
    if not total:
        return ["Memory: peak %.1f GB (runner's total memory unknown). %s" % (gb(peak), players)], False
    share = peak / total
    warn = share > config.MEMORY_WARNING_SHARE
    line = "Memory: peak %.1f GB of %.1f GB on the runner (%d%%). %s" % (gb(peak), gb(total), round(100 * share), players)
    if warn:
        return ["WARNING: peak memory is over %d%% of the runner's memory. Tell Alejandro." % round(100 * config.MEMORY_WARNING_SHARE), line], True
    return [line], False


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


def _site_role_champion(roles):
    """True when a champion is played enough in bot lane, support or jungle."""
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
The last 5 patches are kept. `players.json.gz` is kept only for the newest few
(see `KEEP_PLAYER_PATCHES` in `collector/config.py`).
- `summary.json`: games counted, games per server, Diamond+ average win rate
  (weighted and unweighted), and average win rate per role.
- `champions.json`: per champion ID: name, games and wins per role, and bans.
  Bans count once per game: [games banned on double-weight servers, on other servers].
- `bottom.json.gz`, `utility.json.gz`, `jungle.json.gz`: per champion played
  in that role: games, final items, rune pages, and allies/enemies as
  "championId:role". Jungle was added on Oct 3, 2026.
- `players.json.gz`: per scrambled player code, `[games, wins]` per champion ID
  (all roles), plus `"ID:B"` (bot lane), `"ID:S"` (support) and `"ID:J"`
  (jungle, from Oct 3, 2026) for games in those roles. Used for the "recent games" part of the OTP rule (current +
  previous patch). Real player IDs are never stored.

## archive/<patch>/
`summary.json` and `champions.json` of every patch, kept forever (tiny). They
survive the cleanup of the `patches/` folders.

## season/<season>/
Saved in 16 pieces by the first character of the player code
(`players-0.json.gz` ... `players-f.json.gz`), plus `season.json` (the champion
list and the day the pieces were made). Each piece holds `players` and `seen`
(the last day each player was counted). Players with 5 games or fewer that have
not been seen for 30 days are dropped. `players-preconversion.json.gz` is the
old single file, kept for 7 days after the split as a rollback copy.
Running totals for the whole season (season 16 = patches 16.x); only the
current season is kept, for the "50 games this season" part of the OTP rule:
- `players` (in each piece): per scrambled player code, `"all"` = `[games, wins]` across every
  champion, plus `[games, wins]` per champion ID and per `"ID:B"` / `"ID:S"` /
  `"ID:J"`, only for bot-lane, support and jungle champions.
- `champions`: the champion IDs counted this season (at least 200 games in a
  patch with at least 10% in bot lane, support or jungle; once in, they stay).
  When a champion joins, its earlier games are copied in from the patch files
  still kept (the patches that keep a `players.json.gz`).
Games collected before season totals existed were copied in from the patch
files (without the bot/support split, which starts from that point).

## Player codes
A code is `HMAC-SHA256(secret, SHA-256(player ID)[:16])[:16]`. The secret is a
GitHub secret that is never published, so a code can't be matched to a known
player ID. `codes.json` holds the format version and a short fingerprint of the
secret; the collector refuses data made with another secret.

Only Diamond+ players (from Riot's Diamond, Master, Grandmaster and Challenger
lists for ranked solo/duo) are counted.

## Counters
Every game/win counter is `[games x2, wins x2, games x1, wins x1]`. The x2 part
is LAN, NA, EUW and KR, the x1 part is every other server.
Weighted games = 2 * games x2 + games x1.

## scores/
Written right after each save by the scoring code (`scoring/` on the `main` branch,
model v0.44): `latest.json` and `<patch>.json` (the last 20 patches) with the Pick Score
list, Meta Score list, Growth advisor suggestions, and champions without a card.

## state/
The collector's memory: when each player was last checked, which games were
already processed (last 14 days), and games waiting to be downloaded.
"""
