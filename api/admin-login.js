"use strict";
// Vercel serverless function behind the hidden /admin login. All the logic is in lib/admin-login.js.
const { handle } = require("../lib/admin-login");

module.exports = async function (req, res) {
  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { body = null; }
  }
  const out = await handle(
    { method: req.method, body: body, headers: req.headers },
    process.env,
    { fetch: fetch, sleep: function (ms) { return new Promise(function (done) { setTimeout(done, ms); }); } }
  );
  res.setHeader("Cache-Control", "no-store");
  if (out.cookies) res.setHeader("Set-Cookie", out.cookies);
  res.status(out.status).json(out.body);
};
