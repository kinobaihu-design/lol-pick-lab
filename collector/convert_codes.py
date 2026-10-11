"""One-time conversion of saved player codes from the old unsalted form to secret-key codes.

    new code = HMAC-SHA256(secret, old code), shortened to 16 characters

Run on an unpacked copy of the data branch (never needs real player IDs):

    PLAYER_CODE_SALT=... python3 -m collector.convert_codes DATA_DIR

It converts every file that holds player codes (state/players, patches/*/players,
season/*/players), writes `codes.json`, and refuses to run twice.
"""

import gzip
import os
import re
import sys

from . import store as st

HEX16 = re.compile(r"(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])")


def convert_tree(root, secret):
    """Convert all player-code keys in `root` in place. Returns the list of old codes seen."""
    if os.path.exists(os.path.join(root, st.CODES_FILE)):
        raise SystemExit("Already converted (%s exists). Nothing changed." % st.CODES_FILE)
    old_codes = set()
    cache = {}

    def new(old):
        old_codes.add(old)
        if old not in cache:
            cache[old] = st.salted_code(old, secret)
        return cache[old]

    def convert_keys(table):
        out = {new(code): value for code, value in table.items()}
        if len(out) != len(table):
            raise SystemExit("Two old codes became the same new code; stopping before saving.")
        return out

    # Read and convert everything first, write only when nothing failed.
    pending = []
    path = os.path.join(root, "state", "players.json.gz")
    if os.path.exists(path):
        data = st._read(path)
        pending.append((path, {server: convert_keys(codes) for server, codes in data.items()}))
    patches_dir = os.path.join(root, "patches")
    for name in sorted(os.listdir(patches_dir)) if os.path.isdir(patches_dir) else []:
        path = os.path.join(patches_dir, name, "players.json.gz")
        if os.path.exists(path):
            pending.append((path, convert_keys(st._read(path))))
    seasons_dir = os.path.join(root, "season")
    for name in sorted(os.listdir(seasons_dir)) if os.path.isdir(seasons_dir) else []:
        path = os.path.join(seasons_dir, name, "players.json.gz")
        if os.path.exists(path):
            data = st._read(path)
            data["players"] = convert_keys(data["players"])
            pending.append((path, data))

    for path, data in pending:
        st._write(path, data)
    st._write(os.path.join(root, st.CODES_FILE),
              {"version": st.CODES_VERSION, "check": st.secret_check(secret)})
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write(st.DATA_README)
    return old_codes


def find_leftovers(root, old_codes):
    """Files (raw text, or unpacked if .gz) that still contain any old code. Should be empty."""
    found = []
    for folder, _, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as f:
                raw = f.read()
            if name.endswith(".gz"):
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", "ignore")
            # Every 16-character hex word in the file is compared with the set of old codes.
            if any(word in old_codes for word in HEX16.findall(text)):
                found.append(os.path.relpath(path, root))
    return found


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 -m collector.convert_codes DATA_DIR")
    root = sys.argv[1]
    secret = st.player_secret()
    old_codes = convert_tree(root, secret)
    leftovers = find_leftovers(root, old_codes)
    print("Converted %d player codes." % len(old_codes))
    if leftovers:
        raise SystemExit("Old codes still found in: %s" % ", ".join(leftovers))
    print("No old codes left in any file.")


if __name__ == "__main__":
    main()
