# LoL Pick Lab — instructions for Claude

`project-brief.pdf` (kept locally, not in the repo) is the source of truth. This file summarizes it; current brief: **v0.33**. If the two disagree, the brief wins; ask the owner which to update.

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
2. **Build recommendations**: items, runes and skill order.
3. **Draft helper**: enter the draft, get the top 3 picks with reasons.

The final site covers 3 roles: bot lane (ADC and APC), jungle and support. Nothing is built for jungle or support until the bot-lane (ADC) tier list is done.

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
- Data lives on the `data` branch, replaced each save with no history (fetch it with `git fetch origin +data:refs/remotes/origin/data`). `data-backup` holds the previous run's copy, and the collector falls back to it if a file is damaged. Totals for the last 3 patches are kept. See the `README.md` on the data branch for the file format. Player IDs are stored only as scrambled codes.
- Champions are stored by Riot's champion ID. The `name` field is Riot's internal name (`Kaisa`, `MissFortune`, `KogMaw`); the website must take display names from Data Dragon.
- **Player files (for the OTP rule).** Players appear only as scrambled codes. Counters are `[games, wins]`; a key `"ID"` means all roles, `"ID:B"` bot-lane games and `"ID:S"` support games.
  - `patches/<patch>/players.json.gz` holds every champion each player played that patch. It answers "55% of recent games", where recent = current + previous patch.
  - `season/<season>/players.json.gz` holds running totals for the season (season 16 = patches 16.x), never pruned during the season. It answers "at least 50 games on it this season". `"all"` is the player's total ranked games, any champion. Per-champion counts (with the B/S split) are kept only for bot-lane and support champions: at least 200 games in a patch with ≥10% in bot lane or support (`SEASON_CHAMPION_MIN_GAMES`, `SEASON_CHAMPION_MIN_SHARE`). Once a champion qualifies it stays for the season, and its `champions` list is stored in the file.
  - A new season starts when the first part of the patch number changes. The current and the previous season are kept (`KEEP_SEASONS = 2`).
  - When a season file is missing, it's rebuilt from the patch files, so nothing is lost. Games from before Oct 2, 2026 (the start of season totals) have no B/S split.
  - Only games we collect are counted, starting Oct 2, 2026, so season totals undercount early on. The OTP reliability formula keeps small OTP samples near neutral.
- Bans count once per game. Ban rate = games banned ÷ games counted.
- Skill order isn't collected yet. It's planned for Phase 3, since it needs an extra request per game.
- Keep-active: the first workflow step (`scripts/keep_active.sh`) adds an empty commit to `main` if it has had no commits for 30 days, so GitHub never pauses the schedule (it pauses after 60 days without activity). It runs before collection and is allowed to fail without stopping it.
- Offline checks: `python3 -m unittest discover -s tests`.

## Scoring model v0.33 (bot lane: ADC and APC): the full recipe

Bot lane includes APCs (bot-lane mages). They're in the same list as the ADCs and share the same trait average. Every part is scored 0–100, then weighted. The order of the steps:

1. **Filters.** A champion needs all four to be ranked: Diamond+ games, ≥10% lane share, ≥1,000 **real** games this patch (counted before the double weight), ≥1% pick rate. The sample-size label (low, medium, high) also uses real games. The double weight (LAN, KR, NA, EUW ×2) still applies to all stats.
2. **Stats (40%)** = 75% win rate points + 25% pick rate. Win rate says how strong a champion is; pick rate says it's proven and popular. (PBI was removed in v0.33.)
   - Win rate points = `50 + 12.5 × (win rate − Diamond+ average)`, clamped to 0–100: +4% → 100, +2% → 75, average → 50, −2% → 25, −4% → 0. The Diamond+ average comes from our own data each patch (expected to sit above 50%; Lolalytics shows 52.27%).
   - Pick rate is ranked 0–100 among the eligible bot-lane champions (ADCs and APCs). Ban rate isn't part of the Pick Score.
3. **Comfort (50%)** comes from the champion cards (see "Comfort in detail"), capped at 100.
4. **OTP (10%)** = OTP win rate − overall win rate, ranked 0–100 among eligible champions (raw OTP points), then pulled toward 50 by its reliability:
   - `OTP points = 50 + (raw OTP points − 50) × reliability`, where `reliability = OTP games ÷ (OTP games + 300)`. 100 OTP games → 25%; 300 → 50%; 1,000 → 77%; 3,000 → 91%.
   - **OTP rule (for now):** a Diamond+ player is an OTP of a champion when at least 55% of their recent ranked games are on it, and they have at least 50 games on it this season.
   - The tier list shows the number of OTP players and OTP games behind each OTP score.
