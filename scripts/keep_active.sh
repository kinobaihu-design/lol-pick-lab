#!/usr/bin/env bash
# GitHub pauses scheduled workflows in public repos after 60 days without activity.
# If main has had no commits for KEEP_ACTIVE_DAYS days, add one empty commit to it.
set -euo pipefail
days="${KEEP_ACTIVE_DAYS:-30}"
git fetch --no-tags --depth=1 origin main
last=$(git log -1 --format=%ct FETCH_HEAD)
age=$(( ( $(date +%s) - last ) / 86400 ))
echo "Last change on main: ${age} days ago (keep-active limit: ${days} days)."
if [ "$age" -lt "$days" ]; then
  echo "Nothing to do."
  exit 0
fi
export GIT_AUTHOR_NAME="github-actions[bot]" GIT_COMMITTER_NAME="github-actions[bot]"
export GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
commit=$(git commit-tree "FETCH_HEAD^{tree}" -p FETCH_HEAD -m "Keep the scheduled collector active (no changes)")
git push origin "$commit:refs/heads/main"
echo "Added an empty keep-active commit to main."
