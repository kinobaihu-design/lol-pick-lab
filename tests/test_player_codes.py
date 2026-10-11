"""Player codes: secret-key codes, conversion of old codes, and the refusals."""

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from collector import convert_codes  # noqa: E402
from collector import store as st  # noqa: E402
from tests.test_collector import fake_match  # noqa: E402

SECRET = "unit-test-secret-" + "abcdef0123456789" * 2   # made up; the real one is a GitHub secret
OTHER = "another-test-secret-" + "fedcba9876543210" * 2


def with_secret(value):
    return mock.patch.dict(os.environ, {st.SECRET_ENV: value})


def write_old_style_tree(root, puuids):
    """A data folder as it was before this change: codes are plain SHA-256 of the player ID."""
    old = [st.unsalted_code(p) for p in puuids]
    st._write(os.path.join(root, "state", "players.json.gz"), {"EUW1": {old[0]: [1, 5], old[1]: [2, 7]}, "KR": {}})
    st._write(os.path.join(root, "state", "processed.json.gz"), {"EUW1": {}})
    st._write(os.path.join(root, "state", "pending.json.gz"), {"EUW1": ["EUW1_1"]})
    st._write(os.path.join(root, "patches", "16.19", "players.json.gz"),
              {old[0]: {"103": [3, 2], "103:B": [3, 2]}, old[1]: {"22": [1, 0]}})
    st._write(os.path.join(root, "season", "16", "players.json.gz"),
              {"champions": ["103"], "players": {old[0]: {"all": [9, 5], "103": [3, 2]}, old[1]: {"all": [4, 1]}}})
    return old


class SecretTests(unittest.TestCase):
    def test_codes_need_the_secret(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop(st.SECRET_ENV, None)
            with self.assertRaises(st.MissingSecret):
                st.scramble("player-1")
        with with_secret("short"):
            with self.assertRaises(st.MissingSecret):
                st.scramble("player-1")

    def test_collector_refuses_to_run_without_the_secret(self):
        env = {k: v for k, v in os.environ.items() if k != st.SECRET_ENV}
        env["RIOT_API_KEY"] = "not-a-real-key"
        with tempfile.TemporaryDirectory() as data:
            result = subprocess.run([sys.executable, "-m", "collector", "--data-dir", data, "--max-minutes", "1"],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1)
            self.assertIn("PLAYER_CODE_SALT", result.stdout)
            self.assertEqual(os.listdir(data), [])  # nothing written

    def test_formula_is_hmac_sha256_of_the_old_code_cut_to_16(self):
        import hashlib
        import hmac
        old = hashlib.sha256(b"player-1").hexdigest()[:16]               # how codes were made before
        expected = hmac.new(SECRET.encode(), old.encode(), hashlib.sha256).hexdigest()[:16]
        with with_secret(SECRET):
            self.assertEqual(st.scramble("player-1"), expected)
            self.assertEqual(st.salted_code(old), expected)

    def test_code_depends_on_the_secret(self):
        with with_secret(SECRET):
            first = st.scramble("player-1")
        with with_secret(OTHER):
            second = st.scramble("player-1")
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertNotEqual(first, st.unsalted_code("player-1"))


class ConversionTests(unittest.TestCase):
    def test_converted_old_code_matches_a_new_code_from_the_player_id(self):
        puuids = ["player-1", "player-2"]
        with tempfile.TemporaryDirectory() as root:
            old = write_old_style_tree(root, puuids)
            with with_secret(SECRET):
                convert_codes.convert_tree(root, SECRET)
                new = [st.scramble(p) for p in puuids]
            state = st._read(os.path.join(root, "state", "players.json.gz"))
            patch = st._read(os.path.join(root, "patches", "16.19", "players.json.gz"))
            season = st._read(os.path.join(root, "season", "16", "players.json.gz"))
            self.assertEqual(state["EUW1"][new[0]], [1, 5])
            self.assertEqual(state["EUW1"][new[1]], [2, 7])
            self.assertEqual(patch[new[0]], {"103": [3, 2], "103:B": [3, 2]})
            self.assertEqual(season["players"][new[0]], {"all": [9, 5], "103": [3, 2]})
            self.assertEqual(season["champions"], ["103"])
            self.assertEqual(convert_codes.find_leftovers(root, set(old)), [])

    def test_nothing_unsalted_survives_and_it_runs_only_once(self):
        with tempfile.TemporaryDirectory() as root:
            old = write_old_style_tree(root, ["player-1", "player-2"])
            self.assertEqual(len(convert_codes.find_leftovers(root, set(old))), 3)  # the check can see them
            convert_codes.convert_tree(root, SECRET)
            with self.assertRaises(SystemExit):
                convert_codes.convert_tree(root, SECRET)   # a second run would hash twice

    def test_break_it_check_leftover_scan_catches_an_old_code(self):
        with tempfile.TemporaryDirectory() as root:
            old = write_old_style_tree(root, ["player-1", "player-2"])
            convert_codes.convert_tree(root, SECRET)
            with open(os.path.join(root, "README.md"), "a") as f:
                f.write("oops " + old[0])
            self.assertEqual(convert_codes.find_leftovers(root, set(old)), ["README.md"])

    def test_collector_refuses_unconverted_or_wrong_secret_data(self):
        with tempfile.TemporaryDirectory() as root:
            write_old_style_tree(root, ["player-1", "player-2"])
            shutil.rmtree(os.path.join(root, "patches"))     # the made-up tree has no summary files
            with with_secret(SECRET):
                with self.assertRaises(st.CodesMismatch):    # not converted yet
                    st.Store.load(root)
                convert_codes.convert_tree(root, SECRET)
                st.Store.load(root)                          # fine now
            with with_secret(OTHER):
                with self.assertRaises(st.CodesMismatch):    # wrong secret would orphan every player
                    st.Store.load(root)


class NoUnsaltedCodesTests(unittest.TestCase):
    def test_saved_files_hold_only_salted_codes(self):
        with with_secret(SECRET):
            store = st.Store()
            puuids = ["player-%d" % i for i in range(10)]
            everyone = {st.scramble(p) for p in puuids}
            for n in range(3):
                store.add_match(st.compact_match(fake_match(), "EUW1_%d" % n, "EUW1"), everyone)
            store.player_state["EUW1"][st.scramble("player-3")] = [1, 5]
            with tempfile.TemporaryDirectory() as root:
                store.save(root, {})
                old = {st.unsalted_code(p) for p in puuids}
                self.assertEqual(convert_codes.find_leftovers(root, old), [])
                season = st._read(os.path.join(root, "season", "16", "players.json.gz"))["players"]
                self.assertIn(st.scramble("player-3"), season)
                self.assertNotIn("player-3", json.dumps(season))
                self.assertEqual(st.Store.load(root).seasons["16"]["players"].keys(), season.keys())

    def test_break_it_check_would_catch_an_unsalted_save(self):
        # If scramble() ever went back to the plain hash, the scan above must fail.
        with with_secret(SECRET), mock.patch.object(st, "scramble", st.unsalted_code):
            store = st.Store()
            puuids = ["player-%d" % i for i in range(10)]
            everyone = {st.unsalted_code(p) for p in puuids}
            store.add_match(st.compact_match(fake_match(), "EUW1_1", "EUW1"), everyone)
            with tempfile.TemporaryDirectory() as root:
                store.save(root, {})
                self.assertNotEqual(convert_codes.find_leftovers(root, everyone), [])


if __name__ == "__main__":
    unittest.main()
