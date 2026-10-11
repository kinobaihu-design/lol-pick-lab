// Small helpers that turn the scores file into text for the table (also tested with Node).
(function (root) {
  function number(value, digits) {
    return Number(value).toFixed(digits);
  }

  function signed(value, digits) {
    var n = Number(value);
    var text = Math.abs(n).toFixed(digits);
    if (Number(text) === 0) return text;            // no "+0.00" or "-0.00"
    return (n > 0 ? "+" : "−") + text;
  }

  function games(value) {
    return Math.round(Number(value)).toLocaleString("en-US");
  }

  // Hours between the "generated" time in the file and `now` (both Date or ISO text).
  function ageHours(generated, now) {
    var ms = new Date(now).getTime() - new Date(generated).getTime();
    return ms / 3600000;
  }

  function isStale(generated, now, limitHours) {
    var age = ageHours(generated, now);
    return !(age <= limitHours);                     // an unreadable date also counts as stale
  }

  function describeAge(hours) {
    if (!(hours >= 0)) return "just now";
    if (hours < 1) return Math.max(1, Math.round(hours * 60)) + " min ago";
    if (hours < 48) {
      var h = Math.round(hours);
      return h + (h === 1 ? " hour ago" : " hours ago");
    }
    return Math.round(hours / 24) + " days ago";
  }

  // The ranked list, highest Pick Score first (ties keep the file's order).
  function ranked(list) {
    return list
      .map(function (c, i) { return { champ: c, i: i }; })
      .sort(function (a, b) { return (b.champ.pick_score - a.champ.pick_score) || (a.i - b.i); })
      .map(function (x) { return x.champ; });
  }

  function tierText(champ) {
    return champ.tier;
  }

  // ---- slice 2 ----

  var MASTERY_NAMES = { main: "Main", good: "Good", average: "Average", below_average: "Below average",
                        never_played: "Never played" };
  var MASTERY_ORDER = ["never_played", "below_average", "average", "good", "main"];   // weak to strong
  var TRAIT_ORDER = ["wave_clear", "team_utility", "aoe", "cc", "sustain", "burst", "poke", "vision"];
  var TRAIT_NAMES = { wave_clear: "Wave clear", team_utility: "Team utility", aoe: "AoE", cc: "CC",
                      sustain: "Sustain", burst: "Burst", poke: "Poke", vision: "Vision" };
  var LEVEL_NAMES = { low: "Low", mid: "Mid", high: "High" };
  var TIER_ORDER = ["D", "C", "B", "A", "S"];                                          // weak to strong

  function masteryText(key) {
    return MASTERY_NAMES[key] || "";
  }

  // 1 (Never played) to 5 (Main); 0 when unknown.
  function masteryLevel(key) {
    return MASTERY_ORDER.indexOf(key) + 1;
  }

  // The traits that exist on the card, in the owner's priority order, with their level.
  function traitList(traits) {
    var out = [];
    TRAIT_ORDER.forEach(function (key) {
      var level = traits && traits[key];
      if (level) out.push({ key: key, name: TRAIT_NAMES[key], level: level, levelName: LEVEL_NAMES[level] || level });
    });
    return out;
  }

  // "Low" (under the medium limit), "Medium" or "High" by real games (this patch + last patch, before any double weight).
  // Below the Low limit the sample is "Very low" (such champions are normally not ranked at all).
  function sampleLabel(realGames, limits) {
    var n = Number(realGames);
    if (n >= limits.high) return "High";
    if (n >= limits.medium) return "Medium";
    if (n >= limits.low) return "Low";
    return "Very low";
  }

  // "Data: 96% this patch". The scores file writes it; if it is missing, work it out.
  function dataLabel(champ) {
    if (champ.data_label) return champ.data_label;
    if (typeof champ.this_patch_share === "number") return "Data: " + Math.round(100 * champ.this_patch_share) + "% this patch";
    return "";
  }

  // A win rate this far (or more) below the Diamond+ average gets a warning sign (display only).
  function hasWinRateWarning(champ, limit) {
    if (typeof champ.win_rate_warning === "boolean") return champ.win_rate_warning;
    return Number(champ.win_rate_delta) <= limit;
  }

  // What the OTP numbers count: the one-tricks' BOT-LANE games on the champion (the rule that makes
  // someone a one-trick looks at all roles, so they may have many more games on it elsewhere).
  function otpText(champ) {
    var players = champ.otp_players || 0, games = champ.otp_games || 0;
    var text = players + (players === 1 ? " OTP player" : " OTP players") + ", " +
      Math.round(games).toLocaleString("en-US") + (games === 1 ? " bot-lane game" : " bot-lane games");
    if (champ.otp_games_all_roles) {
      text += " (" + Math.round(champ.otp_games_all_roles).toLocaleString("en-US") + " games on it in all roles)";
    }
    return text;
  }

  // One text for a card that missed the filters: "Senna: bot-lane pick rate under 0.8%".
  // Older score files only list the names.
  function notRankedText(entry) {
    if (typeof entry === "string") return entry;
    var why = entry.failed && entry.failed.length ? entry.failed.join("; ") : "did not pass the filters";
    return entry.name + ": " + why;
  }

  // ---- slice 3: tabs ----

  var TYPE_NAMES = { mobility: "Mobility", peel: "Peel", hypercarry: "Hypercarry", utility: "Utility",
                     mage: "Mage", lane_bully: "Lane bully" };
  var STRENGTH_NAMES = { high: "High", mid: "Mid", low: "Low" };
  var RANGE_NAMES = { short: "Short", medium: "Medium", long: "Long" };

  function typeText(key) {
    return TYPE_NAMES[key] || "";
  }

  // "Peel (High)"; empty when the file has no card details.
  function mainTypeText(champ) {
    var info = champ.card_info;
    if (!info || !champ.main_type) return champ.main_type ? typeText(champ.main_type) : "";
    return typeText(champ.main_type) + " (" + (STRENGTH_NAMES[info.main_strength] || info.main_strength) + ")";
  }

  // "Utility (Mid)", or "Mobility (Mid), Peel (Low)" with two; "none" when there is no secondary type.
  function secondaryTypeText(champ) {
    var info = champ.card_info;
    if (!info) return "";
    var list = info.secondary_types || [];
    if (!list.length) return "none";
    return list.map(function (s) { return typeText(s.type) + " (" + (STRENGTH_NAMES[s.strength] || s.strength) + ")"; }).join(", ");
  }

  // 2 -> "2", 2.5 -> "2.5"
  function plain(value) {
    return String(Number(Number(value).toFixed(2)));
  }

  // "3 / 2 \u2192 2.2": Riot's rating, the owner's rating, and the final difficulty used in Comfort.
  function difficultyText(champ) {
    var info = champ.card_info, parts = champ.comfort_parts;
    if (!parts) return "";
    var final = Number(parts.difficulty).toFixed(1);
    if (!info) return "\u2192 " + final;
    return plain(info.difficulty_riot) + " / " + plain(info.difficulty_mine) + " \u2192 " + final;
  }

  function masteryPointsText(champ) {
    var parts = champ.comfort_parts;
    return masteryText(champ.mastery) + (parts ? " (" + parts.mastery_points + ")" : "");
  }

  // Bonus shown as +1.00; "\u2013" when the card has none.
  function flexText(champ) {
    var f = champ.comfort_parts && champ.comfort_parts.flexibility_bonus;
    return f ? signed(f, 2) : "\u2013";
  }

  // Champions that pass the filters but have no card yet, best Meta Score first.
  function needsCard(list) {
    return list.filter(function (c) { return c.has_card === false; })
      .map(function (c, i) { return { champ: c, i: i }; })
      .sort(function (a, b) { return (b.champ.meta_score - a.champ.meta_score) || (a.i - b.i); })
      .map(function (x) { return x.champ; });
  }

  // OTP win rate, or "too few games" below the minimum number of bot-lane OTP games.
  function otpWinRateText(champ, minGames) {
    if (champ.otp_win_rate === null || champ.otp_win_rate === undefined || !(Number(champ.otp_games) >= minGames)) {
      return "too few games";
    }
    return number(champ.otp_win_rate, 1) + "%";
  }

  // The OTP win rate minus the overall win rate, only with enough bot-lane OTP games; otherwise null.
  function skillDelta(champ, minGames) {
    if (!champ || champ.otp_delta === null || champ.otp_delta === undefined) return null;
    return Number(champ.otp_games) >= minGames ? Number(champ.otp_delta) : null;
  }

  // Compact "skill pays off" line: "OTP +4.6% \u00b7 12 OTPs \u00b7 340 games" (OTP win rate minus the overall
  // win rate). Empty with fewer than minGames bot-lane OTP games. Information only: it never changes a score.
  function skillPaysOffText(champ, minGames) {
    var d = skillDelta(champ, minGames);
    if (d === null) return "";
    var players = champ.otp_players || 0;
    return "OTP " + signed(d, 1) + "% \u00b7 " + players + (players === 1 ? " OTP" : " OTPs") + " \u00b7 " +
      Math.round(champ.otp_games).toLocaleString("en-US") + " games";
  }

  // Growth tip: one plain sentence. `list` is the Pick Score list (to find the champion's OTP numbers).
  function growthTipText(tip) {
    var now = masteryText(tip.current_mastery), target = masteryText(tip.target_mastery);
    var from = number(tip.pick_score_now, 1), to = number(tip.pick_score_at_target, 1);
    if (tip.kind === "New champion") {
      return "You've never played " + tip.name + ", but at " + target + " it would rank #" + tip.would_rank +
        " this patch (" + from + " \u2192 " + to + ", " + tip.tier_at_target + " tier); worth starting.";
    }
    return "You're " + now + " with " + tip.name + "; at " + target + " it would go from " + from + " to " + to +
      " (" + tip.tier_at_target + " tier, #" + tip.would_rank + ").";
  }

  // "Kalista: 71.0 \u2192 79.0 if Good"
  function growthHeadline(tip) {
    return tip.name + ": " + number(tip.pick_score_now, 1) + " \u2192 " + number(tip.pick_score_at_target, 1) +
      " if " + masteryText(tip.target_mastery);
  }

  // ---- v0.38 ----

  function normalise(name) {
    return String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  // The card details the Comfort tab shows next to the Comfort numbers.
  function cardInfo(card) {
    return { main_strength: card.main_strength, secondary_types: card.secondary_types || [],
             difficulty_riot: card.difficulty.riot, difficulty_mine: card.difficulty.mine,
             range: card.range, flexible_build: !!card.flexible_build };
  }

  // Read the card-only information (type, strength, traits, mastery, difficulty, range) straight from
  // the champion cards (data/cards.json), so it never waits for the collector. Rows keep the scores
  // file's own values only when the card can't be found. Returns how many rows were matched.
  function applyCards(rows, cards) {
    var byName = {};
    (cards || []).forEach(function (card) { byName[normalise(card.riot_name)] = card; });
    var matched = 0;
    rows.forEach(function (c) {
      var card = byName[normalise(c.riot_name || c.name)];
      if (!card) return;
      c.mastery = card.mastery;
      c.traits = card.traits || {};
      c.main_type = card.main_type;
      c.kind = card.kind;
      c.card_info = cardInfo(card);
      matched++;
    });
    return matched;
  }

  function meanAndSpread(values) {
    var n = values.length;
    if (!n) return { mean: 0, spread: 0 };
    var mean = values.reduce(function (a, b) { return a + b; }, 0) / n;
    var variance = values.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n;
    return { mean: mean, spread: Math.sqrt(variance) };
  }

  // How far a number is from the average, in the same steps as the tiers: -2 (1.5 spreads or more
  // below), -1 (0.5 or more below), 0 (within 0.5), +1, +2. `steps` = { mild: 0.5, strong: 1.5 }.
  function spreadStep(value, mean, spread, steps) {
    if (!spread) return 0;
    var z = Math.round(((value - mean) / spread) * 100) / 100;       // rounded like the tier spreads
    if (z >= steps.strong) return 2;
    if (z >= steps.mild) return 1;
    if (z <= -steps.strong) return -2;
    if (z <= -steps.mild) return -1;
    return 0;
  }

  function stepClass(step) {
    return "box box-" + (step > 0 ? "p" + step : step < 0 ? "n" + (-step) : "0");
  }

  // "Patch 16.20 \u00b7 most champions 61\u201396% this patch": the middle 80% of champions (10th to 90th
  // percentile of this patch's share), with the full range for the hover text.
  function patchMix(list) {
    var shares = list.map(function (c) { return c.this_patch_share; })
      .filter(function (x) { return typeof x === "number"; }).sort(function (a, b) { return a - b; });
    if (!shares.length) return null;
    var at = function (p) { return shares[Math.min(shares.length - 1, Math.floor(p * shares.length))]; };
    var pct = function (x) { return Math.round(100 * x); };
    return { low: pct(at(0.1)), high: pct(at(0.9)), min: pct(shares[0]), max: pct(shares[shares.length - 1]) };
  }

  function patchMixText(patch, mix) {
    if (!mix) return "Patch " + patch;
    return "Patch " + patch + " \u00b7 most champions " + mix.low + "\u2013" + mix.high + "% this patch";
  }

  // The quiet extra on Growth rows: "at Main: S" (the ceiling; information only, never decides who is listed).
  function ceilingText(champ) {
    return champ && champ.best_tier_at_main ? "at Main: " + champ.best_tier_at_main : "";
  }

  // The one line shown when "Next step to A or S" is empty.
  function closestText(closest) {
    if (!closest) return "None this patch";
    return "None this patch \u00b7 closest: " + closest.name + ", " + number(closest.points_short, 1) + " points short";
  }

  // ---- Utopy picks (v0.40): long-term goals, information only ----
  function stepsText(n) { return n + (n === 1 ? " step" : " steps"); }

  // "68.0 \u2192 78.5 at Main", or "68.0 \u2192 74.1 at Good \u00b7 78.5 at Main" when both levels reach S.
  function utopyScoresText(row) {
    return number(row.pick_score_now, 1) + " \u2192 " + row.scores.map(function (s) {
      return number(s.score, 1) + " at " + masteryText(s.level);
    }).join(" \u00b7 ");
  }

  // The compact skill line, or "too few games" (below the minimum bot-lane OTP games).
  function utopySkillText(champ, minGames) {
    return skillPaysOffText(champ, minGames) || "too few games";
  }

  // The one line shown when "Utopy picks" is empty.
  function utopyClosestText(closest) {
    if (!closest) return "None this patch";
    return "None this patch \u00b7 closest: " + closest.name + ", " + number(closest.points_short, 1) + " points short of S at Main";
  }

  // Hover text on a name in the Tier list for a champion that can't reach A even at Main.
  function bestReachText(champ) {
    if (!champ.best_tier_at_main || champ.best_tier_at_main === "A" || champ.best_tier_at_main === "S") return "";
    return "Best reachable: " + champ.best_tier_at_main + " at Main";
  }

  // Sorting. Each tab has its own columns: what to sort by, and which way is the first click
  // ("desc" = best first). `tie` is the value used to break ties (then the file's order).
  var SORT_COLUMNS = {
    rank:    { first: "desc", value: function (c) { return c.pick_score; } },
    champion:{ first: "asc",  value: function (c) { return c.name.toLowerCase(); } },
    tier:    { first: "desc", value: function (c) { return TIER_ORDER.indexOf(c.tier); }, then: "pick_score" },
    mastery: { first: "desc", value: function (c) { return MASTERY_ORDER.indexOf(c.mastery); }, then: "pick_score" },
    pick_score: { first: "desc", value: function (c) { return c.pick_score; } },
    comfort: { first: "desc", value: function (c) { return c.comfort; } },
    stats:   { first: "desc", value: function (c) { return c.stats; } },
    otp:     { first: "desc", value: function (c) { return c.otp_points; } },
    win_rate:{ first: "desc", value: function (c) { return c.win_rate; } },
    vs_average: { first: "desc", value: function (c) { return c.win_rate_delta; } },
    games:   { first: "desc", value: function (c) { return c.real_games; } }
  };

  var META_COLUMNS = {
    meta_rank:  { first: "desc", value: function (c) { return c.meta_score; } },
    m_champion: { first: "asc",  value: function (c) { return c.name.toLowerCase(); } },
    meta_score: { first: "desc", value: function (c) { return c.meta_score; } },
    wr_points:  { first: "desc", value: function (c) { return c.win_rate_points; } },
    pr_points:  { first: "desc", value: function (c) { return c.pick_rate_points; } },
    win_rate:   SORT_COLUMNS.win_rate,
    vs_average: SORT_COLUMNS.vs_average,
    pick_rate:  { first: "desc", value: function (c) { return c.pick_rate; } },
    games:      SORT_COLUMNS.games
  };

  var COMFORT_COLUMNS = {
    c_champion: { first: "asc", value: function (c) { return c.name.toLowerCase(); } },
    c_comfort: { first: "desc", value: function (c) { return c.comfort; } },
    trait_score: { first: "desc", value: function (c) { return c.comfort_parts.trait_score; } },
    c_mastery: { first: "desc", value: function (c) { return MASTERY_ORDER.indexOf(c.mastery); } },
    main_type: { first: "desc", value: function (c) { return c.comfort_parts.main_points; } },
    secondary_type: { first: "desc", value: function (c) { return c.comfort_parts.secondary_bonus; } },
    type_points: { first: "desc", value: function (c) { return c.comfort_parts.type_points; } },
    mastery_pts: { first: "desc", value: function (c) { return c.comfort_parts.mastery_points; } },
    base:     { first: "desc", value: function (c) { return c.comfort_parts.base; } },
    kit_adj:  { first: "desc", value: function (c) { return c.comfort_parts.kit_adjustment; } },
    difficulty: { first: "asc", value: function (c) { return c.comfort_parts.difficulty; } },
    diff_adj: { first: "desc", value: function (c) { return c.comfort_parts.difficulty_adjustment; } },
    range_adj: { first: "desc", value: function (c) { return c.comfort_parts.range_adjustment; } },
    flex:     { first: "desc", value: function (c) { return c.comfort_parts.flexibility_bonus; } }
  };

  var GROWTH_COLUMNS = {
    g_champion: { first: "asc", value: function (t) { return t.name.toLowerCase(); } },
    g_kind:   { first: "asc", value: function (t) { return t.kind; } },
    g_mastery: { first: "asc", value: function (t) { return MASTERY_ORDER.indexOf(t.current_mastery); } },
    g_score:  { first: "desc", value: function (t) { return t.pick_score_at_target; } },
    g_gain:   { first: "desc", value: function (t) { return t.gain; } },
    g_rank:   { first: "asc", value: function (t) { return t.would_rank; } },
    g_tier:   { first: "desc", value: function (t) { return TIER_ORDER.indexOf(t.tier_at_target); } },
    g_ceiling: { first: "desc", value: function (t) { return TIER_ORDER.indexOf(t.ceiling); } },
    g_skill:  { first: "desc", value: function (t) { return t.skill_delta; } }
  };

  var UTOPY_COLUMNS = {
    u_champion: { first: "asc", value: function (t) { return t.name.toLowerCase(); } },
    u_mastery: { first: "asc", value: function (t) { return MASTERY_ORDER.indexOf(t.current_mastery); } },
    u_level:  { first: "asc", value: function (t) { return MASTERY_ORDER.indexOf(t.first_level); } },
    u_steps:  { first: "asc", value: function (t) { return t.steps; } },
    u_score:  { first: "desc", value: function (t) { return t.scores[t.scores.length - 1].score; } },
    u_skill:  { first: "desc", value: function (t) { return t.skill_delta; } }
  };
  var NEXT_COLUMNS = {
    n_champion: { first: "asc", value: function (t) { return t.name.toLowerCase(); } },
    n_mastery: { first: "asc", value: function (t) { return MASTERY_ORDER.indexOf(t.current_mastery); } },
    n_tier:   { first: "desc", value: function (t) { return TIER_ORDER.indexOf(t.tier_next); } },
    n_score:  { first: "desc", value: function (t) { return t.pick_score_next; } },
    n_gain:   { first: "desc", value: function (t) { return t.gain; } },
    n_ceiling: { first: "desc", value: function (t) { return TIER_ORDER.indexOf(t.ceiling); } },
    n_skill:  { first: "desc", value: function (t) { return t.skill_delta; } }
  };

  function firstDirection(key, columns) {
    var col = (columns || SORT_COLUMNS)[key];
    return col ? col.first : "desc";
  }

  // Sorted copy of the list. `direction` is "asc" or "desc". `columns` is one of the column sets above
  // (default: the tier table's). Empty values (null) always go last. Ties keep `tie` order (default Pick
  // Score, highest first), then the file's order.
  function sortRows(list, key, direction, columns, tie) {
    columns = columns || SORT_COLUMNS;
    var col = columns[key] || columns[Object.keys(columns)[0]];
    var tiebreak = tie || function (c) { return c.pick_score; };
    var sign = direction === "asc" ? 1 : -1;
    return list
      .map(function (c, i) { return { champ: c, i: i }; })
      .sort(function (a, b) {
        var x = col.value(a.champ), y = col.value(b.champ);
        var xEmpty = x === null || x === undefined || x !== x, yEmpty = y === null || y === undefined || y !== y;
        if (xEmpty !== yEmpty) return xEmpty ? 1 : -1;
        if (!xEmpty && x !== y) return x < y ? -sign : sign;
        return (tiebreak(b.champ) - tiebreak(a.champ)) || (a.i - b.i);
      })
      .map(function (x) { return x.champ; });
  }

  function looksLikeScores(data) {
    return !!data && Array.isArray(data.pick_score_list) && typeof data.patch === "string" &&
      typeof data.generated === "string";
  }

  var api = { number: number, signed: signed, games: games, ageHours: ageHours, isStale: isStale,
              describeAge: describeAge, ranked: ranked, tierText: tierText, looksLikeScores: looksLikeScores,
              masteryText: masteryText, masteryLevel: masteryLevel, traitList: traitList, sampleLabel: sampleLabel, dataLabel: dataLabel,
              hasWinRateWarning: hasWinRateWarning, otpText: otpText, notRankedText: notRankedText,
              sortRows: sortRows, firstDirection: firstDirection, SORT_COLUMNS: SORT_COLUMNS,
              META_COLUMNS: META_COLUMNS, COMFORT_COLUMNS: COMFORT_COLUMNS, GROWTH_COLUMNS: GROWTH_COLUMNS, NEXT_COLUMNS: NEXT_COLUMNS, UTOPY_COLUMNS: UTOPY_COLUMNS,
              stepsText: stepsText, utopyScoresText: utopyScoresText, utopySkillText: utopySkillText, utopyClosestText: utopyClosestText,
              normalise: normalise, cardInfo: cardInfo, applyCards: applyCards, meanAndSpread: meanAndSpread,
              spreadStep: spreadStep, stepClass: stepClass, patchMix: patchMix, patchMixText: patchMixText,
              bestReachText: bestReachText, ceilingText: ceilingText, closestText: closestText,
              typeText: typeText, mainTypeText: mainTypeText, secondaryTypeText: secondaryTypeText,
              difficultyText: difficultyText, masteryPointsText: masteryPointsText, flexText: flexText,
              needsCard: needsCard, otpWinRateText: otpWinRateText, skillDelta: skillDelta,
              skillPaysOffText: skillPaysOffText, growthTipText: growthTipText, growthHeadline: growthHeadline };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Format = api;
})(typeof window !== "undefined" ? window : this);
