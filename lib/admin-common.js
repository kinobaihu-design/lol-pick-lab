"use strict";
// Shared pieces of the hidden admin helpers (review button, card editing): the password check, the
// GitHub calls and the "one commit on main, only these files" writer. Plain Node, no packages.
// Secrets come in as `env` (Vercel Environment Variables): ADMIN_PASSWORD and GITHUB_TOKEN.
// They are never written to a file, a log or an answer.
const crypto = require("crypto");

const REPO = "kinobaihu-design/lol-pick-lab";
const BRANCH = "main";
const WRONG_PASSWORD_DELAY_MS = 3000;
const MAX_PASSWORD_LENGTH = 200;

class AdminError extends Error {
  constructor(status, message, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function sameSecret(given, expected) {
  // Hash both so the comparison always sees the same length, then compare in constant time.
  const a = crypto.createHash("sha256").update(String(given)).digest();
  const b = crypto.createHash("sha256").update(String(expected)).digest();
  return crypto.timingSafeEqual(a, b);
}

// Method, secrets and password. Throws an AdminError (after the wrong-password wait) or returns.
async function checkAccess(request, env, sleep, method) {
  if (request.method !== method) throw new AdminError(405, "Use the buttons on the admin page");
  if (!env.ADMIN_PASSWORD || !env.GITHUB_TOKEN) throw new AdminError(503, "Admin not set up yet");
  const password = request.body && request.body.password;
  if (typeof password !== "string" || password.length === 0 || password.length > MAX_PASSWORD_LENGTH ||
      !sameSecret(password, env.ADMIN_PASSWORD)) {
    await sleep(WRONG_PASSWORD_DELAY_MS);
    throw new AdminError(401, "Wrong password");
  }
}

function github(fetchFn, token) {
  async function send(path, method, body, accept) {
    let response;
    try {
      response = await fetchFn("https://api.github.com/repos/" + REPO + path, {
        method: method,
        headers: {
          Authorization: "Bearer " + token,
          Accept: accept || "application/vnd.github+json",
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
      throw new AdminError(409, "The main branch changed while saving, press the button again", "branch-moved");
    }
    if (!response.ok) throw new AdminError(502, "GitHub said no (" + response.status + "), try later");
    return response;
  }
  const call = async function (path, method, body) { return (await send(path, method, body)).json(); };
  call.text = async function (path) { return (await send(path, "GET", undefined, "application/vnd.github.raw+json")).text(); };
  return call;
}

// Writes the given files to `main` in ONE commit on top of `head`. Refuses any file set other than `allowed`.
async function commitToMain(call, head, files, message, allowed) {
  const paths = Object.keys(files).sort();
  if (paths.join("|") !== allowed.slice().sort().join("|")) {
    throw new AdminError(500, "Refused: this helper may change only " + allowed.join(" and "));
  }
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

async function currentHead(call) {
  const ref = await call("/git/ref/heads/" + BRANCH, "GET");
  return ref.object.sha;
}

function failure(e) {
  if (e instanceof AdminError) return { status: e.status, body: { ok: false, message: e.message } };
  return { status: 500, body: { ok: false, message: "Something went wrong, nothing was changed" } };
}

module.exports = { AdminError, REPO, BRANCH, WRONG_PASSWORD_DELAY_MS, sameSecret, checkAccess, github, commitToMain, currentHead, failure };
