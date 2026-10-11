"""Checks for the tier list page (site/): files, settings, safety and the data it reads."""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SITE_FILES = ["index.html", "style.css", "app.js", "format.js", "help.js", "settings.js", "data/latest.json"]
COLUMNS = ["rank", "champion", "tier", "Pick Score", "Comfort", "Stats", "OTP", "Win rate", "vs average", "Games"]


sys.path.insert(0, ROOT)
from scoring import comfort, config, model   # noqa: E402


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


def table_html(table_id):
    """The HTML of one <table id="..."> on the page."""
    match = re.search(r'<table id="%s">(.*?)</table>' % table_id, read("index.html"), re.S)
    assert match, table_id
    return match.group(1)


class SiteFilesTests(unittest.TestCase):
    def test_files_exist(self):
        for name in SITE_FILES:
            self.assertTrue(os.path.exists(os.path.join(SITE, name)), name)

    def test_page_has_the_columns_and_header_facts(self):
        html = read("index.html")
        headers = re.findall(r"<th[^>]*>(.*?)</th>", table_html("tier-table"))
        self.assertEqual([h.lower() for h in headers],
                         [c.lower() if c != "rank" else "#" for c in COLUMNS])
        for element_id in ("patch", "updated"):
            self.assertIn('id="%s"' % element_id, html)
        self.assertIn("Last updated", html)

    def test_page_is_english_and_plain_files(self):
        html = read("index.html")
        self.assertIn('<html lang="en">', html)
        scripts = re.findall(r'<script src="([^"]+)"', html)
        self.assertEqual(scripts, ["settings.js", "format.js", "help.js", "app.js"])
        self.assertNotIn("http", " ".join(scripts))      # no outside scripts

    def test_every_tier_has_its_own_color(self):
        css = read("style.css")
        colors = {}
        for tier in "SABCD":
            match = re.search(r"\.tier-%s\s*\{\s*background:\s*([^;]+);" % tier, css)
            self.assertIsNotNone(match, tier)
            colors[tier] = match.group(1).strip()
        self.assertEqual(len(set(colors.values())), 5)

    def test_every_column_can_be_sorted(self):
        keys = re.findall(r'<th[^>]*data-sort="([^"]+)"', table_html("tier-table"))
        self.assertEqual(len(keys), len(COLUMNS))
        for key in keys:
            self.assertIn("%s:" % key, read("format.js"))

    def test_every_column_of_every_tab_can_be_sorted(self):
        """Every sortable title in every table has a matching entry in format.js, in that table's own column set."""
        source = read("format.js")
        sets = {"tier-table": "SORT_COLUMNS", "meta-table": "META_COLUMNS", "needs-table": "META_COLUMNS",
                "comfort-table": "COMFORT_COLUMNS", "growth-table": "GROWTH_COLUMNS"}
        for table, name in sets.items():
            block = re.search(r"var %s = \{(.*?)\n  \};" % name, source, re.S).group(1)
            keys = re.findall(r'data-sort="([^"]+)"', table_html(table))
            self.assertGreater(len(keys), 4, table)
            for key in keys:
                self.assertRegex(block, r"(^|\n)\s+%s:" % key, "%s: %s" % (table, key))

    def test_the_page_does_not_remember_the_sort(self):
        code = read("app.js") + read("format.js")
        for word in ("localStorage", "sessionStorage", "document.cookie", "location.hash"):
            self.assertNotIn(word, code)

    def test_page_opens_sorted_by_pick_score_and_has_the_not_ranked_line(self):
        self.assertIn('sortableTable("tier-table", F.SORT_COLUMNS, "pick_score"', read("app.js"))
        self.assertIn("Carded but not ranked", read("index.html"))

    def test_sample_size_limits_are_in_settings(self):
        text = read("settings.js")
        self.assertRegex(text, r"SAMPLE_SIZE_LIMITS:\s*\{\s*low:\s*1000,\s*medium:\s*3000,\s*high:\s*10000\s*\}")


