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
        self.assertEqual(len(cards), 39)
        average, rows, problems = comfort.self_check(cards, tolerance=0.15)   # the brief rounds the kit adjustment to 1 decimal
        self.assertAlmostEqual(average, 13.9, places=1)
        self.assertEqual(problems, [])
        self.assertLess(max(abs(r["comfort_diff"]) for r in rows), 0.15)

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

    def test_spreads_and_tiers(self):
        self.assertEqual(model.spreads_from_average(75, 65, 5), 2.0)
        self.assertEqual(model.spreads_from_average(75, 65, 0), 0.0)        # no spread at all
        self.assertEqual(model.tier_of(1.5), "S")                   # boundaries count as inside
        self.assertEqual(model.tier_of(1.49), "A")
        self.assertEqual(model.tier_of(0.5), "A")
        self.assertEqual(model.tier_of(0.49), "B")
        self.assertEqual(model.tier_of(-0.5), "B")
        self.assertEqual(model.tier_of(-0.51), "C")
        self.assertEqual(model.tier_of(-1.5), "C")
        self.assertEqual(model.tier_of(-1.51), "D")

    def test_tier_follows_the_pick_score_only(self):
        # v0.36: no stats floor, no win rate condition on S
        self.assertEqual(model.tier_of(2.0), "S")
        self.assertEqual(model.tier_of(1.0), "A")
        self.assertEqual(model.tier_of(-3.0), "D")
        self.assertEqual(model.tier_of(0.66), "A")                          # Caitlyn on patch 16.20 data: was B* before
        import inspect
        self.assertEqual(list(inspect.signature(model.tier_of).parameters), ["spreads"])

    def test_win_rate_warning_is_display_only(self):
        self.assertTrue(model.win_rate_warning(-1.5))
        self.assertTrue(model.win_rate_warning(-3.0))
        self.assertFalse(model.win_rate_warning(-1.49))
        self.assertFalse(model.win_rate_warning(1.0))

    def test_failed_filters_reasons(self):
        c = {"real_games": 5000, "lane_share": 0.9, "pick_rate": 0.005}
        self.assertEqual(model.failed_filters(c), ["bot-lane pick rate under 0.8%"])
        c = {"real_games": 500, "lane_share": 0.05, "pick_rate": 0.5}
        self.assertEqual(len(model.failed_filters(c)), 2)
        self.assertEqual(model.failed_filters({"real_games": 5000, "lane_share": 0.9, "pick_rate": 0.5}), [])

    def test_weights_add_up(self):
        self.assertAlmostEqual(config.WEIGHT_STATS + config.WEIGHT_COMFORT + config.WEIGHT_OTP, 1.0)
        self.assertEqual((config.WEIGHT_STATS, config.WEIGHT_COMFORT, config.WEIGHT_OTP), (0.425, 0.525, 0.05))
        self.assertEqual(config.MIN_PICK_RATE, 0.008)


