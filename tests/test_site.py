"""Checks for the tier list page (site/): files, settings, safety and the data it reads."""

import json
import html.parser
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

# The champion cards as they were when the saved scores copy and the brief numbers were made. The real cards can now
# be edited from the admin page, so tests that compare with those saved numbers read this frozen copy instead.
CARDS_SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cards_snapshot.json")


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


def table_html(table_id):
    """The HTML of one <table id="..."> on the page."""
    match = re.search(r'<table id="%s">(.*?)</table>' % table_id, read("index.html"), re.S)
    assert match, table_id
    return match.group(1)


RIOT_NOTICE = ("LoL Pick Lab is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games "
               "or anyone officially involved in producing or managing Riot Games properties. Riot Games and all "
               "associated properties are trademarks or registered trademarks of Riot Games, Inc")


class _Tree(html.parser.HTMLParser):
    """Remembers, for the legal notice paragraph, every ancestor tag with its attributes."""

    VOID = {"meta", "link", "br", "img", "input", "hr"}

    def __init__(self):
        super().__init__()
        self.stack, self.ancestors, self.text, self._in = [], None, "", False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "legal-notice":
            self.ancestors, self._in = list(self.stack), True
        if tag not in self.VOID:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1][1].get("id") == "legal-notice":
            self._in = False
        while self.stack and self.stack.pop()[0] != tag:
            pass

    def handle_data(self, data):
        if self._in:
            self.text += data


class LegalNoticeTests(unittest.TestCase):
    """Riot's rule: the legal notice must be readily visible to players, on every tab."""

    def test_notice_has_riots_exact_wording_with_our_product_name(self):
        tree = _Tree()
        tree.feed(read("index.html"))
        self.assertIsNotNone(tree.ancestors, "legal notice (id=legal-notice) is missing from the page")
        self.assertIn(RIOT_NOTICE, " ".join(tree.text.split()))

    def test_notice_is_outside_every_tab_and_never_hidden(self):
        tree = _Tree()
        tree.feed(read("index.html"))
        self.assertIsNotNone(tree.ancestors)
        for tag, attrs in tree.ancestors:
            self.assertNotIn("hidden", attrs, "the notice sits inside a hidden element")
            self.assertNotEqual(attrs.get("role"), "tabpanel", "the notice sits inside one tab only")
            self.assertNotIn("tabpanel", attrs.get("class", ""))
            self.assertNotEqual(attrs.get("id"), "content", "the notice would stay hidden until the scores load")
        self.assertEqual(len(re.findall(r'role="tab"', read("index.html"))), 4)   # the 4 tabs it must show under
        code = read("app.js")
        for word in ("legal-notice", "site-footer", "about-line"):
            self.assertNotIn(word, code)                          # the page code never hides or removes it
        self.assertNotRegex(read("style.css"), r"(sitefooter|#legal-notice)[^}]*display:\s*none")

    def test_about_line_is_in_the_footer(self):
        text = " ".join(re.sub(r"<[^>]+>", " ", read("index.html")).split())
        for phrase in ("free personal project", "no ads", "no payments", "no data sold",
                       "never show individual players", "Diamond+ ranked games"):
            self.assertIn(phrase, text)


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
                "comfort-table": "COMFORT_COLUMNS", "utopy-table": "UTOPY_COLUMNS"}
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
        self.assertRegex(text, r"SAMPLE_SIZE_LIMITS:\s*\{\s*low:\s*1000,\s*medium:\s*10000,\s*high:\s*30000\s*\}")


