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
  assert.deepStrictEqual([l.low, l.medium, l.high], [1000, 10000, 30000]);   // v0.39: Low under 10,000, Medium 10,000-29,999, High 30,000+
});

const L = S.SAMPLE_SIZE_LIMITS;

test("sample-size label follows the v0.39 limits at the edges", () => {
  assert.strictEqual(F.sampleLabel(999, L), "Very low");
  assert.strictEqual(F.sampleLabel(1000, L), "Low");
  assert.strictEqual(F.sampleLabel(3000, L), "Low");              // was Medium before v0.39
  assert.strictEqual(F.sampleLabel(9999, L), "Low");
  assert.strictEqual(F.sampleLabel(10000, L), "Medium");
  assert.strictEqual(F.sampleLabel(29999, L), "Medium");
  assert.strictEqual(F.sampleLabel(30000, L), "High");
  assert.strictEqual(F.sampleLabel(105238, L), "High");
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

test("'skill pays off' is compact and shows only with 20 or more bot-lane OTP games", () => {
  const min = S.OTP_MIN_GAMES_SHOWN;
  assert.strictEqual(F.skillPaysOffText({ otp_games: 19, otp_delta: 6, otp_players: 3 }, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 0, otp_delta: null }, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 340, otp_delta: null }, min), "");
  assert.strictEqual(F.skillPaysOffText(undefined, min), "");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 340, otp_delta: 4.62, otp_players: 12 }, min), "OTP +4.6% \u00b7 12 OTPs \u00b7 340 games");
  assert.strictEqual(F.skillPaysOffText({ otp_games: 1442, otp_delta: -1.4, otp_players: 1 }, min), "OTP \u22121.4% \u00b7 1 OTP \u00b7 1,442 games");
  assert.ok(F.skillPaysOffText({ otp_games: 20, otp_delta: 1, otp_players: 2 }, min).length < 45);
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
    { name: "B", mastery: "good", comfort: 80, comfort_parts: { main_points: 90, secondary_bonus: 0, type_points: 90, mastery_points: 80, base: 80, trait_score: 10, kit_adjustment: 1, difficulty: 2, difficulty_adjustment: 0, range_adjustment: 0.5, flexibility_bonus: 0 } },
    { name: "A", mastery: "main", comfort: 90, comfort_parts: { main_points: 100, secondary_bonus: 1, type_points: 101, mastery_points: 100, base: 95, trait_score: 15, kit_adjustment: 3, difficulty: 1, difficulty_adjustment: 3, range_adjustment: -0.5, flexibility_bonus: 0.5 } }
  ];
  Object.keys(F.COMFORT_COLUMNS).forEach(key => {
    const desc = F.sortRows(list, key, "desc", F.COMFORT_COLUMNS).map(c => c.name).join("");
    const asc = F.sortRows(list, key, "asc", F.COMFORT_COLUMNS).map(c => c.name).join("");
    assert.strictEqual(desc.split("").reverse().join(""), asc, key);
    assert.ok(["asc", "desc"].includes(F.firstDirection(key, F.COMFORT_COLUMNS)));
  });
  assert.strictEqual(F.sortRows(list, "c_comfort", "desc", F.COMFORT_COLUMNS).map(c => c.name).join(""), "AB");
  assert.strictEqual(F.sortRows(list, "difficulty", "asc", F.COMFORT_COLUMNS).map(c => c.name).join(""), "AB");   // easiest first
});

test("colored boxes use the tier steps: 0.5 and 1.5 spreads from the average", () => {
  const steps = S.SPREAD_STEPS;
  assert.deepStrictEqual(steps, { mild: 0.5, strong: 1.5 });
  const at = z => F.spreadStep(50 + 10 * z, 50, 10, steps);
  assert.strictEqual(at(2), 2);
  assert.strictEqual(at(1.5), 2);
  assert.strictEqual(at(1.49), 1);
  assert.strictEqual(at(0.5), 1);
  assert.strictEqual(at(0.49), 0);
  assert.strictEqual(at(0), 0);
  assert.strictEqual(at(-0.49), 0);
  assert.strictEqual(at(-0.5), -1);
  assert.strictEqual(at(-1.49), -1);
  assert.strictEqual(at(-1.5), -2);
  assert.strictEqual(F.spreadStep(10, 50, 0, steps), 0);          // no spread at all: everyone is average
  assert.strictEqual(F.stepClass(2), "box box-p2");
  assert.strictEqual(F.stepClass(-1), "box box-n1");
  assert.strictEqual(F.stepClass(0), "box box-0");
  const ms = F.meanAndSpread([2, 4, 4, 4, 5, 5, 7, 9]);
  assert.strictEqual(ms.mean, 5);
  assert.strictEqual(ms.spread, 2);
});

