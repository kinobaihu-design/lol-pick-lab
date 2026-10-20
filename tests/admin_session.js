// Helper for the admin helper tests (not a test itself): requests as a logged-in browser would send them.
const common = require("../lib/admin-common.js");

const ENV = { ADMIN_PASSWORD: "correct horse battery staple", GITHUB_TOKEN: "fake-token-for-tests" };
const NOW = 1800000000000;                       // a fixed "now" the fake helpers use

function cookieFor(env, now) {
  return common.COOKIE_NAME + "=" + common.makeToken(env || ENV, now === undefined ? NOW : now);
}

// A request from a logged-in browser: the cookie and the X-Admin-Request header.
function request(method, body, extra) {
  return Object.assign({ method: method, body: body, headers: { cookie: cookieFor(), "x-admin-request": "1" } }, extra || {});
}

module.exports = { ENV, NOW, cookieFor, request, common };
