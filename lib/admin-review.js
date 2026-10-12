"use strict";
// Logic of the hidden "Mastery review done" helper (admin page, slice 1). Plain Node, no packages.
// It can change exactly two files on `main`, in one commit, and nothing else.
// The secrets come in as `env` (Vercel Environment Variables): ADMIN_PASSWORD and GITHUB_TOKEN.
// They are never written to a file, a log or an answer.
const crypto = require("crypto");

const REPO = "kinobaihu-design/lol-pick-lab";
const BRANCH = "main";
const DATA_URL = "https://raw.githubusercontent.com/" + REPO + "/data/scores/latest.json";
const ALLOWED_FILES = ["scoring/review.json", "site/data/review.json"];
const PATCH_PATTERN = /^\d{1,2}\.\d{1,2}$/;
const WRONG_PASSWORD_DELAY_MS = 3000;
const MAX_PASSWORD_LENGTH = 200;

class AdminError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function sameSecret(given, expected) {
  // Hash both so the comparison always sees the same length, then compare in constant time.
  const a = crypto.createHash("sha256").update(String(given)).digest();
  const b = crypto.createHash("sha256").update(String(expected)).digest();
  return crypto.timingSafeEqual(a, b);
}

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

function github(fetchFn, token) {
  return async function call(path, method, body) {
    let response;
    try {
      response = await fetchFn("https://api.github.com/repos/" + REPO + path, {
        method: method,
        headers: {
          Authorization: "Bearer " + token,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "lol-pick-lab-admin",
          "Content-Type": "application/json"
        },
        body: body === undefined ? undefined : JSON.stringify(body)
      });
    } catch (e) {
      throw new AdminError(502, "Couldn't reach GitHub, try later");
    }
    if (response.status === 401) throw new AdminError(502, "GitHub key expired or invalid: make a new one");
    if (response.status === 403 || response.status === 404) {
      throw new AdminError(502, "GitHub key can't write to this project: check it has Contents = Read and write");
    }
    if (response.status === 422 && method === "PATCH") {
      throw new AdminError(409, "The main branch changed while saving, press the button again");
    }
    if (!response.ok) throw new AdminError(502, "GitHub said no (" + response.status + "), try later");
    return response.json();
  };
}

// Writes the given files to `main` in ONE commit. Refuses any file outside ALLOWED_FILES.
async function commitFiles(fetchFn, token, files, message) {
  const paths = Object.keys(files).sort();
  if (paths.join("|") !== ALLOWED_FILES.slice().sort().join("|")) {
    throw new AdminError(500, "Refused: this helper may change only " + ALLOWED_FILES.join(" and "));
  }
  const call = github(fetchFn, token);
  const ref = await call("/git/ref/heads/" + BRANCH, "GET");
  const head = ref.object.sha;
  const headCommit = await call("/git/commits/" + head, "GET");
  const tree = await call("/git/trees", "POST", {
    base_tree: headCommit.tree.sha,
    tree: paths.map(function (path) {
      return { path: path, mode: "100644", type: "blob", content: files[path] };
    })
  });
  const commit = await call("/git/commits", "POST", { message: message, tree: tree.sha, parents: [head] });
  await call("/git/refs/heads/" + BRANCH, "PATCH", { sha: commit.sha, force: false });
  return "https://github.com/" + REPO + "/commit/" + commit.sha;
}

async function handle(request, env, deps) {
  const fetchFn = deps.fetch;
  const sleep = deps.sleep;
  try {
    if (request.method !== "POST") throw new AdminError(405, "Use the button on the admin page");
    if (!env.ADMIN_PASSWORD || !env.GITHUB_TOKEN) throw new AdminError(503, "Admin not set up yet");
    const password = request.body && request.body.password;
    if (typeof password !== "string" || password.length === 0 || password.length > MAX_PASSWORD_LENGTH ||
        !sameSecret(password, env.ADMIN_PASSWORD)) {
      await sleep(WRONG_PASSWORD_DELAY_MS);
      throw new AdminError(401, "Wrong password");
    }
    // The patch is read here, never taken from the browser.
    const patch = await currentPatch(fetchFn);
    const content = JSON.stringify({ last_mastery_review_patch: patch }, null, 2) + "\n";
    const files = {};
    ALLOWED_FILES.forEach(function (path) { files[path] = content; });
    const url = await commitFiles(fetchFn, env.GITHUB_TOKEN, files, "Mastery review done on patch " + patch + " (admin page)");
    return { status: 200, body: { ok: true, patch: patch, message: "Review set to patch " + patch + " ✓", commit_url: url } };
  } catch (e) {
    if (e instanceof AdminError) return { status: e.status, body: { ok: false, message: e.message } };
    return { status: 500, body: { ok: false, message: "Something went wrong, nothing was changed" } };
  }
}

module.exports = { handle, commitFiles, ALLOWED_FILES, DATA_URL, REPO, BRANCH, WRONG_PASSWORD_DELAY_MS };
