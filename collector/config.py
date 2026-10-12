"""Collector settings. Change numbers here, not in the rest of the code."""

QUEUE_ID = 420  # ranked solo/duo
QUEUE_NAME = "RANKED_SOLO_5x5"

# Riot servers ("platforms"), grouped by the routing region that serves their games.
REGIONS = {
    "americas": ["NA1", "LA1", "LA2", "BR1"],
    "europe": ["EUW1", "EUN1", "TR1", "RU", "ME1"],
    "asia": ["KR", "JP1"],
    "sea": ["OC1", "SG2", "TW2", "VN2"],
}
SERVER_NAMES = {
    "NA1": "NA", "LA1": "LAN", "LA2": "LAS", "BR1": "BR",
    "EUW1": "EUW", "EUN1": "EUNE", "TR1": "TR", "RU": "RU", "ME1": "ME",
    "KR": "KR", "JP1": "JP",
    "OC1": "OCE", "SG2": "SG", "TW2": "TW", "VN2": "VN",
}
ALL_SERVERS = [s for servers in REGIONS.values() for s in servers]
SERVER_REGION = {s: r for r, servers in REGIONS.items() for s in servers}

# Games from these servers count double in the stats. Raw counts are stored
# separately, so this weight can change later without collecting again.
DOUBLE_WEIGHT_SERVERS = {"LA1", "NA1", "EUW1", "KR"}
DOUBLE_WEIGHT = 2

# Share of each region's allowance for game downloads that goes to its priority
# servers (split evenly between them). The rest is split evenly among the others.
# A region without priority servers is split evenly. Unused allowance is passed on.
PRIORITY_SHARE = 0.70
PRIORITY_SERVERS = {
    "americas": ["LA1", "NA1"],
    "europe": ["EUW1"],
    "asia": ["KR"],
    "sea": [],
}

# Roles that get full detail (items, runes, allies, enemies). The site's 3 roles.
DETAIL_ROLES = ("BOTTOM", "UTILITY", "JUNGLE")
# Short role tags used in the player files: "22:B" = Ashe games in bot lane.
ROLE_TAGS = {"BOTTOM": "B", "UTILITY": "S", "JUNGLE": "J"}

# Season totals per player (for the OTP rule). A season is the first part of
# the patch number (16.19 -> season 16). Per-champion counts are kept only for
# bot-lane, support and jungle champions: at least SEASON_CHAMPION_MIN_GAMES
# games in a patch of the season, with at least SEASON_CHAMPION_MIN_SHARE of them
# in one of those roles. Once a champion qualifies it stays for the rest of the
# season, and its earlier games are copied in from the patch files still kept.
SEASON_CHAMPION_MIN_GAMES = 200
SEASON_CHAMPION_MIN_SHARE = 0.10
KEEP_SEASONS = 1                # seasons of player totals kept (the current one only)

# Personal key limits per routing value: (requests, seconds). Riot's response
# headers replace these if they differ. We stay a little under them.
APP_RATE_LIMITS = [(20, 1), (100, 120)]
RATE_LIMIT_SAFETY = 0.97

# How often players are checked for new games.
ACTIVE_RECHECK_HOURS = 5          # player had games last time: check again next run
FIRST_INACTIVE_RECHECK_HOURS = 24  # no games: wait a day, then double each time
MAX_RECHECK_HOURS = 336           # never wait more than 14 days
NEW_PLAYER_LOOKBACK_DAYS = 7      # first check of a player looks this far back
MAX_LOOKBACK_DAYS = 10            # never ask for games older than this
OVERLAP_HOURS = 2                 # re-check a little before the last check (games in progress)

# What is kept.
# Data storage standard (brief v0.44). Cleanup never goes below the floors in
# `store.py` (current + previous patch, current season, latest scores).
KEEP_PATCHES = 5              # per-patch folders kept: champion stats, items, runes, matchups
KEEP_PLAYER_PATCHES = 3       # patches that keep players.json.gz (owner's decision: the season rebuild and
                              # new-champion back-fill read these files)
KEEP_SCORE_FILES = 20         # scores/<patch>.json files kept (latest.json always stays)
ARCHIVE_DIR = "archive"       # tiny summary.json + champions.json per patch, kept forever
SIZE_WARNING_MB = 40          # the run summary warns when the biggest saved file is this big
PROCESSED_KEEP_DAYS = 14      # must stay above MAX_LOOKBACK_DAYS
MAX_PENDING_PER_SERVER = 50000
MIN_GAME_SECONDS = 300        # shorter games are remakes and are skipped

# Run timing.
DEFAULT_MAX_MINUTES = 300
CHECKPOINT_MINUTES = 60
FINAL_SAVE_RESERVE_MINUTES = 8


def server_shares(region):
    """Target share of the region's game allowance for each server."""
    servers = REGIONS[region]
    priority = [s for s in PRIORITY_SERVERS.get(region, []) if s in servers]
    rest = [s for s in servers if s not in priority]
    if not priority or not rest:
        return {s: 1 / len(servers) for s in servers}
    shares = {s: PRIORITY_SHARE / len(priority) for s in priority}
    shares.update({s: (1 - PRIORITY_SHARE) / len(rest) for s in rest})
    return shares


def server_of_match(match_id):
    """'EUW1_7123456789' -> 'EUW1' (None if unknown)."""
    prefix = match_id.split("_", 1)[0].upper()
    return prefix if prefix in SERVER_REGION else None
