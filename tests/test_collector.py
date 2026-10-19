"""Offline checks with a made-up game (no Riot key needed)."""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A made-up secret for tests only (the real one is a GitHub secret and is never in the project).
os.environ.setdefault("PLAYER_CODE_SALT", "test-only-secret-" + "0123456789abcdef" * 2)

from collector import config  # noqa: E402
from collector.riot import Limiter, parse_limits  # noqa: E402
from collector import convert_season, store as store_module  # noqa: E402
from collector.store import (DataDamaged, Store, biggest_file, compact_match, prune_scores, read_season, scramble,  # noqa: E402
                             memory_report, peak_memory_bytes, season_report, size_lines, size_report, total_size, write_season)

POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


def fake_match(queue=420, duration=1800, version="16.19.712.4532"):
    participants = []
    for i in range(10):
        team = 100 if i < 5 else 200
        participants.append({
            "puuid": "player-%d" % i, "championId": 100 + i, "championName": "Champ%d" % i,
            "teamPosition": POSITIONS[i % 5], "teamId": team, "win": team == 100,
            "item0": 3006, "item1": 3031, "item2": 0, "item3": 3006, "item4": 0, "item5": 0, "item6": 3363,
            "perks": {"statPerks": {"offense": 5005, "flex": 5008, "defense": 5011},
                      "styles": [{"style": 8000, "selections": [{"perk": 8008}, {"perk": 9111},
                                                                {"perk": 9104}, {"perk": 8014}]},
                                 {"style": 8100, "selections": [{"perk": 8139}, {"perk": 8135}]}]},
        })
    return {"info": {
        "queueId": queue, "gameDuration": duration, "gameVersion": version,
        "gameStartTimestamp": 1790000000000, "participants": participants,
        "teams": [{"teamId": 100, "bans": [{"championId": 22}, {"championId": 22}, {"championId": -1}]},
                  {"teamId": 200, "bans": [{"championId": 51}]}],
    }}