5. **Pick Score** = `0.4 × Stats + 0.5 × Comfort + 0.1 × OTP`.
6. **Tier:** S ≥ 80 · A 72–79.9 · B 64–71.9 · C 56–63.9 · D < 56. **Stats floor:** a win rate 1.5% or more below the Diamond+ average caps the champion at B. The cutoffs and the floor are first guesses, calibrated in Phase 2 against the owner's gut ranking of 10 ADCs.

**Other lists:**
- **Growth advisor** (replaces "Worth learning"). It nudges the owner toward their preferred types and toward champions with strong stats, instead of keeping them on their mains forever. For each champion the owner isn't a Main on, the app calculates its Pick Score at a target mastery: Never played and Below average as if Good; Average and Good one level up. It shows a suggestion only when that score would beat the owner's current #3 pick, with the gain ("Kalista: 71 → 79 if Good"). There are two kinds of advice:
  - **Upgrade:** "You're Good with Jinx; at Main she'd jump from 74 to 80, S tier."
  - **New champion:** "You've never played Kalista, but at Good she'd rank #2 this patch; worth starting."
  - Details get polished in Phase 2 with real data.
- **Ban suggestions** (any role, separate from picks), by data only: `Ban threat = (win rate − Diamond+ average) × pick rate`, meaning how strong a champion is times how often the owner will face it. Only champions above the average win rate count, ranked by Ban threat.
- **Champions without a card** get no Pick Score, because Comfort needs a card. They still appear in the Meta Score (the data-only ranking) with a "no card yet" label, and in the Growth advisor if they would beat one of the owner's top 3 picks.

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

**Step 3: kit adjustment** = `0.9 × (trait score − average trait score)`, capped at ±5 on Comfort (±2.5 on the Pick Score). The average is recalculated each patch from the eligible bot-lane champions, ADCs and APCs together (v0.31). Until real data exists it's the average of all 32 cards: 13.656, shown in the brief as 13.7. An average champion gets 0, so scores don't inflate.
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

32 cards: 26 ADCs and 6 APCs (marked †). The Comfort column is the brief's result and serves as test data for the scoring code. Claude recalculated all 32 from the inputs below, and every one matched within 0.04. Trait levels are listed in priority order: wave clear, team utility, AoE, CC, sustain, burst, poke, vision; "—" means absent.

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

## Project board

**Phase 0, setup:** all done.

**Phase 1, data collector**
- [x] Pick the regions to collect from
- [x] Claude builds the collector for Diamond+ ADC and support games
- [x] Store the Riot key safely as a GitHub secret (never in the code)
- [ ] Run it for a few days and check that sample sizes grow
- [x] Define the OTP rule (share of recent games on one champion)

**Phase 2, tier list website (first shareable version)**
- [ ] Claude writes the scoring model as code
- [ ] Fill in a champion card (type, traits, mastery, difficulty, note) for every ADC the owner plays
- [ ] Build the bot-lane tier list page: Pick Score, Meta Score, ban suggestions and the Growth advisor, plus games played, a sample-size label (low, medium, high), a data-freshness label ("Data: 75% this patch") and trait badges for every champion, plus the number of OTP players and OTP games behind each OTP score
- [ ] Follow Riot's developer rules: legal notice on the site ("not endorsed by Riot Games"), personal key for a small private community, free and non-commercial, no data sold, key never exposed. Claude checks Riot's current policy page before publishing
- [ ] Show a "last mastery review: patch X" reminder on the site (review every 5–6 patches)
- [ ] Publish on Vercel and share the link with one friend
- [ ] Compare the output with the owner's manual picks for one patch and tune the weights

**Phase 3, builds**
- [ ] Decide the build rules (win rate vs pick rate, minimum games per build)
- [ ] Champion page: best core items, boots, runes, skill order

**Phase 4, draft helper**
- [ ] Add matchup and synergy data from the collected matches
- [ ] Draft screen: enter allies and enemies, get the top 3 picks with reasons, using champion traits (CC vs divers, sustain vs poke)

**Phase 5, later**
- [ ] Support tier list, then jungle tier list (the 3 roles of the final site)
- [ ] Apply for a production key if the site grows beyond friends

## Open questions & improvements