test("card-only information is read straight from the cards, whatever the scores file says", () => {
  const cards = [{ name: "Kai'Sa", riot_name: "Kaisa", kind: "ADC", main_type: "hypercarry", main_strength: "mid", mastery: "average",
                   traits: { aoe: "low" }, secondary_types: [{ type: "mobility", strength: "mid" }], difficulty: { riot: 2, mine: 2 },
                   range: "medium", flexible_build: false }];
  const rows = [{ name: "Kai'Sa", riot_name: "Kaisa", mastery: "never_played", traits: {}, main_type: null },
                { name: "Someone", riot_name: "Someone", mastery: "good" }];
  assert.strictEqual(F.applyCards(rows, cards), 1);
  assert.strictEqual(rows[0].mastery, "average");
  assert.deepStrictEqual(rows[0].traits, { aoe: "low" });
  assert.strictEqual(rows[0].main_type, "hypercarry");
  assert.strictEqual(F.mainTypeText(rows[0]), "Hypercarry (Mid)");
  assert.strictEqual(F.secondaryTypeText(rows[0]), "Mobility (Mid)");
  assert.strictEqual(rows[0].card_info.difficulty_mine, 2);
  assert.strictEqual(rows[1].mastery, "good");                       // no card: left as it was
  assert.strictEqual(F.applyCards(rows, []), 0);
});

test("patch mix line uses the real range of this patch's share", () => {
  const list = [];
  for (let i = 0; i < 10; i++) list.push({ this_patch_share: 0.5 + i * 0.05 });     // 50% ... 95%
  const mix = F.patchMix(list);
  assert.deepStrictEqual(mix, { low: 55, high: 95, min: 50, max: 95 });
  assert.strictEqual(F.patchMixText("16.20", mix), "Patch 16.20 \u00b7 most champions 55\u201395% this patch");
  assert.strictEqual(F.patchMixText("16.20", null), "Patch 16.20");
  assert.strictEqual(F.patchMix([{}]), null);
});

test("best reachable tier is told only for champions that can't reach A at Main", () => {
  assert.strictEqual(F.bestReachText({ best_tier_at_main: "B" }), "Best reachable: B at Main");
  assert.strictEqual(F.bestReachText({ best_tier_at_main: "C" }), "Best reachable: C at Main");
  assert.strictEqual(F.bestReachText({ best_tier_at_main: "A" }), "");
  assert.strictEqual(F.bestReachText({ best_tier_at_main: "S" }), "");
  assert.strictEqual(F.bestReachText({}), "");
});

test("Utopy table: skill line, the reason a champion has no score, and the grey row numbers", () => {
  assert.strictEqual(F.utopySkillText({ otp_delta: 4.6, otp_games: 340, otp_players: 12 }, 20), "OTP +4.6% · 12 OTPs · 340 games");
  assert.strictEqual(F.utopySkillText({ otp_delta: 4.6, otp_games: 5, otp_players: 2 }, 20), "too few games");
  assert.strictEqual(F.utopySkillText(undefined, 20), "too few games");
  // the two parts the table styles: bold percent (green or red by sign) and the quiet rest
  const up = F.skillParts({ otp_delta: 4.6, otp_games: 340, otp_players: 12 }, 20);
  assert.deepStrictEqual([up.percent, up.rest, up.delta > 0], ["OTP +4.6%", "12 OTPs · 340 games", true]);
  const down = F.skillParts({ otp_delta: -1.2, otp_games: 1500, otp_players: 1 }, 20);
  assert.deepStrictEqual([down.percent, down.rest, down.delta < 0], ["OTP −1.2%", "1 OTP · 1,500 games", true]);
  assert.strictEqual(F.skillParts({ otp_delta: 4.6, otp_games: 5, otp_players: 2 }, 20), null);
  assert.strictEqual(F.skillParts(undefined, 20), null);
  assert.strictEqual(F.utopyReason(["bot-lane share under 10%", "bot-lane pick rate under 0.8%"]), "share under 10%, pick rate under 0.8%");
  assert.strictEqual(F.utopyReason(["bot-lane pick rate under 0.8%"]), "pick rate under 0.8%");
  assert.strictEqual(F.utopyReason(["under 1000 real games", "bot-lane pick rate under 0.8%"]), "low data");
  assert.strictEqual(F.utopyReason([]), "not ranked");
  assert.strictEqual(F.utopyUnrankedNumbers({ real_games_this_patch: 3851, real_games: 9000, pick_rate: 0.0042 }), "3,851 games this patch · pick rate 0.4%");
  assert.strictEqual(F.utopyUnrankedNumbers({ real_games: 120, pick_rate: null }), "120 games this patch · pick rate n/a");
});

