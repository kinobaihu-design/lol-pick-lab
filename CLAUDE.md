# LoL Pick Lab — instructions for Claude

`project-brief.pdf` (kept locally, not in the repo) is the source of truth. This file summarizes it; current brief: **v0.21**. If the two disagree, the brief wins; ask the owner which to update.

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
- **Facts vs opinions.** Anything that is a fact about the game (champion types, ranges, item stats, patch changes, Riot difficulty) is checked against an official source before it's used: Riot's data (Data Dragon) or the official League of Legends Wiki. The owner's opinions (mastery, feel, notes, their own difficulty rating) stay theirs and need no check.

## What the project is

A free public website that ranks ADC and support champions each patch using the owner's own rules. Priorities, in order:

1. **Personal tier list** for ADC (support later), from Diamond+ data and the owner's scoring.
2. **Build recommendations**: items, runes and skill order.
3. **Draft helper**: enter the draft, get the top 3 picks with reasons.

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
- Early in a patch, last patch's data can be blended in until the sample is big enough.

## Data collector (Phase 1, built)

- Code: `collector/` (Python standard library only). Settings, including `PRIORITY_SHARE`, double-weight servers, recheck timing and patches kept, are in `collector/config.py`.
- Schedule: `.github/workflows/collect.yml` runs every 6 hours, about 5 hours of work per run, and never two runs at once. "Run workflow" on the Actions page takes a time limit and a per-region game limit for tests. It saves a checkpoint every hour.
- What it does: it loads each server's Diamond+ list and checks players for new queue 420 games. Active players are rechecked after 5 hours; inactive ones after 24 hours, then doubling up to 14 days (lookback stays 10 days). Each new game is downloaded once, and only Diamond+ participants are counted. Within each routing region, the priority servers get `PRIORITY_SHARE` (70%) of requests: Americas LAN and NA, Europe EUW, Asia KR. SEA is split evenly.
- Data lives on the `data` branch, replaced each save with no history (fetch it with `git fetch origin +data:refs/remotes/origin/data`). `data-backup` holds the previous run's copy, and the collector falls back to it if a file is damaged. Totals for the last 3 patches are kept. See the `README.md` on the data branch for the file format. Player IDs are stored only as scrambled codes.
- Champions are stored by Riot's champion ID. The `name` field is Riot's internal name (`Kaisa`, `MissFortune`, `KogMaw`); the website must take display names from Data Dragon.
- Bans count once per game. Ban rate = games banned ÷ games counted.
- Skill order isn't collected yet. It's planned for Phase 3, since it needs an extra request per game.
- Keep-active: the first workflow step (`scripts/keep_active.sh`) adds an empty commit to `main` if it has had no commits for 30 days, so GitHub never pauses the schedule (it pauses after 60 days without activity). It runs before collection and is allowed to fail without stopping it.
- Offline checks: `python3 -m unittest discover -s tests`.

## Scoring model v0.21 (ADC): the full recipe

Every part is scored 0–100, then weighted. The order of the steps:

1. **Filters.** A champion needs all four to be ranked: Diamond+ games, ≥10% lane share, ≥1,000 **real** games this patch (counted before the double weight), ≥1% pick rate. The sample-size label (low, medium, high) also uses real games. The double weight (LAN, KR, NA, EUW ×2) still applies to all stats.
2. **Stats (40%)** = 60% win rate points + 25% PBI + 15% pick rate.
   - Win rate points = `50 + 12.5 × (win rate − Diamond+ average)`, clamped to 0–100: +4% → 100, +2% → 75, average → 50, −2% → 25, −4% → 0. The Diamond+ average comes from our own data each patch (expected to sit above 50%; Lolalytics shows 52.27%).
   - PBI and pick rate are ranked 0–100 among eligible ADCs. Ban rate is not in the Pick Score; it feeds PBI and the ban list.
3. **Comfort (50%)** comes from the champion cards (see "Comfort in detail"), capped at 100.
4. **OTP delta (10%)** = OTP win rate − overall win rate, ranked 0–100 among eligible ADCs.
5. **Pick Score** = `0.4 × Stats + 0.5 × Comfort + 0.1 × OTP`.
6. **Tier:** S ≥ 80 · A 72–79.9 · B 64–71.9 · C 56–63.9 · D < 56. **Stats floor:** a win rate 1.5% or more below the Diamond+ average caps the champion at B. The cutoffs and the floor are first guesses, calibrated in Phase 2 against the owner's gut ranking of 10 ADCs.

