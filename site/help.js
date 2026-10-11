// The hover texts for the column titles. All of them live here, so they can be updated with every
// model version (currently v0.39). A test checks that the weights written below match the scoring code.
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
    games: "Real Diamond+ bot-lane games, this patch and last patch together. Sample size: Low under 10,000, Medium 10,000–29,999, High 30,000+. Not part of the score; a champion needs 1,000 to be ranked.",

    // ---- tabs ----
    tab_tier: "Your Pick Score ranking: data (42.5%), your Comfort (52.5%) and one-tricks (5%) together. Only champions with a card.",
    tab_meta: "The data-only ranking (Meta Score): every champion that passes the filters, with or without a card.",
    tab_comfort: "How each Comfort number is built from the card. View only.",
    tab_growth: "Tips on which champions to learn or improve, because they would beat your current #3 pick.",

    // ---- Meta tab ----
    meta_rank: "Place by Meta Score (1 = strongest on data alone). It keeps its number when you sort by another column.",
    m_champion: "Champions with no card yet say so; they have a Meta Score but no Pick Score.",
    meta_score: "The data alone: 75% win rate points + 25% pick rate points, from 0 to 100. The box is green above the average Meta Score and red below, stronger each 0.5 and 1.5 spreads (standard deviations) away, like the tiers.",
    wr_points: "50 points at the Diamond+ average, 12.5 more for every point of win rate above it and 12.5 less for every point below, kept between 0 and 100. Worth 75% of Meta Score.",
    pr_points: "Pick rate ranked 0–100 among the ranked bot-lane champions (most picked = 100). Worth 25% of Meta Score.",
    pick_rate: "Share of all games the champion is picked in bot lane (Diamond+ participants ÷ 10 is the total). Needs 0.8% to be ranked.",
    needs_card: "Champions that pass the filters but have no card, sorted by Meta Score. Make a card to get a Pick Score.",

    // ---- Comfort tab ----
    c_champion: "A champion with a card. Type, strength, traits and mastery are read straight from the cards.",
    c_comfort: "The final Comfort number, the same one the tier list uses (worth 52.5% of the Pick Score). The box is green above the average Comfort and red below, stronger each 0.5 and 1.5 spreads away.",
    trait_score: "Sum of priority × level over the champion's traits (Low 0.5, Mid 1, High 1.5); the badges show each trait and its level. The Kit adjustment compares it with the patch average.",
    c_mastery: "Your mastery, from 1 dot (Never played) to 5 (Main). Hover the dots for the name.",
    main_type: "The champion's main type and how strongly it fits it: High 100%, Mid 97.5%, Low 95% of the type's points.",
    secondary_type: "Optional second type. If it is worth more than the main type, 20% of the gap is added to the type points; otherwise it is only for information.",
    type_points: "Main type points (Mobility 100, Peel 90, Hypercarry and Utility 80, Mage and Lane bully 70, after strength) plus any secondary bonus. Worth 40% of the base.",
    mastery_pts: "Mastery points: Main 100, Good 90, Average 80, Below average 70, Never played 60. Worth 60% of the base.",
    base: "40% type points + 60% mastery points, before the adjustments.",
    kit_adj: "0.9 × (trait score − average trait score), at most ±5.",
    difficulty: "Riot's rating / your base rating → final difficulty (80% yours + 20% Riot's). Medium is 2.",
    diff_adj: "−3 × (difficulty − 2) × the mastery factor (Main 20% up to Never played 100%), at most ±3. Hard champions lose points unless you master them.",
    range_adj: "Short range −0.5, Medium 0, Long +0.5.",
    flex: "Beta bonus for champions that can be built two ways (Varus only): +1 × the mastery's flexibility factor.",

    // ---- Growth tab ----
    g_champion: "A champion with a card that is not yet a Main.",
    g_kind: "Upgrade = you already play it and could get better. New champion = you have never played it.",
    g_mastery: "Your mastery now. The target is always the next level: Never played → Below average → Average → Good → Main.",
    g_score: "Pick Score now → Pick Score at the next mastery level. A tip appears only when the new score beats your current #3 pick.",
    g_gain: "How many Pick Score points the champion would gain one mastery step up.",
    g_rank: "Where it would rank in the tier list one mastery step up.",
    g_tier: "Its tier one mastery step up, against this patch's average Pick Score.",
    g_skill: "Information only, no effect on any score. How much better one-tricks win than average players, then how many OTPs and their bot-lane games. Shown only with 20 or more bot-lane OTP games.",
    top_upgrades: "One mastery step up only (Never played → Below average → Average → Good → Main). Shown only when the new Pick Score beats your current #3 pick.",
    next_step: "Every carded champion now in B, C or D whose Pick Score one mastery step up would land in A or S. Same scoring code as the tier list; only the mastery changes. If nobody qualifies, the page names the closest one.",
    n_champion: "A champion with a card, now in B, C or D.",
    n_mastery: "Your mastery now → the next level (one step only).",
    n_tier: "Its tier now → its tier one mastery step up, against this patch's average Pick Score.",
    n_score: "Pick Score now → Pick Score one mastery step up.",
    n_gain: "Pick Score points gained one mastery step up.",
    n_skill: "Information only, no effect on any score. How much better one-tricks win than average players, shown only with 20 or more bot-lane OTP games.",

    g_ceiling: "Quiet extra, information only: the best tier the champion could reach at Main mastery. It never decides who appears in either list.",
    n_ceiling: "Quiet extra, information only: the best tier the champion could reach at Main mastery. It never decides who appears in either list.",

    // ---- patch mix and data label ----
    patch_mix: "Most champions (the middle 80%) get this share of their numbers from this patch; the rest comes from last patch. Share of this patch = this patch's games ÷ (this patch's games + 1,000).",
    data_label: "Share of this patch = this patch's games ÷ (this patch's games + 1,000). The rest of the champion's numbers come from last patch, so early in a patch the list is not empty."
  };
  if (typeof module !== "undefined" && module.exports) module.exports = HELP;
  else root.HELP = HELP;
})(typeof window !== "undefined" ? window : this);
