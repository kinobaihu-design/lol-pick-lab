"""Scoring settings (model v0.40). Change numbers here, not in the rest of the code.

Every number below comes from the project brief. If the brief changes, change it here
and bump MODEL_VERSION.
"""

MODEL_VERSION = "v0.40"

# ---- Pick Score = 0.425 x Stats + 0.525 x Comfort + 0.05 x OTP ----
WEIGHT_STATS = 0.425
WEIGHT_COMFORT = 0.525
WEIGHT_OTP = 0.05

# ---- Filters (a champion must pass all four to be ranked) ----
MIN_REAL_GAMES = 1000     # real games (before the double weight), this patch + last patch together
MIN_LANE_SHARE = 0.10     # share of the champion's games played in the lane (blended)
MIN_PICK_RATE = 0.008     # pick rate (blended)
# What "pick rate" means (brief v0.35): the champion's bot-lane games / all games. Games the
# champion plays in other roles never count. Only Diamond+ players are stored (about 7.4 of the
# 10 players per game), so "all games" is estimated as Diamond+ participants / 10; that keeps
# the numerator and the denominator on the same footing. Dividing by the raw number of games
# counted instead would make every pick rate about 25% smaller.
# "games" = the rule above. "lane" = share of all bot-lane picks instead (half as big).
PICK_RATE_BASIS = "games"

# Champions the owner keeps out of the bot-lane pool ("Melee champions (Yasuo, Katarina) stay
# out of my bot-lane pool", brief v0.34, confirmed in v0.35). They still pass the filters on data, so they are
# listed separately and left out of every ranking, average and suggestion.
EXCLUDED_FROM_POOL = ["Yasuo", "Katarina"]   # Riot's internal names

# ---- Patch blending ----
# share of this patch = this patch's games / (this patch's games + BLEND_K)
BLEND_K = 1000

# ---- Stats (42.5%) ----
STATS_WIN_RATE_SHARE = 0.75
STATS_PICK_RATE_SHARE = 0.25
WIN_RATE_POINTS_PER_PERCENT = 12.5   # points per 1% above / below the Diamond+ average

# ---- Comfort (52.5%) ----
TYPE_POINTS = {
    "mobility": 100,
    "peel": 90,
    "hypercarry": 80,
    "utility": 80,
    "mage": 70,
    "lane_bully": 70,
}
STRENGTH = {"high": 1.0, "mid": 0.975, "low": 0.95}
SECONDARY_SHARE = 0.20               # share of the gap added when the secondary type is worth more

MASTERY_ORDER = ["never_played", "below_average", "average", "good", "main"]
MASTERY_POINTS = {"main": 100, "good": 90, "average": 80, "below_average": 70, "never_played": 60}
MASTERY_DIFFICULTY_FACTOR = {"main": 0.20, "good": 0.40, "average": 0.60, "below_average": 0.80, "never_played": 1.0}
MASTERY_FLEXIBILITY_FACTOR = {"main": 1.0, "good": 0.75, "average": 0.50, "below_average": 0.25, "never_played": 0.0}
COMFORT_TYPE_SHARE = 0.4
COMFORT_MASTERY_SHARE = 0.6
COMFORT_CAP = 100

TRAIT_PRIORITY = {   # High 3, Medium 2, Low 1
    "wave_clear": 3, "team_utility": 3, "aoe": 3,
    "cc": 2, "sustain": 2, "burst": 2, "poke": 2,
    "vision": 1,
}
TRAIT_LEVEL = {"low": 0.5, "mid": 1.0, "high": 1.5}
KIT_WEIGHT = 0.9
KIT_CAP = 5.0
# The average trait score is recalculated from the eligible carded champions. With fewer
# than this many, the average of all cards is used instead.
MIN_CARDS_FOR_TRAIT_AVERAGE = 10

DIFFICULTY_WEIGHT = 3.0
DIFFICULTY_CAP = 3.0
DIFFICULTY_MIDDLE = 2.0              # Medium
DIFFICULTY_MINE_SHARE = 0.8          # 80% the owner's base rating + 20% Riot's
DIFFICULTY_RIOT_SHARE = 0.2

RANGE_ADJUSTMENT = {"short": -0.5, "medium": 0.0, "long": 0.5}
FLEXIBILITY_BONUS = 1.0              # x the mastery's flexibility factor (flexible builds only)

# ---- OTP (5%) ----
OTP_MIN_SHARE_OF_RECENT_GAMES = 0.55   # recent = this patch + last patch
OTP_MIN_SEASON_GAMES = 50
OTP_RELIABILITY_K = 300                # reliability = OTP games / (OTP games + K)

# ---- Tiers (v0.36) ----
# A champion's tier comes from the Pick Score only: how far it is from this patch's average Pick
# Score, measured in standard deviations ("spreads"). Only champions with a Pick Score (a card)
# count. Each pair is (tier, lowest number of spreads for it); below the last one is D.
# There is no stats floor and no win rate condition on S any more (removed in v0.36).
TIER_BOUNDARIES = [("S", 1.5), ("A", 0.5), ("B", -0.5), ("C", -1.5)]
# Display only, no effect on the tier: a win rate this far (or more) below the Diamond+ average
# gets a warning sign next to it on the page.
WIN_RATE_WARNING_DELTA = -1.5

# ---- Growth advisor ----
# Only champions with a card (Comfort needs one). Both lists (Top upgrades and Next step to A or S) use the
# NEXT mastery level only (v0.39): Never played -> Below average -> Average -> Good -> Main. Main has no next level.
# "Ceiling at Main" is shown as information only and never decides who appears in either list.
GROWTH_TARGET = {"never_played": "below_average", "below_average": "average", "average": "good", "good": "main"}
# Utopy picks (v0.40, information only): the mastery levels tried as long-term goals.
UTOPY_LEVELS = ["good", "main"]
# Compared with the owner's current #3 pick.
GROWTH_BEAT_RANK = 3

# The role this model scores. Roles in the data files: BOTTOM covers ADCs and APCs.
LANE_ROLE = "BOTTOM"
