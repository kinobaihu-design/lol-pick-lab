# LoL Pick Lab data

Written automatically by the collector (see the `main` branch). This branch is
replaced on every save, so it has no history. `data-backup` holds the previous
run's copy.

## patches/<patch>/
The last 5 patches are kept. `players.json.gz` is kept only for the newest few
(see `KEEP_PLAYER_PATCHES` in `collector/config.py`).
- `summary.json`: games counted, games per server, Diamond+ average win rate
  (weighted and unweighted), and average win rate per role.
- `champions.json`: per champion ID: name, games and wins per role, and bans.
  Bans count once per game: [games banned on double-weight servers, on other servers].
- `bottom.json.gz`, `utility.json.gz`, `jungle.json.gz`: per champion played
  in that role: games, final items, rune pages, and allies/enemies as
  "championId:role". Jungle was added on Oct 3, 2026.
- `players.json.gz`: per scrambled player code, `[games, wins]` per champion ID
  (all roles), plus `"ID:B"` (bot lane), `"ID:S"` (support) and `"ID:J"`
  (jungle, from Oct 3, 2026) for games in those roles. Used for the "recent games" part of the OTP rule (current +
  previous patch). Real player IDs are never stored.

## archive/<patch>/
`summary.json` and `champions.json` of every patch, kept forever (tiny). They
survive the cleanup of the `patches/` folders.

## season/<season>/
Saved in 16 pieces by the first character of the player code
(`players-0.json.gz` ... `players-f.json.gz`), plus `season.json` (the champion
list and the day the pieces were made). Each piece holds `players` and `seen`
(the last day each player was counted). Players with 5 games or fewer that have
not been seen for 30 days are dropped. `players-preconversion.json.gz` is the
old single file, kept for 7 days after the split as a rollback copy.
Running totals for the whole season (season 16 = patches 16.x); only the
current season is kept, for the "50 games this season" part of the OTP rule:
- `players` (in each piece): per scrambled player code, `"all"` = `[games, wins]` across every
  champion, plus `[games, wins]` per champion ID and per `"ID:B"` / `"ID:S"` /
  `"ID:J"`, only for bot-lane, support and jungle champions.
- `champions`: the champion IDs counted this season (at least 200 games in a
  patch with at least 10% in bot lane, support or jungle; once in, they stay).
  When a champion joins, its earlier games are copied in from the patch files
  still kept (the patches that keep a `players.json.gz`).
Games collected before season totals existed were copied in from the patch
files (without the bot/support split, which starts from that point).

## Player codes
A code is `HMAC-SHA256(secret, SHA-256(player ID)[:16])[:16]`. The secret is a
GitHub secret that is never published, so a code can't be matched to a known
player ID. `codes.json` holds the format version and a short fingerprint of the
secret; the collector refuses data made with another secret.

Only Diamond+ players (from Riot's Diamond, Master, Grandmaster and Challenger
lists for ranked solo/duo) are counted.

## Counters
Every game/win counter is `[games x2, wins x2, games x1, wins x1]`. The x2 part
is LAN, NA, EUW and KR, the x1 part is every other server.
Weighted games = 2 * games x2 + games x1.

## scores/
Written right after each save by the scoring code (`scoring/` on the `main` branch,
model v0.44): `latest.json` and `<patch>.json` (the last 20 patches) with the Pick Score
list, Meta Score list, Growth advisor suggestions, and champions without a card.

## state/
The collector's memory: when each player was last checked, which games were
already processed (last 14 days), and games waiting to be downloaded.
