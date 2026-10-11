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
from scoring import config   # noqa: E402


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


class SiteFilesTests(unittest.TestCase):
    def test_files_exist(self):
        for name in SITE_FILES:
            self.assertTrue(os.path.exists(os.path.join(SITE, name)), name)

    def test_page_has_the_columns_and_header_facts(self):
        html = read("index.html")
        headers = re.findall(r"<th[^>]*>(.*?)</th>", html)
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
        html = read("index.html")
        keys = re.findall(r'<th[^>]*data-sort="([^"]+)"', html)
        self.assertEqual(len(keys), len(COLUMNS))
        for key in keys:
            self.assertIn("%s:" % key, read("format.js"))

    def test_the_page_does_not_remember_the_sort(self):
        code = read("app.js") + read("format.js")
        for word in ("localStorage", "sessionStorage", "document.cookie", "location.hash"):
            self.assertNotIn(word, code)

    def test_page_opens_sorted_by_pick_score_and_has_the_not_ranked_line(self):
        self.assertIn('key: "pick_score", dir: "desc"', read("app.js"))
        self.assertIn("Carded but not ranked", read("index.html"))

    def test_sample_size_limits_are_in_settings(self):
        text = read("settings.js")
        self.assertRegex(text, r"SAMPLE_SIZE_LIMITS:\s*\{\s*low:\s*1000,\s*medium:\s*3000,\s*high:\s*10000\s*\}")


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

    def test_the_scoring_code_still_writes_those_fields(self):
        """If the scoring code stops writing a field, the page would show gaps; catch it here."""
        with open(os.path.join(ROOT, "scoring", "model.py"), encoding="utf-8") as f:
            source = f.read()
        for key in ("win_rate_warning", "mastery", "traits", "data_label", "otp_players", "otp_games", "cards_not_ranked",
                    "otp_points", "win_rate_delta", "real_games", "pick_score", "comfort"):
            self.assertIn('"%s"' % key, source)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class SiteFormatTests(unittest.TestCase):
    def test_javascript_helpers(self):
        result = subprocess.run(["node", "--test", os.path.join(ROOT, "tests", "site_format.test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
