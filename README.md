# NBA Player Value Model

Cross-references every rostered NBA player's production (BPM, and optionally
EPM/DARKO) against their salary to produce a **Value Score**, a
dollar-denominated **Market Value** estimate with prediction intervals, and
two baseball-style skill composites (**Rim Scoring Value**, **Foul-Drawing
Value**). Includes CBA-aware max-contract tiering, Guard/Wing/Big position
groups, a descriptive playoff split, a team payroll/apron rollup, and an
in-app **Methodology & Limitations** page -- all wrapped in an interactive
Streamlit dashboard built to be shown to front office execs.

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python run_pipeline.py          # scrapes + builds outputs/player_value_model.csv
streamlit run app/streamlit_app.py   # interactive dashboard
```

First run takes a few minutes (it's scraping Basketball-Reference with a
polite delay between requests, plus ~25 draft-class pages and a season of
playoff data). After that, `config.USE_CACHE = True` means re-running
`run_pipeline.py` reuses the cached HTML in `data/cache/` instantly, until
you delete that folder (or flip the flag off) to force a refresh -- which
you need to do explicitly any time you want to pick up new signings, since
the cache doesn't expire on its own.

## What's fully automatic vs. what needs your input

**Scraped automatically, no setup needed:**
- OBPM, DBPM, BPM, VORP, GP, minutes, age, position, team -- season Advanced
  stats table.
- Points/rebounds/assists/steals/blocks per game, shooting splits -- season
  Per Game table.
- Shot-distance data (FG% and attempt share at the rim) -- season Shooting
  table, feeds Rim Scoring Value.
- Playoff per-game and advanced stats -- for whichever players/teams
  actually made the postseason that year (see the playoff caveat below).
- Cap hit, years remaining, total guaranteed money -- Basketball-Reference's
  live contracts page. This page always reports the *upcoming* season's
  salary as of whenever it's scraped -- see "Why production and salary are
  from two different seasons" below, it matters.
- Draft year -> years of experience -> Rookie Scale vs. Veteran
  classification (heuristic, see below).

**Needs a manual CSV drop-in, because these sites can't be reliably
auto-scraped:**
- **EPM** (dunksandthrees.com) -- renders as a virtualized React table;
  only the visible rows load without a real browser driving it, and full
  league data is behind a subscription.
- **DARKO** (apanalytics.shinyapps.io) -- an R Shiny app with no public
  API; there's no stable way to pull it programmatically.
- **LEBRON** (bball-index.com) -- the full "live database" is
  subscriber-only. Present in the pipeline (`data/manual/lebron.csv`) but
  weighted at 0 in `config.PRODUCTION_METRIC_WEIGHTS` and not currently
  collected -- add real data and flip the weight back on if you want it in
  the composite score.
- **databallr.com playstyle metrics** (OnBall%, rTS%, 3Y RAPM, PVAL, Net
  On/Off) -- the site's API requires a signed request.

For each of these, `run_pipeline.py` writes a starter template to
`data/manual/*.csv` (two columns: `player`, `<METRIC>`). Export or copy the
table from the site into that CSV and re-run the pipeline -- it picks up
whatever subset of metrics you've collected and simply skips the rest. You
don't need all of them for the model to work; it composites over whichever
are present (see `production_pctile` / `n_production_metrics_available` in
the output).

One more thing worth overriding by hand in
`data/manual/contract_overrides.csv` (columns: `player, contract_type,
bird_rights_status, cap_hit_override, notes`): **cap hit vs. salary** are
identical for the vast majority of players. They diverge for stretch
provisions, base-year-compensation trades, incentives, etc., which
Basketball-Reference doesn't expose. Fill in `cap_hit_override` for any
player where it matters.

## How the model works

1. **Percentiles** (`model/percentiles.py`): every metric gets converted to
   a 0-100 percentile rank, computed only among players clearing
   `config.MIN_MINUTES` (default 500) so a small sample can't post a
   99th-percentile mark. Position-relative percentiles (`_pctile_pos`) are
   also computed within Guard/Wing/Big groups (`model/positions.py`).
2. **Composite production score**: a weighted average of whichever
   `config.PRODUCTION_METRICS` are available for that player (BPM always;
   EPM and DARKO if you've imported them -- see `PRODUCTION_METRIC_WEIGHTS`
   for why they're not weighted equally). Missing metrics are dropped from
   that player's average, not zeroed out.
3. **Value Score** (`model/value_score.py`): `production_pctile -
   salary_pctile`. Roughly -100 to +100.
4. **Rim Scoring Value** and **Foul-Drawing Value**
   (`model/value_metrics.py`): baseball-style efficiency-times-volume
   composites for two specific skills the all-in-one metrics compress away.
   Each uses two sample-size thresholds -- a low floor to compute at all, a
   higher one to flag as noisy -- rather than one cutoff, so the metric
   doesn't silently (and unevenly, by position) drop half the rotation.
5. **$-estimator** (`model/dollar_estimate.py`): trained on **veterans
   only** (rookie-scale salaries are CBA-slotted, not performance-based,
   so including them would bias the model), predicts `estimated_market_
   value` from production + age + experience + minutes. Ships with an
   uncertainty range built via cross-conformal prediction (an 80% band and
   a tighter 50% "leaning" band) rather than a bare point estimate --
   realized coverage is printed on every pipeline run so that claim stays
   checkable. `estimate_confidence` (High/Medium/Low) separately reports
   how much to trust a given player's range, based on its relative width
   plus penalties for missing inputs or extrapolation (rookie-scale, or
   very late-career -- see `config.EXTREME_VETERAN_AGE_THRESHOLD`).
6. **CBA max-contract tiering** (`model/contracts.py`): flags players at or
   near their max for their years-of-service tier, since the model that
   only ever saw *capped* salaries in training can't see true surplus for
   the very best players -- and ranks max/near-max players within their own
   cohort instead. Also builds the **Team Payroll rollup** the dashboard
   shows against the current cap/tax/apron lines.
7. **Playoff split**: descriptive only, shown side-by-side with regular-
   season numbers on the player page. Deliberately *not* folded into Value
   Score, Market Value, or any ranking -- only 16 of 30 teams qualify and a
   sweep is 4 games, nowhere near enough sample to rank players on.

This is a starting point, not a full CBA-aware valuation -- it doesn't know
about scheme fit, positional scarcity beyond the coarse position groups, or
injury risk. See the in-app Methodology & Limitations page for the full,
current list of what it doesn't account for.

### Why production and salary are from two different seasons

Advanced/box-score stats come from Basketball-Reference's season-scoped
pages, so they're always the most recently *completed* season. Cap hits
come from a different page -- the live contracts table -- which reports
each player's "y1" as whatever season is *upcoming* relative to the day
it's scraped. Run this after July 1 free agency opens and you get completed
2025-26 production paired against 2026-27 contract figures. That's
intentional (it answers "what's the market now paying for what he just
did?"), but non-obvious, so `config.SALARY_CAP` / `TAX_LINE` / apron
constants are all set to match whichever season the contracts page is
currently reporting -- update them if the pairing shifts. The dashboard
states this explicitly under the title and on the Methodology page.

## Rookie-scale vs. veteran classification

Basketball-Reference doesn't publish "years of NBA experience," so it's
derived: the last `config.DRAFT_CLASSES_TO_SCRAPE` draft classes are
scraped (`scrapers/bref_draft.py`, default 25 -- covers essentially every
active player's draft year), `experience = season_end_year - draft_year`,
and anyone at or below `config.ROOKIE_SCALE_MAX_EXPERIENCE` (default 4,
matching the max length of a rookie-scale deal) is tagged "Rookie Scale."

Undrafted players (two-way signees, G League call-ups, international free
agents who signed outside the draft) were never in any draft class, so
`experience` falls back to a season-count scrape
(`scrapers/bref_seasons_played.py`) that covers players with no draft year
to subtract from. `experience_is_estimated` flags who that applies to.

## Files

```
config.py                     all the knobs: season, thresholds, weights, cap/apron figures
run_pipeline.py                orchestrates everything, writes outputs/
make_public_data.py            strips gated raw metrics -> outputs/player_value_model_public.csv
scrapers/
  bref_advanced.py             OBPM/DBPM/BPM/GP/MP/Age/Pos/Team
  bref_pergame.py               PPG/RPG/APG/SPG/BPG, shooting splits
  bref_shooting.py              shot-distance splits (feeds Rim Scoring Value)
  bref_playoffs.py              playoff per-game + advanced stats (descriptive split)
  bref_contracts.py             cap hit / years remaining / total guaranteed
  bref_draft.py                  draft year -> experience -> rookie/vet
  bref_seasons_played.py        experience fallback for undrafted players
  external_metrics.py           loads the manual EPM/DARKO/LEBRON/databallr CSVs
model/
  merge.py                      joins every source into one master table
  percentiles.py                 0-100 percentile ranks + composite production score
  positions.py                   Guard/Wing/Big grouping, dual-listing
  value_metrics.py               Rim Scoring Value, Foul-Drawing Value
  value_score.py                 Value Score, Value Ratio
  dollar_estimate.py             $-estimator + cross-conformal prediction intervals
  contracts.py                   max-contract tiering, team payroll/apron rollup
app/
  streamlit_app.py               leaderboard, filters, scatter plots, team payroll
  player_page.py                 individual player profile (Savant-style bars)
  methodology_page.py            Methodology & Limitations page
  theme.py                       shared color theme + mobile CSS
data/manual/                    drop your EPM/DARKO/LEBRON/databallr/override CSVs here
outputs/                         player_value_model.csv (full, local-only) +
                                  player_value_model_public.csv (committed, deployed)
```

## Publishing it (Streamlit Community Cloud)

The app is themed (`.streamlit/config.toml`, `app/theme.py`) and ready to
share as a public link, free, via Streamlit Community Cloud.

**Important: don't let the deployed app scrape live.** Basketball-Reference
will very likely rate-limit or block requests from a shared cloud
data-center IP, and re-scraping on every visitor is slow anyway. Instead,
commit a generated CSV to the repo and let the app read that.

**Just as important: never commit the full CSV.** `outputs/
player_value_model.csv` contains raw values from subscription-gated
sources (EPM, DARKO, LEBRON, databallr) -- using those locally for personal
research is fine, but publishing the full league's values to a public repo
republishes someone else's dataset. `make_public_data.py` strips those raw
columns (keeping their derived `_pctile` ranks, which is what the app
actually renders) and writes `outputs/player_value_model_public.csv` --
**that's** the file that gets committed. `.gitignore` enforces this with a
deny-by-default rule (`outputs/*` ignored, only the public CSV explicitly
allowed) specifically so a stale or differently-named full-data file can't
slip past it. The app prefers the full file when it's present (your
machine) and falls back to the public one (deployed), so you keep the
complete local view without any config switching.

Steps:

1. **Create a GitHub repo** (github.com -> New repository -> e.g.
   `nba-player-value-model` -> Public, so Streamlit Cloud's free tier can
   read it).
2. **Push this project to it**, from the project root:
   ```bash
   python run_pipeline.py
   python make_public_data.py
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/nba-player-value-model.git
   git push -u origin main
   ```
3. **Deploy**: go to share.streamlit.io, sign in with GitHub, click "New
   app," pick the repo/branch, and set the main file path to
   `app/streamlit_app.py`. Deploy.
4. You'll get a public URL like `your-app-name.streamlit.app` -- that's
   what you send to front office execs.

**To push a data refresh later:**
```bash
rm -rf data/cache          # forces a re-scrape instead of reusing stale HTML
python run_pipeline.py
python make_public_data.py
git add -A
git commit -m "Refresh data"
git push
```
Streamlit Cloud picks up the new commit and redeploys automatically --
though a stale build occasionally needs a manual "Reboot app" from the
Streamlit Cloud "Manage app" panel to force a clean pull.

## A couple of known rough edges

- The contracts-page scraper identifies year columns by pattern (`y1`,
  `y2`, ...) rather than a hardcoded season, so it should keep working as
  seasons roll over -- but Basketball-Reference does occasionally tweak
  table markup. If `run_pipeline.py` errors out with "Parsed zero rows,"
  open the cached HTML in `data/cache/` and check the `data-stat`
  attributes against what the code expects.
- The playoff scraper raises (and the pipeline degrades gracefully to
  "no playoff data") if run before that season's playoffs have happened
  yet -- expected, not a bug.
- Traded players are collapsed to their season-total row; if
  Basketball-Reference ever stops labeling that row `TOT`/`2TM`/`3TM`, the
  dedup logic in `bref_advanced.py`/`bref_pergame.py`/`bref_playoffs.py`
  will need a small tweak.
- Name matching across sources is done by normalizing accents/suffixes
  (`utils/name_match.py`). Run `model/merge.unmatched_report()` after a
  pipeline run to see who didn't join up cleanly -- most of that list is
  genuinely unsigned free agents rather than a matching failure, but worth
  a spot-check before sharing the dashboard.