**Other lists:**
- **Worth learning:** a Discomfort or Never-played champion with a top-3 Stats score also appears in a separate "Worth learning" list.
- **Ban suggestions** (any role, separate from picks) = 60% PBI + 40% struggle list (100 if the owner struggles against it, otherwise 0).

### Comfort in detail

Comfort measures how much the owner likes a champion and how well they play it. Each card produces one final Comfort:

`Comfort = 40% type points + 60% mastery points + kit adjustment + difficulty adjustment`, capped at 100. Mastery counts more because how well the owner plays matters more than how much they like the style.

**Step 1: type points.** Each champion has one main type, fact-checked against these rules from its kit (official League of Legends Wiki):

| Type | Points | Fact-check rule |
|---|---|---|
| Mobility (favorite) | 100 | Has a dash or blink it uses in fights |
| Peel (2nd) | 90 | Has a tool made to protect itself: spell shield, untargetability, knockback or self-shield (like Sivir's E). Offensive CC like roots or slows doesn't count |
| Hypercarry (3rd, tied) | 80 | Weaker early, scales into top late-game damage |
| Utility (3rd, tied) | 80 | Its main value is reliably helping the team (CC, vision, ally support) more than its own damage or mobility, like Ashe |
| Mage (4th, tied) | 70 | Deals most damage with magic abilities, not attacks |
| Lane bully (4th, tied) | 70 | Strongest early; wins lane through damage and trades and snowballs leads (like Draven). Champions with a dash stay Mobility |

- **Type strength** (how strongly it fits the type): High 100%, Mid 97.5%, Low 95% of the type points. Applies to the main type and the secondary type before they're compared. The 2.5% step is tunable.
- **Secondary type** (optional): if its points (after strength) beat the main type's, add 20% of the gap. If not, it's shown for information only.
- **Discomfort switch:** if the owner dislikes how a champion feels, type points become 30, whatever its type.
- **Type fact-check:** the owner gives their view; Claude checks it against the rules above. If they disagree, the card shows both views and the owner decides.

**Step 2: mastery points.** Main 100 · Comfortable 95 · Learning 80 · Never played 60.

**Step 3: kit adjustment** = `0.9 × (trait score − average trait score)`, capped at ±5 on Comfort (±2.5 on the Pick Score). The average is recalculated each patch from the eligible ADCs (7.175 on the current 20 cards; the brief shows it rounded as 7.2). An average champion gets 0, so scores don't inflate.
- Trait score = sum of `priority × level` for each trait the champion has.
- Levels: Low 0.5 · Mid 1 · High 1.5. A trait that defines the champion's type isn't listed again.

| Trait (7) | Owner's priority | Counts when the kit has… |
|---|---|---|
| Wave clear | High (3) | Clears a minion wave with abilities, without relying on items |
| Team utility | High (3) | Shields, heals or speed for allies |
| CC | Medium (2) | Stuns, roots, knockups, knock asides, snares, slows. High = reliable hard CC that decides fights; Mid = situational hard CC, or hard CC plus slows; Low = slows only |
| Sustain | Medium (2) | Healing or lifesteal in the kit |
| Burst | Medium (2) | Can kill or nearly kill a squishy target with one combo or empowered shot |
| Poke | Medium (2) | Repeated damage from long range (1,000+ units) with abilities, available most of the game |
| Vision | Low (1) | Reveals areas or enemies |

**Step 4: difficulty adjustment** = `−3 × (difficulty − 2) × mastery factor`, capped at ±3 on Comfort (±1.5 on the Pick Score).
- Difficulty = 80% the owner's rating + 20% Riot's (Low 1, Medium 2, High 3). **Riot's rating comes from the 1–10 `info.difficulty` number in Riot's game data (Data Dragon): 1–3 Low, 4–6 Moderate, 7–10 High.** It's compared with Medium (2), so harder means minus, easier means plus, and adding cards never changes other champions.
- Mastery factor (mastery softens it, never to zero): Never played 100% · Learning 75% · Comfortable 50% · Main 25%.

**Range** (on the card, not in the score): base attack range; short < 500, medium 500–599, long ≥ 600.

## Champion cards (ADC)

The cards hold the owner's inputs. The Comfort column is the brief's result and serves as test data for the scoring code, which must reproduce it within rounding (Claude's recalculation of all 20 matched within 0.05). Type pts include strength and the secondary-type bonus. Riot difficulty here is copied from the brief; see "Pending fact-check" below.

| Champion | Type (strength) / secondary (strength) | Type pts | Mastery | Traits (level) | Trait score | Difficulty Riot / mine → final | Comfort |
|---|---|---|---|---|---|---|---|
| Sivir | Peel (High) / Utility | 90 | Main | Team utility High, Wave clear High, Poke Mid, Sustain Low | 12 | 1.5 / 1 → 1.1 | 100 (101.0 capped) |
| Caitlyn | Mobility (Mid) / Lane bully (Mid) | 97.5 | Comfortable | Wave clear Mid, CC Mid, Burst Mid, Poke Mid, Vision Mid | 10 | 1 / 1.5 → 1.4 | 99.4 |
| Tristana | Mobility (High) / Hypercarry (Low) | 100 | Comfortable | Wave clear Mid, CC Low, Burst High | 7 | 2 / 2 → 2.0 | 96.8 |
| Senna | Utility (High) / Hypercarry (Mid) | 80 | Comfortable | Team utility High, CC Mid, Sustain High, Poke Low | 10.5 | 3 / 1 → 1.4 | 92.9 |
| Lucian | Mobility (High) / Lane bully (Low) | 100 | Comfortable | Burst Mid, Vision Low | 2.5 | 2 / 2 → 2.0 | 92.8 |
| Ezreal | Mobility (High) | 100 | Comfortable | Poke Mid | 2 | 3 / 2.5 → 2.6 | 91.4 |
| Jhin | Utility (Mid) | 78 | Comfortable | CC High, Burst High, Poke Mid, Vision Low | 8.5 | 2 / 1 → 1.2 | 90.6 |
| Jinx | Hypercarry (High) | 80 | Comfortable | Wave clear Mid, CC Mid, Burst Low, Poke Low | 7 | 2 / 1 → 1.2 | 90.0 |
| Smolder | Hypercarry (Mid) / Mobility (Mid) | 81.9 | Comfortable | Wave clear Mid, CC Low, Burst Mid | 6 | 2 / 1 → 1.2 | 89.9 |
| Ashe | Utility (High) | 80 | Comfortable | CC High, Poke Mid, Vision High | 6.5 | 1 / 1 → 1.0 | 89.9 |
| Corki | Mobility (Mid) / Lane bully (Low) | 97.5 | Learning | Wave clear Mid, Burst Mid, Poke Mid, Vision Mid | 8 | 2 / 1 → 1.2 | 89.5 |
| Twitch | Hypercarry (High) | 80 | Comfortable | Wave clear Mid, CC Low, Burst High | 7 | 2 / 2 → 2.0 | 88.8 |
| Miss Fortune | Lane bully (High) | 70 | Comfortable | Wave clear Low, CC Low, Burst High, Poke High | 8.5 | 1 / 1 → 1.0 | 87.7 |
| Kalista | Mobility (High) | 100 | Learning | Wave clear Low, Team utility Mid, CC Mid, Burst Low, Vision Mid | 8.5 | 3 / 3 → 3.0 | 86.9 |
| Kai'Sa | Hypercarry (Mid) / Mobility (Mid) | 81.9 | Learning | Wave clear Low, Burst Mid, Poke Low | 4.5 | 2 / 2 → 2.0 | 78.4 |
| Yunara | Hypercarry (High) / Mobility (Low) | 83 | Learning | Wave clear Mid, CC Low | 4 | 2 / 2 → 2.0 | 78.3 |
| Akshan | Mobility (High) / Utility (Low) | 100 | Never played | Wave clear Mid, Team utility Mid, Burst Mid, Vision Mid | 9 | 1 / 2 → 1.8 | 78.2 |
| Aphelios | Hypercarry (High) / Utility (Low) | 80 | Never played | Wave clear Mid, CC Mid, Sustain Mid, Burst Mid, Poke Low, Vision Mid | 11 | 3 / 3 → 3.0 | 68.4 |
| Draven | Lane bully (High) | 70 | Never played | CC Mid, Burst High | 5 | 3 / 3 → 3.0 | 59.0 |
| Zeri | **Discomfort** (Mobility / Hypercarry) | 30 | Never played | Wave clear Mid, CC Low, Poke Mid (draft, to review later) | 6 | 2 / 2 (Riot's used for now) → 2.0 | 46.9 |

Only Zeri has Discomfort. Ranges match Riot's data: Caitlyn 650; Ashe and Senna 600; Yunara 575; Jinx, Kalista and Kai'Sa 525; Lucian, Sivir and Akshan 500; the rest 550 (all Medium except the Long ones: Caitlyn, Ashe, Senna).

**Pending fact-check: Riot difficulty under the v0.21 rule.** Riot's data gives Yunara 4/10 = Moderate (2), which confirms the brief's "2 (to confirm)". Four existing cards don't follow the rule yet, and the owner must confirm before the brief changes:
- **Caitlyn:** 6/10 = Moderate (2); the brief uses 1. Comfort would become 99.1 (from 99.4).
- **Ashe:** 4/10 = Moderate (2); the brief uses 1. Comfort would become 89.6 (from 89.9).
- **Sivir:** 4/10 = Moderate (2); the brief uses 1.5. Comfort stays 100 because of the cap.
- **Akshan:** Riot's data has no rating (0). The brief uses Low (1); a fallback rule is needed.

**Owner's notes (short):**
- **Sivir:** only current main. Felt natural from day 1; great wave clear and CS; an underrated scaler.
- **Caitlyn:** intuitive, long range; wants her as a main. Can still use traps better. Struggles vs very heavy tank comps.
- **Tristana:** elo boosters' favorite, and the owner struggles against her. Gets fed on her but finds it oddly hard to carry. Could be a main.
- **Senna:** easy; the hard part is scaling early and depending on teammates. Close to being a main.
- **Lucian:** one of the most mobile ADCs. Easy once played enough; would rate him Low once a main.
- **Ezreal:** one of the most fun. Farms safely with Q, but missing Qs is fatal. Struggles vs tanks.
- **Jhin:** fun and easy; likes his lore. Struggles vs tanks and in long trades (reload).
- **Jinx:** really easy. Many games, not recently; could be a main again.
- **Smolder:** near-infinite scaling; enemies try to end early. Could become a main soon.
- **Ashe:** hates the lack of mobility, but has had a lot of success. Useful even when behind. Rusty: 3–5 games to get back.
- **Corki:** easy to pick up; could be Comfortable soon. Strong in lane.
- **Twitch:** would rate him Low once a main.
- **Miss Fortune:** crazy burst, really easy; her R is the champion. Poke High is the owner's call (her Q is below the 1,000-range rule).
- **Kalista:** one of the most mobile ADCs, with Lucian. Hard now; should get easier (Mid or Low) as the owner learns her.
- **Kai'Sa:** could be easy once a main (difficulty Low then).
- **Yunara:** most-played ADC in the first data; a newer champion. Mobility is Low because she only dashes during R. Could be Low difficulty once learned.
- **Akshan:** mostly a mid laner, so bot data may be thin. Not intuitive to the owner; OTPs seem to do very well.
- **Aphelios:** hard to learn but rewarding; strong vs divers. OTPs likely beat his average.
- **Draven:** stomps early, huge snowball; OTPs shine. Not planning to learn him soon.
- **Zeri:** "I'll never play her." Card to review later.

### Draft cards (to confirm)

Drafted from their kits, waiting for the owner's mastery, difficulty and corrections. The mages are mainly for the support tier list later. Range and Riot difficulty below are **confirmed from Riot's data** (Data Dragon 16.19.1) using the v0.21 rule. Values that differ from the brief's draft are marked *(brief: …)*.

| Champion | Type (draft) | Traits (draft) | Range (Riot) | Riot difficulty (Riot) | Mastery |
|---|---|---|---|---|---|
| Viktor | Mage | CC Mid, Burst Mid, Wave clear High, Poke Mid | Medium (525) | High (9) | Comfortable |
| Hwei | Mage | CC High, Burst Mid, Wave clear Mid, Poke High | Medium (550) | High (9) | Comfortable |
| Lux | Mage | CC High, Team utility Mid, Burst Mid, Wave clear Mid, Poke Mid, Vision Mid | Medium (550) | Moderate (5) | Comfortable |
| Syndra | Mage | CC Mid, Burst High, Wave clear Mid | Medium (550) | High (8) | Comfortable |
| Xerath | Mage | Poke High, CC Mid, Burst Mid, Wave clear Mid | Medium (525) | High (8) | Comfortable |
| Ziggs | Mage | Poke High, Wave clear High, CC Mid, Burst Mid | Medium (550) | Moderate (4) | Comfortable |
| Kog'Maw | Hypercarry | Poke High, CC Low, Wave clear Mid | Medium (500) *(brief: Short)* | Moderate (6) | Learning or Never played? |
| Nilah | Mobility / Hypercarry | Team utility Mid, Sustain Mid, CC Mid, Wave clear Mid | Short (melee, 225) | High (10) *(brief: Moderate)* | Learning or Never played? |
| Samira | Mobility / Lane bully | Burst High, Wave clear Low | Medium (500) *(brief: Short)* | Moderate (6) *(brief: High)* | Learning or Never played? |
| Varus | Lane bully / Utility | Poke High, CC High, Burst Mid, Wave clear Mid | Medium (575) | Low (2) *(brief: Moderate)* | Learning or Never played? |
| Vayne | Hypercarry / Mobility | CC Mid, Burst Mid | Medium (550) | High (8) | Learning or Never played? |
| Xayah | Peel / Hypercarry | CC Mid, Burst Mid, Wave clear Mid | Medium (525) | Moderate (5) | Learning or Never played? |

Range note: the brief's rule is short < 500 and medium 500–599, so exactly 500 (Kog'Maw, Samira, and also Lucian, Sivir, Akshan) is Medium. The draft calls Kog'Maw and Samira "Short (500)", which conflicts with the rule.

## Project board

**Phase 0, setup:** all done.

**Phase 1, data collector**
- [x] Pick the regions to collect from
- [x] Claude builds the collector for Diamond+ ADC and support games
- [x] Store the Riot key safely as a GitHub secret (never in the code)
- [ ] Run it for a few days and check that sample sizes grow
- [ ] Define the OTP rule (share of recent games on one champion)

**Phase 2, tier list website (first shareable version)**
- [ ] Claude writes the scoring model as code
- [ ] Fill in a champion card (type, traits, mastery, difficulty, note) for every ADC the owner plays
- [ ] Build the ADC tier list page: Pick Score, Meta Score, ban suggestions and Worth learning, plus games played, a sample-size label (low, medium, high) and trait badges for every champion
- [ ] Publish on Vercel and share the link with one friend
- [ ] Compare the output with the owner's manual picks for one patch and tune the weights

**Phase 3, builds**
- [ ] Decide the build rules (win rate vs pick rate, minimum games per build)
- [ ] Champion page: best core items, boots, runes, skill order

**Phase 4, draft helper**
- [ ] Add matchup and synergy data from the collected matches
- [ ] Draft screen: enter allies and enemies, get the top 3 picks with reasons, using champion traits (CC vs divers, sustain vs poke)

**Phase 5, later**
- [ ] Support tier list, then other roles
- [ ] Apply for a production key if the site grows beyond friends

## Open questions & improvements

**Decide before or during Phase 2**
- Which champions does the owner struggle against? Feeds the ban list; so far: Tristana.
- Are the tier cutoffs and the stats floor right? Calibrate in Phase 2.
- Tune the kit weight (0.9) and difficulty weight (3) in Phase 2. Their caps stay ±2.5 and ±1.5 on the Pick Score.
- Champions without a card: show them in the Meta Score with a "no card yet" label, and allow them in Worth learning.

**Review once all ADC cards are done**
- Review the types, type strengths, traits, priorities and levels together, and check that the rules still fit.
- Should range affect Comfort? (Not for now.)

## Model versions

Newest first. Each block of 10 versions is later folded into one summary row.

- **v0.21** (Oct 2, 2026): the 1,000-game filter and the sample-size label use real games (before the double weight); Riot difficulty comes from the 1–10 game-data number (1–3 Low, 4–6 Moderate, 7–10 High); Zeri's and Yunara's ranges corrected to Medium. Four new finished cards: Kalista, Kai'Sa, Yunara, Zeri (trait average now 7.2).
- **v0.20** (Oct 2, 2026): secondary types get a strength too, applied before comparing with the main type; strength levels reviewed for all 16 cards; Ezreal's Poke lowered to Mid.
- **v0.10–v0.19** (Oct 2, 2026): new trait Poke; Comfort base 40% type + 60% mastery, capped at 100; kit and difficulty adjustments inside Comfort (traits up to ±2.5, difficulty up to ±1.5 on the Pick Score); difficulty = 80% the owner's rating + 20% Riot's, compared with Medium (2); traits weighted by priority and level (Low 0.5, Mid 1, High 1.5); Hard and Soft CC merged into one CC trait; type strength (High 100%, Mid 97.5%, Low 95%).
- **v0.1–v0.9** (Oct 1–2, 2026): first ADC model (Stats 40%, Comfort 50%, OTP 10%; LAN, KR, NA, EUW ×2); win rate scored by distance from the Diamond+ average; 5 tiers with fixed cutoffs and a stats floor at B; ban suggestions; types Mobility, Peel, Hypercarry, Utility, Mage, Lane bully; Discomfort as a switch; secondary types that can only help; type and trait fact-checks; traits and the kit adjustment; difficulty adjustment.