class StoreTests(unittest.TestCase):
    def test_counts_only_diamond_players_and_bans_once_per_game(self):
        store = Store()
        diamond = {scramble("player-3"), scramble("player-9")}  # an ADC (team 100) and a support (team 200)
        rec = compact_match(fake_match(), "EUW1_123", "EUW1")
        outcome, counted = store.add_match(rec, diamond)
        self.assertEqual(outcome, "counted")
        self.assertEqual(len(counted), 2)
        patch = store.patches["16.19"]
        self.assertEqual(patch["games"], [1, 0])  # EUW counts in the double-weight group
        self.assertEqual(patch["participants"], [2, 1, 0, 0])
        self.assertEqual(patch["champions"]["22"]["bans"], [1, 0])  # banned twice, counted once
        self.assertNotIn("100", patch["champions"])  # TOP player is not Diamond+
        adc = patch["detail"]["BOTTOM"]["103"]
        self.assertEqual(adc["games"], [1, 1, 0, 0])
        self.assertEqual(adc["items"]["3006"], [1, 1, 0, 0])  # duplicate item counted once
        self.assertNotIn("3363", adc["items"])  # trinket ignored
        self.assertEqual(len(adc["allies"]), 4)
        self.assertEqual(len(adc["enemies"]), 5)
        self.assertIn("109:UTILITY", adc["enemies"])
        self.assertEqual(patch["players"][scramble("player-3")], {"103": [1, 1], "103:B": [1, 1]})
        self.assertEqual(store.summary("16.19")["diamond_plus_average_win_rate"], 50.0)

    def test_skips(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        self.assertEqual(store.add_match(compact_match(fake_match(queue=440), "NA1_1", "NA1"), everyone)[0],
                         "not_ranked")
        self.assertEqual(store.add_match(compact_match(fake_match(duration=200), "NA1_2", "NA1"), everyone)[0],
                         "remake")
        self.assertEqual(store.add_match(compact_match(fake_match(), "NA1_3", "NA1"), set())[0], "no_diamond")
        self.assertEqual(store.patches, {})

    def test_weighting(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        store.add_match(compact_match(fake_match(), "BR1_1", "BR1"), everyone)
        self.assertEqual(store.patches["16.19"]["games"], [0, 1])
        self.assertEqual(store.summary("16.19")["games_weighted"], 1)

    def test_save_load_and_damage(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        store.add_match(compact_match(fake_match(), "KR_5", "KR"), everyone)
        store.mark_processed("KR_5", int(time.time() // 86400))
        store.player_state["KR"]["abc"] = [1, 5]
        store.pending["NA1"] = ["NA1_9"]
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {"test": True})
            loaded = Store.load(root)
            self.assertTrue(loaded.is_processed("KR_5"))
            self.assertEqual(loaded.patches["16.19"]["games"], [1, 0])
            self.assertEqual(loaded.player_state["KR"]["abc"], [1, 5])
            self.assertEqual(loaded.pending["NA1"], ["NA1_9"])
            with open(os.path.join(root, "patches", "16.19", "champions.json"), "w") as f:
                f.write("{broken")
            with self.assertRaises(DataDamaged):
                Store.load(root)

    def test_keeps_only_recent_patches(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        for minor in (14, 15, 16, 17, 18, 19, 20, 9):
            store.add_match(compact_match(fake_match(version="16.%d.1" % minor), "NA1_%d" % minor, "NA1"), everyone)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            self.assertEqual(config.KEEP_PATCHES, 5)
            self.assertEqual(sorted(os.listdir(os.path.join(root, "patches"))),
                             ["16.16", "16.17", "16.18", "16.19", "16.20"])


class SeasonTests(unittest.TestCase):
    def _store_with_bot_champions(self):
        """A store where champion 103 (bot lane) and 109 (support) qualify."""
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        for n in range(config.SEASON_CHAMPION_MIN_GAMES):
            store.add_match(compact_match(fake_match(), "NA1_%d" % n, "NA1"), everyone)
        return store, everyone

    def test_counts_totals_and_bot_support_champions(self):
        store, _ = self._store_with_bot_champions()
        season = store.seasons["16"]
        self.assertEqual(season["champions"], {str(100 + i) for i in range(10)} & season["champions"])
        self.assertIn("103", season["champions"])   # always played bot lane
        self.assertIn("109", season["champions"])   # always played support
        self.assertIn("101", season["champions"])   # always jungle
        self.assertNotIn("100", season["champions"])  # always top lane
        adc = season["players"][scramble("player-3")]
        top = season["players"][scramble("player-0")]
        games = config.SEASON_CHAMPION_MIN_GAMES
        self.assertEqual(adc["all"], [games, games])
        # The champion qualifies at its 200th game; its earlier games are copied in.
        self.assertEqual(adc["103"], [games, games])
        self.assertEqual(adc["103:B"], [games, games])
        jungler = season["players"][scramble("player-1")]
        self.assertEqual(jungler["101:J"], [games, games])
        self.assertEqual(top["all"], [games, games])
        self.assertNotIn("100", top)  # top-lane champion: total only
        patch_player = store.patches["16.19"]["players"][scramble("player-3")]
        self.assertEqual(patch_player["103"], [games, games])
        self.assertEqual(patch_player["103:B"], [games, games])

    def test_new_season_starts_fresh(self):
        store, everyone = self._store_with_bot_champions()
        store.add_match(compact_match(fake_match(version="17.1.1"), "NA1_99999", "NA1"), everyone)
        self.assertEqual(store.seasons["17"]["players"][scramble("player-3")]["all"], [1, 1])
        self.assertEqual(store.seasons["16"]["players"][scramble("player-3")]["all"][0],
                         config.SEASON_CHAMPION_MIN_GAMES)

    def test_seed_from_patch_files_and_save_load(self):
        store, _ = self._store_with_bot_champions()
        games = config.SEASON_CHAMPION_MIN_GAMES
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            # Pretend the season file never existed: it is rebuilt from the patch files.
            shutil.rmtree(os.path.join(root, "season"))
            seeded = Store.load(root)
            player = seeded.seasons["16"]["players"][scramble("player-3")]
            self.assertEqual(player["all"], [games, games])
            self.assertEqual(player["103"], [games, games])
            self.assertEqual(player["103:B"], [games, games])
            self.assertNotIn("100", seeded.seasons["16"]["players"][scramble("player-0")])
            seeded.save(root, {})
            again = Store.load(root)
            self.assertEqual(again.seasons["16"]["players"][scramble("player-3")]["all"], [games, games])

    def test_keeps_only_the_current_season(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        for major in (14, 15, 16):
            store.add_match(compact_match(fake_match(version="%d.1.1" % major), "NA1_%d" % major, "NA1"), everyone)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            self.assertEqual(sorted(os.listdir(os.path.join(root, "season"))), ["16"])
            self.assertEqual(config.KEEP_SEASONS, 1)

    def test_old_season_is_not_rebuilt_from_patch_files(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        for version in ("16.5.1", "17.1.1"):
            store.add_match(compact_match(fake_match(version=version), "NA1_" + version, "NA1"), everyone)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            shutil.rmtree(os.path.join(root, "season"))
            store = Store.load(root)
            store.save(root, {})
            self.assertEqual(sorted(os.listdir(os.path.join(root, "season"))), ["17"])


def patch_store(minors):
    store = Store()
    everyone = {scramble("player-%d" % i) for i in range(10)}
    for minor in minors:
        store.add_match(compact_match(fake_match(version="16.%d.1" % minor), "NA1_%d" % minor, "NA1"), everyone)
    return store


class StorageStandardTests(unittest.TestCase):
    def test_summaries_are_archived_forever(self):
        with tempfile.TemporaryDirectory() as root:
            patch_store(range(10, 18)).save(root, {})          # 8 patches: 3 fall out of patches/
            self.assertEqual(sorted(os.listdir(os.path.join(root, "patches"))),
                             ["16.13", "16.14", "16.15", "16.16", "16.17"])
            archived = sorted(os.listdir(os.path.join(root, config.ARCHIVE_DIR)))
            self.assertEqual(archived, ["16.%d" % m for m in range(13, 18)])
            # Next saves: the loaded store only knows 5 patches, yet the archive keeps the old ones.
            later = Store.load(root)
            later.add_match(compact_match(fake_match(version="16.18.1"), "NA1_18", "NA1"),
                            {scramble("player-%d" % i) for i in range(10)})
            later.save(root, {})
            self.assertEqual(sorted(os.listdir(os.path.join(root, config.ARCHIVE_DIR))),
                             ["16.%d" % m for m in range(13, 19)])
            for name in os.listdir(os.path.join(root, config.ARCHIVE_DIR, "16.13")):
                self.assertIn(name, ("summary.json", "champions.json"))

    def test_archive_survives_cleanup_of_patch_folders(self):
        with tempfile.TemporaryDirectory() as root:
            store = patch_store([10])
            store.save(root, {})
            for minor in range(11, 17):
                store.add_match(compact_match(fake_match(version="16.%d.1" % minor), "NA1_%d" % minor, "NA1"),
                                {scramble("player-%d" % i) for i in range(10)})
            store.save(root, {})
            self.assertFalse(os.path.exists(os.path.join(root, "patches", "16.10")))
            self.assertTrue(os.path.exists(os.path.join(root, config.ARCHIVE_DIR, "16.10", "summary.json")))

    def test_players_files_only_for_newest_patches(self):
        with tempfile.TemporaryDirectory() as root:
            patch_store(range(14, 20)).save(root, {})
            have = sorted(n for n in os.listdir(os.path.join(root, "patches"))
                          if os.path.exists(os.path.join(root, "patches", n, "players.json.gz")))
            self.assertEqual(len(have), config.KEEP_PLAYER_PATCHES)
            self.assertEqual(have, ["16.%d" % m for m in range(20 - config.KEEP_PLAYER_PATCHES, 20)])
            # An older patch without its player file still loads (and keeps its other files).
            loaded = Store.load(root)
            self.assertEqual(loaded.patches["16.15"]["players"], {})
            self.assertTrue(loaded.patches["16.15"]["champions"])

    def test_cleanup_never_removes_current_or_previous_patch(self):
        keep = (config.KEEP_PATCHES, config.KEEP_PLAYER_PATCHES, config.KEEP_SEASONS, config.KEEP_SCORE_FILES)
        try:
            config.KEEP_PATCHES = config.KEEP_PLAYER_PATCHES = config.KEEP_SCORE_FILES = 0
            config.KEEP_SEASONS = 0
            with tempfile.TemporaryDirectory() as root:
                patch_store(range(10, 15)).save(root, {})
                os.makedirs(os.path.join(root, "scores"))
                for name in ("16.13.json", "16.14.json", "latest.json"):
                    open(os.path.join(root, "scores", name), "w").write("{}")
                prune_scores(root)
                self.assertEqual(sorted(os.listdir(os.path.join(root, "patches"))), ["16.13", "16.14"])
                for name in ("16.13", "16.14"):
                    self.assertTrue(os.path.exists(os.path.join(root, "patches", name, "players.json.gz")))
                self.assertEqual(sorted(os.listdir(os.path.join(root, "season"))), ["16"])
                self.assertEqual(sorted(os.listdir(os.path.join(root, "scores"))),
                                 ["16.13.json", "16.14.json", "latest.json"])
        finally:
            (config.KEEP_PATCHES, config.KEEP_PLAYER_PATCHES, config.KEEP_SEASONS, config.KEEP_SCORE_FILES) = keep

    def test_scores_keep_last_20_patches_and_latest(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, "scores")
            os.makedirs(folder)
            for minor in range(1, 25):
                open(os.path.join(folder, "16.%d.json" % minor), "w").write("{}")
            open(os.path.join(folder, "latest.json"), "w").write("{}")
            removed = prune_scores(root)
            self.assertEqual(config.KEEP_SCORE_FILES, 20)
            self.assertEqual(sorted(removed), ["16.1", "16.2", "16.3", "16.4"])
            left = os.listdir(folder)
            self.assertEqual(len(left), 21)
            self.assertIn("latest.json", left)
            self.assertIn("16.24.json", left)
            self.assertNotIn("16.4.json", left)

    def test_size_watch_warns_at_40_mb(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "small.bin"), "wb") as f:
                f.write(b"x" * 1000)
            line, warn = size_report(root)
            self.assertFalse(warn)
            self.assertIn("small.bin", line)
            self.assertEqual(config.SIZE_WARNING_MB, 40)
            os.makedirs(os.path.join(root, "season"))
            with open(os.path.join(root, "season", "big.bin"), "wb") as f:
                f.truncate(40 * 1_000_000)   # sparse file, no real disk used
            self.assertEqual(biggest_file(root)[1], os.path.join("season", "big.bin"))
            line, warn = size_report(root)
            self.assertTrue(warn)
            self.assertTrue(line.startswith("WARNING"))


def season_store(games=config.SEASON_CHAMPION_MIN_GAMES):
    """A store with `games` games: champion 103 (bot lane) and 109 (support) qualify; 10 players."""
    store = Store()
    everyone = {scramble("player-%d" % i) for i in range(10)}
    for n in range(games):
        store.add_match(compact_match(fake_match(), "NA1_%d" % n, "NA1"), everyone)
    return store, everyone


def write_legacy(root, store):
    """Save `store`, then turn its season folder back into the old single-file layout (as the live data is now)."""
    store.save(root, {})
    folder = os.path.join(root, "season", "16")
    season = read_season(folder)
    for name in os.listdir(folder):
        os.remove(os.path.join(folder, name))
    store_module._write(os.path.join(folder, "players.json.gz"),
                        {"champions": sorted(season["champions"], key=int), "players": season["players"]})
    return folder


def totals(season):
    return {"players": len(season["players"]), "champions": sorted(season["champions"]),
            "counters": {code: {k: list(v) for k, v in c.items()} for code, c in season["players"].items()}}


class SeasonPiecesTests(unittest.TestCase):
    """v1.1: the season totals are saved in 16 pieces, small inactive players are dropped, the old file is kept 7 days."""

    def test_saved_in_16_pieces_and_read_back_exactly(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            folder = os.path.join(root, "season", "16")
            names = sorted(os.listdir(folder))
            self.assertEqual(names, sorted(["season.json"] + ["players-%s.json.gz" % c for c in "0123456789abcdef"]))
            self.assertNotIn("players.json.gz", names)
            self.assertEqual(totals(read_season(folder)), totals(store.seasons["16"]))
            self.assertEqual(totals(Store.load(root).seasons["16"]), totals(store.seasons["16"]))
            # every player sits in the piece named by the first character of its code
            for piece in "0123456789abcdef":
                for code in store_module._read(os.path.join(folder, "players-%s.json.gz" % piece))["players"]:
                    self.assertEqual(code[0], piece)

    def test_conversion_from_the_old_single_file_loses_nothing(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            folder = write_legacy(root, store)
            before = read_season(folder)
            self.assertTrue(before["legacy"])
            results = convert_season.convert(root)
            (name, b, a), = results
            self.assertEqual((name, b), ("16", a))
            self.assertEqual(totals(read_season(folder)), totals(before))
            self.assertTrue(os.path.exists(os.path.join(folder, "players-preconversion.json.gz")))
            self.assertFalse(os.path.exists(os.path.join(folder, "players.json.gz")))
            self.assertEqual(convert_season.convert(root), [])   # a second run does nothing

    def test_the_collector_converts_by_itself_and_keeps_the_old_file_7_days(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            folder = write_legacy(root, store)
            with open(os.path.join(folder, "players.json.gz"), "rb") as handle:
                old_bytes = handle.read()
            loaded = Store.load(root)
            before = totals(loaded.seasons["16"])
            original_today = store_module._today
            day = original_today()
            try:
                store_module._today = lambda: day
                loaded.save(root, {})                                   # the conversion
                pre = os.path.join(folder, "players-preconversion.json.gz")
                with open(pre, "rb") as handle:
                    self.assertEqual(handle.read(), old_bytes)     # the old file, renamed, untouched
                self.assertFalse(os.path.exists(os.path.join(folder, "players.json.gz")))
                self.assertEqual(totals(Store.load(root).seasons["16"]), before)
                self.assertEqual(store_module._read(os.path.join(folder, "season.json"))["converted_day"], day)
                for later, kept in ((day + 3, True), (day + 6, True), (day + 7, False), (day + 30, False)):
                    store_module._today = lambda later=later: later
                    again = Store.load(root)
                    if not os.path.exists(pre) and kept:
                        self.fail("deleted too early")
                    again.save(root, {})
                    self.assertEqual(os.path.exists(pre), kept, later)
                    if not kept:
                        break
                self.assertEqual(totals(Store.load(root).seasons["16"]), before)   # data itself unchanged
            finally:
                store_module._today = original_today

    def test_preconversion_file_is_not_deleted_before_the_conversion_day_is_known(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            folder = os.path.join(root, "season", "16")
            store_module._write(os.path.join(folder, "players-preconversion.json.gz"), {"players": {}, "champions": []})
            Store.load(root).save(root, {})        # no conversion day recorded: the rollback file stays
            self.assertTrue(os.path.exists(os.path.join(folder, "players-preconversion.json.gz")))

    def test_a_split_that_would_lose_something_is_refused(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            original = store_module.write_season

            def lossy(folder, season, today=None):
                original(folder, season, today)
                code = next(iter(season["players"]))
                piece = os.path.join(folder, "players-%s.json.gz" % store_module.piece_of(code))
                data = store_module._read(piece)
                data["players"] = {}
                store_module._write(piece, data)
            try:
                store_module.write_season = lossy
                with self.assertRaises(DataDamaged):
                    store.save(root, {})
            finally:
                store_module.write_season = original

    def test_damaged_or_missing_piece_is_detected(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            os.remove(os.path.join(root, "season", "16", "players-a.json.gz"))
            with self.assertRaises(DataDamaged):
                Store.load(root)


class SeasonPruneTests(unittest.TestCase):
    def setUp(self):
        self.original = store_module._today
        self.day = 20000
        store_module._today = lambda: self.day

    def tearDown(self):
        store_module._today = self.original

    def season_with(self, rows):
        """rows: {code: (games, last seen day)}"""
        store = Store()
        season = store._season("16")
        for code, (games, seen) in rows.items():
            season["players"][code] = {"all": [games, games // 2]}
            season["seen"][code] = seen
        return store

    def test_rule_small_and_inactive_players_are_dropped(self):
        old, recent = self.day - 31, self.day - 29
        store = self.season_with({
            "a1": (5, old),       # 5 games, unseen 31 days: dropped
            "a2": (1, old),       # dropped
            "a3": (6, old),       # 6 games: kept
            "a4": (5, recent),    # seen 29 days ago: kept
            "a5": (5, self.day - 30),   # exactly 30 days: kept (more than 30 days is needed)
            "a6": (0, old),       # no games: dropped
            "a7": (300, old),     # big player: kept
        })
        self.assertEqual((config.SEASON_PRUNE_MAX_GAMES, config.SEASON_PRUNE_AFTER_DAYS), (5, 30))
        self.assertEqual(store.prune_seasons(), 3)
        self.assertEqual(sorted(store.seasons["16"]["players"]), ["a3", "a4", "a5", "a7"])
        self.assertEqual(sorted(store.seasons["16"]["seen"]), ["a3", "a4", "a5", "a7"])

    def test_converted_players_all_start_as_seen_on_conversion_day(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            folder = write_legacy(root, store)
            loaded = Store.load(root)
            self.assertEqual(set(loaded.seasons["16"]["seen"].values()), {self.day})
            self.assertEqual(loaded.prune_seasons(), 0)                       # nothing can be dropped on day 0
            self.day += 29
            self.assertEqual(loaded.prune_seasons(), 0)

    def test_seen_day_is_updated_by_new_games_and_saved(self):
        store, everyone = season_store(5)
        self.day += 40
        store.add_match(compact_match(fake_match(), "NA1_9000", "NA1"), {scramble("player-3")})
        seen = store.seasons["16"]["seen"]
        self.assertEqual(seen[scramble("player-3")], self.day)
        self.assertEqual(seen[scramble("player-4")], 20000)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            self.assertEqual(store.pruned_players, 9)     # the 9 others: 5 games each, unseen for 40 days
            self.assertEqual(sorted(Store.load(root).seasons["16"]["players"]), [scramble("player-3")])

    def test_back_fill_does_not_bring_dropped_players_back(self):
        store, everyone = season_store(config.SEASON_CHAMPION_MIN_GAMES - 1)
        patch = store.patches["16.19"]["players"]
        dropped, kept = "dead00000000beef", "cafe00000000f00d"
        patch[dropped] = {"103": [150, 75], "103:B": [150, 75]}      # in the patch file, but dropped from the season file
        patch[kept] = {"103": [100, 50], "103:B": [100, 50]}
        store.seasons["16"]["players"][kept] = {"all": [100, 50]}    # a player the season file still has
        store.seasons["16"]["seen"][kept] = 20000
        # one more game makes champion 103 qualify: its earlier games are copied in from the patch files
        store.add_match(compact_match(fake_match(), "NA1_8000", "NA1"), {scramble("player-3")})
        season = store.seasons["16"]
        self.assertIn("103", season["champions"])
        self.assertNotIn(dropped, season["players"])
        self.assertNotIn(dropped, season["seen"])
        self.assertEqual(season["players"][kept]["103"], [100, 50])           # a kept player is back-filled
        self.assertEqual(season["players"][kept]["103:B"], [100, 50])
        self.assertEqual(season["players"][scramble("player-3")]["103"][0], config.SEASON_CHAMPION_MIN_GAMES)

    def test_repair_rebuilds_the_pieces_from_the_patch_files(self):
        store, _ = season_store()
        games = config.SEASON_CHAMPION_MIN_GAMES
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            shutil.rmtree(os.path.join(root, "season"))
            rebuilt = Store.load(root)
            player = rebuilt.seasons["16"]["players"][scramble("player-3")]
            self.assertEqual((player["all"], player["103"], player["103:B"]), ([games, games],) * 3)
            self.assertEqual(rebuilt.prune_seasons(), 0)                       # rebuilt players count as seen today
            rebuilt.save(root, {})
            self.assertEqual(len(os.listdir(os.path.join(root, "season", "16"))), 17)
            self.assertEqual(totals(Store.load(root).seasons["16"]), totals(rebuilt.seasons["16"]))

    def test_scoring_reads_the_pieces_and_the_old_file(self):
        from scoring import model
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            pieces = model.read_season_players(root, "16")
            self.assertEqual({k: {c: list(v) for c, v in d.items()} for k, d in pieces.items()},
                             totals(store.seasons["16"])["counters"])
            self.assertEqual(model.read_season_players(root, "99"), {})
        with tempfile.TemporaryDirectory() as root:
            write_legacy(root, store)
            self.assertEqual(set(model.read_season_players(root, "16")), set(store.seasons["16"]["players"]))


class MemoryLineTests(unittest.TestCase):
    GB = 1_000_000_000

    def test_normal_line_has_peak_total_and_season_players(self):
        lines, warn = memory_report(461924, peak=2 * self.GB, total=16 * self.GB)
        self.assertFalse(warn)
        self.assertEqual(lines, ["Memory: peak 2.0 GB of 16.0 GB on the runner (12%). Season totals hold 461,924 players."])

    def test_warning_when_peak_passes_60_percent_of_the_runners_memory(self):
        self.assertEqual(config.MEMORY_WARNING_SHARE, 0.6)
        lines, warn = memory_report(1000000, peak=int(9.7 * self.GB), total=16 * self.GB)    # 61%
        self.assertTrue(warn)
        self.assertTrue(lines[0].startswith("WARNING: peak memory is over 60%"))
        self.assertIn("61%", lines[1])
        _, at_limit = memory_report(1, peak=int(9.6 * self.GB), total=16 * self.GB)           # exactly 60%: no warning
        self.assertFalse(at_limit)
        _, small_runner = memory_report(1, peak=5 * self.GB, total=7 * self.GB)               # a 7 GB runner is over the line
        self.assertTrue(small_runner)

    def test_unknown_runner_memory_gives_a_line_and_no_warning(self):
        lines, warn = memory_report(5, peak=self.GB, total=0)
        self.assertFalse(warn)
        self.assertIn("unknown", lines[0])
        self.assertIn("5 players", lines[0])

    def test_peak_memory_units_and_real_reading(self):
        self.assertEqual(peak_memory_bytes(2048, platform="linux"), 2048 * 1024)    # Linux counts KB
        self.assertEqual(peak_memory_bytes(2048, platform="darwin"), 2048)          # macOS counts bytes
        self.assertGreater(peak_memory_bytes(), 10_000_000)
        lines, _ = memory_report(3)                                                  # the real machine
        self.assertRegex(lines[-1], r"^Memory: peak [0-9.]+ GB .*Season totals hold 3 players\.$")

    def test_the_run_summary_and_log_use_it(self):
        from collector import main as collector_main
        self.assertEqual(collector_main.season_players({"seasons": {"15": {"players": 9}, "16": {"players": 12}}}), 12)
        self.assertEqual(collector_main.season_players({}), 0)
        with open(collector_main.__file__) as f:
            code = f.read()
        self.assertGreaterEqual(code.count("memory_report(season_players(info))"), 2)     # step summary and log


class SaveReserveAndSizeTests(unittest.TestCase):
    def test_reserve_is_15_minutes_and_saves_stay_hourly(self):
        self.assertEqual(config.FINAL_SAVE_RESERVE_MINUTES, 15)
        self.assertEqual(config.CHECKPOINT_MINUTES, 60)
        self.assertEqual(config.DEFAULT_MAX_MINUTES, 300)
        # the run still ends well inside the 345-minute job limit
        self.assertLess(config.DEFAULT_MAX_MINUTES + 10, 345)

    def test_run_summary_lines(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            lines, warn = size_lines(root)
            self.assertFalse(warn)
            self.assertEqual(len(lines), 3)
            self.assertTrue(lines[0].startswith("Biggest saved file:"))
            self.assertRegex(lines[1], r"^Season totals: 16 pieces, biggest players-[0-9a-f]\.json\.gz [0-9.]+ MB, together [0-9.]+ MB\.$")
            self.assertRegex(lines[2], r"^All saved data together: [0-9.]+ MB\.$")
            self.assertAlmostEqual(float(lines[2].split(": ")[1].split(" ")[0]), total_size(root) / 1e6, delta=0.06)

    def test_the_40_mb_warning_applies_to_a_season_piece(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            piece = os.path.join(root, "season", "16", "players-3.json.gz")
            with open(piece, "ab") as f:
                f.truncate(40 * 1_000_000)
            lines, warn = size_lines(root)
            self.assertTrue(warn)
            self.assertTrue(lines[0].startswith("WARNING"))
            self.assertIn("players-3.json.gz", lines[0])
            self.assertIn("biggest players-3.json.gz", lines[1])

    def test_the_old_rollback_file_does_not_count_as_a_season_piece(self):
        store, _ = season_store()
        with tempfile.TemporaryDirectory() as root:
            folder = write_legacy(root, store)
            convert_season.convert(root)
            self.assertNotIn("preconversion", season_report(root))


class JungleTests(unittest.TestCase):
    def test_jungle_detail_and_tags(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        store.add_match(compact_match(fake_match(), "EUW1_1", "EUW1"), everyone)
        patch = store.patches["16.19"]
        jungle = patch["detail"]["JUNGLE"]["101"]
        self.assertEqual(jungle["games"], [1, 1, 0, 0])
        self.assertIn("3006", jungle["items"])
        self.assertEqual(len(jungle["enemies"]), 5)
        self.assertEqual(patch["players"][scramble("player-1")], {"101": [1, 1], "101:J": [1, 1]})

    def test_old_saves_without_jungle_file_still_load(self):
        store = Store()
        everyone = {scramble("player-%d" % i) for i in range(10)}
        store.add_match(compact_match(fake_match(), "EUW1_1", "EUW1"), everyone)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            os.remove(os.path.join(root, "patches", "16.19", "jungle.json.gz"))
            loaded = Store.load(root)
            self.assertEqual(loaded.patches["16.19"]["detail"]["JUNGLE"], {})
            self.assertIn("103", loaded.patches["16.19"]["detail"]["BOTTOM"])


class ConfigTests(unittest.TestCase):
    def test_priority_shares(self):
        americas = config.server_shares("americas")
        self.assertAlmostEqual(americas["LA1"], 0.35)
        self.assertAlmostEqual(americas["NA1"], 0.35)
        self.assertAlmostEqual(americas["BR1"], 0.15)
        self.assertAlmostEqual(config.server_shares("europe")["EUW1"], 0.70)
        self.assertAlmostEqual(config.server_shares("asia")["JP1"], 0.30)
        self.assertAlmostEqual(config.server_shares("sea")["OC1"], 0.25)
        for region in config.REGIONS:
            self.assertAlmostEqual(sum(config.server_shares(region).values()), 1.0)

    def test_match_server(self):
        self.assertEqual(config.server_of_match("EUW1_7123"), "EUW1")
        self.assertEqual(config.server_of_match("KR_7123"), "KR")
        self.assertIsNone(config.server_of_match("XX_1"))


class LimiterTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_limits("20:1,100:120"), [(19, 1), (97, 120)])

    def test_never_exceeds_window(self):
        limiter = Limiter([(3, 0.5)])
        start = time.monotonic()
        for _ in range(7):
            limiter.wait_turn()
        self.assertGreaterEqual(time.monotonic() - start, 1.0)  # 3 + 3 + 1 needs two waits


if __name__ == "__main__":
    unittest.main()
