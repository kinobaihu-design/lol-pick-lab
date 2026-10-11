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
  assert.strictEqual(F.otpText({ otp_players: 10, otp_games: 617 }), "10 OTP players, 617 bot-lane games");
  assert.strictEqual(F.otpText({ otp_players: 1, otp_games: 1 }), "1 OTP player, 1 bot-lane game");
  assert.strictEqual(F.otpText({ otp_players: 2, otp_games: 2, otp_games_all_roles: 120 }),
    "2 OTP players, 2 bot-lane games (120 games on it in all roles)");
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

// ---- slice 3 (v0.37) ----

test("OTP win rate shows 'too few games' below the minimum, and the minimum is one setting (20)", () => {
  const min = S.OTP_MIN_GAMES_SHOWN;
  assert.strictEqual(min, 20);
  assert.strictEqual(F.otpWinRateText({ otp_win_rate: 55.4, otp_games: 19 }, min), "too few games");
  assert.strictEqual(F.otpWinRateText({ otp_win_rate: 0, otp_games: 2 }, min), "too few games");   // Mel showed 0.0% from 2 games
  assert.strictEqual(F.otpWinRateText({ otp_win_rate: null, otp_games: 0 }, min), "too few games");
  assert.strictEqual(F.otpWinRateText({ otp_win_rate: 55.4, otp_games: 20 }, min), "55.4%");
  assert.strictEqual(F.otpWinRateText({ otp_win_rate: 55.44, otp_games: 1442 }, min), "55.4%");
});

test("'skill pays off' shows only with 20 or more bot-lane OTP games", () => {
  const min = S.OTP_MIN_GAMES_SHOWN;
  assert.strictEqual(F.skillPaysOffText({ otp_games: 19, otp_delta: 6 }, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 0, otp_delta: null }, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 340, otp_delta: null }, min), "");
  assert.strictEqual(F.skillPaysOffText(undefined, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 340, otp_delta: 6.04 }, min),
    "OTPs win +6.0% more than average players (340 OTP games) → mastering it pays off");
  assert.ok(F.skillPaysOffText({ otp_games: 20, otp_delta: 1 }, min).includes("pays off"));
  assert.ok(F.skillPaysOffText({ otp_games: 100, otp_delta: -2 }, min).includes("less than average players"));
  assert.ok(!F.skillPaysOffText({ otp_games: 100, otp_delta: -2 }, min).includes("pays off"));
  assert.strictEqual(F.skillDelta({ otp_games: 19, otp_delta: 6 }, min), null);
  assert.strictEqual(F.skillDelta({ otp_games: 20, otp_delta: 6 }, min), 6);
});

const META_LIST = [
  { name: "Carded", has_card: true, meta_score: 70, win_rate_points: 60, pick_rate_points: 90, win_rate: 52, win_rate_delta: 2, pick_rate: 0.1, real_games: 9000 },
  { name: "Nocard B", has_card: false, label: "no card yet", meta_score: 80, win_rate_points: 90, pick_rate_points: 30, win_rate: 54, win_rate_delta: 4, pick_rate: 0.01, real_games: 2000 },
  { name: "Nocard A", has_card: false, label: "no card yet", meta_score: 60, win_rate_points: 50, pick_rate_points: 70, win_rate: 50, win_rate_delta: 0, pick_rate: 0.05, real_games: 4000 },
  { name: "Nocard C", has_card: false, label: "no card yet", meta_score: 75, win_rate_points: 80, pick_rate_points: 50, win_rate: 53, win_rate_delta: 3, pick_rate: 0.03, real_games: 3000 }
];

test("Needs a card: only uncarded champions, best Meta Score first, input untouched", () => {
  assert.deepStrictEqual(F.needsCard(META_LIST).map(c => c.name), ["Nocard B", "Nocard C", "Nocard A"]);
  assert.deepStrictEqual(F.needsCard(META_LIST.filter(c => c.has_card)), []);
  assert.strictEqual(META_LIST.length, 4);
});

test("Meta tab sorts by Meta Score with uncarded champions included, and by every column", () => {
  const by = (key, dir) => F.sortRows(META_LIST, key, dir, F.META_COLUMNS, c => c.meta_score).map(c => c.name);
  assert.deepStrictEqual(by("meta_score", "desc"), ["Nocard B", "Nocard C", "Carded", "Nocard A"]);
  assert.deepStrictEqual(by("meta_rank", "desc"), ["Nocard B", "Nocard C", "Carded", "Nocard A"]);
  assert.deepStrictEqual(by("meta_score", "asc"), ["Nocard A", "Carded", "Nocard C", "Nocard B"]);
  assert.deepStrictEqual(by("m_champion", "asc"), ["Carded", "Nocard A", "Nocard B", "Nocard C"]);
  assert.deepStrictEqual(by("wr_points", "desc"), ["Nocard B", "Nocard C", "Carded", "Nocard A"]);
  assert.deepStrictEqual(by("pr_points", "desc"), ["Carded", "Nocard A", "Nocard C", "Nocard B"]);
  assert.deepStrictEqual(by("pick_rate", "desc"), ["Carded", "Nocard A", "Nocard C", "Nocard B"]);
  assert.deepStrictEqual(by("games", "asc"), ["Nocard B", "Nocard C", "Nocard A", "Carded"]);
  assert.deepStrictEqual(by("win_rate", "desc"), ["Nocard B", "Nocard C", "Carded", "Nocard A"]);
  assert.deepStrictEqual(by("vs_average", "asc"), ["Nocard A", "Carded", "Nocard C", "Nocard B"]);
});

