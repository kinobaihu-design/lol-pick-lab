"""Safety checks: no Riot API key (or anything shaped like one) anywhere in the project files."""

import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A Riot key looks like "RGAPI-" followed by letters, digits and dashes (usually a UUID). Built in pieces so this
# file does not match itself.
KEY_SHAPE = re.compile("RGAPI" + r"-[0-9A-Za-z_-]{16,}")
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
SKIP_SUFFIXES = (".pdf", ".gz", ".png", ".jpg", ".ico", ".pyc")


def project_files(root):
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if not name.endswith(SKIP_SUFFIXES):
                yield os.path.join(folder, name)


def find_keys(root):
    hits = []
    for path in project_files(root):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        if KEY_SHAPE.search(text):
            hits.append(os.path.relpath(path, root))          # only the place, never the value
    return hits


class KeyScanTests(unittest.TestCase):
    def test_no_key_shaped_text_in_the_project(self):
        self.assertEqual(find_keys(ROOT), [])

    def test_the_scan_really_catches_a_key(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "oops.txt"), "w") as f:
                f.write("key = " + "RGAPI" + "-" + "0123abcd-4567-89ef-0123-456789abcdef")
            self.assertEqual(find_keys(folder), ["oops.txt"])

    def test_no_key_in_git_history_of_main(self):
        result = subprocess.run(["git", "log", "-p", "HEAD", "-G", "RGAPI" + "-[0-9A-Za-z_-]{16,}", "--format=%h", "--", ".",
                                 ":(exclude)tests/test_safety.py"],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            self.skipTest("git history not available")
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
