// Tests for the admin login (30-day cookie). Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const L = require("../lib/admin-login.js");
const S = require("./admin_session.js");
const common = S.common;

const ENV = S.ENV;
const deps = (extra) => {
  const sleeps = [];
  return Object.assign({ sleeps: sleeps, sleep: async (ms) => { sleeps.push(ms); }, now: () => S.NOW }, extra);
};
const header = { "x-admin-request": "1" };
const login = (password, extra) => Object.assign({ method: "POST", body: { password: password }, headers: Object.assign({}, header) }, extra);

test("right password: ok, a 30-day HttpOnly Secure SameSite=Strict cookie, no waiting", async () => {
  const d = deps();
  const out = await L.handle(login(ENV.ADMIN_PASSWORD), ENV, d);
  assert.strictEqual(out.status, 200);
  assert.deepStrictEqual(out.body, { ok: true, loggedIn: true });
  assert.strictEqual(out.cookies.length, 1);
  const cookie = out.cookies[0];
  assert.match(cookie, /^admin_session=[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+;/);
  assert.ok(cookie.indexOf("Max-Age=2592000") > 0);          // 30 days
  for (const flag of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/api"]) assert.ok(cookie.indexOf(flag) > 0, flag);
  assert.deepStrictEqual(d.sleeps, []);
  assert.ok(JSON.stringify(out).indexOf(ENV.ADMIN_PASSWORD) < 0);   // the password is never sent back
});

test("wrong password: waits 3 seconds, says 'Wrong password', sets no cookie", async () => {
  for (const password of ["nope", "", " ", "x".repeat(500), 5, null, undefined]) {
    const d = deps();
    const out = await L.handle(login(password), ENV, d);
    assert.strictEqual(out.status, 401, String(password));
    assert.strictEqual(out.body.message, "Wrong password");
    assert.strictEqual(out.cookies, undefined);
    assert.deepStrictEqual(d.sleeps, [3000]);
  }
});

test("the cookie from a login is accepted by the other helpers, for 30 days and not a second longer", () => {
  const request = (now) => ({ headers: { cookie: common.COOKIE_NAME + "=" + common.makeToken(ENV, S.NOW), "x-admin-request": "1" }, now: now });
  const token = common.makeToken(ENV, S.NOW);
  const day = 24 * 3600 * 1000;
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW), true);
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW + 29 * day), true);
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW + 30 * day - 1), true);
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW + 30 * day), false);
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW + 31 * day), false);
  assert.strictEqual(common.SESSION_DAYS, 30);
});

test("tampered, truncated, foreign or empty tokens are refused", () => {
  const token = common.makeToken(ENV, S.NOW);
  const [payload, signature] = token.split(".");
  const forged = Buffer.from(JSON.stringify({ v: 1, exp: S.NOW + 10 * 365 * 24 * 3600 * 1000 })).toString("base64").replace(/=+$/, "");
  const bad = [
    forged + "." + signature, payload + "." + signature.slice(0, -2) + "AA", payload, payload + "." + "", "." + signature, "a.b.c", "", "x".repeat(600),
    common.makeToken({ ADMIN_PASSWORD: "another password" }, S.NOW), null, undefined, 5
  ];
  for (const t of bad) assert.strictEqual(common.tokenIsValid(t, ENV, S.NOW), false, String(t).slice(0, 30));
});

test("changing ADMIN_PASSWORD logs every device out at once", () => {
  const token = common.makeToken(ENV, S.NOW);
  assert.strictEqual(common.tokenIsValid(token, ENV, S.NOW), true);
  assert.strictEqual(common.tokenIsValid(token, Object.assign({}, ENV, { ADMIN_PASSWORD: "a brand new long generated password" }), S.NOW), false);
});

test("status check: logged in or not, never needs a password", async () => {
  const d = deps();
  const out = await L.handle({ method: "GET", headers: { cookie: S.cookieFor() } }, ENV, d);
  assert.deepStrictEqual(out.body, { ok: true, loggedIn: true });
  for (const headers of [{}, { cookie: "admin_session=garbage" }, { cookie: S.cookieFor(ENV, S.NOW - 40 * 24 * 3600 * 1000) }]) {
    const no = await L.handle({ method: "GET", headers: headers }, ENV, d);
    assert.deepStrictEqual(no.body, { ok: true, loggedIn: false });
  }
});

test("log out clears the cookie", async () => {
  const out = await L.handle({ method: "DELETE", headers: Object.assign({ cookie: S.cookieFor() }, header) }, ENV, deps());
  assert.strictEqual(out.status, 200);
  assert.match(out.cookies[0], /^admin_session=; Max-Age=0;/);
});

test("a login or logout request without the page's header is refused (a request another website could make)", async () => {
  const d = deps();
  assert.strictEqual((await L.handle({ method: "POST", body: { password: ENV.ADMIN_PASSWORD }, headers: {} }, ENV, d)).status, 400);
  assert.strictEqual((await L.handle({ method: "DELETE", headers: {} }, ENV, d)).status, 400);
  assert.deepStrictEqual(d.sleeps, []);
});

test("extra fields, other methods and unset secrets are refused", async () => {
  const d = deps();
  assert.strictEqual((await L.handle({ method: "POST", body: { password: ENV.ADMIN_PASSWORD, admin: true }, headers: header }, ENV, d)).status, 400);
  assert.strictEqual((await L.handle({ method: "POST", body: [ENV.ADMIN_PASSWORD], headers: header }, ENV, d)).status, 400);
  assert.strictEqual((await L.handle({ method: "PUT", body: {}, headers: header }, ENV, d)).status, 405);
  for (const env of [{}, { ADMIN_PASSWORD: "x" }, { GITHUB_TOKEN: "x" }]) {
    for (const method of ["GET", "POST", "DELETE"]) {
      const out = await L.handle({ method: method, body: { password: "x" }, headers: header }, env, d);
      assert.strictEqual(out.status, 503);
      assert.strictEqual(out.body.message, "Admin not set up yet");
    }
  }
});

test("the cookie only goes to the admin helpers (Path=/api) and never into the page", () => {
  assert.strictEqual(common.COOKIE_PATH, "/api");
  assert.match(common.sessionCookie("t"), /HttpOnly/);
});

test("reading a cookie out of a header with other cookies in it", () => {
  assert.strictEqual(common.cookieValue({ cookie: "a=1; admin_session=abc.def; b=2" }, "admin_session"), "abc.def");
  assert.strictEqual(common.cookieValue({ cookie: "a=1; b=2" }, "admin_session"), null);
  assert.strictEqual(common.cookieValue({}, "admin_session"), null);
  assert.strictEqual(common.cookieValue(undefined, "admin_session"), null);
});
