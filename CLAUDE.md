# LoL Pick Lab — instructions for Claude

`project-brief.pdf` (kept locally, not in the repo) is the source of truth. This file summarizes it; current brief: **v0.43**. If the two disagree, the brief wins; ask the owner which to update.

## Rules for working with the owner

- **The owner is a beginner and does not write code.** Explain everything in plain language, one step at a time. Avoid jargon; when a technical word is unavoidable, explain it in one short sentence.
- **Ask before doing anything that costs money.** That includes paid plans, paid add-ons, going over a free tier, or buying anything. Everything in this project is meant to run on free services.
- **Never put API keys, passwords or tokens in code, files or chat.** The Riot API key is stored only as a GitHub Actions secret named `RIOT_API_KEY` and read from the environment at runtime. Never print it, log it, commit it or send it to the website. If the owner pastes a secret into chat, tell them to revoke and regenerate it.
- The owner makes the decisions about rules, weights and tags. Claude writes and maintains all the code, and explains each change in plain words.

## How we work (every step, before anything is built)

One review round per step, so we keep improving without getting stuck:

1. **Plan.** Claude explains the step in plain words.
2. **Review.** The owner asks questions. Claude names at least one possible improvement or risk.
3. **Approve.** The owner says OK, with any changes agreed on. **Don't build before this.**
4. **Build and test.** Claude builds it and shows the results in simple words.
5. **Close.** Tick the board (tasks are ticked as soon as they're done), log any model change as a new version (see "Model versions"), and remind the owner to refresh the brief if it changed.

- Ideas that don't affect the current step go to the board or the open questions, so they aren't lost.
- **Facts vs opinions.** Anything that is a fact about the game (champion types, ranges, item stats, patch changes, Riot difficulty) is checked against an official source before it's used: Riot's data (Data Dragon) or the official League of Legends Wiki. The owner's opinions (mastery, feel, notes, their own locked base difficulty rating) stay theirs and need no check.

## What the project is

A free public website that ranks ADC and support champions each patch using the owner's own rules. Priorities, in order:

1. **Personal tier list** for ADC (support later), from Diamond+ data and the owner's scoring.
2. ~~Draft helper~~ removed for good in v0.44 (the site is a personal tier list only).

Build recommendations (items, runes, skill order) were dropped from the goals on Oct 11, 2026; they may come back later as an extra (Phase 4). The collector keeps saving items and runes meanwhile.

The final site covers 3 roles: bot lane (ADC and APC), support and jungle, built in that order. Nothing is built for support or jungle until the bot-lane (ADC) tier list is done.

## How it works (all free)

- **Data:** our own Diamond+ ranked solo/duo matches from the official Riot Games API, using a personal API key (100 requests / 2 min per region).
- **Collector, every 6 hours (GitHub Actions, free for public repos).** A run can last at most 6 hours while Riot's limit refills all day, so four runs a day use the full free allowance. Each run:
  1. List Diamond, Master, Grandmaster and Challenger players in each region.
  2. Get each player's recent ranked solo/duo match IDs.
  3. Download each new match once. For each champion, store role, win/loss, items, runes, skill order, and the allies and enemies.
  4. Mark a player as an OTP (one-trick) of a champion when most of their recent games are on it.
  5. Recalculate the Diamond+ average win rate for the patch.
- **Regions:** every server the Riot API covers (China isn't included). LAN, KR, NA and EUW games count double.
- **Priority inside each routing region:** match downloads are split into four buckets (Americas, Europe, Asia, SEA). In each bucket the priority servers get about 70% (Americas: LAN and NA; Europe: EUW; Asia: KR), and the rest share 30%. SEA is split evenly. Recently active players are checked more often than inactive ones.
- **Storage:** champion stats per patch, kept in this GitHub repository.
- **Website:** hosted on Vercel's free plan, updates automatically when new data lands.
- **Patch blending:** early in a patch, each champion's stats blend in last patch's data. Share of this patch = `this patch's games ÷ (this patch's games + 1,000)`: 200 games → 17%, 1,000 → 50%, 3,000 → 75%, 9,000 → 90%. The site shows a label like "Data: 75% this patch".

## Data collector (Phase 1, built)

- Code: `collector/` (Python standard library only). Settings, including `PRIORITY_SHARE`, double-weight servers, recheck timing and patches kept, are in `collector/config.py`.
- Schedule: `.github/workflows/collect.yml` runs every 6 hours, about 5 hours of work per run, and never two runs at once. "Run workflow" on the Actions page takes a time limit and a per-region game limit for tests. It saves a checkpoint every hour.
- What it does: it loads each server's Diamond+ list and checks players for new queue 420 games. Active players are rechecked after 5 hours; inactive ones after 24 hours, then doubling up to 14 days (lookback stays 10 days). Each new game is downloaded once, and only Diamond+ participants are counted. Within each routing region, the priority servers get `PRIORITY_SHARE` (70%) of requests: Americas LAN and NA, Europe EUW, Asia KR. SEA is split evenly.
- Data lives on the `data` branch, replaced each save with no history (fetch it with `git fetch origin +data:refs/remotes/origin/data`). `data-backup` holds the previous run's copy, and the collector falls back to it if a file is damaged. Storage standard v0.44: see "Brief changes v0.44". See the `README.md` on the data branch for the file format. Player IDs are stored only as secret-key codes (v0.41).
- **Roles with full detail:** bot lane (`BOTTOM`), support (`UTILITY`) and jungle (`JUNGLE`, from Oct 3, 2026), set in `config.DETAIL_ROLES`. Each has a per-patch file (`bottom`, `utility`, `jungle`.json.gz) with games, final items, rune pages, and allies/enemies per champion. Jungle costs no extra Riot requests, since every downloaded game already has all 10 players. Nothing is built on jungle data until the bot-lane tier list is done, and the role order is bot lane, then support, then jungle.
- Champions are stored by Riot's champion ID. The `name` field is Riot's internal name (`Kaisa`, `MissFortune`, `KogMaw`); the website must take display names from Data Dragon.
- **Player files (for the OTP rule).** Players appear only as scrambled codes. Counters are `[games, wins]`; a key `"ID"` means all roles, `"ID:B"` bot-lane games, `"ID:S"` support games and `"ID:J"` jungle games (from Oct 3, 2026).
  - `patches/<patch>/players.json.gz` holds every champion each player played that patch. It answers "55% of recent games", where recent = current + previous patch.
  - `season/<season>/players.json.gz` holds running totals for the season (season 16 = patches 16.x), never pruned during the season. It answers "at least 50 games on it this season". `"all"` is the player's total ranked games, any champion. Per-champion counts (with the B/S/J split) are kept only for the site's 3 roles: bot-lane, support and jungle champions, meaning at least 200 games in a patch with ≥10% in one of those roles (`SEASON_CHAMPION_MIN_GAMES`, `SEASON_CHAMPION_MIN_SHARE`). Once a champion qualifies it stays for the season, and its earlier games are copied in from the patch files that still have a players file. The `champions` list is stored in the file.
  - A new season starts when the first part of the patch number changes. The current and the previous season are kept (`KEEP_SEASONS = 2`).
  - When a season file is missing, it's rebuilt from the patch files, so nothing is lost. Games from before Oct 2, 2026 (the start of season totals) have no B/S split.
  - Only games we collect are counted, starting Oct 2, 2026, so season totals undercount early on. The OTP reliability formula keeps small OTP samples near neutral.
- Bans count once per game. Ban rate = games banned ÷ games counted.
- Skill order isn't collected yet (the brief says "saved but not used for now"); it would need an extra request per game. Builds were dropped from the goals in v0.34, so it waits for the maybe-later builds extra.
- Keep-active: the first workflow step (`scripts/keep_active.sh`) adds an empty commit to `main` if it has had no commits for 30 days, so GitHub never pauses the schedule (it pauses after 60 days without activity). It runs before collection and is allowed to fail without stopping it.
- Offline checks: `python3 -m unittest discover -s tests`.

## Scoring model v0.36 (bot lane: ADC and APC): the full recipe

Bot lane includes APCs (bot-lane mages). They're in the same list as the ADCs and share the same trait average. Every part is scored 0–100, then weighted. The order of the steps:

1. **Filters.** A champion needs all four to be ranked: Diamond+ games, ≥10% lane share, ≥1,000 **real** games across this patch and last patch together (counted before the double weight), ≥0.8% pick rate. Lane share and pick rate use the same blended numbers (see "Patch blending"); the data-freshness label shows how much is this patch. The sample-size label (low, medium, high) also uses real games. The double weight (LAN, KR, NA, EUW ×2) still applies to all stats.
2. **Stats (42.5%)** = 75% win rate points + 25% pick rate. Win rate says how strong a champion is; pick rate says it's proven and popular. (PBI was removed in v0.33.)
   - Win rate points = `50 + 12.5 × (win rate − Diamond+ average)`, clamped to 0–100: +4% → 100, +2% → 75, average → 50, −2% → 25, −4% → 0. The Diamond+ average comes from our own data each patch (expected to sit above 50%; Lolalytics shows 52.27%).
   - **Pick rate** = the champion's bot-lane games ÷ all games (v0.35). Games it plays in other roles never count. Only Diamond+ players are stored (about 7.4 of 10 per game), so "all games" is estimated as Diamond+ participants ÷ 10; dividing by the raw games counted would make every pick rate about 25% smaller.
   - Pick rate is ranked 0–100 among the eligible bot-lane champions (ADCs and APCs). Ban rate isn't part of the Pick Score.
   - **Meta Score** = the Stats points alone (the data-only ranking). Every champion that passes the filters gets one, with or without a card.
3. **Comfort (52.5%)** comes from the champion cards (see "Comfort in detail"), capped at 100.
4. **OTP (5%)** = OTP win rate − overall win rate, ranked 0–100 among eligible champions (raw OTP points), then pulled toward 50 by its reliability:
   - `OTP points = 50 + (raw OTP points − 50) × reliability`, where `reliability = OTP games ÷ (OTP games + 300)`. 100 OTP games → 25%; 300 → 50%; 1,000 → 77%; 3,000 → 91%.
   - **OTP rule (for now):** a Diamond+ player is an OTP of a champion when at least 55% of their recent ranked games are on it, and they have at least 50 games on it this season.
   - The tier list shows the number of OTP players and OTP games behind each OTP score.
5. **Pick Score** = `0.425 × Stats + 0.525 × Comfort + 0.05 × OTP`.
6. **Tier (v0.36): the Pick Score only.** Each champion is compared with this patch's average Pick Score (champions with a card), measured in standard deviations ("spreads"). **S** +1.5 spreads or more · **A** +0.5 to +1.5 · **B** −0.5 to +0.5 · **C** −1.5 to −0.5 · **D** below −1.5. There is no stats floor and no win rate condition on S any more. **Win rate warning (display only):** a champion whose win rate is 1.5% or more below the Diamond+ average shows a ⚠ next to its win rate; it never changes the tier (`WIN_RATE_WARNING_DELTA` in `scoring/config.py`). The boundaries are in `scoring/config.py` (`TIER_BOUNDARIES`).

**Other lists:**
- **Growth advisor** (replaces "Worth learning"). It nudges the owner toward their preferred types and toward champions with strong stats, instead of keeping them on their mains forever. Only champions with a card count (v0.35). For each champion the owner isn't a Main on, the app calculates its Pick Score at the NEXT mastery level only (v0.39): Never played → Below average → Average → Good → Main (before v0.39 Never played and Below average jumped straight to Good). It shows a suggestion only when that score would beat the owner's current #3 pick, with the gain ("Kalista: 71 → 79 if Below average" is the same idea, one step). There are two kinds of advice:
  - **Upgrade:** "You're Good with Jinx; at Main she'd jump from 74 to 80, S tier."
  - **New champion:** "You've never played Kalista, but at Good she'd rank #2 this patch; worth starting."
  - Details get polished in Phase 2 with real data.
- **Ban suggestions (removed for good in v0.44; the old code was removed in v0.38; do not build any ban list)** (any role, separate from picks), by data only (needs the same 1,000 real games and the same pick-rate bar, 0.8%, my reading, so thin samples can't top the list): `Ban threat = (win rate − Diamond+ average) × pick rate`, meaning how strong a champion is times how often the owner will face it. Only champions above the average win rate count, ranked by Ban threat. Any role, and each champion's main role is shown.
- **Champions without a card** get no Pick Score, because Comfort needs a card. They still appear in the Meta Score (the data-only ranking) with a "no card yet" label, and in the **Needs a card** list: champions that pass the filters but have no card, sorted by Meta Score. They are not in the Growth advisor (v0.35).

### Comfort in detail

Comfort measures how much the owner likes a champion and how well they play it. Each card produces one final Comfort:

`Comfort = 40% type points + 60% mastery points + kit adjustment + difficulty adjustment + range adjustment (+ flexibility bonus, Varus only)`, capped at 100.

**Step 1: type points.** Each champion has one main type, fact-checked against these rules from its kit (official League of Legends Wiki):

| Type | Points | Fact-check rule |
|---|---|---|
| Mobility (favorite) | 100 | Has a dash or blink it uses in fights |
| Peel (2nd) | 90 | Has a tool made to protect itself: spell shield, untargetability, knockback or self-shield (like Sivir's E). Offensive CC like roots or slows doesn't count |
| Hypercarry (3rd, tied) | 80 | Weaker early, scales into top late-game damage |
| Utility (3rd, tied) | 80 | Its main value is reliably helping the team (CC, vision, ally support) more than its own damage or mobility, like Ashe |
| Mage (4th, tied) | 70 | Deals most damage with magic abilities, not attacks |
| Lane bully (4th, tied) | 70 | Strongest early; wins lane through damage and trades and snowballs leads (like Draven). Champions with a dash stay Mobility |

- **Type strength:** High 100%, Mid 97.5%, Low 95% of the type points. It applies to the main type and to the secondary type before they're compared.
- **Secondary type** (optional): if its points (after strength) beat the main type's, add 20% of the gap. If not, it's shown for information only. If a card lists two secondary types (Vayne), the best one counts.
- **No Discomfort switch any more.** A champion the owner doesn't play is simply Never played. The Growth advisor suggests learning it if its type and data are strong.

**Step 2: mastery.** Reviewed every 5 to 10 patches. Steps of 10 points give mains a small edge, not a wall.

| Mastery | Points | Difficulty factor | Flexibility factor | Meaning |
|---|---|---|---|---|
| Main | 100 | 20% | 100% | Played mostly this champion in the last patches |
| Good | 90 | 40% | 75% | Good with it, lots of games, but not a main |
| Average | 80 | 60% | 50% | Just OK, casual; usually easy champions |
| Below average | 70 | 80% | 25% | Knows how it works; can jump in and try to win |
| Never played | 60 | 100% | 0% | Knows nothing about it; would struggle |

**Step 3: kit adjustment** = `0.9 × (trait score − average trait score)`, capped at ±5 on Comfort (±2.5 on the Pick Score). The average is recalculated each patch from the eligible bot-lane champions, ADCs and APCs together (v0.31). Until real data exists it's the average of all 39 cards: 13.897, shown in the brief as 13.9. An average champion gets 0, so scores don't inflate.
- Trait score = sum of `priority × level`. Levels: Low 0.5 · Mid 1 · High 1.5.
- **Every trait gets at least Low if the champion has any of it.** A trait is left empty only when it's truly absent, which should be the exception. A trait that defines the champion's type isn't listed again.

| Trait (8) | Owner's priority | Counts when the kit has… |
|---|---|---|
| Wave clear | High (3) | Clears a minion wave with abilities, without relying on items |
| Team utility | High (3) | General usefulness to the team: helping allies, setting up plays, staying useful when behind (v0.31) |
| AoE | High (3) | Damage that hits several champions at once |
| CC | Medium (2) | Stuns, roots, knockups, knock asides, snares, slows. High = reliable hard CC that decides fights; Mid = situational hard CC, or hard CC plus slows; Low = slows only |
| Sustain | Medium (2) | Healing or lifesteal in the kit |
| Burst | Medium (2) | Can kill or nearly kill a squishy target with one combo or empowered shot |
| Poke | Medium (2) | Repeated damage from long range (1,000+ units) with abilities, available most of the game |
| Vision | Low (1) | Reveals areas or enemies |

**Step 4: difficulty adjustment** = `−3 × (difficulty − 2) × difficulty factor`, capped at ±3 on Comfort (±1.5 on the Pick Score).
- Difficulty = 80% the owner's **base rating** + 20% Riot's (Low 1, Medium 2, High 3).
- The base rating is how hard the champion is to learn from scratch, not how easy it feels now. It stays locked, like Riot's. How easy it feels now comes from mastery, through the factor.
- **Riot's rating** comes from the 1–10 `info.difficulty` number in Riot's game data (Data Dragon): 1–3 Low, 4–6 Moderate, 7–10 High. If the game data has no number (0), Riot's website rating is used instead (Akshan: Low).

**Step 5: range adjustment.** Short (≤500) −0.5 · Medium (525–575) 0 · Long (≥600) +0.5 Comfort, at most ±0.25 on the Pick Score.
- The group comes from the base attack range. It moves up one group when a modifier is available most of the game: Tristana's range grows with level, Jinx can switch to rockets anytime, and Kog'Maw's W is up often.
- Short-lived modifiers don't count (Twitch's R, Aphelios's Calibrum).
- Ability range is already counted through Poke.

**Flexibility bonus (beta, Varus only).** A champion that can be built two different ways gets `+1 Comfort × flexibility factor` (see the mastery table), at most +0.5 on the Pick Score. It's a test: kept, extended or removed after Phase 2.

## Champion cards (bot lane: ADC and APC)

39 cards: 26 ADCs and 13 APCs. The table below is the original 32 from brief v0.34; its Comfort numbers are out of date because the trait average moved from 13.7 to 13.9. Current numbers and the 7 new cards are in `scoring/cards.json` and the "Brief changes v0.35" block below. Original text (APCs marked †): The Comfort column is the brief's result and serves as test data for the scoring code. Claude recalculated all 32 from the inputs below, and every one matched within 0.04 (v0.34). Trait levels are listed in priority order: wave clear, team utility, AoE, CC, sustain, burst, poke, vision; "—" means absent.

| Champion | Main type (str) / secondary (str) | Type pts | Mastery | Wave · TU · AoE · CC · Sus · Burst · Poke · Vis | Trait score | Difficulty Riot / mine → final | Range (adj) | Comfort |
|---|---|---|---|---|---|---|---|---|
| Sivir | Peel (High) / Utility (Mid) | 90 | Main | H · H · H · — · L · L · M · — | 17.5 | 2 / 2 → 2.0 | Short (−0.5) | 99.0 |
| Caitlyn | Mobility (Mid) / Lane bully (Mid) | 97.5 | Good | M · L · L · M · — · M · M · M | 13 | 2 / 1.5 → 1.6 | Long (+0.5) | 93.4 |
| Senna | Utility (High) / Hypercarry (Mid) | 80 | Good | L · H · L · M · H · L · L · L | 15 | 3 / 1 → 1.4 | Long (+0.5) | 88.4 |
| Jinx | Hypercarry (High) | 80 | Good | M · L · H · M · L · L · L · L | 14.5 | 2 / 1 → 1.2 | Long, rockets (+0.5) | 88.2 |
| Lux † | Mage (High) / Lane bully (Mid) | 70 | Good | H · L · H · M · — · H · H · L | 19 | 2 / 1 → 1.2 | Medium (0) | 87.8 |
| Tristana | Mobility (High) / Hypercarry (Low) | 100 | Average | M · — · M · L · L · H · L · — | 12 | 2 / 2 → 2.0 | Long, by level (+0.5) | 87.0 |
| Jhin | Utility (Mid) | 78 | Good | L · L · L · H · L · H · M · L | 14 | 2 / 1 → 1.2 | Medium (0) | 86.5 |
| Ziggs † | Mage (High) / Lane bully (Mid) | 70 | Good | H (assumed) · M · H · L · — · M · H · — | 18 | 2 / 1.5 → 1.6 | Medium (0) | 86.4 |
| Miss Fortune | Lane bully (High) | 70 | Good | L · L · H · L · L · H · H · L | 16 | 1 / 1 → 1.0 | Medium (0) | 85.3 |
| Syndra † | Mage (High) / Peel (Low) | 73.1 | Good | M · L · L · H · — · H · H · L | 15.5 | 3 / 2 → 2.2 | Medium (0) | 84.7 |
| Lucian | Mobility (High) / Lane bully (Low) | 100 | Average | L · — · L · — · M · H · L · L | 9.5 | 2 / 2 → 2.0 | Short (−0.5) | 83.8 |
| Ashe | Utility (High) | 80 | Average | L · H · L · H · L · L · M · H | 16 | 2 / 2 → 2.0 | Long (+0.5) | 82.6 |
| Smolder | Hypercarry (Mid) / Mobility (Mid) | 81.9 | Average | M · L · M · L · L · M · M · — | 13.5 | 2 / 1 → 1.2 | Medium (0) | 82.1 |
| Ezreal | Mobility (High) | 100 | Average | L · — · L · — · L · L · H · — | 8 | 3 / 2.5 → 2.6 | Medium (0) | 81.9 |
| Corki | Mobility (Mid) / Lane bully (Low) | 97.5 | Below average | M · L · M · — · — · M · M · M | 12.5 | 2 / 1 → 1.2 | Medium (0) | 81.9 |
| Twitch | Hypercarry (High) | 80 | Average | M · L · H · L · L · H · L · — | 15 | 2 / 2 → 2.0 | Medium (0) | 81.2 |
| Hwei † | Mage (High) / Peel (Low) | 73.1 | Average | H · H · H · H · L · L · H · L | 22 | 3 / 3 → 3.0 | Medium (0) | 80.4 |
| Xayah | Peel (High) / Hypercarry (Mid or Low) | 90 | Below average | H · L · M · M · L · L · L · — | 14 | 2 / 1 → 1.2 | Medium (0) | 80.2 |
| Viktor † | Mage (High) | 70 | Average | H · L · H · L · — · L · H · — | 15.5 | 3 / 1 → 1.4 | Medium (0) | 78.7 |
| Kalista | Mobility (High) | 100 | Below average | L · M · L · M · L · L · L · M | 12 | 3 / 3 → 3.0 | Medium (0) | 78.1 |
| Yunara | Hypercarry (High) / Mobility (Low) | 83 | Below average | M · L · H · L · L · M · L · L | 14.5 | 2 / 2 → 2.0 | Medium (0) | 76.0 |
| Zeri | Mobility (High) / Hypercarry (Mid) | 100 | Never played | M · — · M · L · L · M · M · — | 12 | 2 / 2 → 2.0 | Medium (0) | 74.5 |
| Varus | Hypercarry (High) / Utility (Low); flexible build | 80 | Below average | L · L · L · M · L · M · H · L | 13 | 1 / 2 → 1.8 | Medium (0); flexibility +0.25 | 74.1 |
| Akshan | Mobility (High) / Utility (Low) | 100 | Never played | M · M · — · — · L · M · L · M | 11 | 1 (website) / 2 → 1.8 | Short (−0.5) | 73.7 |
| Kog'Maw | Hypercarry (High) | 80 | Below average | L · L · L · L · M · L · M · L | 11 | 2 / 2 → 2.0 | Medium, W up often (0) | 71.6 |
| Kai'Sa | Hypercarry (Mid) / Mobility (Mid) | 81.9 | Below average | L · — · L · — · L · M · M · L | 8.5 | 2 / 2 → 2.0 | Medium (0) | 70.1 |
| Vayne | Hypercarry (High) / Mobility (Mid); Peel (Low) noted | 83.5 | Below average | L · L · — · L · M · L · — · L | 7.5 | 3 / 2 → 2.2 | Medium (0) | 69.9 |
| Xerath † | Mage (High) | 70 | Below average | M · L · M · M · — · L · H · L | 14 | 3 / 2.5 → 2.6 | Medium (0) | 68.9 |
| Aphelios | Hypercarry (High) / Utility (Low) | 80 | Never played | M · L · M · M · M · M · L · M | 15.5 | 3 / 3 → 3.0 | Medium (0) | 66.7 |
| Samira | Lane bully (High) / Mobility (Low) | 75 | Never played | L · — · H · L · M · H · — · — | 12 | 2 / 3 → 2.8 | Short (−0.5) | 61.6 |
| Draven | Lane bully (High) | 70 | Never played | L · L · L · M · M · H · L · — | 12.5 | 3 / 3 → 3.0 | Medium (0) | 60.0 |
| Nilah | Lane bully (High) | 70 | Never played | L · L · M · L · H · H · — · — | 13 | 3 / 3 → 3.0 | Short, melee (−0.5) | 59.9 |

All Riot difficulties follow the 1–10 rule (checked against Data Dragon 16.19.1). All range groups match Riot's base ranges plus the listed modifiers.

**Owner's notes (short):**
- **Sivir:** only current main. Felt natural from day 1; best wave clear among ADCs; an underrated scaler.
- **Caitlyn:** intuitive, long range; wants her as a main. Can still use traps better. Struggles vs very heavy tank comps.
- **Senna:** easy; the hard part is scaling early and depending on teammates. Close to being a main.
- **Jinx:** really easy. Many games, not recently; could be a main again.
- **Tristana:** elo boosters' favorite, and the owner struggles against her. Gets fed on her but finds it oddly hard to carry.
- **Jhin:** fun and easy; likes his lore. Struggles vs tanks and in long trades (reload).
- **Miss Fortune:** crazy burst, really easy; her R is the champion. Poke High is the owner's call (her Q is below the 1,000-range rule).
- **Lucian:** one of the most mobile ADCs. Easy once played enough.
- **Ashe:** hates the lack of mobility, but has had a lot of success. Useful even when behind. Rusty: 3–5 games to get back.
- **Smolder:** near-infinite scaling; enemies try to end early. Could become a main soon.
- **Ezreal:** one of the most fun. Missing Qs is fatal. Struggles vs tanks.
- **Corki:** easy to pick up; could improve fast. Strong in lane.
- **Twitch:** would feel easy once a main, like Lucian.
- **Kalista:** one of the most mobile ADCs. Hard now; should get easier with practice.
- **Yunara:** most-played ADC in the first data; a newer champion. Mobility is Low because she only dashes during R.
- **Zeri:** not planning to play her for now; card to review later.
- **Varus:** can be built for attacks or for poke, and each build gives up the other style. Burst and Sustain depend on the build.
- **Akshan:** mostly a mid laner, so bot data may be thin. OTPs seem to do very well.
- **Kog'Maw:** difficulty to lower when the owner checks again.
- **Kai'Sa:** could be easy once a main.
- **Vayne:** three types in one: hypercarry, some mobility, and a bit of self-peel with her ultimate.
- **Aphelios:** hard to learn but rewarding; strong vs divers. OTPs likely beat his average.
- **Draven:** stomps early, huge snowball; OTPs shine. Not planning to learn him soon.
- **Lux, Syndra:** APCs in the current bot-lane meta. **Ziggs:** a bot-lane mage for several seasons. **Hwei:** probably very strong right now; check with data.

## Brief changes v0.45 (no change to the Pick Score), Oct 12, 2026

Pasted from the owner; the live brief has the full details.

- **Card adder CANCELLED.** Adding cards stays a chat process: the owner tells Claude in chat, Claude fact-checks the kit and drafts the card with them, Claude Code adds it. Reason: the fact-check against the kit can't be done by the page, and reliability matters more than speed. (A draft was built and discarded before any commit; nothing was pushed.)
- Range groups: no change (Short ≤500, Medium 525–575, Long ≥600 as before).
- **Phase 3 is now only the smooth run:** 7 days with no collector failures, no red "scores are old" warnings, and no code changes. Mastery review done and card editing already worked live on Oct 11.
- **Code freeze** from Oct 12 until the owner says so.

## Brief changes v0.44 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- **Draft helper, build recommendations and ban suggestions removed for good.** The site is the personal tier list only. Items, runes and matchup data keep being saved.
- Admin page done (slices 1–2, 139 tests).
- **New Phase 3 "Road to 1.0":** (a) Admin page: add new cards, (b) smooth run = one full patch with no collector failures and no red "scores are old" warnings, and every admin action working live once. Then the site is v1.0. Phase 4 = "After 1.0": weight tuning (1.x), support tier list (v2.0), jungle (v3.0), production key.
- **Version numbering:** v0.x = setup until Phase 3 is done; a new role = a new main number; rule/feature changes inside a role = 1.1, 1.2…; no version for admin card edits, adding a card with existing rules, bug fixes or wording.
- **Data storage standard (all settings in `collector/config.py`):**
  - Raw matches never stored. Match IDs 14 days.
  - Per-patch folders (champion stats, items, runes, matchups): last **5** patches (`KEEP_PATCHES`).
  - `archive/<patch>/summary.json` + `champions.json`: every patch, **forever** (about 31 KB a patch), written on every save and never cleaned (`ARCHIVE_DIR`).
  - `scores/<patch>.json`: last **20** (`KEEP_SCORE_FILES`; `latest.json` always stays). Cleanup is `prune_scores` in `collector/store.py`, run after each scoring.
  - Per-patch `players.json.gz`: **last 3 patches** (`KEEP_PLAYER_PATCHES = 3`). Decided by the owner within v0.44 (the brief's storage table says 3 too): safety for the season rebuild (`_seed_seasons`) and the new-champion back-fill (`_copy_from_patches`) matters more than about 8 MB. Older patch folders load fine without the file.
  - Season file: current season only (`KEEP_SEASONS = 1`); older seasons are no longer rebuilt from patch files.
  - Cleanup floors (`MIN_PATCHES = 2` in `store.py`): never fewer than the current + previous patch, the current season, `latest.json`.
  - **Size watch:** the run summary and log show the biggest saved file; a clear WARNING at `SIZE_WARNING_MB` = 40. No emails.
- Tests: `StorageStandardTests` in `tests/test_collector.py`.

## Brief changes v0.35 (no model change), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- Pick rate: keep the current "total games = Diamond+ players ÷ 10" method. Keep the note in `config.py`.
- Nilah stays in the bot-lane pool (proper ADC). `EXCLUDED_FROM_POOL` stays Yasuo and Katarina only.
- Vladimir is ranged (450, LoL Wiki), not melee.
- Tier boundaries confirmed at ±0.5 / ±1.5 spreads. The 1.0 and 1.25 comparison is removed from the report (`scoring/report.py`; done Oct 11).
- New for the tier-list page (build it with the page, not now): a "Carded but not ranked" line naming each carded champion that failed the filters and which filter it failed (e.g. Senna: bot-lane pick rate below 0.8%).
- 7 new bot-lane cards: Aurelion Sol, Karthus, Swain, Veigar, Vladimir (secondary Peel High), Seraphine, Mel (secondary Peel Low). They leave the "Needs a card" list. Cards are in `scoring/cards.json` (done).
- Ziggs Wave clear confirmed High. Xerath difficulty now High / High (3.0).
- Trait average is now 13.9 (39 cards). Kit adjustments recalculated for every card; the Comfort numbers in `cards.json` now come from the live brief (e.g. Sivir 98.7, Seraphine 89.0).
- Rule: types and trait levels are the owner's opinion; only numbers (ranges, Riot difficulty, item stats) get fact-checked.

## Brief changes v0.35, second block (no model change), Oct 11, 2026

- Removed the board item "Get an email from GitHub when a collector run fails" (no email alerts). Added to open questions: check collector health by eye when the site looks stale.
- Tier list page item updated: Comfort shown next to the Pick Score (Pick Score stays the main number); sample-size label by real games (this patch + last patch together): Low 1,000–2,999, Medium 3,000–9,999, High 10,000+, kept as one setting in the code (`SAMPLE_SIZE_LIMITS` in `site/settings.js`); PC first, phone only needs to be readable; English only; built in 3 slices.
- Open question added: recheck the sample-size limits after a few patches.
- Growth advisor: the Oct 11 test works as intended; keep as is.

## Brief changes v0.36 (model change), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- MODEL v0.36: the tier follows the Pick Score only. Remove the stats floor (no more B cap, no more "*") and the S condition "win rate at or above the Diamond+ average". Tiers: S +1.5 spreads or more, A +0.5 to +1.5, B −0.5 to +0.5, C −1.5 to −0.5, D below −1.5.
- New: a champion whose win rate is 1.5% or more below the Diamond+ average shows a ⚠ next to its win rate (display only, no effect on the tier).
- Board: slice 2 also includes a colored mastery badge, column sorting and the "Carded but not ranked" line.
- Open question added: Vladimir and Mel sit right at the 0.8% pick-rate bar.

## Brief changes v0.36, second block (no model change), Oct 11, 2026

- Board, tier list page: slice 2 done; mastery shown as 1–5 colored dots under Comfort. New: column titles show a short explanation on hover (what the number means and its weight in the Pick Score); the texts live in one file (`site/help.js`) and get updated with every model version.
- Open question added: sorting by mastery was removed with the dots; maybe a mastery filter later.

## Brief changes v0.37 (display and plan changes, no score change), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- Ban suggestions removed from Phase 2 (moved to later; per-champion counter bans stay in Phase 3, maybe). **Do not build any ban list.** (The old Ban threat code was removed in v0.38.)
- Growth advisor gets a "skill pays off" signal: OTP win rate − overall win rate for that champion, shown only with 20+ bot-lane OTP games. Information only: it must not change any score.
- OTP win rate is hidden below 20 bot-lane OTP games and shows "too few games" instead (Mel showed 0.0% from 2 games). The OTP score calculation itself does not change. The 20 is one setting: `OTP_MIN_GAMES_SHOWN` in `site/settings.js`.
- Slice 3 = tabs instead of one long page.

## Brief changes v0.38 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- Growth advisor split into two lists: "Top upgrades" (same rule as before: target mastery, shown only when it beats the current #3 pick) and "Could reach A or S" (every carded champion now in B, C or D whose Pick Score at Main mastery would land in A or S).
- "Skill pays off" shown compact (e.g. "OTP +4.6% · 12 OTPs · 340 games"), still hidden below 20 bot-lane OTP games.
- Slice 3 polish: patch-mix line at the top; colored Meta Score and Comfort boxes (tier steps ±0.5 / ±1.5 spreads); Comfort tab reordered; card-only information read straight from the cards; "best reachable" hover on the Tier list; old ban code removed.

## Brief changes v0.39 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- Growth advisor uses the next mastery level only, for both lists: Never played → Below average → Average → Good → Main. Never played and Below average no longer jump straight to Good (`GROWTH_TARGET` in `scoring/config.py`).
- "Could reach A or S" is renamed **"Next step to A or S"** and uses one step up, not Main. If it is empty the page shows one line: "None this patch · closest: <champion>, <x> points short" (the B/C/D champion nearest the A line after one step).
- **"Ceiling at Main"** is kept as information only (a quiet "at Main: S" on each Growth row; "Best reachable" hover on the Tier list). It never decides who appears in either list.
- Sample-size labels: **Low under 10,000, Medium 10,000–29,999, High 30,000+** real games (this patch + last patch). One setting: `SAMPLE_SIZE_LIMITS` in `site/settings.js` (`low: 1000` is only the ranking floor).
- No change to the Pick Score.

## Brief changes v0.40 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- Growth tab gets a third table, **"Utopy picks"** (Alejandro's private name for long-term goals). Information only; no change to the Pick Score.
  - Listed: every carded champion whose mastery is not Main and whose tier now is not S, whose Pick Score would reach S at Good or at Main. Same maths as the ceiling at Main (only that champion's mastery changes, compared with this patch's normal tier cutoffs). Only levels above the current mastery are tried (`UTOPY_LEVELS` in `scoring/config.py`).
  - Columns: champion · mastery now · first level that reaches S · steps away · Pick Score now → score at that level (both Good and Main when both reach S) · the compact "skill pays off" line (or "too few games" below 20 bot-lane OTP games). Order: fewest steps first, then highest score at the first level.
  - Last table on the Growth tab, smaller and quieter, subtitle "Long-term goals, information only", line "Based on patch X data; can change each patch.". When empty: "None this patch · closest: <champion>, N points short of S at Main". Code: `utopy_list` in `scoring/model.py` (written to the scores file as `utopy_list` and `utopy_closest`); the page reads them.
  - It never changes a score or the "Top upgrades" / "Next step to A or S" lists (tests check).
- **Riot developer rules plan approved** (Part B below).
- **Phase 3 note:** the draft helper must always offer several choices with reasons, never one forced pick (Riot rule: apps can't dictate player decisions).

## Brief changes v0.41 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- **Player codes get a secret key (salt)**, stored as the GitHub secret `PLAYER_CODE_SALT`. Existing codes were **converted, not dropped**, so season OTP totals since Oct 2 are kept. New code = `HMAC-SHA256(secret, old code)` shortened to 16 characters; for a new player the collector makes the old code first, then the HMAC (`scramble` in `collector/store.py`).
- The history of the public `data` and `data-backup` branches was reset after a private backup, so old unsalted codes are no longer on any branch. Game IDs in `state/` stay (not personal data).
- Riot policy dates: general policy **May 29, 2025**; League game policy **Aug 21, 2026** (https://developer.riotgames.com/policies/game-specific). The product is already registered in the Developer Portal; the owner updates its description.
- Done Oct 11 (the conversion): backup of both branches kept outside the repo; before/after comparison identical (players, season games and wins per champion, OTP players and games, every Pick Score); the 42 Actions logs checked, no codes or player IDs in them.
- **Rules now in the code:** the collector refuses to start without `PLAYER_CODE_SALT` (at least 32 characters), and refuses saved data made with another secret or not converted (`codes.json` in the data holds a format version and a short fingerprint of the secret). A wrong secret would otherwise orphan every player and lose the OTP totals. **Never change or lose the secret**; keep a copy in the password manager. Running the collector by hand needs `PLAYER_CODE_SALT` in the environment; the tests use a made-up one.
- One-time converter: `python3 -m collector.convert_codes DATA_DIR` (refuses to run twice). Tests: `tests/test_player_codes.py`.
- Known limit: GitHub still serves the old (replaced) commits to anyone who knows their exact ID; only GitHub Support can erase them. The old codes were unsalted hashes, so this is a small leak, but it is why the secret matters from now on.
- Small fix: the "near misses" list breaks ties by name (it flipped order between runs on the same data). Display only.

### Riot developer rules (checked Oct 11, 2026)

- Riot policy pages re-read on Oct 11, 2026. `developer.riotgames.com/policies/general`: **LAST UPDATED: MAY 29, 2025**. `developer.riotgames.com/docs/lol` (Developer API Policy and Game Policy sections): the page shows **no "last updated" date** (only "© 2021 Riot Games, Inc." and a Nov 20, 2023 note about Riot IDs).
- Nothing changed from the rules we planned around: legal notice required; product must be registered with an up-to-date description; key never in code; HTTPS only; no data broker; no identifying hidden players; no apps that dictate player decisions. (Also noted: Riot logos only from the Press Kit and only when unavoidable; free tier required; no MMR/ELO alternatives to the official ranking.)
- **Legal notice (footer, visible under all 4 tabs, outside `#content` so it shows while loading):** Riot's exact League wording from the docs/lol page with "LoL Pick Lab" as the product name: "LoL Pick Lab is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc." Below it, a small about line: free personal project for me and friends, no ads, no payments, no data sold; stats are combined from many Diamond+ ranked games and never show individual players.
- Tests: `tests/test_site.py` (`LegalNoticeTests`: notice present with the exact wording, never inside one tab or a hidden element) and `tests/test_safety.py` (fails on any `RGAPI-` key-shaped text in the project files or in the main branch history).
- **Safety audit, Oct 11 (report only; nothing was deleted or rewritten):** no key or key-shaped text in the code, any git branch's history, the unpacked `data` and `data-backup` files, the site files or the 42 GitHub Actions logs. Every Riot call is HTTPS (`collector/riot.py`), the key travels in the `X-Riot-Token` header and comes only from the `RIOT_API_KEY` secret. The site has no images and no Riot logos. Open finding: player codes were an unsalted truncated SHA-256 of the PUUID, so anyone who knew a player's PUUID could look that player up in the public `data` branch. Fixed in v0.41 with a secret key (see "Brief changes v0.41").

## Brief changes v0.42 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- New: a **"Last mastery review: patch X"** reminder on the Comfort tab only. The one value lives in `scoring/review.json` (`last_mastery_review_patch`, starts at "16.20"), next to the cards, with a copy in `site/data/review.json` that a test keeps equal (copy it again when it changes). Not in the scoring code, so a future admin page can change just this value. Count = current minor − review minor in the same season: 0–4 grey (information), exactly 5 amber ("Mastery review due soon (5 patches since 16.20)"), 6 or more red ("Mastery review overdue (N patches since 16.20)"), new season red ("New season: mastery review due"), unknown current patch grey line with no count. Hover help: "Review your mastery levels every 5–6 patches. Tell Claude Code 'mastery review done on patch X' to reset (admin button coming later)." Code: `masteryReview` in `site/format.js`; tests in `tests/test_site.py` (`MasteryReviewTests`) and `tests/site_format.test.js`. **To reset: when the owner says "mastery review done on patch X", change `scoring/review.json` and copy it to `site/data/review.json`.**
- New board item (moved to Phase 2, right after "Publish on Vercel"): **Admin page**, with a "Mastery review done" button first, then card editing. It replaces the open question about editing cards.
- No change to the Pick Score.

## Brief changes v0.43 (no change to the Pick Score), Oct 11, 2026

Pasted from the owner; the live brief has the full details.

- **Admin page slice 2 approved: card editing** (mastery + traits) with a Comfort preview and a quick rescore after each edit. Phase 4 board item added: "Admin page: add new cards" (not built).
- **The card files in the repo are now the source of truth for card values** (`scoring/cards.json`, copied to `site/data/cards.json`). The brief's card tables are a v0.43 snapshot. No change to the Pick Score formula.
- **What was built (Oct 11):**
  - `/admin` shows every card (sorted by name) under the review button: a Mastery dropdown and one dropdown per trait (None / Low / Mid / High), starting at the card's current values, a live preview line ("Comfort 86.3 → 89.1", plus "trait average 13.95 → 13.82, all cards move slightly" when a trait changes) and an Update button. One password box at the top, emptied after every action. Type, strength, difficulty, range and notes are not editable. The preview maths is `site/comfort-preview.js`, a copy of `scoring/comfort.py` and its constants; tests compare it with the Python code for every card and every possible single change (including trait-average changes, caps and Varus's flexibility bonus). **When `scoring/comfort.py` or `scoring/config.py` changes, update the copy; the tests fail otherwise.**
  - Helper `api/admin-card.js` (logic `lib/admin-cards.js`, shared parts `lib/admin-common.js`): `GET` returns the newest cards; `POST` changes ONE value. Same password check and wrong-password wait as slice 1. It accepts only `{password, champion, field, from, value}` with field = `mastery` or one of the 8 traits and only the allowed values (anything else, unknown champions included, is refused before GitHub is touched). It re-reads the newest `scoring/cards.json` from GitHub right before saving; if the card no longer has the `from` value it answers "Someone else changed the cards, reload and try again"; if `main` moved meanwhile it re-reads and retries (up to 3 times). It edits the file text in place (nothing else in the file changes) and checks that the result is the old data plus exactly that one change. One commit per edit, e.g. "Card edit: Jinx mastery Good → Main" or "Card edit: Jinx AoE High → Mid"; those commits are the edit history. It writes only the two card files and **never touches `review.json`**. Same Vercel secrets (`ADMIN_PASSWORD`, `GITHUB_TOKEN`); no new token permission. The page sends one request per changed field.
  - **Quick rescore:** `.github/workflows/rescore.yml` runs when `scoring/cards.json` or `site/data/cards.json` changes on `main`. It reapplies the scoring to the data already on the `data` branch (zero Riot requests; no Riot key or player-code secret in the workflow) and replaces only the scores. Rule chosen: **if a collector run is going or waiting, the rescore stops at once** (it does not queue behind it, and it never shares the collector's concurrency group, because a queued rescore would cancel a waiting collector). That is safe because **the collector now reads the newest cards from `main` every time it scores** (`newest_cards` in `collector/main.py`, at least once an hour; falls back to its checkout's cards if GitHub can't be reached). Otherwise the rescore pushes with `--force-with-lease` against the `data` commit it loaded, so it can never overwrite a collector save. Quick edits in a row replace each other (newest cards win). A rescore keeps the scores file's "generated" time (`--keep-generated`), so "Last updated" still means when games were last collected. If a rescore fails, the old scores stay on the site and the next collector run fixes it.
  - New options: `python -m scoring --cards-file FILE` and `--keep-generated`.
  - **Timing:** the cards on the page (and the admin page) update when Vercel rebuilds from `main` (about a minute); the scores update about 2 to 3 minutes after the edit (rescore), then up to 5 minutes of GitHub caching; with a collector run in progress, at the collector's next save (within an hour).
- **Tests and the card files:** tests that compare with the saved scores copy or the brief numbers read a frozen copy of the cards, `tests/fixtures/cards_snapshot.json` (the cards as of Oct 11), so editing a card from the admin page never breaks the tests (and the collector workflow, which runs them, keeps working). `python -m scoring --self-check` compares the *current* cards with the brief snapshot numbers, so it will report differences after any card edit; that is expected.
- Comfort tab hover text reworded: it now mentions the review button on the admin page (the address stays hidden).

## Tier list page (`site/`, Phase 2, slices 1, 2 and 3 built Oct 11, 2026)

- Plain static files (HTML, CSS, JavaScript; no server, no build step). `index.html` + `style.css` + `app.js` draw the table; `format.js` holds the small text helpers; `settings.js` holds every setting (data address, sample-size limits, "stale after" hours).
- It reads only the finished scores file the collector writes (`scores/latest.json` on the `data` branch, fetched from `raw.githubusercontent.com`). It never calls the Riot API and never contains a key; a test scans `site/` for key names and Riot addresses.
- If the live file can't be reached it shows `site/data/latest.json` (a saved copy) with a visible notice. This copy is only a fallback and goes stale; refresh it by copying a new `scores/latest.json` over it.
- Slice 1 shows: patch, "Last updated" (the file's `generated` time, with a red warning when older than 13 hours), then one table sorted by Pick Score: rank, champion, tier (own color), Pick Score, Comfort, Stats, OTP points, win rate, difference from the Diamond+ average, games (real games, this patch + last patch).
- **Slice 2 (Oct 11)** adds, in the same table: a colored **Mastery** column (outlined pill, strong to weak: Main gold, Good green, Average blue, Below average purple-grey, Never played grey; from `cards.json`); a **sample-size label** under Games (Low / Medium / High by real games, limits in `SAMPLE_SIZE_LIMITS` in `site/settings.js`); the **OTP players and OTP games** under each OTP score; the **⚠** next to a win rate 1.5 points or more below average. **Click a champion** to open its details row: trait badges with their level (High, Mid, Low; absent traits aren't shown), "Data: X% this patch", sample size, pick rate, OTP players, games and OTP win rate vs everyone's. **Click a column title** to sort, click again to reverse; the page always opens sorted by Pick Score (so by tier) and does not remember the sort. Below the table, a **"Carded but not ranked"** line lists each carded champion that failed the filters and why (from `cards_not_ranked` in the scores file, now a list of `{name, failed, ...}`). The scores file also carries `traits`, `main_type`, `kind` and `win_rate_warning` for each ranked champion. The page copes with an older scores file that lacks them.
- **Hover help on column titles:** every column title shows 1–2 plain lines (what the number means and its weight in the Pick Score). All the texts live in `site/help.js`; update them with every model version. `tests/test_site.py` fails if the weights, tier cutoffs, ⚠ limit, win-rate points per point or sample-size limits written in the texts differ from `scoring/config.py` and `site/settings.js`.
- **Mastery** is shown as 5 small dots under the Comfort score (more filled = better, colored by level); the Mastery column and its sorting were removed.
- **What "OTP games" counts:** the one-tricks' *bot-lane* games on the champion, this patch and last patch. The OTP rule itself (55% of recent games, 50+ this season) looks at all roles, so a champion mostly played elsewhere (Mel, mostly mid) can have OTP players with only a few bot-lane games. The page now says "bot-lane games" and shows the all-role games too (`otp_games_all_roles`, display only; the scores didn't change).
- **Slice 3 (Oct 11, v0.37): four tabs** at the top: **Tier list** (opens first, unchanged) · **Meta** · **Comfort** · **Growth**. Every table sorts by clicking its column titles; each tab has its own sort, nothing is remembered.
  - **Meta:** every champion that passes the 4 filters, ranked by Meta Score (= Stats points: 75% win rate points + 25% pick rate points). Champions without a card show "no card yet". Below it, **Needs a card**: the uncarded ones, best Meta Score first (empty message when there are none). Read from `meta_score_list` and `has_card` in the scores file.
  - **Comfort** (view only): one row per carded champion: main type (strength), secondary type (strength), type points, mastery (points), base, trait score, kit adj., difficulty (Riot / mine → final), diff. adj., range adj., flexibility, final Comfort. Every number comes from `comfort_parts` (the same Comfort code the Pick Score uses); the card details (`card_info`: strengths, secondary types, difficulty ratings, range) are written next to it by `scoring/model.py`. An older scores file without `card_info` still draws, with a notice.
  - **Growth:** the Growth advisor as before (only carded champions; a tip shows only when the target-mastery Pick Score beats the current #3 pick), with the gain, the new rank and tier, and the "skill pays off" line (OTP win rate − overall win rate, from the champion's `otp_delta`) when the champion has `OTP_MIN_GAMES_SHOWN` (20) or more bot-lane OTP games; with fewer games nothing is shown. Information only.
  - **OTP win rate** everywhere on the page shows "too few games" below 20 bot-lane OTP games.
  - **Hover help:** an instant custom tooltip (any element with `data-tip`; not the slow browser tooltip). Hover the **column titles** (the gray capital-letter words above each table), the **tab names**, the **Needs a card** heading, the ⚠ sign and the mastery dots. Texts for every tab and column are in `site/help.js` (currently v0.37); `tests/test_site.py` checks the numbers written there against `scoring/config.py` and `site/settings.js`.
  - `index.html?saved` forces the saved copy (`site/data/latest.json`), useful for checking new fields before the collector has produced them.
- **v0.38 polish (Oct 11):**
  - **Patch mix:** a line under the title, e.g. "Patch 16.20 · most champions 61–96% this patch" (10th to 90th percentile of the champions' this-patch share, worked out by the page), with a hover bubble giving the rule. Every champion's "Data: X% this patch" shows as a blue chip under Games (tier and Meta tables), with the same bubble.
  - **Games are real games** (this patch + last patch, before the LAN/KR/NA/EUW double weight): `real_games` in the scores file is `counter[0] + counter[2]`; the double weight only feeds win rate and pick rate. A test checks the page never reads weighted numbers.
  - **Colored boxes** for the Meta Score (Meta tab, Needs a card) and Comfort (Comfort tab): green above the average, red below, stronger each 0.5 and 1.5 spreads away (`SPREAD_STEPS` in `site/settings.js`, equal to the tier boundaries; a test checks). Average and spread come from the champions on that tab.
  - **Cards are read straight from `site/data/cards.json`** (a copy of `scoring/cards.json`; **copy it again whenever a card changes, a test fails if they differ**). Type, strength, secondary type, traits, mastery, difficulty ratings and range come from there, so those never wait for the collector. The Comfort *numbers* (type points, base, kit adj.…) still come from `comfort_parts` in the scores file, so a changed card shows its new numbers after the next collector run. `card_info` is no longer written to the scores file.
  - **Comfort tab order:** Champion · Comfort (colored box) · Trait score with trait badges · Mastery dots · then the smaller, lighter detail columns. Sorted by Comfort, highest first.
  - **Growth tab (v0.39):** two tables. **Top upgrades**: the next mastery level only, shown only when the new Pick Score beats the current #3 pick. **Next step to A or S** (`next_step_list` in the scores file): carded champions now in B, C or D whose Pick Score one step up lands in A or S (tier now → next, gain); when empty, `next_step_closest` gives the "None this patch · closest: …" line. Both show a quiet **Ceiling** column ("at Main: S", from `best_tier_at_main`, information only). The scores file gives every carded champion `pick_score_at_main` and `best_tier_at_main` (same Comfort and Pick Score code, only the mastery changes; tier read against the patch's current average and spread). The Tier list shows "Best reachable: B at Main" in a hover bubble on the name of a champion that can't reach A even at Main.
  - **Which scores file:** the live file is used; only if it is from an older model version than `MIN_MODEL_VERSION` (settings) and the saved copy is newer, the saved copy is shown with a notice until the next collector run.
  - The old, unused ban code (Ban threat) was removed from `scoring/` and its tests.
- **Local preview:** the preview program can't read the Documents folder, so it serves a copy at `~/.lol-pick-lab-preview` (see `.claude/launch.json`, port 8124). **Run `scripts/sync_preview.sh` after every change to `site/`**, or the preview shows old code (this is why the slice-2 hover help looked missing: the old preview served a frozen copy).
- Vercel setup (Oct 11): `vercel.json` at the repo root publishes only `site/` (no build, no install) and builds only branch `main` (`ignoreCommand`). Nothing secret on Vercel; the page reads live scores from the `data` branch. (Before that: the repository had no `vercel.json`, no webhooks, no deployments and no Vercel check on `main`, so a push does not deploy the site. Nothing was published then.)
- **v0.40:** the Growth tab has a third, quieter table **Utopy picks** (see "Brief changes v0.40"), and every tab has the Riot legal notice and about line in a footer. `MIN_MODEL_VERSION` is now v0.40.
- Tests: `tests/test_site.py` and `tests/site_format.test.js` (the Python run calls Node for the JavaScript tests when Node is installed).
- Deployed on Vercel Oct 11 as baihu-lol-pl.vercel.app (owner imported it by hand; settings in the Vercel setup line above). Collector schedule re-enabled Oct 11 (UTC 02:14 manual run).

## Project board

**Phase 0, setup:** all done.

**Phase 1, data collector**
- [x] Pick the regions to collect from
- [x] Claude builds the collector for Diamond+ ADC and support games
- [x] Store the Riot key safely as a GitHub secret (never in the code)
- [ ] Run it for a few days and check that sample sizes grow
- [x] Define the OTP rule (share of recent games on one champion)

**Phase 2, tier list website (first shareable version)**
- [x] Claude writes the scoring model as code (`scoring/`, see "Scoring code")
- [ ] Fill in a champion card (type, traits, mastery, difficulty, note) for every ADC the owner plays
- [ ] Build the bot-lane tier list page in 3 slices (`site/`): Pick Score with Comfort next to it (Pick Score stays the main number), Meta Score and the Growth advisor (ban suggestions moved to later in v0.37), plus games played, a sample-size label by real games (this patch + last patch together: Low under 10,000, Medium 10,000–29,999, High 30,000+ since v0.39; one setting in the code so it can be retuned), a data-freshness label ("Data: 75% this patch") and trait badges for every champion, plus the number of OTP players and OTP games behind each OTP score. PC first (phone only needs to be readable), English only.
  - [x] Slice 1: basic tier table (Oct 11)
  - [x] Slice 2: mastery shown as 1–5 colored dots under Comfort, trait badges, sample-size label, data-freshness label, OTP counts, ⚠ win-rate warning, column sorting, "Carded but not ranked" (Oct 11)
  - [x] Slice 3: tabs Tier list · Meta · Comfort · Growth, Meta Score with Needs a card, Comfort breakdown, Growth advisor with "skill pays off", "too few games" below 20 OTP games (Oct 11, v0.37). Ban suggestions removed from this phase.
- [ ] Follow Riot's developer rules (v0.40: policies re-read Oct 11, 2026, no change; legal notice + about line footer done; safety audit done, salting done in v0.41; product already registered in the Developer Portal, the owner updates its description): legal notice on the site ("not endorsed by Riot Games"), personal key for a small private community, free and non-commercial, no data sold, key never exposed. Claude checks Riot's current policy page before publishing
- [x] Show a "last mastery review: patch X" reminder on the Comfort tab (review every 5–6 patches; v0.42, Oct 11)
- [x] Publish on Vercel and share the link with one friend (project `baihu-lol-pl`, site baihu-lol-pl.vercel.app; published and checked by the owner Oct 11: fresh data, no saved-copy notice, 4 tabs OK; Riot portal Product URL updated; shared with the owner's brother)
- [ ] Admin page (plan approved Oct 11): hidden address `/admin` only, no link on the site, password typed for every action.
  - [x] Slice 1 (built Oct 11): password box + "Mastery review done" button. Page `site/admin.html` + `site/admin.js` (noindex meta and `X-Robots-Tag`); Vercel helper `api/admin-review.js` with its logic in `lib/admin-review.js`. The helper reads the Vercel secrets `ADMIN_PASSWORD` and `GITHUB_TOKEN`, compares the password in constant time (wrong password: waits 3 s, "Wrong password"), reads the CURRENT patch itself from `scores/latest.json` on the data branch (never from the browser; must look like "16.20"), and writes it to `scoring/review.json` and `site/data/review.json` in ONE commit on `main` ("Mastery review done on patch X (admin page)"). It can change only those two files. Errors: "Admin not set up yet", "GitHub key expired or invalid: make a new one", "Couldn't read the current patch, try later". Tests: `tests/admin_review.test.js` (fake GitHub) and `tests/test_vercel.py`. The owner still has to set the two secrets on Vercel (never in chat or files).
  - [ ] Slice 2 (approved v0.43; built Oct 11, see "Brief changes v0.43"): card editing (mastery + the 8 traits) on `/admin`, with a live Comfort preview, one commit per edit and a quick rescore. **Card updates NEVER reset the review reminder; only "Mastery review done" does.**
- [ ] Compare the output with the owner's manual picks for one patch and tune the weights

**Phase 3, Road to 1.0**
- [ ] Smooth run: 7 days with no collector failures, no red "scores are old" warnings and no code changes. Then the site is v1.0. (Adding cards stays a chat process; the admin card adder was cancelled in v0.45.)

**Phase 4, after 1.0**
- [ ] Weight tuning (1.x)
- [ ] Support tier list (v2.0), then jungle tier list (v3.0)
- [x] Make cards for new bot-lane champions that pass the filters (Aurelion Sol, Karthus, Swain, Veigar, Vladimir, Seraphine, Mel; done Oct 11; more if the "Needs a card" list grows)
- [ ] Apply for a production key if the site grows beyond friends

## Open questions & improvements

**Decide before or during Phase 2**
- **Ban list check:** the owner's bans in the last 3 months were Tristana, and they'd also ban Yunara or Jinx. Does the Ban threat ranking put them near the top? (Bans go by data, not by these examples.)
- **Tier boundaries:** confirmed at ±0.5 / ±1.5 spreads (Oct 11). The stats floor was removed in v0.36.
- **Mastery filter:** sorting by mastery was removed with the dots; maybe add a mastery filter later.
- **Pick-rate bar:** Vladimir and Mel sit right at the 0.8% bar (0.82% and 0.81% on patch 16.20), so they may drop in and out of the ranking from patch to patch. Decide in Phase 2 whether that is fine.
- Tune the kit weight (0.9) and difficulty weight (3) in Phase 2. Their caps stay ±2.5 and ±1.5 on the Pick Score.
- **Are Pick Scores spread enough?** Comfort for the owner's pool sits mostly between 86 and 100, so Stats should do most of the separating. Check with real data and widen the gaps if the tiers feel too similar.
- Review all cards' traits with the "at least Low" rule (only Lucian is done so far), and fill in mastery and difficulty for any remaining draft cards.
- Flexibility bonus (beta, Varus only): check in Phase 2 whether it's worth keeping or extending.
- **Calibration list** (the owner's opinion, written Oct 3 before any data): the strongest bot-lane champions this meta, unordered: Jinx, Hwei, Lux, Tristana, Xayah, Caitlyn, Viktor, Ziggs, Twitch, Yunara, Zeri, Ashe, Draven. Test in Phase 2: do they land at the top of the Meta Score (data only)?
- **Cards per role (Phase 2 design note from the owner):** store champion cards per champion + role, with the same card structure, but each role has its own types, trait list and priorities. A champion can have a bot-lane card and a support card.

- **Player codes (decided v0.41, done Oct 11):** salted with the secret `PLAYER_CODE_SALT`, old codes converted, branch history reset. Game IDs in `state/` stay. Still open: the old commits remain fetchable by exact ID on GitHub (see v0.41).
- **Collector health:** no email alerts (decided Oct 11). Check the collector by eye when the site looks stale; the page shows a "Last updated" time and warns when it is old.
- **Sample-size limits:** recheck the Low / Medium / High limits (changed in v0.39 to under 10,000 / 10,000 / 30,000 real games) after a few patches.

**Review once all ADC cards are done**
- Review the types, type strengths, traits, priorities and levels together, and check that the rules still fit.
- Range: decide champion by champion which modifiers last "most of the game" when finishing the remaining cards.

## Scoring code (Phase 2, built Oct 11, 2026)

- Code: `scoring/` (Python standard library only). Settings, every number of the recipe, in `scoring/config.py`; the 32 champion cards, with the brief's Comfort printed next to each, in `scoring/cards.json`; Comfort in `scoring/comfort.py`; filters, blending, Stats, OTP, Pick Score, tiers, Ban threat and Growth advisor in `scoring/model.py`.
- Run: `python3 -m scoring --data-dir DATA --report` (tables) or `python3 -m scoring --self-check` (every card's Comfort against the brief; all 32 match within 0.04).
- After every collector save, `collector/main.py` runs it as a separate process and writes `scores/latest.json` and `scores/<patch>.json` into the `data` branch. A scoring failure is logged and never stops the data from being saved.
- Choices the brief doesn't spell out (the owner can change any of them):
  - **Pick rate** = the champion's bot-lane games ÷ all games (`PICK_RATE_BASIS = "games"`), with all games estimated as Diamond+ participants ÷ 10 (see the recipe). The other reading, share of all bot-lane picks (`"lane"`), is half as big and drops Hwei, Lux, Ziggs, Syndra, Xerath and Veigar from the ranking.
  - **Blend:** "this patch's games" = the champion's real games in the lane this patch. Win rate is compared with each patch's own Diamond+ average, then blended; pick rate and lane share are blended too. A champion with no games last patch is 100% this patch.
  - **OTP:** the 55% / 50-game rule uses all roles; the OTP win rate and OTP games are the player's bot-lane games on that champion, compared with the champion's bot-lane win rate over the same two patches (unweighted, because player files have no server split). Champions with no OTP games get a neutral 50.
  - **Trait average:** the average over the eligible champions that have a card (fallback: all cards when fewer than 10).
  - **Tiers** use spreads rounded to 2 decimals; one spread is the population standard deviation of the Pick Scores of the champions with a card. Tier at target in the Growth advisor is read against the patch's current average and spread.
  - **Pool exclusion:** Yasuo and Katarina (melee, "stay out of my bot-lane pool") are left out of every ranking (`EXCLUDED_FROM_POOL`) and listed separately.

## Model versions

Newest first. Each block of 10 versions is later folded into one summary row.

- **v0.45** (Oct 12, 2026): no score change. Card adder cancelled (cards are added through chat); Phase 3 = smooth run only; code freeze.
- **v0.44** (Oct 11, 2026): no score change. Draft helper, builds and ban suggestions removed for good; Road to 1.0; version numbering rule; data storage standard.
- **v0.43** (Oct 11, 2026): no score change. Admin page card editing (mastery + traits) with Comfort preview, one commit per edit, quick rescore workflow; the card files become the source of truth.
- **v0.42** (Oct 11, 2026): no score change. "Last mastery review: patch X" reminder on the Comfort tab (one setting in `scoring/review.json`); Admin page added to the board (later).
- **v0.41** (Oct 11, 2026): no score change. Player codes get a secret key (`PLAYER_CODE_SALT`); old codes converted without losing data; `data` and `data-backup` history reset; Riot policy dates logged (general May 29, 2025; League game policy Aug 21, 2026).
- **v0.40** (Oct 11, 2026): no score change. Growth tab gets the third table "Utopy picks" (long-term goals, information only). Riot developer rules plan: legal notice and about line footer on all tabs, key-scan and legal-notice tests, safety audit.
- **v0.39** (Oct 11, 2026): no score change. Growth advisor uses the next mastery level only (both lists); "Could reach A or S" becomes "Next step to A or S" with a "closest" line when empty; ceiling at Main kept as information only; sample-size labels Low under 10,000, Medium 10,000–29,999, High 30,000+.
- **v0.38** (Oct 11, 2026): no score change. Growth advisor split into Top upgrades and Could reach A or S (Main mastery lands in A or S); skill pays off shown compact; ban code removed.
- **v0.37** (Oct 11, 2026): no score change. Ban suggestions moved to later. Growth advisor gets an information-only "skill pays off" signal (OTP win rate − overall win rate, shown with 20+ bot-lane OTP games). OTP win rate shows "too few games" below 20 bot-lane OTP games. Tier list page gets tabs (slice 3).
- **v0.36** (Oct 11, 2026): the tier follows the Pick Score only. Stats floor removed (no more B cap, no more "*") and the S condition "win rate at or above the Diamond+ average" removed. Tiers: S +1.5 spreads or more, A +0.5 to +1.5, B −0.5 to +0.5, C −1.5 to −0.5, D below −1.5. New display-only ⚠ next to a win rate 1.5% or more below the Diamond+ average. On patch 16.20 data only Caitlyn changes tier (B* → A).
- **v0.35** (Oct 11, 2026): weights Stats 42.5% / Comfort 52.5% / OTP 5%. Pick rate defined as the champion's bot-lane games ÷ all games (same numbers as before); pick-rate filter lowered from 1% to 0.8%. Tiers by spreads from the patch's average Pick Score (S +1.5 and win rate at or above average, A +0.5, B −0.5, C −1.5); stats floor kept; boundaries in config. Growth advisor only for champions with a card; new "Needs a card" list. Ban threat shows each champion's role. Yasuo and Katarina stay excluded.
- **v0.34** (Oct 11, 2026): the 1,000-game filter counts this patch and last patch together, so the tier list stays full early in a patch (lane share and pick rate use the same blended numbers; the data-freshness label shows how much is this patch). Meta Score defined = Stats points alone. Build recommendations dropped from the goals (maybe later). Roles built in order bot lane → support → jungle.
- **v0.33** (Oct 3, 2026): PBI removed, so Stats = 75% win rate points + 25% pick rate. Bans by data only: Ban threat = (win rate − Diamond+ average) × pick rate. Growth advisor rule (Never played and Below average → as if Good; Average and Good → one level up; shown if it beats the #3 pick). The final site covers bot lane, jungle and support.
- **v0.32** (Oct 3, 2026): patch blending, where share of this patch = this patch's games ÷ (this patch's games + 1,000) and the rest comes from last patch, with a data-freshness label per champion. Season totals for OTPs stored (current and previous season).
- **v0.31** (Oct 3, 2026): Team utility means general usefulness to the team. Trait average and Stats ranks use all eligible bot-lane champions (ADCs and APCs).
- **v0.30** (Oct 3, 2026): bot lane includes APCs. The 6 mage cards (Lux, Ziggs, Syndra, Hwei, Viktor, Xerath) join the same list and the same trait average as the ADCs (13.7). Every card recalculated.
- **v0.20–v0.29** (Oct 2–3, 2026): secondary types get a strength; real games for the 1,000-game filter; Riot difficulty from the 1–10 game-data number, with the website as backup; range groups (Short ≤500, Medium 525–575, Long 600+) and a range adjustment (±0.5 Comfort); OTP rule (55% of recent games, 50+ games) and OTP reliability; mastery reworked (Main 100, Good 90, Average 80, Below average 70, Never played 60) with matching difficulty factors; Discomfort removed; Growth advisor; every trait at least Low unless absent; new trait AoE (High); flexibility bonus beta (Varus); the owner's difficulty is a locked base rating.
- **v0.10–v0.19** (Oct 2, 2026): new trait Poke; Comfort base 40% type + 60% mastery, capped at 100; kit and difficulty adjustments inside Comfort (traits up to ±2.5, difficulty up to ±1.5 on the Pick Score); difficulty = 80% the owner's rating + 20% Riot's, compared with Medium (2); traits weighted by priority and level (Low 0.5, Mid 1, High 1.5); Hard and Soft CC merged into one CC trait; type strength (High 100%, Mid 97.5%, Low 95%).
- **v0.1–v0.9** (Oct 1–2, 2026): first ADC model (Stats 40%, Comfort 50%, OTP 10%; LAN, KR, NA, EUW ×2); win rate scored by distance from the Diamond+ average; 5 tiers with fixed cutoffs and a stats floor at B; ban suggestions; types Mobility, Peel, Hypercarry, Utility, Mage, Lane bully; secondary types that can only help; type and trait fact-checks; traits and the kit adjustment; difficulty adjustment.
