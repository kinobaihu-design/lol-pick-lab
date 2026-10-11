"""Scoring settings (model v0.34). Change numbers here, not in the rest of the code.

Every number below comes from the project brief. If the brief changes, change it here
and bump MODEL_VERSION.
"""

MODEL_VERSION = "v0.34"

# ---- Pick Score = 0.4 x Stats + 0.5 x Comfort + 0.1 x OTP ----
WEIGHT_STATS = 0.4
WEIGHT_COMFORT = 0.5
WEIGHT_OTP = 0.1

# ---- Filters (a champion must pass all four to be ranked) ----
MIN_REAL_GAMES = 1000     # real games (before the double weight), this patch + last patch together
MIN_LANE_SHARE = 0.10     # share of the champion's games played in the lane (blended)
MIN_PICK_RATE = 0.01      # pick rate (blended)
# What "pick rate" means. The brief doesn't say, so this is a choice:
#   "games" = share of all games the champion appears in (Riot / Lolalytics style). Every
#             game has two bot laners, so this is twice the lane share below.
#   "lane"  = share of all bot-lane picks. The picks of all champions add up to 100%.
# Only the 1% filter cares: the Stats ranking (0-100) is the same either way.
PICK_RATE_BASIS = "games"

# Champions the owner keeps out of the bot-lane pool ("Melee champions (Yasuo, Katarina) stay
# out of my bot-lane pool", brief v0.34). They still pass the filters on data, so they are
# listed separately and left out of every ranking, average and suggestion.
EXCLUDED_FROM_POOL = ["Yasuo", "Katarina"]   # Riot's internal names

# ---- Patch blending ----
# share of this patch = this patch's games / (this patch's games + BLEND_K)
BLEND_K = 1000

# ---- Stats (40%) ----
STATS_WIN_RATE_SHARE = 0.75
STATS_PICK_RATE_SHARE = 0.25
WIN_RATE_POINTS_PER_PERCENT = 12.5   # points per 1% above / below the Diamond+ average

# ---- Comfort (50%) ----
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

# ---- OTP (10%) ----
OTP_MIN_SHARE_OF_RECENT_GAMES = 0.55   # recent = this patch + last patch
OTP_MIN_SEASON_GAMES = 50
OTP_RELIABILITY_K = 300                # reliability = OTP games / (OTP games + K)

# ---- Tiers ----
TIER_CUTOFFS = [("S", 80.0), ("A", 72.0), ("B", 64.0), ("C", 56.0)]   # below the last one: D
STATS_FLOOR = -1.5                     # win rate this far (or more) below the average caps the tier
STATS_FLOOR_TIER = "B"
TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}

# ---- Growth advisor ----
# Never played and Below average are scored as if Good; Average and Good one level up.
GROWTH_TARGET = {"never_played": "good", "below_average": "good", "average": "good", "good": "main"}
# Compared with the owner's current #3 pick.
GROWTH_BEAT_RANK = 3

# The role this model scores. Roles in the data files: BOTTOM covers ADCs and APCs.
LANE_ROLE = "BOTTOM"
