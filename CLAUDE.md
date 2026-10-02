# LoL Pick Lab — instructions for Claude

`project-brief.pdf` (kept locally, not in the repo) is the source of truth. This file summarizes it. If the two disagree, the brief wins; ask the owner which to update.

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
5. **Close.** Tick the board, log any model change as a new version (see "Model versions"), and remind the owner to refresh the brief if it changed.

Ideas that don't affect the current step go to the board or the open questions, so they aren't lost.

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
- What it does: it loads each server's Diamond+ list and checks players for new queue 420 games. Active players are rechecked after 5 hours; inactive ones after 24 hours, then doubling up to 7 days. Each new game is downloaded once, and only Diamond+ participants are counted. Within each routing region, the priority servers get `PRIORITY_SHARE` (70%) of requests: Americas LAN and NA, Europe EUW, Asia KR. SEA is split evenly.
- Data lives on the `data` branch, replaced each save with no history. `data-backup` holds the previous run's copy, and the collector falls back to it if a file is damaged. Totals for the last 3 patches are kept. See the `README.md` on the data branch for the file format. Player IDs are stored only as scrambled codes.
- Bans count once per game. Ban rate = games banned ÷ games counted.
- Skill order isn't collected yet. It's planned for Phase 3, since it needs an extra request per game.
- Keep-active: the first workflow step (`scripts/keep_active.sh`) adds an empty commit to `main` if it has had no commits for 30 days, so GitHub never pauses the schedule (it pauses after 60 days without activity). It runs before collection and is allowed to fail without stopping it.
- Offline checks: `python3 -m unittest discover -s tests`.

## Scoring model v0.3 (ADC)

`Pick Score = 0.4 × Stats + 0.5 × Comfort + 0.1 × OTP`. Each part is scored 0–100.

**Filters.** A champion needs all four to be ranked: Diamond+ games, ≥10% lane share, ≥1,000 games this patch, ≥1% pick rate.

**Stats (40%)** = 60% win rate points + 25% PBI + 15% pick rate.
- Win rate points = `50 + 12.5 × (win rate − Diamond+ average win rate)`, clamped to 0–100. The average comes from our own data each patch.
- PBI and pick rate are ranked 0–100 among eligible ADCs. Ban rate is not in the Pick Score; it feeds PBI and the ban list.

**Comfort (50%)** = 70% champion type + 30% mastery.
- Type: Mobility 100, Peel 90, Hypercarry 80, Mage 70, Discomfort 30.
- Mastery: Main 100, Comfortable 95, Learning 80, Never played 60.
- Each champion has a card with its type, mastery and a one-line note in the owner's words.

**OTP delta (10%)** = OTP win rate − overall win rate, ranked 0–100 among eligible ADCs.

**Tiers:** S ≥ 80 · A 72–79.9 · B 64–71.9 · C 56–63.9 · D < 56.
- **Stats floor:** a champion 1.5% or more below the Diamond+ average win rate can't go above B.
- **Worth learning:** a Discomfort or Never-played champion with a top-3 Stats score also appears in a separate "Worth learning" list.
- **Ban suggestions** cover any role: 60% PBI + 40% struggle list (100 if the owner struggles against it, otherwise 0).

The cutoffs and the floor are first guesses, to be calibrated in Phase 2 against the owner's gut ranking of 10 ADCs.

## Project phases

- **Phase 0, setup:** done.
- **Phase 1, data collector:** collector built and the Riot key stored as a secret. Still to do: run it a few days and check that sample sizes grow, and define the OTP rule.
- **Phase 2, tier list website:** scoring code, champion cards, the ADC tier list page (Pick Score, Meta Score, ban suggestions, Worth learning, plus games played and a sample-size label of low, medium or high for every champion), publishing on Vercel, then tuning.
- **Phase 3, builds:** build rules, and a champion page with core items, boots, runes and skill order.
- **Phase 4, draft helper:** matchup and synergy data, and the draft screen.
- **Phase 5, later:** support and other roles, and a production key if the site grows beyond friends.

**Open questions:** which champions the owner struggles against, and whether the tier cutoffs and stats floor are right.

## Model versions

- **v0.1** (Oct 1, 2026): first ADC model. Stats 40%, Comfort 50%, OTP delta 10%. LAN, KR, NA and EUW weighted ×2.
- **v0.2** (Oct 1, 2026): win rate scored by distance from the Diamond+ average; ban rate moved to the ban list; smaller comfort gaps; 5 tiers with fixed cutoffs; stats floor at B; ban suggestions. Later versions will shift weight from Comfort to Stats as the owner improves.
- **v0.3** (Oct 1, 2026): Comfort type points 100 / 90 / 80 / 70, Discomfort 30.