class EndToEndTests(unittest.TestCase):
    """Two patches, five bot-lane champions, one player who is a Jinx one-trick."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        # [games x2, wins x2, games x1, wins x1]
        last = {
            "222": champ("Jinx", [300, 160, 400, 200], [5, 2, 0, 0]),         # 700 games
            "15": champ("Sivir", [60, 30, 40, 20]),                           # 100 games
            "1": champ("Newcomer", [0, 0, 0, 0]),
            "50": champ("Nocardium", [100, 55, 100, 55]),                         # invented name, so it never gets a card
            "103": champ("Ahri", [10, 5, 10, 5], [3000, 1500, 3000, 1500]),   # mostly mid
        }
        this = {
            "222": champ("Jinx", [100, 60, 100, 56], [2, 1, 0, 0]),           # 200 games
            "15": champ("Sivir", [40, 20, 60, 30]),                           # 100 games
            "50": champ("Nocardium", [60, 33, 60, 33]),                           # 120 games
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
        # Jinx 900 + Sivir 200 + Nocardium 440 real games: only Jinx has 1,000 across both patches?
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
        self.assertEqual(names, {"Jinx", "Nocardium"})          # Sivir 200 games, Ahri is mostly mid
        jinx = next(c for c in result["meta_score_list"] if c["name"] == "Jinx")
        self.assertEqual(jinx["real_games"], 900)
        self.assertAlmostEqual(jinx["this_patch_share"], 200 / 1200, places=3)   # 200 games this patch -> 17%
        self.assertEqual(jinx["data_label"], "Data: 17% this patch")
        swain = next(c for c in result["meta_score_list"] if c["name"] == "Nocardium")
        self.assertFalse(swain["has_card"])
        self.assertEqual(swain["label"], "no card yet")
        self.assertNotIn("pick_score", swain)
        self.assertEqual(result["needs_a_card"][0]["name"], "Nocardium")

    def test_pick_rate_counts_bot_lane_games_only(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        swain = next(c for c in result["meta_score_list"] if c["name"] == "Nocardium")
        patch = model.Patch(self.root, "16.20")
        # this patch: 2 x 60 + 60 weighted bot-lane games; games = participants / 10
        expected = (2 * 60 + 60) / (patch.participants_weighted / 10)
        self.assertAlmostEqual(model.lane_pick_rate(patch, model.lane_numbers(patch, "50", "BOTTOM")), expected)

    def test_tiers_and_advisor_only_use_champions_with_a_card(self):
        old = config.MIN_REAL_GAMES
        config.MIN_REAL_GAMES = 300
        try:
            result = model.score_all(self.root)
        finally:
            config.MIN_REAL_GAMES = old
        self.assertEqual(result["tier_stats"]["champions"], 1)
        self.assertEqual([c["name"] for c in result["pick_score_list"]], ["Jinx"])
        self.assertEqual(result["pick_score_list"][0]["spreads"], 0.0)
        self.assertEqual(result["growth_advisor"], [])
        self.assertNotIn("uncarded_champions", result)

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


class NeedsACardTests(unittest.TestCase):
    """Meta Score ranks every champion that passes the filters, carded or not; Needs a card is the uncarded ones by Meta Score."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        # Jinx has a card; Zzalpha, Zzbeta and Zzgamma are invented, so they never get one.
        # [games x2, wins x2, games x1, wins x1]
        this = {
            "222": champ("Jinx", [1000, 520, 1000, 520]),
            "901": champ("Zzalpha", [1000, 560, 1000, 560]),   # best win rate
            "902": champ("Zzbeta", [1000, 500, 1000, 500]),    # worst win rate
            "903": champ("Zzgamma", [1000, 530, 1000, 530]),
        }
        make_patch(self.root, "16.20", this, 50.0, [4000, 2000, 4000, 2000], [40000, 20000, 40000, 20000])
        write(os.path.join(self.root, "patches", "16.20", "players.json.gz"), {})
        self.result = model.score_all(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_meta_list_includes_uncarded_champions_ranked_by_meta_score(self):
        meta = self.result["meta_score_list"]
        self.assertEqual(len(meta), 4)
        scores = [c["meta_score"] for c in meta]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual([c["meta_rank"] for c in meta], [1, 2, 3, 4])
        self.assertEqual(meta[0]["name"], "Zzalpha")               # uncarded champions can be on top
        for c in meta:
            self.assertEqual(c["meta_score"], c["stats"])           # Meta Score = Stats points alone
            self.assertEqual("pick_score" in c, c["has_card"])
            if not c["has_card"]:
                self.assertEqual(c["label"], "no card yet")

    def test_needs_a_card_is_the_uncarded_ones_in_meta_score_order(self):
        needs = self.result["needs_a_card"]
        self.assertEqual([c["name"] for c in needs], ["Zzalpha", "Zzgamma", "Zzbeta"])
        self.assertTrue(all(not c["has_card"] for c in needs))
        self.assertEqual([c["name"] for c in self.result["pick_score_list"]], ["Jinx"])   # no Pick Score without a card


class GrowthAdvisorRuleTests(unittest.TestCase):
    """The advisor compares with the current #3 pick; fewer than 3 carded champions means no tips."""

    def test_no_tips_with_fewer_than_three_carded_champions(self):
        self.assertEqual(model.growth_advisor({}, {}, [{"pick_score": 80}, {"pick_score": 70}], 13.9, {}), [])

    def test_a_tip_must_beat_the_third_best_pick(self):
        cards = {c["riot_name"]: c for c in comfort.load_cards()}
        average = comfort.average_trait_score(list(cards.values()))
        names = ["Sivir", "Jinx", "Caitlyn", "Kalista"]
        eligible, carded = {}, {}
        for i, name in enumerate(names):
            card = cards[name]
            parts = comfort.comfort(card, average)
            eligible[i] = {"id": i, "name": name, "has_card": True, "mastery": card["mastery"], "stats": 50.0,
                           "otp_points": 50.0, "comfort": parts["comfort"],
                           "pick_score": config.WEIGHT_STATS * 50 + config.WEIGHT_COMFORT * parts["comfort"] + config.WEIGHT_OTP * 50}
            carded[i] = card
        pick_list = sorted(eligible.values(), key=lambda v: -v["pick_score"])
        stats = {"average_pick_score": 70.0, "spread": 5.0}
        bar = pick_list[2]["pick_score"]
        tips = model.growth_advisor(eligible, carded, pick_list, average, stats)
        for tip in tips:
            self.assertGreater(tip["pick_score_at_target"], bar)
            self.assertGreater(tip["pick_score_at_target"], tip["pick_score_now"])
        # raise Kalista's stats so that even her current score is a top pick: she no longer needs a tip
        eligible[3]["stats"] = 99.0
        eligible[3]["pick_score"] += config.WEIGHT_STATS * 49
        pick_list = sorted(eligible.values(), key=lambda v: -v["pick_score"])
        again = model.growth_advisor(eligible, carded, pick_list, average, stats)
        self.assertTrue(all(t["pick_score_at_target"] > pick_list[2]["pick_score"] for t in again))


class NextStepTests(unittest.TestCase):
    """v0.39: both Growth lists use the NEXT mastery level only; the ceiling at Main is information only."""

    STEPS = {"never_played": "below_average", "below_average": "average", "average": "good", "good": "main"}
    STATS = {"average_pick_score": 70.0, "spread": 5.0}

    def setUp(self):
        self.cards = {c["riot_name"]: c for c in comfort.load_cards()}
        self.average = comfort.average_trait_score(list(self.cards.values()))

    def champion(self, i, name, stats, tier, mastery=None):
        card = self.cards[name]
        mastery = mastery or card["mastery"]
        parts = comfort.comfort(card, self.average, mastery)
        score = config.WEIGHT_STATS * stats + config.WEIGHT_COMFORT * parts["comfort"] + config.WEIGHT_OTP * 50
        v = {"id": i, "name": name, "has_card": True, "mastery": mastery, "stats": stats, "otp_points": 50.0,
             "pick_score": score, "tier": tier}
        v["best_tier_at_main"] = model.score_at_mastery(v, card, self.average, self.STATS, "main")[1]
        return v, card

    def run_list(self, rows):
        eligible = {v["id"]: v for v, _ in rows}
        carded = {v["id"]: c for v, c in rows}
        return model.next_step_list(eligible, carded, [v for v, _ in rows], self.average, self.STATS)

    def test_the_step_table_is_one_level_up_and_main_has_none(self):
        self.assertEqual(config.GROWTH_TARGET, self.STEPS)
        self.assertEqual(config.MASTERY_ORDER, ["never_played", "below_average", "average", "good", "main"])
        for level, target in self.STEPS.items():
            self.assertEqual(config.MASTERY_ORDER.index(target), config.MASTERY_ORDER.index(level) + 1)
        self.assertNotIn("main", config.GROWTH_TARGET)

    def test_top_upgrades_go_exactly_one_step_for_every_mastery_level(self):
        fillers = [{"pick_score": 20.0, "id": 100 + i} for i in range(3)]             # a low #3 bar, so every tip can show
        eligible, carded, pick = {}, {}, list(fillers)
        for i, level in enumerate(config.MASTERY_ORDER):
            v, card = self.champion(i, "Kalista", 100.0, "B", level)
            eligible[i], carded[i] = v, card
        tips = model.growth_advisor(eligible, carded, pick, self.average, self.STATS)
        got = {t["current_mastery"]: t["target_mastery"] for t in tips}
        self.assertEqual(got, self.STEPS)                                               # Main champions get no tip
        for t in tips:
            main_comfort = comfort.comfort(self.cards["Kalista"], self.average, t["target_mastery"])["comfort"]
            expected = config.WEIGHT_STATS * 100 + config.WEIGHT_COMFORT * main_comfort + config.WEIGHT_OTP * 50
            self.assertAlmostEqual(t["pick_score_at_target"], expected)
            self.assertEqual(t["kind"] == "New champion", t["current_mastery"] == "never_played")

    def test_next_step_list_uses_one_step_up_not_main(self):
        # Never played Draven with strong data: one step up is only Below average, Main would be far better.
        for stats in range(0, 101, 5):
            v, card = self.champion(1, "Draven", float(stats), "C", "never_played")
            step_after, step_tier = model.score_at_mastery(v, card, self.average, self.STATS, "below_average")
            rows, _ = self.run_list([(v, card)])
            self.assertEqual([r["tier_next"] for r in rows], [step_tier] if step_tier in "AS" else [], stats)
            for r in rows:
                self.assertEqual(r["next_mastery"], "below_average")
                self.assertAlmostEqual(r["pick_score_next"], step_after)
                self.assertAlmostEqual(r["gain"], step_after - v["pick_score"])

    def test_the_sweep_covers_a_s_and_neither(self):
        seen = set()
        for stats in range(0, 101, 5):
            v, card = self.champion(1, "Kalista", float(stats), "B", "average")
            after = model.score_at_mastery(v, card, self.average, self.STATS, "good")[0]
            z = (after - 70.0) / 5.0
            expected = "S" if z >= 1.5 else "A" if z >= 0.5 else "none"
            seen.add(expected)
            rows, _ = self.run_list([(v, card)])
            self.assertEqual([r["tier_next"] for r in rows], [] if expected == "none" else [expected], stats)
        self.assertEqual(seen, {"S", "A", "none"})

    def test_the_ceiling_at_main_never_decides_who_is_listed(self):
        found = False
        for stats in range(0, 101, 5):
            v, card = self.champion(1, "Zeri", float(stats), "B", "never_played")
            step_tier = model.score_at_mastery(v, card, self.average, self.STATS, "below_average")[1]
            if step_tier in "AS" or v["best_tier_at_main"] not in "AS":
                continue
            found = True                                                # reaches A or S at Main, but not one step up
            rows, closest = self.run_list([(v, card)])
            self.assertEqual(rows, [], stats)
            self.assertIsNotNone(closest)
        self.assertTrue(found)
        # a listed champion carries its ceiling as plain information
        v, card = self.champion(1, "Kalista", 100.0, "B", "average")
        rows, _ = self.run_list([(v, card)])
        self.assertEqual(rows[0]["tier_at_main"], v["best_tier_at_main"])
        # and changing the ceiling field changes nothing in the lists
        v["best_tier_at_main"] = "D"
        again, _ = self.run_list([(v, card)])
        self.assertEqual([r["name"] for r in again], [r["name"] for r in rows])

    def test_only_b_c_d_champions_not_at_main_are_listed(self):
        rows, _ = self.run_list([self.champion(1, "Kalista", 100.0, "B", "average"),
                                 self.champion(2, "Sivir", 100.0, "A", "good"),         # already A: not B, C or D
                                 self.champion(3, "Jinx", 100.0, "C", "main")])         # at Main: no next step
        self.assertEqual([r["name"] for r in rows], ["Kalista"])

    def test_closest_line_when_the_list_is_empty(self):
        a_line = 70.0 + 0.5 * 5.0
        low = self.champion(1, "Draven", 0.0, "D", "never_played")
        mid = self.champion(2, "Nilah", 40.0, "C", "never_played")
        rows, closest = self.run_list([low, mid])
        self.assertEqual(rows, [])
        afters = {}
        for v, card in (low, mid):
            afters[v["name"]] = model.score_at_mastery(v, card, self.average, self.STATS, "below_average")[0]
        self.assertEqual(closest["name"], max(afters, key=afters.get))                  # the nearest to the A line
        self.assertAlmostEqual(closest["points_short"], a_line - afters[closest["name"]])
        self.assertGreater(closest["points_short"], 0)
        # with someone listed there is no closest line
        rows, closest = self.run_list([self.champion(3, "Kalista", 100.0, "B", "average")])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(closest)
        self.assertEqual(model.next_step_list({}, {}, [], self.average, {"average_pick_score": None, "spread": 0.0}), ([], None))


if __name__ == "__main__":
    unittest.main()
