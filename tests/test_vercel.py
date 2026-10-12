"""Vercel publishing setup: only the site folder, only from main, nothing secret."""

import json
import os
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
