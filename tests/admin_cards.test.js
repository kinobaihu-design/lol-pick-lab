// Tests for the card-editing helper, with a fake GitHub (no real calls). Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const A = require("../lib/admin-cards.js");
const R = require("../lib/admin-review.js");

const ENV = { ADMIN_PASSWORD: "correct horse battery staple", GITHUB_TOKEN: "fake-token-for-tests" };
const CARDS_TEXT = fs.readFileSync(path.join(__dirname, "..", "scoring", "cards.json"), "utf8");

// A fake GitHub holding the card file. `options.movesBeforePatch`: how many times main "moves" under us.
function fakeWorld(options) {
  options = options || {};
  const world = { calls: [], sleeps: [], trees: [], commits: [], refUpdates: 0, text: options.text || CARDS_TEXT, head: 1, moves: options.movesBeforePatch || 0 };
  world.fetch = async function (url, init) {
    init = init || {};
    const method = init.method || "GET";
    world.calls.push({ url: url, method: method });
    const reply = (status, data, text) => ({ ok: status >= 200 && status < 300, status: status, json: async () => data, text: async () => text });
    if (options.githubStatus) return reply(options.githubStatus, {});
    const p = url.replace("https://api.github.com/repos/" + A.REPO, "");
    if (p === "/git/ref/heads/main") return reply(200, { object: { sha: "head" + world.head } });
    if (p.indexOf("/contents/scoring/cards.json?ref=head") === 0) return reply(200, {}, world.text);
    if (/^\/git\/commits\/head\d+$/.test(p)) return reply(200, { tree: { sha: "tree0" } });
    if (p === "/git/trees") { world.trees.push(JSON.parse(init.body)); return reply(201, { sha: "tree1" }); }
    if (p === "/git/commits") { const b = JSON.parse(init.body); world.commits.push(b); return reply(201, { sha: "commit" + world.commits.length }); }
    if (p === "/git/refs/heads/main") {
      if (world.moves > 0) { world.moves--; world.head++; if (options.otherEdit) world.text = options.otherEdit(world.text); return reply(422, {}); }
      world.refUpdates++; return reply(200, {});
    }
    return reply(404, {});
  };
  world.sleep = async function (ms) { world.sleeps.push(ms); };
  world.deps = { fetch: world.fetch, sleep: world.sleep };
  return world;
}
const post = (extra) => ({ method: "POST", body: Object.assign({ password: ENV.ADMIN_PASSWORD }, extra) });
const mastery = (champion, from, value) => post({ champion: champion, field: "mastery", from: from, value: value });
const parse = (text) => JSON.parse(text);
const card = (text, name) => parse(text).cards.find((c) => c.name === name);

test("wrong password: waits, says so, reads nothing", async () => {
  const w = fakeWorld();
  const out = await A.handle({ method: "POST", body: { password: "nope", champion: "Jinx", field: "mastery", from: "good", value: "main" } }, ENV, w.deps);
  assert.strictEqual(out.status, 401);
  assert.strictEqual(out.body.message, "Wrong password");
  assert.deepStrictEqual(w.sleeps, [3000]);
  assert.strictEqual(w.calls.length, 0);
});

test("secrets not set yet: 'Admin not set up yet' for both the list and the edit", async () => {
  for (const env of [{}, { ADMIN_PASSWORD: "x" }, { GITHUB_TOKEN: "x" }]) {
    const w = fakeWorld();
    assert.strictEqual((await A.handle(mastery("Jinx", "good", "main"), env, w.deps)).body.message, "Admin not set up yet");
    assert.strictEqual((await A.handle({ method: "GET" }, env, w.deps)).body.message, "Admin not set up yet");
    assert.strictEqual(w.calls.length, 0);
  }
});

test("invalid values, unknown fields and extra fields are refused before anything is read", async () => {
  const bad = [
    { champion: "Jinx", field: "mastery", from: "good", value: "godlike" },
    { champion: "Jinx", field: "mastery", from: "good", value: "good" },          // no change
    { champion: "Jinx", field: "mastery", from: "bogus", value: "main" },
    { champion: "Jinx", field: "aoe", from: "high", value: "huge" },
    { champion: "Jinx", field: "wave", from: "high", value: "low" },               // not a trait
    { champion: "Jinx", field: "difficulty", from: "2", value: "3" },              // not editable
    { champion: "Jinx", field: "main_type", from: "hypercarry", value: "mage" },
    { champion: "Jinx", field: "note", from: "", value: "hi" },
    { champion: "Jinx", field: "__proto__", from: "none", value: "low" },
    { champion: "Jinx", field: "mastery", from: "good", value: "main", note: "sneaky" },   // extra field
    { champion: "Jinx", field: "mastery", from: "good", value: "main", path: "scoring/config.py" },
    { champion: "Jinx", field: "mastery", from: "good", value: ["main"] },
    { champion: 5, field: "mastery", from: "good", value: "main" },
    {}
  ];
  for (const extra of bad) {
    const w = fakeWorld();
    const out = await A.handle(post(extra), ENV, w.deps);
    assert.strictEqual(out.body.ok, false, JSON.stringify(extra));
    assert.strictEqual(out.status, 400, JSON.stringify(extra));
    assert.strictEqual(w.calls.length, 0);
    assert.strictEqual(w.commits.length, 0);
  }
});

