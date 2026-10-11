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

  // "Low", "Medium" or "High" by real games (this patch + last patch, before any double weight).
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

  // Each sortable column: what to sort by, and which way is the first click ("desc" = best first).
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

  function firstDirection(key) {
    return SORT_COLUMNS[key] ? SORT_COLUMNS[key].first : "desc";
  }

  // Sorted copy of the list. `direction` is "asc" or "desc". Ties keep Pick Score order, then the file's order.
  function sortRows(list, key, direction) {
    var col = SORT_COLUMNS[key] || SORT_COLUMNS.pick_score;
    var sign = direction === "asc" ? 1 : -1;
    return list
      .map(function (c, i) { return { champ: c, i: i }; })
      .sort(function (a, b) {
        var x = col.value(a.champ), y = col.value(b.champ);
        if (x !== y) return x < y ? -sign : sign;
        return (b.champ.pick_score - a.champ.pick_score) || (a.i - b.i);
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
              sortRows: sortRows, firstDirection: firstDirection, SORT_COLUMNS: SORT_COLUMNS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Format = api;
})(typeof window !== "undefined" ? window : this);