class TabTests(unittest.TestCase):
    """Slice 3: four tabs, the page opens on the Tier list, tabs are plain buttons (no addresses, nothing remembered)."""

    def test_four_tabs_in_order_and_tier_list_is_open_first(self):
        html = read("index.html")
        buttons = re.findall(r'<button[^>]*role="tab"[^>]*data-tab="(\w+)"[^>]*aria-selected="(\w+)"[^>]*>([^<]+)</button>', html)
        self.assertEqual([(b[0], b[2]) for b in buttons],
                         [("tier", "Tier list"), ("meta", "Meta"), ("comfort", "Comfort"), ("growth", "Growth")])
        self.assertEqual([b[1] for b in buttons], ["true", "false", "false", "false"])
        panels = re.findall(r'<section id="tab-(\w+)" class="tabpanel"[^>]*?( hidden)?>', html)
        self.assertEqual([p[0] for p in panels], ["tier", "meta", "comfort", "growth"])
        self.assertEqual([bool(p[1]) for p in panels], [False, True, True, True])

    def test_tier_list_tab_keeps_its_columns_and_not_ranked_line(self):
        self.assertIn("Carded but not ranked", read("index.html"))
        self.assertIn('"pick_score"', read("app.js"))

    def test_meta_tab_has_the_needs_a_card_list_and_the_columns_asked_for(self):
        html = read("index.html")
        self.assertIn("Needs a card", html)
        heads = [h.lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html("meta-table"))]
        self.assertEqual(heads, ["#", "champion", "meta score", "win rate pts", "pick rate pts", "win rate",
                                 "vs average", "pick rate", "games"])
        self.assertIn("no card yet", read("app.js"))

    def test_comfort_tab_has_every_column_asked_for(self):
        heads = [h.lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html("comfort-table"))]
        self.assertEqual(heads, ["#", "champion", "main type", "secondary type", "type pts", "mastery", "base",
                                 "trait score", "kit adj.", "difficulty", "diff. adj.", "range adj.", "flexibility", "comfort"])
        for word in ("<input", "<textarea", "<select", "contenteditable"):
            self.assertNotIn(word, read("index.html"))            # view only, no editing

    def test_growth_tab_has_the_skill_column_and_no_ban_list(self):
        heads = [h.lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html("growth-table"))]
        self.assertIn("skill pays off?", heads)
        self.assertIn("gain", heads)
        self.assertNotRegex(read("index.html") + read("app.js"), r"(?i)ban threat|ban suggestion|ban list")

    def test_tabs_are_not_remembered_and_the_tooltip_is_instant(self):
        code = read("app.js")
        for word in ("localStorage", "sessionStorage", "document.cookie", "location.hash"):
            self.assertNotIn(word, code)
        self.assertIn('id="tip"', read("index.html"))
        self.assertIn('"mouseover"', code)          # custom tooltip, shown at once
        self.assertNotRegex(code, r"\.title\s*=")        # no slow built-in browser tooltips

    def test_otp_minimum_is_one_setting(self):
        self.assertRegex(read("settings.js"), r"OTP_MIN_GAMES_SHOWN:\s*20\b")
        for name in ("app.js", "format.js"):
            self.assertNotRegex(read(name), r">=\s*20\b")      # the page code never writes the 20 itself
            self.assertNotIn("OTP_MIN_GAMES_SHOWN", read(name) if name == "format.js" else "")
        self.assertIn("S.OTP_MIN_GAMES_SHOWN", read("app.js"))


def help_texts():
    """The hover texts in site/help.js, as {column key: text}. Symbols are written as plain characters."""
    found = re.findall(r'^\s{4}(\w+):\s*"((?:[^"\\]|\\.)*)"', read("help.js"), re.M)
    return {key: text for key, text in found}


