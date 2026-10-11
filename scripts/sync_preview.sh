#!/bin/sh
# Copies the site/ folder to the fixed preview folder that the local preview serves.
# (The preview program is not allowed to read the Documents folder, so it serves a copy.)
# Run this after every change to site/ so the preview shows the newest code.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.lol-pick-lab-preview"
mkdir -p "$DEST"
rsync -a --delete "$HERE/site/" "$DEST/"
echo "Preview copy updated: $DEST"
