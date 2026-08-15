# NBA Player Value Model

Cross-references every rostered NBA player's production (BPM, and optionally
EPM/DARKO/LEBRON) against their salary to produce a **Value Score**: are
they outproducing their contract, or overpaid relative to it? Includes a
rookie-scale vs. veteran filter and a $-value estimator, plus an
interactive Streamlit dashboard you can point at front office execs.

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python run_pipeline.py          # scrapes + builds outputs/player_value_model.csv
streamlit run app/streamlit_app.py   # interactive dashboard
```

First run takes a few minutes (it's scraping Basketball-Reference with a
polite delay between requests, plus 4-5 draft-class pages). After that,
`config.USE_CACHE = True` means re-running `run_pipeline.py` reuses the
cached HTML in `data/cache/` instantly, until you delete that folder or
flip the flag off.

## What's fully automatic vs. what needs your input

**Scraped automatically, no setup needed:**
- OBPM, DBPM, BPM, VORP, GP, minutes, age, position, team -- from
  Basketball-Reference's season Advanced stats table.
- Current-season salary, cap hit (see caveat below), years remaining,
  total guaranteed money -- from Basketball-Reference's contracts page.
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
  subscriber-only.

For each of these, `run_pipeline.py` writes a starter template to
`data/manual/epm.csv`, `darko.csv`, and `lebron.csv` (two columns:
`player`, `<METRIC>`). Export or copy the table from the site into that
CSV (most of them let you copy a table or download a CSV if you're
subscribed) and re-run the pipeline -- it'll pick up whatever subset of
metrics you've collected and simply skip the rest. You don't need all
three for the model to work; it composites over whichever are present
(see `production_pctile` / `n_production_metrics_available` in the
output).

Two more things worth overriding by hand in
`data/manual/contract_overrides.csv` (columns: `player, contract_type,
bird_rights_status, cap_hit_override, notes`):
- **Cap hit vs. salary**: for ~95% of players these are identical.
  They diverge for stretch provisions, base-year-compensation trades,
  etc., which Basketball-Reference doesn't expose. Fill in
  `cap_hit_override` for any player where it matters.
- **Bird rights status**: not published in structured form anywhere
  scraped here. Fill in from your own front-office records or Spotrac if
  you need it for cap-planning purposes.

## How the model works

1. **Percentiles** (`model/percentiles.py`): every metric gets converted
   to a 0-100 percentile rank. Production percentiles are computed only
   among players clearing `config.MIN_MINUTES` (default 500) so a
   30-minute hot streak can't post a 99th-percentile mark. Salary
   percentile uses everyone with a known cap hit, since that's the real
   population you're paid relative to.
2. **Composite production score**: the average of whichever
   `config.PRODUCTION_METRICS` percentiles are available for that player
   (default: BPM, EPM, DARKO, LEBRON -- edit the list in `config.py`).
   Missing metrics are dropped from that player's average, not zeroed
   out.
3. **Value Score** (`model/value_score.py`): `production_pctile -
   salary_pctile`. Roughly -100 to +100. +50 or higher = playing like a
   top-tier producer on a bargain; -50 or lower = paid like a star but
   not producing like one.
4. **$-estimator** (`model/dollar_estimate.py`): a random forest trained
   on **veterans only** (rookie-scale salaries are CBA-slotted, not
   performance-based, so including them would bias the model) predicts
   `estimated_market_value` for every player based on production + age +
   experience + minutes. Compare to actual cap hit for a dollar-
   denominated surplus/deficit. This is a starting point, not a
   CBA-aware valuation -- it doesn't know about max contracts, cap space,
   positional scarcity, or injury risk.

## Rookie-scale vs. veteran classification

Basketball-Reference doesn't publish "years of NBA experience," so it's
derived: the last `config.DRAFT_CLASSES_TO_SCRAPE` draft classes are
scraped (`scrapers/bref_draft.py`, default 25 -- covers essentially every
active player's draft year), `experience = season_end_year - draft_year`,
and anyone at or below `config.ROOKIE_SCALE_MAX_EXPERIENCE` (default 4,
matching the max length of a rookie-scale deal) is tagged "Rookie Scale."

Undrafted players (Seth Curry, two-way signees, G League call-ups,
international free agents who signed outside the draft) were never in
any draft class, so `experience` shows up blank for them specifically --
there's no draft year to subtract from. This is a known, accepted gap:
the `contract_type` classification still comes out correct (blank
experience falls back to "Veteran," which is right for anyone who's
actually been in the league a while), it's only the raw `experience`
number that's cosmetically missing for that subset of players. Override
specific players in `contract_overrides.csv` if you want to hand-fill a
number for someone.

## Files

```
config.py                    all the knobs: season, thresholds, which metrics feed the model
run_pipeline.py               orchestrates everything, writes outputs/
scrapers/
  bref_advanced.py            OBPM/DBPM/BPM/GP/MP/Age
  bref_contracts.py           salary/cap hit/years remaining
  bref_draft.py                draft year -> experience -> rookie/vet
  external_metrics.py         loads the manual EPM/DARKO/LEBRON CSVs
