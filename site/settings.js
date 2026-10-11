// Settings for the tier list page. Change numbers here, not in the page code.
// No secrets belong in this folder: the page only reads the finished scores file.
(function (root) {
  var SETTINGS = {
    // Where the page reads the scores from: the file the collector saves on the `data` branch.
    DATA_URL: "https://raw.githubusercontent.com/kinobaihu-design/lol-pick-lab/data/scores/latest.json",
    // A saved copy shipped with the page, used only when DATA_URL can't be reached (the page says so).
    FALLBACK_URL: "data/latest.json",
    // Sample-size labels, by real games (this patch + last patch together, before any double
    // weight): Low from 1,000, Medium from 3,000, High from 10,000. Retune them here.
    SAMPLE_SIZE_LIMITS: { low: 1000, medium: 3000, high: 10000 },
    // The collector saves every 6 hours; if the scores are older than this, the page warns.
    STALE_AFTER_HOURS: 13,
    // A win rate this many points (or more) below the Diamond+ average gets a warning sign.
    // Display only: it never changes a tier. Used only if the scores file doesn't say.
    WIN_RATE_WARNING_DELTA: -1.5
  };
  if (typeof module !== "undefined" && module.exports) module.exports = SETTINGS;
  else root.SETTINGS = SETTINGS;
})(typeof window !== "undefined" ? window : this);
