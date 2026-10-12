"""Vercel publishing setup: only the site folder, only from main, nothing secret."""

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VercelConfigTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
            self.config = json.load(f)

    def test_publishes_only_the_site_folder_with_no_build(self):
        self.assertEqual(self.config["outputDirectory"], "site")
        self.assertEqual(self.config["buildCommand"], "")
        self.assertEqual(self.config["installCommand"], "")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "site", "index.html")))

    def test_builds_only_from_main(self):
        command = self.config["ignoreCommand"]
        self.assertIn("VERCEL_GIT_COMMIT_REF", command)
        self.assertIn('"main"', command)
        self.assertIn("exit 1", command)      # exit 1 = build; exit 0 = skip

    def test_no_environment_variables_or_secrets(self):
        self.assertNotIn("env", self.config)
        self.assertNotIn("build", self.config)

    def test_the_page_reads_scores_from_the_data_branch_not_from_vercel(self):
        with open(os.path.join(ROOT, "site", "settings.js"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("raw.githubusercontent.com/kinobaihu-design/lol-pick-lab/data/scores/latest.json", text)


if __name__ == "__main__":
    unittest.main()


class AdminPageTests(unittest.TestCase):
    """Admin page slice 1: hidden page, hidden helper, nothing secret in the files."""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_admin_page_exists_and_is_noindex(self):
        page = self.read("site", "admin.html")
        self.assertRegex(page, r'<meta name="robots" content="[^"]*noindex')
        headers = json.loads(self.read("vercel.json"))["headers"]
        sources = {h["source"]: {x["key"]: x["value"] for x in h["headers"]} for h in headers}
        self.assertIn("noindex", sources["/admin"]["X-Robots-Tag"])
        self.assertIn("noindex", sources["/api/(.*)"]["X-Robots-Tag"])

    def test_admin_is_not_linked_from_the_site(self):
        for name in os.listdir(os.path.join(ROOT, "site")):
            path = os.path.join(ROOT, "site", name)
            if name in ("admin.html", "admin.js") or not os.path.isfile(path):
                continue
            text = self.read("site", name).lower()
            self.assertNotIn("/admin", text, name)          # no link or address anywhere
            self.assertNotIn("admin.html", text, name)
            self.assertNotIn("admin.js", text, name)
        self.assertNotIn("admin", self.read("site", "index.html").lower())

    def test_admin_page_has_no_secret_and_only_the_one_button(self):
        text = self.read("site", "admin.html") + self.read("site", "admin.js")
        for word in ("ADMIN_PASSWORD", "GITHUB_TOKEN", "ghp_", "github_pat_", "process.env", "localStorage",
                     "sessionStorage", "document.cookie"):
            self.assertNotIn(word, text)
        self.assertEqual(self.read("site", "admin.html").count("<button"), 1)   # the cards' Update buttons are added by admin.js
        self.assertIn("Mastery review done", self.read("site", "admin.html"))
        self.assertIn('type="password"', self.read("site", "admin.html"))

    def test_the_helper_is_the_only_extra_published_code_and_reads_secrets_from_the_environment(self):
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "api"))), ["admin-card.js", "admin-review.js"])
        self.assertIn("process.env", self.read("api", "admin-review.js"))
        self.assertIn("process.env", self.read("api", "admin-card.js"))
        logic = "".join(self.read("lib", n) for n in sorted(os.listdir(os.path.join(ROOT, "lib"))))
        self.assertNotRegex(logic, r"(ghp_|github_pat_)[A-Za-z0-9_]{10,}")
        self.assertIn("timingSafeEqual", logic)
        config = json.loads(self.read("vercel.json"))
        self.assertEqual(config["outputDirectory"], "site")
        self.assertIn('"main"', config["ignoreCommand"])

    def test_the_collector_and_data_files_are_not_touched_by_the_helper(self):
        logic = "".join(self.read("lib", n) for n in sorted(os.listdir(os.path.join(ROOT, "lib"))))
        for word in ("collector/", "state/", "collect.yml", "/.github", "\".github"):
            self.assertNotIn(word, logic)

    def test_review_files_the_helper_writes_exist_and_match(self):
        self.assertEqual(self.read("scoring", "review.json"), self.read("site", "data", "review.json"))

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_helper_behaviour_with_a_fake_github(self):
        result = subprocess.run(["node", "--test", os.path.join(ROOT, "tests", "admin_review.test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-1000:])
