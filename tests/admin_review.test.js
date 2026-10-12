// Tests for the hidden admin helper, with a fake GitHub (no real calls). Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const A = require("../lib/admin-review.js");

const ENV = { ADMIN_PASSWORD: "correct horse battery staple", GITHUB_TOKEN: "fake-token-for-tests" };

function fakeWorld(options) {
  options = options || {};
  const world = { calls: [], sleeps: [], trees: [], refUpdates: 0 };
  world.fetch = async function (url, init) {
    init = init || {};
    world.calls.push({ url: url, method: init.method || "GET", auth: init.headers && init.headers.Authorization });
    const reply = function (status, data) { return { ok: status >= 200 && status < 300, status: status, json: async () => data }; };
    if (url === A.DATA_URL) {
      if (options.dataDown) return reply(500, {});
      return reply(200, { patch: options.patch === undefined ? "16.21" : options.patch });
    }
    if (options.githubStatus) return reply(options.githubStatus, {});
    const path = url.replace("https://api.github.com/repos/" + A.REPO, "");
    if (path === "/git/ref/heads/main") return reply(200, { object: { sha: "head1" } });
    if (path === "/git/commits/head1") return reply(200, { tree: { sha: "tree0" } });
    if (path === "/git/trees") { world.trees.push(JSON.parse(init.body)); return reply(201, { sha: "tree1" }); }
    if (path === "/git/commits") { world.commitBody = JSON.parse(init.body); return reply(201, { sha: "abc123" }); }
    if (path === "/git/refs/heads/main") { world.refUpdates++; world.refBody = JSON.parse(init.body); return reply(200, {}); }
    return reply(404, {});
  };
  world.sleep = async function (ms) { world.sleeps.push(ms); };
  world.deps = { fetch: world.fetch, sleep: world.sleep };
  return world;
}

const post = (password) => ({ method: "POST", body: { password: password } });
const githubCalls = (w) => w.calls.filter((c) => c.url.indexOf("api.github.com") >= 0);

test("wrong password: waits about 3 seconds, says so, and touches nothing", async () => {
  const w = fakeWorld();
  const out = await A.handle(post("nope"), ENV, w.deps);
  assert.strictEqual(out.status, 401);
  assert.strictEqual(out.body.message, "Wrong password");
  assert.deepStrictEqual(w.sleeps, [3000]);
  assert.strictEqual(w.calls.length, 0);
});

test("missing or empty password is refused like a wrong one", async () => {
  for (const body of [null, {}, { password: "" }, { password: 5 }, { password: "x".repeat(500) }]) {
    const w = fakeWorld();
    const out = await A.handle({ method: "POST", body: body }, ENV, w.deps);
    assert.strictEqual(out.body.message, "Wrong password");
    assert.strictEqual(w.calls.length, 0);
  }
});

test("secrets not set yet: 'Admin not set up yet', nothing called", async () => {
  for (const env of [{}, { ADMIN_PASSWORD: "x" }, { GITHUB_TOKEN: "x" }, { ADMIN_PASSWORD: "", GITHUB_TOKEN: "" }]) {
    const w = fakeWorld();
    const out = await A.handle(post("x"), env, w.deps);
    assert.strictEqual(out.status, 503);
    assert.strictEqual(out.body.message, "Admin not set up yet");
    assert.strictEqual(w.calls.length, 0);
  }
});

test("only POST is accepted", async () => {
  const w = fakeWorld();
  const out = await A.handle({ method: "GET" }, ENV, w.deps);
  assert.strictEqual(out.status, 405);
  assert.strictEqual(w.calls.length, 0);
});

test("invalid current patch is refused and nothing is written", async () => {
  for (const patch of ["abc", "16.2.1", "16.20; rm", "", null, undefined, 16.2, "../etc"]) {
    const w = fakeWorld({ patch: patch === undefined ? "__missing__" : patch });
    if (patch === undefined) w.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
    const deps = patch === undefined ? { fetch: w.fetch, sleep: w.sleep } : w.deps;
    const out = await A.handle(post(ENV.ADMIN_PASSWORD), ENV, deps);
    assert.strictEqual(out.body.ok, false, String(patch));
    assert.strictEqual(githubCalls(w).length, 0, String(patch));
  }
});

