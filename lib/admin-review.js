"use strict";
// Logic of the hidden "Mastery review done" helper (admin page, slice 1).
// It can change exactly two files on `main`, in one commit, and nothing else.
const common = require("./admin-common");
const { AdminError, REPO, BRANCH, WRONG_PASSWORD_DELAY_MS } = common;

const DATA_URL = "https://raw.githubusercontent.com/" + REPO + "/data/scores/latest.json";
const ALLOWED_FILES = ["scoring/review.json", "site/data/review.json"];
const PATCH_PATTERN = /^\d{1,2}\.\d{1,2}$/;

async function currentPatch(fetchFn) {
  let data;
  try {
    const response = await fetchFn(DATA_URL, { headers: { "Cache-Control": "no-cache" } });
    if (!response.ok) throw new Error("status " + response.status);
    data = await response.json();
  } catch (e) {
    throw new AdminError(502, "Couldn't read the current patch, try later");
  }
  const patch = data && data.patch;
  if (typeof patch !== "string" || !PATCH_PATTERN.test(patch)) {
    throw new AdminError(422, "The current patch looks invalid, nothing was changed");
  }
  return patch;
}

// Writes the given files to `main` in ONE commit. Refuses any file outside ALLOWED_FILES.
async function commitFiles(fetchFn, token, files, message) {
  const call = common.github(fetchFn, token);
  const paths = Object.keys(files).sort();
  if (paths.join("|") !== ALLOWED_FILES.slice().sort().join("|")) {
    throw new AdminError(500, "Refused: this helper may change only " + ALLOWED_FILES.join(" and "));
  }
  const head = await common.currentHead(call);
  return common.commitToMain(call, head, files, message, ALLOWED_FILES);
}

async function handle(request, env, deps) {
  try {
    await common.checkAccess(request, env, deps, "POST");
    // The patch is read here, never taken from the browser.
    const patch = await currentPatch(deps.fetch);
    const content = JSON.stringify({ last_mastery_review_patch: patch }, null, 2) + "\n";
    const files = {};
    ALLOWED_FILES.forEach(function (path) { files[path] = content; });
    const url = await commitFiles(deps.fetch, env.GITHUB_TOKEN, files, "Mastery review done on patch " + patch + " (admin page)");
    return { status: 200, body: { ok: true, patch: patch, message: "Review set to patch " + patch + " ✓", commit_url: url } };
  } catch (e) {
    return common.failure(e);
  }
}

module.exports = { handle, commitFiles, ALLOWED_FILES, DATA_URL, REPO, BRANCH, WRONG_PASSWORD_DELAY_MS };
