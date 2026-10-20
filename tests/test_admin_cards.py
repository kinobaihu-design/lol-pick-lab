"""Admin page slice 2 (card editing): preview maths, the helper, the quick rescore and the files around them."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from collector import main as collector_main     # noqa: E402
from scoring import comfort, config, model       # noqa: E402
from scoring.__main__ import kept_time, main as scoring_main   # noqa: E402
from test_scoring import champ, make_patch, write   # noqa: E402

CARDS_FILE = os.path.join(ROOT, "scoring", "cards.json")
NODE = shutil.which("node")
TRAITS = list(config.TRAIT_PRIORITY)
LEVELS = ["none", "low", "mid", "high"]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def node(payload):
    result = subprocess.run([NODE, os.path.join(ROOT, "tests", "card_driver.js")], input=json.dumps(payload),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout)


def python_average(cards, ranked):
    """The trait average the scoring uses (scoring/model.py), for the given set of ranked champions."""
    keys = {model.normalise(n) for n in ranked}
    scores = [comfort.trait_score(c) for c in cards if model.normalise(c["riot_name"]) in keys]
    if len(scores) >= config.MIN_CARDS_FOR_TRAIT_AVERAGE:
        return sum(scores) / len(scores)
    return comfort.average_trait_score(cards)


def with_change(card, field, value):
    card = json.loads(json.dumps(card))
    if field == "mastery":
        card["mastery"] = value
    elif value == "none":
        card["traits"].pop(field, None)
    else:
        card["traits"][field] = value
    return card


@unittest.skipUnless(NODE, "Node is not installed")
class PreviewMatchesTheScoringCodeTests(unittest.TestCase):
    """The admin page's preview maths (site/comfort-preview.js) must equal the real scoring code."""

    @classmethod
    def setUpClass(cls):
        cls.cards = comfort.load_cards(CARDS_FILE)
        # Most cards count as "ranked" (as on the live page); a few do not, so both kinds of card are tested.
        cls.ranked = [c["riot_name"] for c in cls.cards[:-4]]

    def test_the_constants_are_the_same(self):
        js = node({"mode": "config"})
        for key, value in js.items():
            self.assertEqual(value, getattr(config, key), key)

    def test_every_card_with_every_possible_single_change(self):
        scenarios = []
        for card in self.cards:
            for m in config.MASTERY_ORDER:
                if m != card["mastery"]:
                    scenarios.append({"name": card["name"], "changes": [{"field": "mastery", "value": m}]})
            for trait in TRAITS:
                now = card["traits"].get(trait, "none")
                for level in LEVELS:
                    if level != now:
                        scenarios.append({"name": card["name"], "changes": [{"field": trait, "value": level}]})
        self.assertGreater(len(scenarios), 1000)
        self.compare(scenarios)

    def test_several_changes_at_once_caps_and_varus_flexibility(self):
        scenarios = [
            {"name": "Varus", "changes": [{"field": "mastery", "value": m}]} for m in config.MASTERY_ORDER[:-1] + ["main"]
        ] + [
            {"name": "Hwei", "changes": [{"field": "wave_clear", "value": "none"}, {"field": "cc", "value": "low"}, {"field": "mastery", "value": "never_played"}]},
            {"name": "Vayne", "changes": [{"field": t, "value": "none"} for t in TRAITS]},
            {"name": "Hwei", "changes": [{"field": t, "value": "high"} for t in TRAITS]},
            {"name": "Sivir", "changes": [{"field": "cc", "value": "high"}, {"field": "vision", "value": "high"}]},
        ]
        results = self.compare(scenarios)
        # The caps really are hit by these scenarios (so the test means something)
        self.assertEqual(comfort.comfort(with_change(next(c for c in self.cards if c["name"] == "Hwei"), "cc", "high"), 5.0)["kit_adjustment"], 5.0)
        self.assertGreater(len(results), 5)

    def test_batch_preview_matches_the_scoring_code(self):
        """Several pending changes at once (Save all): trait average and every changed champion's Comfort."""
        batches = [
            [{"champion": "Jinx", "field": "mastery", "value": "main"}],
            [{"champion": "Jinx", "field": "mastery", "value": "main"}, {"champion": "Sivir", "field": "aoe", "value": "mid"},
             {"champion": "Sivir", "field": "cc", "value": "low"}, {"champion": "Hwei", "field": "wave_clear", "value": "none"}],
            [{"champion": "Vayne", "field": t, "value": "none"} for t in TRAITS],
            [{"champion": "Hwei", "field": t, "value": "high"} for t in TRAITS] + [{"champion": "Ashe", "field": "mastery", "value": "never_played"}],
            [{"champion": "Varus", "field": "mastery", "value": "main"}],
        ]
        for ranked in (self.ranked, [], ["Jinx", "Sivir"]):
            got = node({"mode": "batch", "cards": self.cards, "ranked": ranked, "batches": batches})
            for batch, result in zip(batches, got):
                after = [dict(c) for c in self.cards]
                for change in batch:
                    index = next(i for i, c in enumerate(after) if c["name"] == change["champion"])
                    after[index] = with_change(after[index], change["field"], change["value"])
                before_avg, after_avg = python_average(self.cards, ranked), python_average(after, ranked)
                self.assertAlmostEqual(result["traitAverageBefore"], before_avg, places=9)
                self.assertAlmostEqual(result["traitAverageAfter"], after_avg, places=9)
                names = {c["champion"] for c in batch}
                self.assertEqual(set(result["byChampion"]), names)
                for name in names:
                    old = next(c for c in self.cards if c["name"] == name)
                    new = next(c for c in after if c["name"] == name)
                    self.assertAlmostEqual(result["byChampion"][name]["before"], comfort.comfort(old, before_avg)["comfort"], places=9)
                    self.assertAlmostEqual(result["byChampion"][name]["after"], comfort.comfort(new, after_avg)["comfort"], places=9)

    def test_with_few_ranked_champions_the_average_of_all_cards_is_used(self):
        scenarios = [{"name": "Jinx", "changes": [{"field": "cc", "value": "none"}]}]
        for ranked in ([], ["Jinx", "Sivir"], [c["riot_name"] for c in self.cards[:9]]):
            self.compare(scenarios, ranked)

    def compare(self, scenarios, ranked=None):
        ranked = self.ranked if ranked is None else ranked
        js = node({"mode": "preview", "cards": self.cards, "ranked": ranked, "scenarios": scenarios})
        for scenario, got in zip(scenarios, js):
            card = next(c for c in self.cards if c["name"] == scenario["name"])
            edited = card
            for change in scenario["changes"]:
                edited = with_change(edited, change["field"], change["value"])
            after_cards = [edited if c["name"] == card["name"] else c for c in self.cards]
            before = comfort.comfort(card, python_average(self.cards, ranked))["comfort"]
            after = comfort.comfort(edited, python_average(after_cards, ranked))["comfort"]
            label = "%s %s" % (scenario["name"], scenario["changes"])
            self.assertAlmostEqual(got["comfortBefore"], before, places=9, msg=label)
            self.assertAlmostEqual(got["comfortAfter"], after, places=9, msg=label)
            self.assertAlmostEqual(got["traitAverageBefore"], python_average(self.cards, ranked), places=9, msg=label)
            self.assertAlmostEqual(got["traitAverageAfter"], python_average(after_cards, ranked), places=9, msg=label)
        return js

    def test_the_page_uses_the_preview_and_shows_what_changed(self):
        page = read("site", "admin.js")
        self.assertIn("ComfortPreview", page)
        self.assertIn("previewBatch", page)
        self.assertIn("Comfort ", page)
        self.assertIn("Trait average", page)
        self.assertIn("every card's Comfort moves slightly", page)
        html = read("site", "admin.html")
        self.assertLess(html.index("settings.js"), html.index("comfort-preview.js"))
        self.assertLess(html.index("comfort-preview.js"), html.index("admin.js"))
        self.assertIn("Unsaved changes", html)
        self.assertIn("Find a champion", html)
        for text in ("Scores update in about 3 minutes", "See the commit on GitHub", "beforeunload"):
            self.assertIn(text, page)
        self.assertIn('"/api/admin-card", "POST", { changes:', page)          # Save all = one request, one commit