class TabTests(unittest.TestCase):
    def data_text(self):
        return read("data/latest.json")

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
        self.assertEqual(heads, ["champion", "comfort", "trait score &amp; traits", "mastery", "main type", "secondary type",
                                 "type pts", "mastery pts", "base", "kit adj.", "difficulty", "diff. adj.", "range adj.", "flexibility"])
        self.assertIn('"c_comfort"', read("app.js"))              # sorted by Comfort, highest first
        for word in ("<input", "<textarea", "<select", "contenteditable"):
            self.assertNotIn(word, read("index.html"))            # view only, no editing

    def test_growth_tab_is_only_the_utopy_table_and_there_is_no_ban_list(self):
        html = read("index.html")
        heads = [h.lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html("utopy-table"))]
        self.assertEqual(heads, ["champion", "never", "below avg", "avg", "good", "main", "skill pays off?"])
        for gone in ("Top upgrades", "Next step to A or S", "Could reach", 'id="growth-table"', 'id="next-table"', "Ceiling"):
            self.assertNotIn(gone, html)
        self.assertNotRegex(read("app.js") + read("format.js") + read("help.js"), r"growth_advisor|next_step|growthTip|GROWTH_COLUMNS|NEXT_COLUMNS")
        self.assertNotRegex(read("index.html") + read("app.js"), r"(?i)ban threat|ban suggestion|ban list")
        with open(os.path.join(ROOT, "scoring", "model.py"), encoding="utf-8") as f:
            self.assertNotRegex(f.read(), r"ban_threat|def ban_|ROLE_NAMES")      # the old ban code is gone
        self.assertNotIn("ban_threat_list", self.data_text())

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
        self.assertEqual((medium, high), (10000, 30000))             # v0.39: Low under 10,000, Medium 10,000-29,999, High 30,000+
        t = self.help["games"]
        self.assertIn("Low under {:,}".format(medium), t)
        self.assertIn("Medium {:,}\u2013{:,}".format(medium, high - 1), t)
        self.assertIn("High {:,}+".format(high), t)
        self.assertIn("needs {:,} to be ranked".format(config.MIN_REAL_GAMES), t)
        self.assertEqual(low, config.MIN_REAL_GAMES)                  # the ranking floor
        foot = read("index.html")
        self.assertIn("Low under {:,}, Medium {:,}&ndash;{:,}, High {:,}+".format(medium, medium, high - 1, high), foot)


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
        return {model.normalise(c["riot_name"]): c for c in comfort.load_cards(CARDS_SNAPSHOT)}

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
            self.assertEqual(row["comfort_parts"]["mastery_points"], config.MASTERY_POINTS[card["mastery"]])

    def test_the_page_reads_the_cards_file_which_is_a_copy_of_the_scoring_cards(self):
        with open(os.path.join(ROOT, "scoring", "cards.json"), encoding="utf-8") as f:
            original = json.load(f)
        self.assertEqual(json.loads(read("data/cards.json")), original)
        self.assertIn('CARDS_URL: "data/cards.json"', read("settings.js"))
        code = read("app.js")
        self.assertIn("F.applyCards(picks, cards)", code)           # type, traits, mastery from the cards, not the collector
        self.assertNotIn("card_info", read("../scoring/model.py"))   # nothing card-only is copied into the scores file any more

    def test_colored_box_steps_are_the_tier_steps(self):
        b = dict(config.TIER_BOUNDARIES)
        self.assertRegex(read("settings.js"), r"SPREAD_STEPS:\s*\{\s*mild:\s*%g,\s*strong:\s*%g\s*\}" % (b["A"], b["S"]))
        self.assertEqual(b["B"], -b["A"])
        self.assertEqual(b["C"], -b["S"])

    def test_the_page_shows_real_games_never_the_double_weight(self):
        for name in ("app.js", "format.js"):
            self.assertNotRegex(read(name), r"weighted|double_weight|doubled")
        code = read("app.js")
        self.assertEqual(code.count("F.games(c.real_games)"), 4)     # tier table, details, meta, needs a card
        for row in self.data["pick_score_list"]:
            self.assertEqual(row["real_games"], row["real_games_this_patch"] + row["real_games_last_patch"], row["name"])

    def test_utopy_table_matches_a_fresh_calculation_and_changes_no_score(self):
        """Every ranked champion has the 5 levels; each score and tier recomputes from the saved numbers."""
        cards = self.cards_by_name()
        tiers = self.data["tier_stats"]
        mean, spread = tiers["average_pick_score"], tiers["spread"]
        table = {r["id"]: r for r in self.data["utopy_table"]}
        ranked = {r["id"]: r for r in self.data["pick_score_list"]}
        self.assertEqual(set(table), set(ranked))
        for cid, row in table.items():
            champ = ranked[cid]
            card = cards[model.normalise(champ["riot_name"])]
            self.assertEqual(set(row["scores"]), set(config.MASTERY_ORDER))      # the file's keys are sorted
            self.assertEqual(row["current_mastery"], champ["mastery"])
            for level in config.MASTERY_ORDER:
                c = comfort.comfort(card, self.data["trait_average"], level)["comfort"]
                score = config.WEIGHT_STATS * champ["stats"] + config.WEIGHT_COMFORT * c + config.WEIGHT_OTP * champ["otp_points"]
                self.assertAlmostEqual(row["scores"][level]["score"], score, delta=0.02)
                self.assertEqual(row["scores"][level]["tier"], model.tier_of(model.spreads_from_average(score, mean, spread)))
            self.assertAlmostEqual(row["scores"][champ["mastery"]]["score"], champ["pick_score"], delta=0.02)
        for row in self.data["pick_score_list"]:      # information only: every Pick Score is still exactly the recipe
            self.assertAlmostEqual(row["pick_score"], config.WEIGHT_STATS * row["stats"] + config.WEIGHT_COMFORT * row["comfort"]
                                   + config.WEIGHT_OTP * row["otp_points"], delta=0.02)
        self.assertNotIn("utopy_list", self.data)
        self.assertNotIn("utopy_closest", self.data)

    def test_unranked_carded_champions_have_what_the_grey_rows_show(self):
        for r in self.data["cards_not_ranked"]:
            for key in ("name", "mastery", "real_games", "real_games_this_patch", "pick_rate", "failed"):
                self.assertIn(key, r, r["name"])
            self.assertNotIn(r["name"], [x["name"] for x in self.data["pick_score_list"]])

    def test_utopy_table_is_the_growth_tab_with_its_new_look(self):
        html = read("index.html")
        growth = html[html.index('id="tab-growth"'):]
        for text in ("Utopy table", "if I mained everyone", 'id="utopy-basis"', 'id="utopy-legend"', "Skill pays off"):
            self.assertIn(text, growth)
        self.assertNotIn("Utopy picks", growth)
        self.assertNotIn("Steps away", growth)
        for tier in "SABCD":                                            # the tier color legend, with a hover for each
            self.assertIn('class="tier tier-%s" data-tip-key="tier_%s"' % (tier, tier), growth)
        app, css = read("app.js"), read("style.css")
        self.assertIn("Based on patch", app)
        self.assertIn("can change each patch", app)
        self.assertIn('"u_main"', app)                                  # opens sorted by the Main column
        self.assertIn("utopy-grey", app)                                # unranked rows are grey, at the bottom
        self.assertIn("utopy-now", app)                                 # the current level has the ring
        self.assertIn("utopy-up", app)                                  # the up arrow
        self.assertIn("i > here", app)                                  # ... only above the current level
        self.assertIn("state.third", app)                               # ... when the score beats the current #3 pick
        self.assertIn("skill-pos", app)
        self.assertIn("skill-neg", app)
        self.assertIn("sampleLabel", app)                               # sample size under the name, like the Tier list
        self.assertIn("dataChip", app)                                  # data-freshness chip, like the Tier list
        self.assertNotIn("utopy_list", app + read("format.js"))
        # one ring that shows on every tier color: two tones, not a single outline
        ring = re.search(r"\.utopy-now \{[^}]*\}", css).group(0)
        self.assertIn("box-shadow", ring)
        self.assertNotIn("outline", ring)
        self.assertRegex(css, r"#utopy-table \.u-score \{ width: \d+px")        # all 5 score columns the same fixed width
        self.assertIn("table-layout: fixed", css)
        self.assertRegex(css, r"#utopy-wrap \{ overflow-x: auto")                # sideways scroll on a phone

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
                    "otp_points", "win_rate_delta", "real_games", "pick_score", "comfort", "comfort_parts",
                    "otp_delta", "otp_win_rate", "needs_a_card", "meta_score_list", "utopy_table",
                    "pick_score_at_main", "best_tier_at_main"):
            self.assertIn('"%s"' % key, source)


