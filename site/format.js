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

  // "B*" when the stats floor held the champion down to B.
  function tierText(champ) {
    return champ.tier + (champ.tier_capped_by_floor ? "*" : "");
  }

  function looksLikeScores(data) {
    return !!data && Array.isArray(data.pick_score_list) && typeof data.patch === "string" &&
      typeof data.generated === "string";
  }

  var api = { number: number, signed: signed, games: games, ageHours: ageHours, isStale: isStale,
              describeAge: describeAge, ranked: ranked, tierText: tierText, looksLikeScores: looksLikeScores };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Format = api;
})(typeof window !== "undefined" ? window : this);