def num(text):
    return float(text.replace(",", ""))


class HoverHelpTests(unittest.TestCase):
    def setUp(self):
        self.help = help_texts()

    def test_every_column_title_has_a_short_text(self):
        keys = re.findall(r'<th[^>]*data-sort="([^"]+)"', read("index.html"))
        self.assertGreater(len(set(keys)), 30)                      # all four tabs
        for key in keys:
            self.assertIn(key, self.help, key)
            self.assertGreater(len(self.help[key]), 20, key)
            self.assertLess(len(self.help[key]), 330, key)          # 1-2 plain lines

    def test_pick_score_weights_match_the_scoring_code(self):
        t = self.help["pick_score"]
        got = [float(x) for x in re.findall(r"([\d.]+) \u00d7 (?:Stats|Comfort|OTP)", t)]
        self.assertEqual(got, [config.WEIGHT_STATS, config.WEIGHT_COMFORT, config.WEIGHT_OTP])
        percents = [float(x) for x in re.findall(r"([\d.]+)%", t)]
        self.assertEqual(percents, [round(100 * w, 1) for w in (config.WEIGHT_STATS, config.WEIGHT_COMFORT, config.WEIGHT_OTP)])

    def test_weights_in_the_other_texts_match_too(self):
        pct = lambda w: "%g%%" % round(100 * w, 1)
        self.assertIn("Worth " + pct(config.WEIGHT_COMFORT) + " of the Pick Score", self.help["comfort"])
        self.assertIn("Worth " + pct(config.WEIGHT_STATS) + " of the Pick Score", self.help["stats"])
        self.assertIn("Worth " + pct(config.WEIGHT_OTP) + " of the Pick Score", self.help["otp"])
        self.assertIn("%s win rate points and %s pick rate" % (pct(config.STATS_WIN_RATE_SHARE), pct(config.STATS_PICK_RATE_SHARE)),
                      self.help["stats"])
        self.assertIn("(%s of Stats)" % pct(config.STATS_WIN_RATE_SHARE), self.help["win_rate"])
        self.assertIn("moves the win rate points in Stats by %g" % config.WIN_RATE_POINTS_PER_PERCENT, self.help["vs_average"])

    def test_tier_cutoffs_and_warning_match_the_scoring_code(self):
        t = self.help["tier"]
        b = dict(config.TIER_BOUNDARIES)
        self.assertIn("S +%g or more" % b["S"], t)
        self.assertIn("A +%g to +%g" % (b["A"], b["S"]), t)
        self.assertIn("B -%g to +%g" % (-b["B"], b["A"]), t)
        self.assertIn("C -%g to -%g" % (-b["C"], -b["B"]), t)
        self.assertIn("D below -%g" % -b["C"], t)
        self.assertIn("%g points or more below" % -config.WIN_RATE_WARNING_DELTA, self.help["win_rate"])

    def test_sample_size_limits_match_settings(self):
        limits = [int(x) for x in re.findall(r"(\d+)", re.search(r"SAMPLE_SIZE_LIMITS:\s*\{(.*?)\}", read("settings.js")).group(1))]
        low, medium, high = limits
        t = self.help["games"]
        self.assertIn("Low {:,}\u2013{:,}".format(low, medium - 1), t)
        self.assertIn("Medium {:,}\u2013{:,}".format(medium, high - 1), t)
        self.assertIn("High {:,}+".format(high), t)
        self.assertIn("needs {:,} to be ranked".format(config.MIN_REAL_GAMES), t)


    def test_every_tab_and_heading_has_a_text(self):
        for key in re.findall(r'data-tip-key="([^"]+)"', read("index.html")):
            self.assertIn(key, self.help, key)
            self.assertGreater(len(self.help[key]), 20, key)

    def test_the_help_file_says_v0_37(self):
        self.assertIn("currently v0.37", read("help.js"))
        self.assertEqual(config.MODEL_VERSION, "v0.37")

    def test_new_texts_match_the_v0_37_numbers(self):
        h = self.help
        pct = lambda w: "%g%%" % round(100 * w, 1)
        # Meta tab
        self.assertIn("%s win rate points + %s pick rate" % (pct(config.STATS_WIN_RATE_SHARE), pct(config.STATS_PICK_RATE_SHARE)), h["meta_score"])
        self.assertIn("%g more for every point" % config.WIN_RATE_POINTS_PER_PERCENT, h["wr_points"])
        self.assertIn("Worth %s of Meta Score" % pct(config.STATS_WIN_RATE_SHARE), h["wr_points"])
        self.assertIn("Worth %s of Meta Score" % pct(config.STATS_PICK_RATE_SHARE), h["pr_points"])
        self.assertIn("Needs %s to be ranked" % pct(config.MIN_PICK_RATE), h["pick_rate"])
        self.assertIn("Worth %s of the Pick Score" % pct(config.WEIGHT_COMFORT), h["c_comfort"])
        self.assertIn(pct(config.WEIGHT_STATS), h["tab_tier"])
        self.assertIn(pct(config.WEIGHT_COMFORT), h["tab_tier"])
        self.assertIn(pct(config.WEIGHT_OTP), h["tab_tier"])
        # Comfort tab
        self.assertIn("Worth %s of the base" % pct(config.COMFORT_TYPE_SHARE), h["type_points"])
        self.assertIn("Worth %s of the base" % pct(config.COMFORT_MASTERY_SHARE), h["c_mastery"])
        self.assertIn("%s type points + %s mastery points" % (pct(config.COMFORT_TYPE_SHARE), pct(config.COMFORT_MASTERY_SHARE)), h["base"])
        self.assertIn("High 100%, Mid 97.5%, Low 95%", h["main_type"])
        self.assertEqual([config.STRENGTH[k] for k in ("high", "mid", "low")], [1.0, 0.975, 0.95])
        self.assertIn("20% of the gap", h["secondary_type"])
        self.assertEqual(config.SECONDARY_SHARE, 0.20)
        self.assertEqual(config.TYPE_POINTS, {"mobility": 100, "peel": 90, "hypercarry": 80, "utility": 80, "mage": 70, "lane_bully": 70})
        self.assertIn("Mobility 100, Peel 90, Hypercarry and Utility 80, Mage and Lane bully 70", h["type_points"])
        self.assertIn("Main 100, Good 90, Average 80, Below average 70, Never played 60", h["c_mastery"])
        self.assertEqual([config.MASTERY_POINTS[k] for k in ("main", "good", "average", "below_average", "never_played")], [100, 90, 80, 70, 60])
        self.assertIn("0.9 × (trait score", h["kit_adj"])
        self.assertIn("at most ±%g" % config.KIT_CAP, h["kit_adj"])
        self.assertIn("−%g × (difficulty − %g)" % (config.DIFFICULTY_WEIGHT, config.DIFFICULTY_MIDDLE), h["diff_adj"])
        self.assertIn("at most ±%g" % config.DIFFICULTY_CAP, h["diff_adj"])
        self.assertIn("80% yours + 20% Riot's", h["difficulty"])
        self.assertEqual((config.DIFFICULTY_MINE_SHARE, config.DIFFICULTY_RIOT_SHARE), (0.8, 0.2))
        self.assertIn("Short range −%g, Medium 0, Long +%g" % (-config.RANGE_ADJUSTMENT["short"], config.RANGE_ADJUSTMENT["long"]), h["range_adj"])
        self.assertIn("+%g × the mastery" % config.FLEXIBILITY_BONUS, h["flex"])
        self.assertIn("Main 20%% up to Never played %d%%" % (100 * config.MASTERY_DIFFICULTY_FACTOR["never_played"]), h["diff_adj"])
        self.assertEqual(config.MASTERY_DIFFICULTY_FACTOR["main"], 0.20)
        # Growth tab
        minimum = int(re.search(r"OTP_MIN_GAMES_SHOWN:\s*(\d+)", read("settings.js")).group(1))
        self.assertIn("%d or more bot-lane OTP games" % minimum, h["g_skill"])
        self.assertIn("#3", h["g_score"])
        self.assertEqual(config.GROWTH_BEAT_RANK, 3)
        self.assertIn("Never played and Below average are scored as Good", h["g_mastery"])
        self.assertEqual(config.GROWTH_TARGET, {"never_played": "good", "below_average": "good", "average": "good", "good": "main"})