**Decide before or during Phase 2**
- **Ban list check:** the owner's bans in the last 3 months were Tristana, and they'd also ban Yunara or Jinx. Does the Ban threat ranking put them near the top? (Bans go by data, not by these examples.)
- Are the tier cutoffs and the stats floor right? Calibrate in Phase 2.
- Tune the kit weight (0.9) and difficulty weight (3) in Phase 2. Their caps stay ±2.5 and ±1.5 on the Pick Score.
- **Are Pick Scores spread enough?** Comfort for the owner's pool sits mostly between 86 and 100, so Stats should do most of the separating. Check with real data and widen the gaps if the tiers feel too similar.
- Review all cards' traits with the "at least Low" rule (only Lucian is done so far), and fill in mastery and difficulty for any remaining draft cards.
- **Mage cards:** confirm Ziggs's Wave clear (assumed High) and Xerath's difficulty (set between Medium and High).
- Flexibility bonus (beta, Varus only): check in Phase 2 whether it's worth keeping or extending.
- **Calibration list** (the owner's opinion, written Oct 3 before any data): the strongest bot-lane champions this meta, unordered: Jinx, Hwei, Lux, Tristana, Xayah, Caitlyn, Viktor, Ziggs, Twitch, Yunara, Zeri, Ashe, Draven. Test in Phase 2: do they land at the top of the Meta Score (data only)?
- **Cards per role (Phase 2 design note from the owner):** store champion cards per champion + role, with the same card structure, but each role has its own types, trait list and priorities. A champion can have a bot-lane card and a support card.

**Review once all ADC cards are done**
- Review the types, type strengths, traits, priorities and levels together, and check that the rules still fit.
- Range: decide champion by champion which modifiers last "most of the game" when finishing the remaining cards.

## Model versions

Newest first. Each block of 10 versions is later folded into one summary row.

- **v0.33** (Oct 3, 2026): PBI removed, so Stats = 75% win rate points + 25% pick rate. Bans by data only: Ban threat = (win rate − Diamond+ average) × pick rate. Growth advisor rule (Never played and Below average → as if Good; Average and Good → one level up; shown if it beats the #3 pick). The final site covers bot lane, jungle and support.
- **v0.32** (Oct 3, 2026): patch blending, where share of this patch = this patch's games ÷ (this patch's games + 1,000) and the rest comes from last patch, with a data-freshness label per champion. Season totals for OTPs stored (current and previous season).
- **v0.31** (Oct 3, 2026): Team utility means general usefulness to the team. Trait average and Stats ranks use all eligible bot-lane champions (ADCs and APCs).
- **v0.30** (Oct 3, 2026): bot lane includes APCs. The 6 mage cards (Lux, Ziggs, Syndra, Hwei, Viktor, Xerath) join the same list and the same trait average as the ADCs (13.7). Every card recalculated.
- **v0.20–v0.29** (Oct 2–3, 2026): secondary types get a strength; real games for the 1,000-game filter; Riot difficulty from the 1–10 game-data number, with the website as backup; range groups (Short ≤500, Medium 525–575, Long 600+) and a range adjustment (±0.5 Comfort); OTP rule (55% of recent games, 50+ games) and OTP reliability; mastery reworked (Main 100, Good 90, Average 80, Below average 70, Never played 60) with matching difficulty factors; Discomfort removed; Growth advisor; every trait at least Low unless absent; new trait AoE (High); flexibility bonus beta (Varus); the owner's difficulty is a locked base rating.
- **v0.10–v0.19** (Oct 2, 2026): new trait Poke; Comfort base 40% type + 60% mastery, capped at 100; kit and difficulty adjustments inside Comfort (traits up to ±2.5, difficulty up to ±1.5 on the Pick Score); difficulty = 80% the owner's rating + 20% Riot's, compared with Medium (2); traits weighted by priority and level (Low 0.5, Mid 1, High 1.5); Hard and Soft CC merged into one CC trait; type strength (High 100%, Mid 97.5%, Low 95%).
- **v0.1–v0.9** (Oct 1–2, 2026): first ADC model (Stats 40%, Comfort 50%, OTP 10%; LAN, KR, NA, EUW ×2); win rate scored by distance from the Diamond+ average; 5 tiers with fixed cutoffs and a stats floor at B; ban suggestions; types Mobility, Peel, Hypercarry, Utility, Mage, Lane bully; secondary types that can only help; type and trait fact-checks; traits and the kit adjustment; difficulty adjustment.
