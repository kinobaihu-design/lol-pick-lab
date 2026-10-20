"use strict";
// Shared pieces of the hidden admin helpers (login, review button, card editing): the password check, the
// 30-day login cookie, the GitHub calls and the "one commit on main, only these files" writer. Plain Node,
// no packages. Secrets come in as `env` (Vercel Environment Variables): ADMIN_PASSWORD and GITHUB_TOKEN.
// They are never written to a file, a log or an answer.
//
// Login (v1.5): the password is typed once on the login screen. The helper then sets a signed session token in an
// HttpOnly, Secure, SameSite=Strict cookie that lasts 30 days. The token is signed with a key made from
// ADMIN_PASSWORD, so changing that secret logs every device out at once. The password itself is never stored
// in the browser. Every other helper accepts only a valid cookie plus the X-Admin-Request header (a request
// another website could not make).
const crypto = require("crypto");

const REPO = "kinobaihu-design/lol-pick-lab";
const BRANCH = "main";
const WRONG_PASSWORD_DELAY_MS = 3000;
const MAX_PASSWORD_LENGTH = 200;
const SESSION_DAYS = 30;
const SESSION_MS = SESSION_DAYS * 24 * 60 * 60 * 1000;
const COOKIE_NAME = "admin_session";
const COOKIE_PATH = "/api";
const REQUEST_HEADER = "x-admin-request";

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

function sessionKey(env) {
  return crypto.createHash("sha256").update("lol-pick-lab admin session v1:" + String(env.ADMIN_PASSWORD)).digest();
}

const b64url = (buffer) => Buffer.from(buffer).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const sign = (env, text) => b64url(crypto.createHmac("sha256", sessionKey(env)).update(text).digest());

// A signed token that says "valid until <time>". Nothing secret is inside it.
function makeToken(env, nowMs) {
  const payload = b64url(JSON.stringify({ v: 1, exp: nowMs + SESSION_MS }));
  return payload + "." + sign(env, payload);
}

function tokenIsValid(token, env, nowMs) {
  if (typeof token !== "string" || token.length > 500 || !env.ADMIN_PASSWORD) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const wanted = Buffer.from(sign(env, parts[0]));
  const given = Buffer.from(parts[1]);
  if (wanted.length !== given.length || !crypto.timingSafeEqual(wanted, given)) return false;
  try {
    const data = JSON.parse(Buffer.from(parts[0].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"));
    return data && data.v === 1 && typeof data.exp === "number" && data.exp > nowMs;
  } catch (e) {
    return false;
  }
}

function cookieValue(headers, name) {
  const raw = headers && (headers.cookie || headers.Cookie);
  if (typeof raw !== "string") return null;
  const found = raw.split(";").map((part) => part.trim()).find((part) => part.indexOf(name + "=") === 0);
  return found ? found.slice(name.length + 1) : null;
}

function sessionCookie(token) {
  return COOKIE_NAME + "=" + token + "; Max-Age=" + (SESSION_MS / 1000) + "; Path=" + COOKIE_PATH + "; HttpOnly; Secure; SameSite=Strict";
}
function clearedCookie() {
  return COOKIE_NAME + "=; Max-Age=0; Path=" + COOKIE_PATH + "; HttpOnly; Secure; SameSite=Strict";
}

const nowOf = (deps) => (deps && deps.now ? deps.now() : Date.now());

// Is this request from a logged-in browser? (valid cookie)
function hasSession(request, env, deps) {
  return tokenIsValid(cookieValue(request.headers, COOKIE_NAME), env, nowOf(deps));
}

// Method, secrets, the request header and the login cookie. Throws an AdminError or returns.
async function checkAccess(request, env, deps, method) {
  if (request.method !== method) throw new AdminError(405, "Use the buttons on the admin page");
  if (!env.ADMIN_PASSWORD || !env.GITHUB_TOKEN) throw new AdminError(503, "Admin not set up yet");
  const headers = request.headers || {};
  if (headers[REQUEST_HEADER] !== "1" || !hasSession(request, env, deps)) {
    throw new AdminError(401, "Please log in");
  }
}

// The typed password (login only). Waits after a wrong one.
async function checkPassword(given, env, sleep) {
  if (typeof given !== "string" || given.length === 0 || given.length > MAX_PASSWORD_LENGTH || !sameSecret(given, env.ADMIN_PASSWORD)) {
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

module.exports = { AdminError, REPO, BRANCH, WRONG_PASSWORD_DELAY_MS, SESSION_DAYS, SESSION_MS, COOKIE_NAME, COOKIE_PATH, REQUEST_HEADER,
  sameSecret, makeToken, tokenIsValid, cookieValue, sessionCookie, clearedCookie, hasSession, nowOf, checkAccess, checkPassword,
  github, commitToMain, currentHead, failure };
