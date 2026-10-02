"""Offline checks with a made-up game (no Riot key needed)."""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config  # noqa: E402
from collector.riot import Limiter, parse_limits  # noqa: E402
from collector.store import DataDamaged, Store, compact_match, scramble  # noqa: E402

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
        self.assertEqual(patch["players"][scramble("player-3")], {"103": [1, 1]})
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
        for minor in (16, 17, 18, 19, 9):
            store.add_match(compact_match(fake_match(version="16.%d.1" % minor), "NA1_%d" % minor, "NA1"), everyone)
        with tempfile.TemporaryDirectory() as root:
            store.save(root, {})
            self.assertEqual(sorted(os.listdir(os.path.join(root, "patches"))), ["16.17", "16.18", "16.19"])


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
