"use strict";
// The hidden admin login (v1.5). GET: is this browser logged in? POST {password}: log in (sets the 30-day cookie).
// DELETE: log out. Everything else on the admin page needs the cookie this sets.
const common = require("./admin-common");
const { AdminError } = common;

function secretsOk(env) {
  if (!env.ADMIN_PASSWORD || !env.GITHUB_TOKEN) throw new AdminError(503, "Admin not set up yet");
}

function needHeader(request) {
  if ((request.headers || {})[common.REQUEST_HEADER] !== "1") throw new AdminError(400, "Use the admin page");
}

async function handle(request, env, deps) {
  try {
    secretsOk(env);
    if (request.method === "GET") {
      return { status: 200, body: { ok: true, loggedIn: common.hasSession(request, env, deps) } };
    }
    needHeader(request);
    if (request.method === "DELETE") {
      return { status: 200, body: { ok: true, loggedIn: false }, cookies: [common.clearedCookie()] };
    }
    if (request.method !== "POST") throw new AdminError(405, "Use the admin page");
    const body = request.body;
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some((k) => k !== "password")) {
      throw new AdminError(400, "Type the password and press Log in");
    }
    await common.checkPassword(body.password, env, deps.sleep);
    return { status: 200, body: { ok: true, loggedIn: true }, cookies: [common.sessionCookie(common.makeToken(env, common.nowOf(deps)))] };
  } catch (e) {
    return common.failure(e);
  }
}

module.exports = { handle };
