# LoL Pick Lab — instructions for Claude

`project-brief.pdf` (kept locally, not in the repo) is the source of truth. This file summarizes it. If the two disagree, the brief wins; ask the owner which to update.

## Rules for working with the owner

- **The owner is a beginner and does not write code.** Explain everything in plain language, one step at a time. Avoid jargon; when a technical word is unavoidable, explain it in one short sentence.
- **Ask before doing anything that costs money.** That includes paid plans, paid add-ons, going over a free tier, or buying anything. Everything in this project is meant to run on free services.
- **Never put API keys, passwords or tokens in code, files or chat.** The Riot API key is stored only as a GitHub Actions secret named `RIOT_API_KEY` and read from the environment at runtime. Never print it, log it, commit it or send it to the website. If the owner pastes a secret into chat, tell them to revoke and regenerate it.
- The owner makes the decisions about rules, weights and tags. Claude writes and maintains all the code, and explains each change in plain words.

## What the project is

A free public website that ranks ADC and support champions each patch using the owner's own rules. Priorities, in order:

1. **Personal tier list** for ADC (support later), from Diamond+ data and the owner's scoring.
2. **Build recommendations**: items, runes and skill order.
3. **Draft helper**: enter the draft, get the top 3 picks with reasons.

## How it works (all free)

- **Data:** our own Diamond+ ranked solo/duo matches from the official Riot Games API, using a personal API key (100 requests / 2 min per region).
- **Daily collector (GitHub Actions, free for public repos):**
  1. List Diamond, Master, Grandmaster and Challenger players in each region.
  2. Get each player's recent ranked solo/duo match IDs.
  3. Download each new match once. For each champion, store role, win/loss, items, runes, skill order, and the allies and enemies.
  4. Mark a player as an OTP (one-trick) of a champion when most of their recent games are on it.
- **Regions:** every server the Riot API covers (China isn't included). LAN, KR, NA and EUW games count double.
- **Storage:** champion stats per patch, kept in this GitHub repository.
- **Website:** hosted on Vercel's free plan, updates automatically when new data lands.
- Early in a patch, last patch's data can be blended in until the sample is big enough.

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
- **Phase 1, data collector:** regions picked. Still to do: build the daily collector, store the Riot key as a secret, run it a few days and check sample sizes, define the OTP rule.
- **Phase 2, tier list website:** scoring code, champion cards, the ADC tier list page (Pick Score, Meta Score, ban suggestions, Worth learning), publishing on Vercel, then tuning.
- **Phase 3, builds:** build rules, and a champion page with core items, boots, runes and skill order.
- **Phase 4, draft helper:** matchup and synergy data, and the draft screen.
- **Phase 5, later:** support and other roles, and a production key if the site grows beyond friends.

**Open questions:** which champions the owner struggles against, and whether the tier cutoffs and stats floor are right.
