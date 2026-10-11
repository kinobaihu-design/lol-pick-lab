// Settings for the tier list page. Change numbers here, not in the page code.
// No secrets belong in this folder: the page only reads the finished scores file.
(function (root) {
  var SETTINGS = {
    // Where the page reads the scores from: the file the collector saves on the `data` branch.
    DATA_URL: "https://raw.githubusercontent.com/kinobaihu-design/lol-pick-lab/data/scores/latest.json",
    // A saved copy shipped with the page, used only when DATA_URL can't be reached (the page says so).
    FALLBACK_URL: "data/latest.json",
    // Sample-size labels, by real games (this patch + last patch together). The label itself
    // arrives in slice 2; the limits live here so they can be retuned in one place.
    SAMPLE_SIZE_LIMITS: { low: 1000, medium: 3000, high: 10000 },
    // The collector saves every 6 hours; if the scores are older than this, the page warns.
    STALE_AFTER_HOURS: 13
  };
  if (typeof module !== "undefined" && module.exports) module.exports = SETTINGS;
  else root.SETTINGS = SETTINGS;
})(typeof window !== "undefined" ? window : this);