@unittest.skipUnless(NODE, "Node is not installed")
class EditThenRevertTests(unittest.TestCase):
    """Editing a card and changing it back leaves the file, and so the scores, exactly as before."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        this = {
            "222": champ("Jinx", [1000, 520, 1000, 520]),
            "15": champ("Sivir", [1000, 540, 1000, 540]),
            "429": champ("Kalista", [1000, 510, 1000, 510]),
            "901": champ("Zzalpha", [1000, 560, 1000, 560]),
        }
        make_patch(self.root, "16.20", this, 50.0, [4000, 2000, 4000, 2000], [40000, 20000, 40000, 20000])
        write(os.path.join(self.root, "patches", "16.20", "players.json.gz"), {})

    def tearDown(self):
        shutil.rmtree(self.root)

    def score(self, text):
        cards = json.loads(text)["cards"]
        return json.dumps(model.round_floats(model.score_all(self.root, cards=cards, now=kept_time(self.root) or
                                                        __import__("datetime").datetime(2026, 10, 11))), sort_keys=True)

    def test_back_and_forth_gives_identical_files_and_scores(self):
        text = read("scoring", "cards.json")
        edits = [{"champion": "Jinx", "field": "mastery", "from": "good", "value": "main"},
                 {"champion": "Jinx", "field": "cc", "from": "mid", "value": "none"},
                 {"champion": "Sivir", "field": "cc", "from": "none", "value": "high"}]
        steps = node({"mode": "edit", "text": text, "edits": edits})
        reverse = [{"champion": e["champion"], "field": e["field"], "from": e["value"], "value": e["from"]} for e in reversed(edits)]
        back = node({"mode": "edit", "text": steps[-1], "edits": reverse})
        self.assertEqual(back[-1], text)
        before, edited, after = self.score(text), self.score(steps[-1]), self.score(back[-1])
        self.assertNotEqual(before, edited)       # the edits really move the scores
        self.assertEqual(before, after)

    def test_a_card_edit_does_not_touch_the_review_reminder(self):
        text = read("scoring", "cards.json")
        node({"mode": "edit", "text": text, "edits": [{"champion": "Jinx", "field": "mastery", "from": "good", "value": "main"}]})
        self.assertEqual(read("scoring", "review.json"), read("site", "data", "review.json"))
        code = "\n".join(l for l in read("lib", "admin-cards.js").splitlines() if not l.strip().startswith("//"))
        self.assertNotIn("review", code)                    # the card editor never names the review files
        self.assertNotIn("review.json", read("api", "admin-card.js"))

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_helper_behaviour_with_a_fake_github(self):
        result = subprocess.run([NODE, "--test", os.path.join(ROOT, "tests", "admin_cards.test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-1000:])


class RescoreTests(unittest.TestCase):
    def test_scoring_can_use_another_cards_file_and_keep_the_generated_time(self):
        root = tempfile.mkdtemp()
        try:
            this = {"222": champ("Jinx", [1000, 520, 1000, 520]), "15": champ("Sivir", [1000, 540, 1000, 540])}
            make_patch(root, "16.20", this, 50.0, [4000, 2000, 4000, 2000], [40000, 20000, 40000, 20000])
            write(os.path.join(root, "patches", "16.20", "players.json.gz"), {})
            with contextlib.redirect_stdout(io.StringIO()):
                scoring_main(["--data-dir", root])
            path = os.path.join(root, "scores", "latest.json")
            with open(path) as f:
                first = json.load(f)
            with open(CARDS_FILE) as f:
                cards = json.load(f)
            for c in cards["cards"]:
                if c["name"] == "Jinx":
                    c["mastery"] = "main"
            other = os.path.join(root, "cards-copy.json")
            with open(other, "w") as f:
                json.dump(cards, f)
            first["generated"] = "2026-01-02T03:04:05Z"
            with open(path, "w") as f:
                json.dump(first, f)
            with contextlib.redirect_stdout(io.StringIO()):
                scoring_main(["--data-dir", root, "--cards-file", other, "--keep-generated"])
            with open(path) as f:
                second = json.load(f)
            self.assertEqual(second["generated"], "2026-01-02T03:04:05Z")          # not new data, so not a new time
            jinx = lambda d: next(c for c in d["pick_score_list"] if c["name"] == "Jinx")
            self.assertEqual(jinx(second)["mastery"], "main")
            self.assertGreater(jinx(second)["comfort"], jinx(first)["comfort"])
        finally:
            shutil.rmtree(root)

    def test_collector_falls_back_to_its_own_cards_when_main_cannot_be_fetched(self):
        with tempfile.TemporaryDirectory() as folder:       # not a git repository: no `main` to fetch
            self.assertIsNone(collector_main.newest_cards(folder))

    def test_collector_scoring_asks_for_the_newest_cards(self):
        source = read("collector", "main.py")
        self.assertIn("newest_cards(repo)", source)
        self.assertIn('"--cards-file"', source)
        self.assertIn("FETCH_HEAD:scoring/cards.json", source)

    def test_rescore_workflow_is_safe(self):
        flow = read(".github", "workflows", "rescore.yml")
        self.assertIn("scoring/cards.json", flow)                      # runs when the cards change
        self.assertIn("workflow_dispatch", flow)
        self.assertIn("python -m scoring", flow)
        self.assertIn("--cards-file scoring/cards.json", flow)
        self.assertIn("--keep-generated", flow)
        # zero Riot requests: no collector, no Riot key, no player-code secret
        for word in ("RIOT_API_KEY", "PLAYER_CODE_SALT", "python -m collector", "secrets."):
            self.assertNotIn(word, flow)
        # never alongside a collector that is writing data
        self.assertIn("--workflow collect.yml", flow)
        self.assertIn("in_progress", flow)
        self.assertIn("queued", flow)
        self.assertIn("--force-with-lease=", flow)
        self.assertNotIn("push --force origin", flow)                  # never a plain force push
        self.assertRegex(flow, r"concurrency:\s+group: rescore\s+cancel-in-progress: true")
        self.assertNotRegex(flow, r"group: collector")                 # a queued rescore must never cancel a waiting collector

    def test_the_collector_workflow_and_schedule_are_untouched(self):
        flow = read(".github", "workflows", "collect.yml")
        self.assertIn('cron: "7 */6 * * *"', flow)
        self.assertRegex(flow, r"concurrency:\s+group: collector\s+cancel-in-progress: false")
        self.assertNotIn("rescore", flow)

    def test_the_page_picks_up_rescored_data_the_same_way_as_after_a_collector_run(self):
        self.assertIn("data/scores/latest.json", read("site", "settings.js"))     # the live scores file on the data branch
        config_json = json.loads(read("vercel.json"))
        self.assertIn('"main"', config_json["ignoreCommand"])                      # cards on the page rebuild from main only


if __name__ == "__main__":
    unittest.main()