test("unknown champion is refused and nothing is written", async () => {
  const w = fakeWorld();
  const out = await A.handle(mastery("Teemo", "good", "main"), ENV, w.deps);
  assert.strictEqual(out.status, 404);
  assert.strictEqual(out.body.message, "Unknown champion");
  assert.strictEqual(w.commits.length, 0);
});

test("a mastery edit: one commit, both card files, right message, review.json untouched", async () => {
  const jinx = card(CARDS_TEXT, "Jinx");
  const w = fakeWorld();
  const out = await A.handle(mastery("Jinx", jinx.mastery, "main"), ENV, w.deps);
  assert.strictEqual(out.status, 200, JSON.stringify(out.body));
  assert.strictEqual(w.commits.length, 1);
  assert.strictEqual(w.commits[0].message, "Card edit: Jinx mastery Good → Main");
  assert.deepStrictEqual(w.trees[0].tree.map((t) => t.path).sort(), ["scoring/cards.json", "site/data/cards.json"]);
  for (const entry of w.trees[0].tree) assert.ok(entry.path.indexOf("review.json") < 0);
  const [a, b] = w.trees[0].tree;
  assert.strictEqual(a.content, b.content);
  assert.strictEqual(card(a.content, "Jinx").mastery, "main");
  assert.strictEqual(out.body.commit_url, "https://github.com/kinobaihu-design/lol-pick-lab/commit/commit1");
  assert.strictEqual(w.refUpdates, 1);
  assert.deepStrictEqual(w.sleeps, []);
});

test("only the one value changes: every other card and field is byte for byte the same", async () => {
  const w = fakeWorld();
  await A.handle(mastery("Jinx", "good", "main"), ENV, w.deps);
  const after = w.trees[0].tree[0].content;
  const oldLines = CARDS_TEXT.split("\n"), newLines = after.split("\n");
  assert.strictEqual(oldLines.length, newLines.length);
  const different = oldLines.map((l, i) => [l, newLines[i]]).filter(([x, y]) => x !== y);
  assert.deepStrictEqual(different, [['   "mastery": "good",', '   "mastery": "main",']]);
});

test("trait edits: change, remove, add (kept in the card's usual order), with readable messages", async () => {
  const sivir = card(CARDS_TEXT, "Sivir");
  assert.strictEqual(sivir.traits.aoe, "high");
  assert.strictEqual(sivir.traits.cc, undefined);
  let w = fakeWorld();
  let out = await A.handle(post({ champion: "Sivir", field: "aoe", from: "high", value: "mid" }), ENV, w.deps);
  assert.strictEqual(w.commits[0].message, "Card edit: Sivir AoE High → Mid");
  assert.strictEqual(card(w.trees[0].tree[0].content, "Sivir").traits.aoe, "mid");
  w = fakeWorld();
  await A.handle(post({ champion: "Sivir", field: "aoe", from: "high", value: "none" }), ENV, w.deps);
  assert.strictEqual(w.commits[0].message, "Card edit: Sivir AoE High → None");
  assert.strictEqual("aoe" in card(w.trees[0].tree[0].content, "Sivir").traits, false);
  w = fakeWorld();
  await A.handle(post({ champion: "Sivir", field: "cc", from: "none", value: "low" }), ENV, w.deps);
  const traits = card(w.trees[0].tree[0].content, "Sivir").traits;
  assert.deepStrictEqual(Object.keys(traits), ["wave_clear", "team_utility", "aoe", "cc", "sustain", "burst", "poke"]);
  assert.strictEqual(w.commits[0].message, "Card edit: Sivir CC None → Low");
});

