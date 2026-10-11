// The hover texts for the column titles. All of them live here, so they can be updated with every
// model version (currently v0.36). A test checks that the weights written below match the scoring code.
(function (root) {
  var HELP = {
    rank: "Place in the list by Pick Score (1 = best pick). It keeps its number when you sort by another column.",
    champion: "Click a name to see its traits, data and one-trick details.",
    tier: "Follows the Pick Score only, measured in spreads (standard deviations) from this patch's average: S +1.5 or more, A +0.5 to +1.5, B -0.5 to +0.5, C -1.5 to -0.5, D below -1.5. Win rate does not change it.",
    pick_score: "The main number: 0.425 × Stats + 0.525 × Comfort + 0.05 × OTP (42.5%, 52.5% and 5%).",
    comfort: "How much you like and play the champion, from your card. Worth 52.5% of the Pick Score. The dots under it are your mastery, from 1 (Never played) to 5 (Main).",
    stats: "How strong and popular it is in Diamond+ games: 75% win rate points and 25% pick rate points. Worth 42.5% of the Pick Score.",
    otp: "How much better one-tricks do on this champion than average players, ranked 0–100 and pulled toward 50 when there are few OTP games. Worth 5% of the Pick Score. (The games counted are the one-tricks' bot-lane games.)",
    win_rate: "Diamond+ win rate in bot lane. It feeds Stats (75% of Stats). ⚠ = 1.5 points or more below the Diamond+ average: a warning only, the tier does not change.",
    vs_average: "Win rate minus the Diamond+ average. Every point above or below moves the win rate points in Stats by 12.5.",
    games: "Real Diamond+ bot-lane games, this patch and last patch together. Sample size: Low 1,000–2,999, Medium 3,000–9,999, High 10,000+. Not part of the score; a champion needs 1,000 to be ranked."
  };
  if (typeof module !== "undefined" && module.exports) module.exports = HELP;
  else root.HELP = HELP;
})(typeof window !== "undefined" ? window : this);