test("data unreachable: 'Couldn't read the current patch, try later'", async () => {
  const w = fakeWorld({ dataDown: true });
  const out = await A.handle(post(ENV.ADMIN_PASSWORD), ENV, w.deps);
  assert.strictEqual(out.body.message, "Couldn't read the current patch, try later");
  assert.strictEqual(githubCalls(w).length, 0);
});

test("the browser cannot choose the patch: extra fields are ignored", async () => {
  const w = fakeWorld({ patch: "16.21" });
  const out = await A.handle({ method: "POST", body: { password: ENV.ADMIN_PASSWORD, patch: "99.99", files: ["x"] } }, ENV, w.deps);
  assert.strictEqual(out.body.patch, "16.21");
});

test("success: both files in ONE commit on main, right message, confirmation and link", async () => {
  const w = fakeWorld({ patch: "16.21" });
  const out = await A.handle(post(ENV.ADMIN_PASSWORD), ENV, w.deps);
  assert.strictEqual(out.status, 200);
  assert.strictEqual(out.body.message, "Review set to patch 16.21 ✓");
  assert.strictEqual(out.body.commit_url, "https://github.com/kinobaihu-design/lol-pick-lab/commit/abc123");
  assert.strictEqual(w.trees.length, 1);
  assert.strictEqual(w.commitBody.message, "Mastery review done on patch 16.21 (admin page)");
  assert.deepStrictEqual(w.commitBody.parents, ["head1"]);
  const written = w.trees[0].tree;
  assert.deepStrictEqual(written.map((t) => t.path).sort(), ["scoring/review.json", "site/data/review.json"]);
  for (const entry of written) {
    assert.deepStrictEqual(JSON.parse(entry.content), { last_mastery_review_patch: "16.21" });
  }
  assert.strictEqual(w.trees[0].base_tree, "tree0");
  assert.strictEqual(w.refUpdates, 1);
  assert.strictEqual(w.refBody.force, false);
  assert.strictEqual(githubCalls(w).filter((c) => c.method === "POST" && c.url.endsWith("/git/commits")).length, 1);
  assert.deepStrictEqual(w.sleeps, []);
});

test("only the two review files may be changed", async () => {
  const w = fakeWorld();
  const ok = { "scoring/review.json": "{}", "site/data/review.json": "{}" };
  const bad = [
    { "scoring/review.json": "{}", "site/data/review.json": "{}", "collector/main.py": "x" },
    { "scoring/review.json": "{}", "scoring/config.py": "x" },
    { "scoring/review.json": "{}" },
    { ".github/workflows/collect.yml": "x", "site/data/review.json": "{}" }
  ];
  for (const files of bad) {
    await assert.rejects(A.commitFiles(w.fetch, "t", files, "m"), /may change only/);
  }
  assert.strictEqual(w.calls.length, 0);
  await A.commitFiles(w.fetch, "t", ok, "m");
  assert.strictEqual(w.calls.length > 0, true);
});

test("GitHub key expired or invalid gives the clear message", async () => {
  const w = fakeWorld({ githubStatus: 401 });
  const out = await A.handle(post(ENV.ADMIN_PASSWORD), ENV, w.deps);
  assert.strictEqual(out.body.message, "GitHub key expired or invalid: make a new one");
});

test("GitHub key without write permission says what to check", async () => {
  const w = fakeWorld({ githubStatus: 403 });
  const out = await A.handle(post(ENV.ADMIN_PASSWORD), ENV, w.deps);
  assert.match(out.body.message, /Contents = Read and write/);
});

test("secrets never appear in an answer", async () => {
  for (const options of [{}, { githubStatus: 401 }, { dataDown: true }]) {
    const w = fakeWorld(options);
    const text = JSON.stringify(await A.handle(post(ENV.ADMIN_PASSWORD), ENV, w.deps));
    assert.ok(text.indexOf(ENV.ADMIN_PASSWORD) < 0 && text.indexOf(ENV.GITHUB_TOKEN) < 0);
  }
});