test("changing a value and changing it back gives the identical file", async () => {
  for (const [name, field, from, value] of [["Jinx", "mastery", "good", "never_played"], ["Sivir", "cc", "none", "high"], ["Sivir", "aoe", "high", "none"], ["Kai'Sa", "burst", "mid", "low"]]) {
    const original = fs.readFileSync(path.join(__dirname, "..", "scoring", "cards.json"), "utf8");
    const start = card(original, name);
    const was = field === "mastery" ? start.mastery : (start.traits[field] || "none");
    if (was !== from) continue;
    const there = A.applyEdit(original, { champion: name, field: field, from: from, value: value });
    assert.notStrictEqual(there, original);
    const back = A.applyEdit(there, { champion: name, field: field, from: value, value: from });
    assert.strictEqual(back, original, name + " " + field);
  }
});

test("someone else changed the card: 'reload and try again', nothing written", async () => {
  const w = fakeWorld();
  const out = await A.handle(mastery("Jinx", "average", "main"), ENV, w.deps);   // the page thought Jinx was Average
  assert.strictEqual(out.status, 409);
  assert.strictEqual(out.body.message, "Someone else changed the cards, reload and try again");
  assert.strictEqual(w.commits.length, 0);
});

test("two quick edits: if main moves, the newest file is read again and the other edit is kept", async () => {
  const w = fakeWorld({
    movesBeforePatch: 1,
    otherEdit: (text) => A.applyEdit(text, { champion: "Sivir", field: "cc", from: "none", value: "high" })   // the other edit lands first
  });
  const out = await A.handle(mastery("Jinx", "good", "main"), ENV, w.deps);
  assert.strictEqual(out.status, 200, JSON.stringify(out.body));
  assert.strictEqual(w.commits.length, 2);                     // first try was rejected, second one went through
  const final = w.trees[1].tree[0].content;
  assert.strictEqual(card(final, "Jinx").mastery, "main");
  assert.strictEqual(card(final, "Sivir").traits.cc, "high");   // nothing overwritten
  assert.strictEqual(w.refUpdates, 1);
});

test("two quick edits to the SAME value: the second one is a clash", async () => {
  const w = fakeWorld({
    movesBeforePatch: 1,
    otherEdit: (text) => A.applyEdit(text, { champion: "Jinx", field: "mastery", from: "good", value: "average" })
  });
  const out = await A.handle(mastery("Jinx", "good", "main"), ENV, w.deps);
  assert.strictEqual(out.status, 409);
  assert.strictEqual(out.body.message, "Someone else changed the cards, reload and try again");
  assert.strictEqual(w.refUpdates, 0);
});

test("GitHub key expired or invalid gives the clear message", async () => {
  const w = fakeWorld({ githubStatus: 401 });
  assert.strictEqual((await A.handle(mastery("Jinx", "good", "main"), ENV, w.deps)).body.message, "GitHub key expired or invalid: make a new one");
  assert.strictEqual((await A.handle({ method: "GET" }, ENV, w.deps)).body.message, "GitHub key expired or invalid: make a new one");
});

test("the list returns the newest cards", async () => {
  const w = fakeWorld();
  const out = await A.handle({ method: "GET" }, ENV, w.deps);
  assert.strictEqual(out.status, 200);
  assert.strictEqual(out.body.cards.length, parse(CARDS_TEXT).cards.length);
  assert.strictEqual(w.commits.length, 0);
});

test("the editor can write only the two card files; the review helper only the two review files", async () => {
  const common = require("../lib/admin-common.js");
  const w = fakeWorld();
  const call = common.github(w.fetch, "t");
  const sets = [
    { "scoring/cards.json": "x" },
    { "scoring/cards.json": "x", "site/data/cards.json": "x", "scoring/review.json": "x" },
    { "scoring/review.json": "x", "site/data/review.json": "x" },
    { "scoring/cards.json": "x", "scoring/config.py": "x" }
  ];
  for (const files of sets) {
    await assert.rejects(common.commitToMain(call, "head1", files, "m", A.CARD_FILES), /may change only/);
  }
  assert.strictEqual(w.commits.length, 0);
  await assert.rejects(R.commitFiles(w.fetch, "t", { "scoring/cards.json": "x", "site/data/cards.json": "x" }, "m"), /may change only/);
});

test("secrets never appear in an answer", async () => {
  for (const options of [{}, { githubStatus: 401 }]) {
    const w = fakeWorld(options);
    const text = JSON.stringify([await A.handle(mastery("Jinx", "good", "main"), ENV, w.deps), await A.handle({ method: "GET" }, ENV, w.deps)]);
    assert.ok(text.indexOf(ENV.ADMIN_PASSWORD) < 0 && text.indexOf(ENV.GITHUB_TOKEN) < 0);
  }
});