model/
  merge.py                     joins everything into one master table
  percentiles.py                0-100 percentile ranks + composite production score
  value_score.py                Value Score, Value Ratio, rookie/vet + position filters
  dollar_estimate.py            $-value regression model
app/
  streamlit_app.py               interactive dashboard
data/manual/                   drop your EPM/DARKO/LEBRON/override CSVs here
outputs/                        player_value_model.csv / .xlsx land here
```

## Publishing it (Streamlit Community Cloud)

The app is themed (`.streamlit/config.toml`, `app/theme.py`) and ready to
share as a public link, free, via Streamlit Community Cloud.

**Important: don't let the deployed app scrape live.** Basketball-Reference
will very likely rate-limit or block requests coming from a shared cloud
data-center IP, and re-scraping on every visitor is slow anyway. Instead,
commit your already-generated `outputs/player_value_model.csv` to the repo
-- the app reads that file directly and only offers to scrape if it's
missing. Whenever you want to refresh the data, re-run `run_pipeline.py`
locally and push the updated CSV.

Steps:

1. **Create a GitHub repo** (github.com -> New repository -> e.g.
   `nba-player-value-model` -> Public, so Streamlit Cloud's free tier can
   read it).
2. **Push this project to it**, from the project root:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/nba-player-value-model.git
   git push -u origin main
   ```
   (`.gitignore` already excludes the venv and the disposable HTML cache;
   `outputs/player_value_model.csv` is NOT excluded on purpose -- you want
   that committed.)
3. **Deploy**: go to share.streamlit.io, sign in with GitHub, click "New
   app," pick the repo/branch, and set the main file path to
   `app/streamlit_app.py`. Deploy.
4. You'll get a public URL like `your-app-name.streamlit.app` -- that's
   what you send to front office execs.

To push a data refresh later: re-run `python run_pipeline.py` locally,
then `git add outputs/player_value_model.csv && git commit -m "Refresh data" && git push`
-- Streamlit Cloud picks up the new commit and redeploys automatically.

## A couple of known rough edges

- The contracts-page scraper identifies year columns by pattern
  (`2025-26`, `2026-27`, ...) rather than a hardcoded season, so it
  should keep working as seasons roll over -- but Basketball-Reference
  does occasionally tweak table markup. If `run_pipeline.py` errors out
  with "Parsed zero rows," open the cached HTML in `data/cache/` and
  check the `data-stat` attributes against what the code expects.
- Traded players are collapsed to their season-total row; if
  Basketball-Reference ever stops labeling that row `TOT`/`2TM`/`3TM`,
  the dedup logic in `bref_advanced.py` will need a small tweak.
- Name matching across sources is done by normalizing accents/suffixes
  (`utils/name_match.py`). Run `model/merge.unmatched_report()` after a
  pipeline run to see who didn't join up cleanly.
