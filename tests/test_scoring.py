"""Offline checks for the scoring model, with made-up data (no Riot key needed)."""

import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import comfort, config, model  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = json.dumps(data).encode()
    if path.endswith(".gz"):
        raw = gzip.compress(raw)
    with open(path, "wb") as f:
        f.write(raw)


def champ(name, bottom=None, other=None):
    roles = {}
    if bottom:
        roles["BOTTOM"] = bottom
    if other:
        roles["MIDDLE"] = other
    return {"name": name, "bans": [0, 0], "roles": roles}


def make_patch(root, name, champions, average, bottom_total, participants):
    folder = os.path.join(root, "patches", name)
    write(os.path.join(folder, "summary.json"), {
        "patch": name, "diamond_plus_average_win_rate": average, "double_weight": 2,
        "participants": participants, "roles": {"BOTTOM": bottom_total}, "games_counted": 1000})
    write(os.path.join(folder, "champions.json"), champions)


class CardTests(unittest.TestCase):
    def test_every_card_matches_the_brief(self):
        cards = comfort.load_cards()
        self.assertEqual(len(cards), 32)
        average, rows, problems = comfort.self_check(cards)
        self.assertAlmostEqual(average, 13.656, places=3)
        self.assertEqual(problems, [])
        self.assertLess(max(abs(r["comfort_diff"]) for r in rows), 0.1)

    def test_aphelios_worked_example(self):
        card = next(c for c in comfort.load_cards() if c["name"] == "Aphelios")
        parts = comfort.comfort(card, 13.7)
        self.assertAlmostEqual(parts["base"], 68.0)
        self.assertAlmostEqual(parts["difficulty_adjustment"], -3.0)
        self.assertAlmostEqual(parts["comfort"], 66.7, delta=0.1)   # the brief rounds the kit adjustment to 1.8

    def test_secondary_type_and_caps(self):
        cards = {c["name"]: c for c in comfort.load_cards()}
        self.assertAlmostEqual(comfort.type_points(cards["Vayne"])[1], 3.5)      # best secondary counts
        self.assertAlmostEqual(comfort.type_points(cards["Sivir"])[1], 0.0)      # secondary is lower
        self.assertEqual(comfort.comfort(cards["Hwei"], 13.656)["kit_adjustment"], 5.0)    # capped
        self.assertEqual(comfort.comfort(cards["Vayne"], 13.656)["kit_adjustment"], -5.0)
        self.assertEqual(comfort.comfort(cards["Varus"], 13.656)["flexibility_bonus"], 0.25)
        self.assertEqual(comfort.comfort(cards["Varus"], 13.656, "main")["flexibility_bonus"], 1.0)
        self.assertEqual(comfort.comfort(cards["Jinx"], 13.656)["flexibility_bonus"], 0.0)


class SmallHelperTests(unittest.TestCase):
    def test_blend_share(self):
        self.assertAlmostEqual(model.this_patch_share(200, True), 1 / 6, places=3)
        self.assertEqual(model.this_patch_share(1000, True), 0.5)
        self.assertEqual(model.this_patch_share(3000, True), 0.75)
        self.assertEqual(model.this_patch_share(0, False), 1.0)

    def test_percentile_points_ties(self):
        points = model.percentile_points({"a": 1, "b": 2, "c": 2, "d": 9})
        self.assertEqual(points["a"], 0)
        self.assertEqual(points["d"], 100)
        self.assertAlmostEqual(points["b"], points["c"])
        self.assertEqual(model.percentile_points({"x": 5}), {"x": 50.0})

    def test_tiers_and_floor(self):
        self.assertEqual(model.tier_of(80.0)[0], "S")
        self.assertEqual(model.tier_of(79.96)[0], "S")   # shown as 80.0
        self.assertEqual(model.tier_of(72.0)[0], "A")
        self.assertEqual(model.tier_of(55.9)[0], "D")
        self.assertEqual(model.tier_of(85, -1.4)[0], "S")
        self.assertEqual(model.tier_of(85, -1.5), ("B", True))
        self.assertEqual(model.tier_of(60, -3), ("C", False))   # the floor only lowers