const CARD = {
  name: "Vayne", mastery: "below_average", main_type: "hypercarry", comfort: 69.9,
  card_info: { main_strength: "high", secondary_types: [{ type: "mobility", strength: "mid" }, { type: "peel", strength: "low" }],
               difficulty_riot: 3, difficulty_mine: 2, range: "medium", flexible_build: false },
  comfort_parts: { type_points: 83.5, main_points: 80, secondary_bonus: 3.5, mastery_points: 70, base: 75.4, trait_score: 7.5,
                   kit_adjustment: -5, difficulty: 2.2, difficulty_adjustment: -0.48, range_adjustment: 0, flexibility_bonus: 0 }
};

test("Comfort tab texts come straight from the card details and the Comfort parts", () => {
  assert.strictEqual(F.mainTypeText(CARD), "Hypercarry (High)");
  assert.strictEqual(F.secondaryTypeText(CARD), "Mobility (Mid), Peel (Low)");
  assert.strictEqual(F.secondaryTypeText({ card_info: { secondary_types: [] } }), "none");
  assert.strictEqual(F.difficultyText(CARD), "3 / 2 → 2.2");
  assert.strictEqual(F.difficultyText({ comfort_parts: { difficulty: 2.6 }, card_info: { difficulty_riot: 3, difficulty_mine: 2.5 } }), "3 / 2.5 → 2.6");
  assert.strictEqual(F.masteryPointsText(CARD), "Below average (70)");
  assert.strictEqual(F.flexText(CARD), "–");
  assert.strictEqual(F.flexText({ comfort_parts: { flexibility_bonus: 0.25 } }), "+0.25");
  // an older scores file without card details still draws
  assert.strictEqual(F.mainTypeText({ main_type: "peel" }), "Peel");
  assert.strictEqual(F.secondaryTypeText({}), "");
});

test("Comfort tab sorts by every column", () => {
  const list = [
    { name: "B", comfort: 80, comfort_parts: { main_points: 90, secondary_bonus: 0, type_points: 90, mastery_points: 80, base: 80, trait_score: 10, kit_adjustment: 1, difficulty: 2, difficulty_adjustment: 0, range_adjustment: 0.5, flexibility_bonus: 0 } },
    { name: "A", comfort: 90, comfort_parts: { main_points: 100, secondary_bonus: 1, type_points: 101, mastery_points: 100, base: 95, trait_score: 15, kit_adjustment: 3, difficulty: 1, difficulty_adjustment: 3, range_adjustment: -0.5, flexibility_bonus: 0.5 } }
  ];
  Object.keys(F.COMFORT_COLUMNS).forEach(key => {
    const col = F.COMFORT_COLUMNS[key];
    const desc = F.sortRows(list, key, "desc", F.COMFORT_COLUMNS).map(c => c.name).join("");
    const asc = F.sortRows(list, key, "asc", F.COMFORT_COLUMNS).map(c => c.name).join("");
    assert.strictEqual(desc.split("").reverse().join(""), asc, key);
    assert.ok(["asc", "desc"].includes(F.firstDirection(key, F.COMFORT_COLUMNS)));
  });
  assert.strictEqual(F.sortRows(list, "c_comfort", "desc", F.COMFORT_COLUMNS).map(c => c.name).join(""), "AB");
  assert.strictEqual(F.sortRows(list, "difficulty", "asc", F.COMFORT_COLUMNS).map(c => c.name).join(""), "AB");   // easiest first
});

test("Growth tips: wording, headline and sorting (empty skill values go last)", () => {
  const tip = { name: "Kalista", kind: "New champion", current_mastery: "never_played", target_mastery: "good",
                pick_score_now: 71, pick_score_at_target: 79, gain: 8, would_rank: 2, tier_at_target: "A" };
  assert.strictEqual(F.growthHeadline(tip), "Kalista: 71.0 → 79.0 if Good");
  assert.ok(F.growthTipText(tip).startsWith("You've never played Kalista, but at Good it would rank #2 this patch"));
  const up = { name: "Jinx", kind: "Upgrade", current_mastery: "good", target_mastery: "main", pick_score_now: 74, pick_score_at_target: 80, gain: 6, would_rank: 1, tier_at_target: "S" };
  assert.ok(F.growthTipText(up).startsWith("You're Good with Jinx; at Main it would go from 74.0 to 80.0"));
  const tips = [
    Object.assign({}, up, { skill_delta: null }),
    Object.assign({}, tip, { skill_delta: 2 }),
    Object.assign({}, up, { name: "Zed", skill_delta: 5 })
  ];
  const by = (key, dir) => F.sortRows(tips, key, dir, F.GROWTH_COLUMNS, t => t.pick_score_at_target).map(t => t.name);
  assert.deepStrictEqual(by("g_skill", "desc"), ["Zed", "Kalista", "Jinx"]);
  assert.deepStrictEqual(by("g_skill", "asc"), ["Kalista", "Zed", "Jinx"]);     // null stays last both ways
  assert.deepStrictEqual(by("g_champion", "asc"), ["Jinx", "Kalista", "Zed"]);
  Object.keys(F.GROWTH_COLUMNS).forEach(key => assert.ok(["asc", "desc"].includes(F.firstDirection(key, F.GROWTH_COLUMNS))));
});
