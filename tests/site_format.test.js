// Run with: node --test tests/   (the Python test suite runs this too when Node is installed)
const test = require("node:test");
const assert = require("node:assert");
const F = require("../site/format.js");
const S = require("../site/settings.js");

test("numbers are fixed to the asked digits", () => {
  assert.strictEqual(F.number(82.119, 1), "82.1");
  assert.strictEqual(F.number(50.1, 2), "50.10");
});

test("signed shows + and a real minus sign, and no signed zero", () => {
  assert.strictEqual(F.signed(1.932, 2), "+1.93");
  assert.strictEqual(F.signed(-4.03, 2), "\u22124.03");
  assert.strictEqual(F.signed(-0.001, 2), "0.00");
  assert.strictEqual(F.signed(0, 2), "0.00");
});

test("games get thousands separators", () => {
  assert.strictEqual(F.games(83709), "83,709");
  assert.strictEqual(F.games(950), "950");
});

test("age and stale check", () => {
  const now = "2026-10-11T18:00:00Z";
  assert.strictEqual(F.ageHours("2026-10-11T12:00:00Z", now), 6);
  assert.strictEqual(F.isStale("2026-10-11T12:00:00Z", now, 13), false);
  assert.strictEqual(F.isStale("2026-10-10T12:00:00Z", now, 13), true);
  assert.strictEqual(F.isStale("not a date", now, 13), true);
});

test("age is described in plain words", () => {
  assert.strictEqual(F.describeAge(0.2), "12 min ago");
  assert.strictEqual(F.describeAge(1), "1 hour ago");
  assert.strictEqual(F.describeAge(5.6), "6 hours ago");
  assert.strictEqual(F.describeAge(72), "3 days ago");
  assert.strictEqual(F.describeAge(-1), "just now");
});

test("ranked sorts by Pick Score, highest first, ties keep file order", () => {
  const list = [{ name: "a", pick_score: 60 }, { name: "b", pick_score: 80 },
                { name: "c", pick_score: 60 }, { name: "d", pick_score: 70 }];
  assert.deepStrictEqual(F.ranked(list).map(c => c.name), ["b", "d", "a", "c"]);
  assert.deepStrictEqual(list.map(c => c.name), ["a", "b", "c", "d"]);   // input untouched
});

test("tier text marks the stats floor", () => {
  assert.strictEqual(F.tierText({ tier: "B", tier_capped_by_floor: true }), "B*");
  assert.strictEqual(F.tierText({ tier: "S", tier_capped_by_floor: false }), "S");
});

test("a scores file is recognised, junk is not", () => {
  assert.strictEqual(F.looksLikeScores({ pick_score_list: [], patch: "16.20", generated: "2026-10-11T17:46:32Z" }), true);
  assert.strictEqual(F.looksLikeScores({ patch: "16.20" }), false);
  assert.strictEqual(F.looksLikeScores(null), false);
});

test("the sample-size limits live in settings, in order", () => {
  const l = S.SAMPLE_SIZE_LIMITS;
  assert.deepStrictEqual([l.low, l.medium, l.high], [1000, 3000, 10000]);
});