class SiteSafetyTests(unittest.TestCase):
    def test_no_riot_api_calls_and_no_keys_anywhere_in_site(self):
        bad = [r"api\.riotgames\.com", r"RGAPI-", r"X-Riot-Token", r"RIOT_API_KEY", r"api_key", r"apikey", r"process\.env"]
        for folder, _, names in os.walk(SITE):
            for name in names:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                    text = f.read()
                for pattern in bad:
                    self.assertIsNone(re.search(pattern, text, re.I), "%s has %s" % (name, pattern))

    def test_page_only_reads_the_scores_file_from_this_repository(self):
        urls = re.findall(r"https?://[^\s\"']+", read("settings.js") + read("app.js") + read("index.html"))
        for url in urls:
            self.assertTrue(url.startswith("https://raw.githubusercontent.com/kinobaihu-design/lol-pick-lab/data/scores/"), url)


class SiteDataTests(unittest.TestCase):
    """The saved copy has to look like the real scoring output, because the page reads both the same way."""

    def setUp(self):
        self.data = json.loads(read("data/latest.json"))

    def test_header_fields(self):
        for key in ("patch", "generated", "diamond_plus_average_win_rate", "pick_score_list"):
            self.assertIn(key, self.data)
        self.assertRegex(self.data["generated"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_every_row_has_what_the_table_shows(self):
        keys = ["name", "tier", "win_rate_warning", "mastery", "traits", "data_label", "otp_players", "otp_games",
                "pick_score", "comfort", "stats", "otp_points", "win_rate", "win_rate_delta", "real_games"]
        self.assertGreater(len(self.data["pick_score_list"]), 0)
        for row in self.data["pick_score_list"]:
            for key in keys:
                self.assertIn(key, row, "%s is missing %s" % (row.get("name"), key))
            self.assertIn(row["tier"], "SABCD")
            self.assertNotIn("tier_capped_by_floor", row)

    def test_no_champion_has_a_win_rate_warning_that_disagrees_with_the_number(self):
        for row in self.data["pick_score_list"]:
            self.assertEqual(row["win_rate_warning"], row["win_rate_delta"] <= -1.5, row["name"])

    def test_cards_not_ranked_say_why(self):
        for entry in self.data["cards_not_ranked"]:
            self.assertTrue(entry["failed"], entry["name"])

    def cards_by_name(self):
        return {model.normalise(c["riot_name"]): c for c in comfort.load_cards()}

    def test_comfort_tab_numbers_are_the_ones_the_pick_score_uses(self):
        """Every number on the Comfort tab is read from the file; recompute each with the Comfort code and compare."""
        cards = self.cards_by_name()
        average = self.data["trait_average"]
        w = config
        for row in self.data["pick_score_list"]:
            card = cards[model.normalise(row["riot_name"])]
            again = comfort.comfort(card, average)
            for key, value in again.items():
                if isinstance(value, float) or isinstance(value, int):
                    self.assertAlmostEqual(row["comfort_parts"][key], value, delta=0.01, msg="%s %s" % (row["name"], key))
            self.assertAlmostEqual(row["comfort"], again["comfort"], delta=0.01, msg=row["name"])
            # the Pick Score is built from exactly this Comfort number
            expected = w.WEIGHT_STATS * row["stats"] + w.WEIGHT_COMFORT * row["comfort"] + w.WEIGHT_OTP * row["otp_points"]
            self.assertAlmostEqual(row["pick_score"], expected, delta=0.02, msg=row["name"])
            # the type, difficulty and range columns come from the card
            info = row["card_info"]
            self.assertEqual(info["main_strength"], card["main_strength"])
            self.assertEqual(info["secondary_types"], card.get("secondary_types", []))
            self.assertEqual((info["difficulty_riot"], info["difficulty_mine"]), (card["difficulty"]["riot"], card["difficulty"]["mine"]))
            self.assertEqual(info["range"], card["range"])
            self.assertEqual(row["main_type"], card["main_type"])
            self.assertEqual(row["comfort_parts"]["mastery_points"], config.MASTERY_POINTS[card["mastery"]])

    def test_growth_tips_follow_the_number_3_rule(self):
        """A tip exists exactly when the target-mastery Pick Score beats both the champion's own score and the current #3 pick."""
        cards = self.cards_by_name()
        rows = self.data["pick_score_list"]
        third = sorted((r["pick_score"] for r in rows), reverse=True)[config.GROWTH_BEAT_RANK - 1]
        tips = {t["id"]: t for t in self.data["growth_advisor"]}
        for row in rows:
            if row["mastery"] == "main":
                self.assertNotIn(row["id"], tips, row["name"])
                continue
            target = config.GROWTH_TARGET[row["mastery"]]
            new_comfort = comfort.comfort(cards[model.normalise(row["riot_name"])], self.data["trait_average"], target)["comfort"]
            after = config.WEIGHT_STATS * row["stats"] + config.WEIGHT_COMFORT * new_comfort + config.WEIGHT_OTP * row["otp_points"]
            should = after > third + 0.02 and after > row["pick_score"]
            if abs(after - third) < 0.02:
                continue                                    # too close to call after rounding
            self.assertEqual(row["id"] in tips, should, "%s: %.2f vs #3 %.2f" % (row["name"], after, third))
            if should:
                self.assertAlmostEqual(tips[row["id"]]["pick_score_at_target"], after, delta=0.02)
                self.assertAlmostEqual(tips[row["id"]]["gain"], after - row["pick_score"], delta=0.03)
        for tip in tips.values():
            self.assertGreater(tip["pick_score_at_target"], third)
            self.assertIn(tip["kind"], ("Upgrade", "New champion"))
            self.assertEqual(tip["kind"] == "New champion", tip["current_mastery"] == "never_played")

    def test_growth_tips_do_not_change_any_score(self):
        """The skill-pays-off line reads the OTP numbers; the Pick Score still uses only the OTP points."""
        for row in self.data["pick_score_list"]:
            expected = (config.WEIGHT_STATS * row["stats"] + config.WEIGHT_COMFORT * row["comfort"]
                        + config.WEIGHT_OTP * row["otp_points"])
            self.assertAlmostEqual(row["pick_score"], expected, delta=0.02)

    def test_the_scoring_code_still_writes_those_fields(self):
        """If the scoring code stops writing a field, the page would show gaps; catch it here."""
        with open(os.path.join(ROOT, "scoring", "model.py"), encoding="utf-8") as f:
            source = f.read()
        for key in ("win_rate_warning", "mastery", "traits", "data_label", "otp_players", "otp_games", "cards_not_ranked",
                    "otp_points", "win_rate_delta", "real_games", "pick_score", "comfort", "card_info", "comfort_parts",
                    "otp_delta", "otp_win_rate", "needs_a_card", "meta_score_list", "growth_advisor"):
            self.assertIn('"%s"' % key, source)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class SiteFormatTests(unittest.TestCase):
    def test_javascript_helpers(self):
        result = subprocess.run(["node", "--test", os.path.join(ROOT, "tests", "site_format.test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
