"""One-time converter (v1.1): split season/<season>/players.json.gz into 16 pieces and prove nothing was lost.

    python3 -m collector.convert_season DATA_DIR

It reads the season totals, writes the pieces next to them, reads the pieces back and compares the totals.
The old file is renamed to players-preconversion.json.gz (kept 7 days by the collector's next save).
The collector does the same conversion by itself on its next save; this tool is for proving it on a copy first.
Nothing here needs the player-code secret, and no player ID is ever printed.
"""

import os
import sys

from . import config
from .store import (LEGACY_SEASON_FILE, SEASON_FILE, finish_conversion, read_season, season_fingerprint, write_season)


def counts(season):
    games = wins = entries = 0
    for counters in season["players"].values():
        for g, w in counters.values():
            games += g
            wins += w
            entries += 1
    return {"players": len(season["players"]), "champions": len(season["champions"]),
            "entries": entries, "games": games, "wins": wins}


def convert(data_dir):
    """Converts every season folder; returns [(season, before, after)] and raises if anything differs."""
    seasons_dir = os.path.join(data_dir, "season")
    results = []
    for name in sorted(os.listdir(seasons_dir)) if os.path.isdir(seasons_dir) else []:
        folder = os.path.join(seasons_dir, name)
        if os.path.exists(os.path.join(folder, SEASON_FILE)) or not os.path.exists(os.path.join(folder, LEGACY_SEASON_FILE)):
            continue   # already converted (or nothing saved)
        before = read_season(folder)
        write_season(folder, before)
        after = read_season(folder)
        if season_fingerprint(before) != season_fingerprint(after) or counts(before) != counts(after):
            raise SystemExit("STOPPED: season %s differs after the split. The old file was not touched." % name)
        finish_conversion(folder, after)
        results.append((name, counts(before), counts(after)))
    return results


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 -m collector.convert_season DATA_DIR")
    results = convert(sys.argv[1])
    if not results:
        print("Nothing to convert.")
    for name, before, after in results:
        print("Season %s:" % name)
        for key in before:
            print("  %-10s before %-12d after %-12d %s" % (key, before[key], after[key], "same" if before[key] == after[key] else "DIFFERENT"))
        folder = os.path.join(sys.argv[1], "season", name)
        sizes = sorted(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.startswith("players-") and f != "players-preconversion.json.gz")
        print("  pieces: %d, smallest %.2f MB, biggest %.2f MB" % (len(sizes), sizes[0] / 1e6, sizes[-1] / 1e6))


if __name__ == "__main__":
    main()
