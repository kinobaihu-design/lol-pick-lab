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

test("tier text is just the tier (no star since v0.36)", () => {
  assert.strictEqual(F.tierText({ tier: "B", tier_capped_by_floor: true }), "B");
  assert.strictEqual(F.tierText({ tier: "S" }), "S");
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

const L = S.SAMPLE_SIZE_LIMITS;

test("sample-size label follows the limits at the edges", () => {
  assert.strictEqual(F.sampleLabel(999, L), "Very low");
  assert.strictEqual(F.sampleLabel(1000, L), "Low");
  assert.strictEqual(F.sampleLabel(2999, L), "Low");
  assert.strictEqual(F.sampleLabel(3000, L), "Medium");
  assert.strictEqual(F.sampleLabel(9999, L), "Medium");
  assert.strictEqual(F.sampleLabel(10000, L), "High");
});

test("mastery names and trait badges", () => {
  assert.strictEqual(F.masteryText("below_average"), "Below average");
  assert.strictEqual(F.masteryText("never_played"), "Never played");
  assert.strictEqual(F.masteryText("nope"), "");
  assert.deepStrictEqual(["never_played", "below_average", "average", "good", "main"].map(F.masteryLevel), [1, 2, 3, 4, 5]);
  assert.strictEqual(F.masteryLevel("nope"), 0);
  const list = F.traitList({ vision: "low", wave_clear: "high", cc: "mid", poke: "mid" });
  assert.deepStrictEqual(list.map(t => t.name + " " + t.levelName), ["Wave clear High", "CC Mid", "Poke Mid", "Vision Low"]);
  assert.deepStrictEqual(F.traitList(undefined), []);
});

test("data label is read from the file or worked out", () => {
  assert.strictEqual(F.dataLabel({ data_label: "Data: 96% this patch" }), "Data: 96% this patch");
  assert.strictEqual(F.dataLabel({ this_patch_share: 0.5 }), "Data: 50% this patch");
  assert.strictEqual(F.dataLabel({}), "");
});

test("win rate warning: from the file, or from the limit", () => {
  assert.strictEqual(F.hasWinRateWarning({ win_rate_warning: true, win_rate_delta: 2 }, -1.5), true);
  assert.strictEqual(F.hasWinRateWarning({ win_rate_delta: -1.5 }, -1.5), true);
  assert.strictEqual(F.hasWinRateWarning({ win_rate_delta: -1.49 }, -1.5), false);
  assert.strictEqual(S.WIN_RATE_WARNING_DELTA, -1.5);
});

test("OTP text and not-ranked text", () => {
  assert.strictEqual(F.otpText({ otp_players: 10, otp_games: 617 }), "10 OTP players, 617 OTP games");
  assert.strictEqual(F.otpText({ otp_players: 1, otp_games: 1 }), "1 OTP player, 1 OTP game");
  assert.strictEqual(F.otpText({ otp_players: 0, otp_games: 0 }), "no OTP games yet");
  assert.strictEqual(F.notRankedText({ name: "Senna", failed: ["bot-lane pick rate under 0.8%"] }),
    "Senna: bot-lane pick rate under 0.8%");
  assert.strictEqual(F.notRankedText({ name: "Akshan", failed: ["a", "b"] }), "Akshan: a; b");
  assert.strictEqual(F.notRankedText("Senna"), "Senna");
});

const SORT_LIST = [
  { name: "Bee", tier: "B", mastery: "good", pick_score: 70, comfort: 80, stats: 60, otp_points: 50, win_rate: 51, win_rate_delta: -1, real_games: 5000 },
  { name: "Ace", tier: "A", mastery: "main", pick_score: 80, comfort: 90, stats: 70, otp_points: 55, win_rate: 52, win_rate_delta: 1, real_games: 2000 },
  { name: "Cee", tier: "C", mastery: "never_played", pick_score: 60, comfort: 70, stats: 50, otp_points: 45, win_rate: 50, win_rate_delta: -2, real_games: 9000 }
];
const names = (key, dir) => F.sortRows(SORT_LIST, key, dir).map(c => c.name).join("");

test("sorting: every column, both ways, input untouched", () => {
  assert.strictEqual(names("pick_score", "desc"), "AceBeeCee");
  assert.strictEqual(names("pick_score", "asc"), "CeeBeeAce");
  assert.strictEqual(names("rank", "desc"), "AceBeeCee");
  assert.strictEqual(names("champion", "asc"), "AceBeeCee");
  assert.strictEqual(names("champion", "desc"), "CeeBeeAce");
  assert.strictEqual(names("tier", "desc"), "AceBeeCee");
  assert.strictEqual(names("tier", "asc"), "CeeBeeAce");
  assert.strictEqual(names("mastery", "desc"), "AceBeeCee");
  assert.strictEqual(names("comfort", "desc"), "AceBeeCee");
  assert.strictEqual(names("stats", "asc"), "CeeBeeAce");
  assert.strictEqual(names("otp", "desc"), "AceBeeCee");
  assert.strictEqual(names("win_rate", "desc"), "AceBeeCee");
  assert.strictEqual(names("vs_average", "asc"), "CeeBeeAce");
  assert.strictEqual(names("games", "desc"), "CeeBeeAce");
  assert.strictEqual(names("games", "asc"), "AceBeeCee");
  assert.deepStrictEqual(SORT_LIST.map(c => c.name), ["Bee", "Ace", "Cee"]);
});

test("sorting: ties keep Pick Score order; first click direction per column", () => {
  const tied = [{ name: "x", tier: "A", pick_score: 70 }, { name: "y", tier: "A", pick_score: 75 }, { name: "z", tier: "B", pick_score: 60 }];
  assert.strictEqual(F.sortRows(tied, "tier", "desc").map(c => c.name).join(""), "yxz");
  assert.strictEqual(F.firstDirection("champion"), "asc");
  assert.strictEqual(F.firstDirection("games"), "desc");
  Object.keys(F.SORT_COLUMNS).forEach(k => assert.ok(["asc", "desc"].includes(F.firstDirection(k))));
});