test("Utopy table sorts by every column, opens on Main, and grey rows always stay last", () => {
  const sc = (n, b, a, g, m) => ({ never_played: { score: n }, below_average: { score: b }, average: { score: a }, good: { score: g }, main: { score: m } });
  const list = [
    { name: "Kai", scores: sc(60, 65, 70, 75, 80), skill_delta: 3 },
    { name: "Zed", scores: sc(50, 55, 60, 65, 90), skill_delta: null },
    { name: "Bob", scores: sc(70, 71, 72, 73, 74), skill_delta: 1 },
    { name: "Grey", unranked: true, skill_delta: null }
  ];
  const by = (k, d) => F.sortRows(list, k, d, F.UTOPY_COLUMNS, t => (t.unranked ? -1 : t.scores.main.score)).map(t => t.name).join("");
  assert.strictEqual(F.firstDirection("u_main", F.UTOPY_COLUMNS), "desc");
  assert.strictEqual(by("u_main", "desc"), "ZedKaiBobGrey");            // the default: score at Main, highest first
  assert.strictEqual(by("u_main", "asc"), "BobKaiZedGrey");
  assert.strictEqual(by("u_never_played", "desc"), "BobKaiZedGrey");
  assert.strictEqual(by("u_below_average", "desc"), "BobKaiZedGrey");
  assert.strictEqual(by("u_average", "desc"), "BobKaiZedGrey");
  assert.strictEqual(by("u_good", "desc"), "KaiBobZedGrey");
  assert.strictEqual(by("u_champion", "asc"), "BobKaiZedGrey");
  assert.strictEqual(by("u_champion", "desc"), "ZedKaiBobGrey");
  assert.strictEqual(by("u_skill", "desc"), "KaiBobZedGrey");
  assert.deepStrictEqual(Object.keys(F.UTOPY_COLUMNS), ["u_champion", "u_never_played", "u_below_average", "u_average", "u_good", "u_main", "u_skill"]);
});

test("mastery review: grey up to 4 patches, amber at 5, red at 6 or more", () => {
  const r = (now) => F.masteryReview("16.20", now);
  assert.deepStrictEqual(r("16.20"), { level: "quiet", text: "Last mastery review: patch 16.20" });
  assert.strictEqual(r("16.24").level, "quiet");
  assert.strictEqual(r("16.24").text, "Last mastery review: patch 16.20");
  assert.deepStrictEqual(r("16.25"), { level: "warn", text: "Mastery review due soon (5 patches since 16.20)" });
  assert.deepStrictEqual(r("16.26"), { level: "bad", text: "Mastery review overdue (6 patches since 16.20)" });
  assert.strictEqual(r("16.31").text, "Mastery review overdue (11 patches since 16.20)");
});

test("mastery review: a new season is red, an unknown patch is a grey line with no count and no error", () => {
  assert.deepStrictEqual(F.masteryReview("16.20", "17.2"), { level: "bad", text: "New season: mastery review due" });
  for (const unknown of [undefined, null, "", "soon", "16"]) {
    assert.deepStrictEqual(F.masteryReview("16.20", unknown), { level: "quiet", text: "Last mastery review: patch 16.20" });
  }
  assert.strictEqual(F.masteryReview(null, "16.25").level, "quiet");
  assert.strictEqual(F.masteryReview("16.20", "16.18").level, "quiet");   // a review "from the future" never nags
});
