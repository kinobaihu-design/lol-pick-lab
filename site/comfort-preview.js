// A copy of the Comfort maths (scoring/comfort.py and scoring/config.py) for the hidden admin page's live
// preview. Tests run it next to the Python code for every card and fail if the two ever disagree.
(function (root) {
  var C = {
    TYPE_POINTS: { mobility: 100, peel: 90, hypercarry: 80, utility: 80, mage: 70, lane_bully: 70 },
    STRENGTH: { high: 1.0, mid: 0.975, low: 0.95 },
    SECONDARY_SHARE: 0.20,
    MASTERY_POINTS: { main: 100, good: 90, average: 80, below_average: 70, never_played: 60 },
    MASTERY_DIFFICULTY_FACTOR: { main: 0.20, good: 0.40, average: 0.60, below_average: 0.80, never_played: 1.0 },
    MASTERY_FLEXIBILITY_FACTOR: { main: 1.0, good: 0.75, average: 0.50, below_average: 0.25, never_played: 0.0 },
    COMFORT_TYPE_SHARE: 0.4,
    COMFORT_MASTERY_SHARE: 0.6,
    COMFORT_CAP: 100,
    TRAIT_PRIORITY: { wave_clear: 3, team_utility: 3, aoe: 3, cc: 2, sustain: 2, burst: 2, poke: 2, vision: 1 },
    TRAIT_LEVEL: { low: 0.5, mid: 1.0, high: 1.5 },
    KIT_WEIGHT: 0.9,
    KIT_CAP: 5.0,
    MIN_CARDS_FOR_TRAIT_AVERAGE: 10,
    DIFFICULTY_WEIGHT: 3.0,
    DIFFICULTY_CAP: 3.0,
    DIFFICULTY_MIDDLE: 2.0,
    DIFFICULTY_MINE_SHARE: 0.8,
    DIFFICULTY_RIOT_SHARE: 0.2,
    RANGE_ADJUSTMENT: { short: -0.5, medium: 0.0, long: 0.5 },
    FLEXIBILITY_BONUS: 1.0
  };

  function normalise(name) { return String(name).toLowerCase().replace(/[^a-z0-9]/g, ""); }

  function traitScore(card) {
    var sum = 0;
    Object.keys(card.traits || {}).forEach(function (t) { sum += C.TRAIT_PRIORITY[t] * C.TRAIT_LEVEL[card.traits[t]]; });
    return sum;
  }

  function typePoints(card) {
    var main = C.TYPE_POINTS[card.main_type] * C.STRENGTH[card.main_strength];
    var best = 0;
    (card.secondary_types || []).forEach(function (s) { best = Math.max(best, C.TYPE_POINTS[s.type] * C.STRENGTH[s.strength]); });
    return main + (best > main ? C.SECONDARY_SHARE * (best - main) : 0);
  }

  function comfort(card, traitAverage, mastery) {
    mastery = mastery || card.mastery;
    var base = C.COMFORT_TYPE_SHARE * typePoints(card) + C.COMFORT_MASTERY_SHARE * C.MASTERY_POINTS[mastery];
    var kit = Math.max(-C.KIT_CAP, Math.min(C.KIT_CAP, C.KIT_WEIGHT * (traitScore(card) - traitAverage)));
    var difficulty = C.DIFFICULTY_MINE_SHARE * card.difficulty.mine + C.DIFFICULTY_RIOT_SHARE * card.difficulty.riot;
    var diff = Math.max(-C.DIFFICULTY_CAP, Math.min(C.DIFFICULTY_CAP,
      -C.DIFFICULTY_WEIGHT * (difficulty - C.DIFFICULTY_MIDDLE) * C.MASTERY_DIFFICULTY_FACTOR[mastery]));
    var range = C.RANGE_ADJUSTMENT[card.range];
    var flex = card.flexible_build ? C.FLEXIBILITY_BONUS * C.MASTERY_FLEXIBILITY_FACTOR[mastery] : 0;
    return Math.min(C.COMFORT_CAP, base + kit + diff + range + flex);
  }

  // The trait average the scoring uses: the mean over the ranked champions that have a card (their riot_names
  // in `rankedNames`); with fewer than 10 of them, the mean over all cards.
  function traitAverage(cards, rankedNames) {
    var ranked = {};
    (rankedNames || []).forEach(function (n) { ranked[normalise(n)] = true; });
    var scores = cards.filter(function (c) { return ranked[normalise(c.riot_name)]; }).map(traitScore);
    if (scores.length < C.MIN_CARDS_FOR_TRAIT_AVERAGE) scores = cards.map(traitScore);
    var total = 0;
    scores.forEach(function (s) { total += s; });
    return total / scores.length;
  }

  // Returns a copy of the card with one change: field "mastery", or a trait key with a level ("none" removes it).
  function withChange(card, field, value) {
    var copy = JSON.parse(JSON.stringify(card));
    if (field === "mastery") copy.mastery = value;
    else if (value === "none") delete copy.traits[field];
    else copy.traits[field] = value;
    return copy;
  }

  // Comfort and trait average before and after the given changes ([{field, value}, ...]) to one card.
  function preview(cards, rankedNames, name, changes) {
    var index = -1;
    cards.forEach(function (c, i) { if (c.name === name) index = i; });
    var edited = cards[index];
    changes.forEach(function (c) { edited = withChange(edited, c.field, c.value); });
    var after = cards.slice();
    after[index] = edited;
    var avgBefore = traitAverage(cards, rankedNames);
    var avgAfter = traitAverage(after, rankedNames);
    return {
      comfortBefore: comfort(cards[index], avgBefore),
      comfortAfter: comfort(edited, avgAfter),
      traitAverageBefore: avgBefore,
      traitAverageAfter: avgAfter
    };
  }

  var api = { CONFIG: C, normalise: normalise, traitScore: traitScore, comfort: comfort, traitAverage: traitAverage, preview: preview };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ComfortPreview = api;
})(typeof window !== "undefined" ? window : this);