class MasteryReviewTests(unittest.TestCase):
    """v0.42: the "last mastery review" reminder lives on the Comfort tab only, with one setting next to the cards."""

    def test_one_setting_next_to_the_cards_and_the_page_copy_matches(self):
        with open(os.path.join(ROOT, "scoring", "review.json"), encoding="utf-8") as f:
            original = json.load(f)
        self.assertEqual(original, {"last_mastery_review_patch": "16.20"})
        self.assertEqual(json.loads(read("data/review.json")), original)
        self.assertIn('REVIEW_URL: "data/review.json"', read("settings.js"))
        for code in ("app.js", "format.js"):                    # the value is never written into the page code
            self.assertNotIn("last_mastery_review_patch", read(code).replace("file.last_mastery_review_patch", ""))
        scoring_code = ""
        for name in ("model.py", "comfort.py", "config.py"):
            with open(os.path.join(ROOT, "scoring", name), encoding="utf-8") as f:
                scoring_code += f.read()
        self.assertNotIn("mastery_review", scoring_code)      # no score can depend on it

    def test_the_line_is_only_on_the_comfort_tab(self):
        html = read("index.html")
        self.assertEqual(html.count('id="mastery-review"'), 1)
        panels = dict(re.findall(r'<section id="tab-(\w+)".*?>(.*?)</section>', html, re.S))
        self.assertIn('id="mastery-review"', panels["comfort"])
        for other in ("tier", "meta", "growth"):
            self.assertNotIn("mastery-review", panels[other])
            self.assertNotIn("mastery review", panels[other].lower())
        self.assertIn('data-tip-key="mastery_review"', panels["comfort"])

    def test_hover_help_text(self):
        help_text = read("help.js")
        self.assertIn("Review your mastery levels every 5", help_text)
        self.assertIn("mastery review done on patch X", help_text)
        self.assertIn("review button on the admin page", help_text)
        self.assertNotIn("coming later", help_text)
        self.assertNotIn("/admin", help_text)                  # the address stays hidden
        self.assertIn("Editing cards never resets", help_text)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class SiteFormatTests(unittest.TestCase):
    def test_javascript_helpers(self):
        result = subprocess.run(["node", "--test", os.path.join(ROOT, "tests", "site_format.test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