class EndToEndTests(unittest.TestCase):
    """Two patches, five bot-lane champions, one player who is a Jinx one-trick."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        # [games x2, wins x2, games x1, wins x1]
        last = {
            "222": champ("Jinx", [300, 160, 400, 200], [5, 2, 0, 0]),         # 700 games
            "15": champ("Sivir", [60, 30, 40, 20]),                           # 100 games
            "1": champ("Newcomer", [0, 0, 0, 0]),
            "50": champ("Swain", [100, 55, 100, 55]),                         # no card
            "103": champ("Ahri", [10, 5, 10, 5], [3000, 1500, 3000, 1500]),   # mostly mid
        }
        this = {
            "222": champ("Jinx", [100, 60, 100, 56], [2, 1, 0, 0]),           # 200 games
            "15": champ("Sivir", [40, 20, 60, 30]),                           # 100 games
            "50": champ("Swain", [60, 33, 60, 33]),                           # 120 games
            "103": champ("Ahri", [5, 2, 5, 2], [1500, 750, 1500, 750]),
            "99": champ("Tiny", [3, 1, 3, 1]),
        }
        make_patch(self.root, "16.19", last, 50.0, [620, 310, 750, 375], [60000, 30000, 60000, 30000])
        make_patch(self.root, "16.20", this, 50.0, [300, 150, 400, 200], [30000, 15000, 30000, 15000])
        write(os.path.join(self.root, "patches", "16.19", "players.json.gz"), {
            "otp": {"222": [60, 36], "222:B": [60, 36], "15": [5, 2]},
            "mixed": {"222": [40, 20], "222:B": [40, 20], "15": [60, 30]},
            "fan": {"222": [60, 30], "222:B": [60, 30], "15": [40, 20]},   # 60% but few season games
        })
        write(os.path.join(self.root, "patches", "16.20", "players.json.gz"), {
            "otp": {"222": [20, 12], "222:B": [20, 12]},
        })
        write(os.path.join(self.root, "season", "16", "players.json.gz"), {
            "champions": ["222", "15"],
            "players": {"otp": {"222": [80, 48], "all": [105, 50]},
                        "mixed": {"222": [40, 20]}, "fan": {"222": [30, 15]}},
        })
        self.result = model.score_all(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def by_name(self, name):
        return next(c for c in self.result["meta_score_list"] if c["name"] == name)

    def test_filters(self):
        names = [c["name"] for c in self.result["meta_score_list"]]
        # Jinx 900 + Sivir 200 + Swain 440 real games: only Jinx has 1,000 across both patches?
        # Jinx: 700 + 200 = 900 -> not enough; so nobody passes.
        self.assertEqual(names, [])

    def test_filters_pass_with_a_lower_bar(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        names = {c["name"] for c in result["meta_score_list"]}
        self.assertEqual(names, {"Jinx", "Swain"})          # Sivir 200 games, Ahri is mostly mid
        jinx = next(c for c in result["meta_score_list"] if c["name"] == "Jinx")
        self.assertEqual(jinx["real_games"], 900)
        self.assertAlmostEqual(jinx["this_patch_share"], 200 / 1200, places=3)   # 200 games this patch -> 17%
        self.assertEqual(jinx["data_label"], "Data: 17% this patch")
        swain = next(c for c in result["meta_score_list"] if c["name"] == "Swain")
        self.assertFalse(swain["has_card"])
        self.assertEqual(swain["label"], "no card yet")
        self.assertNotIn("pick_score", swain)
        self.assertEqual(result["uncarded_champions"][0]["name"], "Swain")

    def test_otp_rule(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        jinx = next(c for c in result["meta_score_list"] if c["name"] == "Jinx")
        # "otp": 80 of 105 recent games (76%), 80 season games -> OTP; 60 + 20 bot games, 48 wins
        # "mixed": 40 of 100 games -> not an OTP. "fan": 60% but only 30 season games -> not an OTP.
        self.assertEqual(jinx["otp_players"], 1)
        self.assertEqual(jinx["otp_games"], 80)
        self.assertAlmostEqual(jinx["otp_win_rate"], 60.0)
        self.assertAlmostEqual(jinx["otp_reliability"], 80 / 380, places=3)

    def test_win_rate_is_blended_against_each_patchs_own_average(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        jinx = next(c for c in result["meta_score_list"] if c["name"] == "Jinx")
        last = 100 * (2 * 160 + 200) / (2 * 300 + 400)       # 52.0
        this = 100 * (2 * 60 + 56) / (2 * 100 + 100)         # 58.67
        share = 200 / 1200
        self.assertAlmostEqual(jinx["win_rate_delta"], share * (this - 50) + (1 - share) * (last - 50), places=3)

    def test_ban_threat_is_any_role_and_positive_only(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        for row in result["ban_threat_list"]:
            self.assertGreater(row["win_rate_delta"], 0)
        self.assertEqual(result["ban_threat_list"], sorted(result["ban_threat_list"], key=lambda r: -r["ban_threat"]))


if __name__ == "__main__":
    unittest.main()
