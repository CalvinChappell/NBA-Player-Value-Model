"""
Central configuration for the NBA player value model.

Edit the constants below to point at a different season, change which
metrics feed the composite "production score," or adjust thresholds.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Season / paths
# ---------------------------------------------------------------------------

# Basketball-Reference season string, e.g. 2025-26 season -> "2026"
SEASON_END_YEAR = 2026

ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / "data" / "cache"
MANUAL_DIR = ROOT_DIR / "data" / "manual"
OUTPUT_DIR = ROOT_DIR / "outputs"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Set True to reuse cached HTML/CSV pulls instead of re-hitting the sites.
# Useful while iterating so you don't hammer Basketball-Reference.
USE_CACHE = True

# ---------------------------------------------------------------------------
# Scraping courtesy settings
# ---------------------------------------------------------------------------

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; nba-value-model/1.0; personal research use)"
}
REQUEST_DELAY_SECONDS = 3.0  # be polite to Basketball-Reference, avoid getting rate-limited/blocked

# ---------------------------------------------------------------------------
# Filtering thresholds
# ---------------------------------------------------------------------------

# Players below this many total minutes are excluded from percentile ranking
# (small samples produce wild per-metric values that distort percentiles).
MIN_MINUTES = 500

# A player is classified "Rookie Scale" if their years of NBA experience is
# at or below this value. This is a heuristic (see model/value_score.py) --
# override individual players in data/manual/contract_overrides.csv if you
# have better ground truth (e.g. two-way deals, Exhibit 10s, etc).
ROOKIE_SCALE_MAX_EXPERIENCE = 4

# How many past draft classes to scrape when computing "experience" (see
# scrapers/bref_draft.py). Only needs to cover ROOKIE_SCALE_MAX_EXPERIENCE
# years to correctly flag rookie-scale contracts, but a small number here
# means every veteran drafted further back than that shows up with a blank
# "experience" column (they just aren't in the lookup at all). 25 years
# covers effectively every active NBA player's draft class, at the cost of
# ~25 extra (cached-after-first-run) requests to Basketball-Reference.
DRAFT_CLASSES_TO_SCRAPE = 25

# How many past seasons to scan when counting seasons played, which is
# how undrafted players get an experience value at all (they have no
# draft class to subtract from). 20 covers all but the longest careers,
# and every page is cached after the first run.
SEASONS_FOR_EXPERIENCE = 20

# ---------------------------------------------------------------------------
# Which metrics feed the composite "production score" used for percentiles
# and the value score. Any metric not present for a player (e.g. missing
# EPM/DARKO/LEBRON because you haven't imported them yet) is simply dropped
# from that player's average -- it does NOT zero them out.
# ---------------------------------------------------------------------------

PRODUCTION_METRICS = [
    "BPM",     # Basketball-Reference, always available
    "EPM",     # manual import, dunksandthrees.com
    "DARKO",   # manual import, apanalytics DARKO
    # "LEBRON" intentionally left out -- bball-index.com's full league data
    # is subscription-gated, so we're not pursuing it right now. Add it back
    # here (and drop real data into data/manual/lebron.csv) if that changes.
]

# Relative weights for the composite production score. These are NOT
# equal, deliberately:
#
#   BPM is box-score-only -- it infers impact from counting stats and
#   knows nothing about who a player guarded, shot quality, or what
#   happened when they sat. EPM and DARKO are both RAPM-informed and
#   built on play-by-play, so they capture on/off impact that BPM
#   structurally cannot. Weighting all three equally over-credits the
#   weakest input.
#
#   Weights are renormalized over whichever metrics a given player
#   actually has (see model/percentiles.py), so a player missing EPM and
#   DARKO still gets a score -- it's just derived entirely from BPM, and
#   `n_production_metrics_available` records that so you can tell the
#   difference between a 3-metric and a 1-metric player.
PRODUCTION_METRIC_WEIGHTS = {
    "BPM": 0.25,
    "EPM": 0.375,
    "DARKO": 0.375,
    "LEBRON": 0.0,  # unused unless re-enabled above
}

# Descriptive metrics that are shown in the output table but NOT folded into
# the composite production score (OBPM/DBPM are already inside BPM; mins/GP/
# age are context, not production).
DESCRIPTIVE_METRICS = ["OBPM", "DBPM", "MP", "GP", "AGE"]

# Basic per-game box score stats (Basketball-Reference's Per Game table).
# Also excluded from the composite production score -- these are shown as
# their own percentile bars on the player page, Baseball-Savant style,
# rather than folded into the all-in-one production score.
BOX_SCORE_METRICS = ["PPG", "RPG", "APG", "SPG", "BPG", "FG_PCT", "FG3_PCT", "FT_PCT"]

# Playstyle / secondary impact metrics from databallr.com (manual import --
# see data/manual/databallr_metrics.csv and scrapers/external_metrics.py).
# Like BOX_SCORE_METRICS, these get their own percentile bars on the player
# page rather than folding into the composite production score, since
# they measure playstyle/role (OnBall%) or narrower slices of impact
# (rTS%, 3Y RAPM, PVAL, Net On/Off) rather than being all-in-one metrics
# like BPM/EPM/DARKO.
PLAYSTYLE_METRICS = ["OnBall_Pct", "rTS_rel", "RAPM_3Y", "PVAL", "NET_ON_OFF"]

# ---------------------------------------------------------------------------
# Composite "Value" metrics (model/value_metrics.py) -- baseball-style
# efficiency x volume scores, each on a 0-100 scale.
# ---------------------------------------------------------------------------

# Each of these is itself a 0-100 score, so it gets a percentile like any
# other metric and shows up as its own bar on the player page.
VALUE_METRICS = ["FoulDraw_Value", "Rim_Scoring_Value"]

# Foul-Drawing Value: how much weight goes to volume vs. efficiency
# (FT%). Above 0.5 means volume matters more -- drawing a foul has value
# even on a miss (defender foul trouble, clock stoppage, no transition
# defense), so a high-volume average shooter beats a low-volume great
# one. Not 1.0 though: bricking free throws is still leaving points on
# the floor.
FOUL_DRAW_VOLUME_WEIGHT = 0.60

# Within the volume component, how much weight goes to FTA per 36
# minutes (actual trips to the line, playing-time adjusted) vs. free
# throw rate / FTr (FTA per field goal attempt).
#
# Both matter, but they measure different things and FTr alone is
# misleading: it's a rate relative to SHOT ATTEMPTS, so a low-usage
# player who happens to draw contact on his rare shots scores highly
# without actually generating many free throws. FTA/36 captures how
# often a player really gets to the line; FTr captures foul-drawing
# skill independent of how much he shoots. Weighting the former higher
# keeps the metric anchored to real production.
FOUL_DRAW_RATE_VS_PER36_WEIGHT = 0.65  # share going to FTA/36

# Same two-threshold structure as Rim Scoring Value above. Free throw
# volume is less positionally skewed than rim volume, so the old single
# cutoff of 50 was less damaging here (83% of the rotation cleared it),
# but the same principle applies: report with a caveat rather than
# withhold.
FOUL_DRAW_MIN_FTA = 30          # below this, too noisy to report (~92% of rotation clears)
FOUL_DRAW_LOW_SAMPLE_FTA = 75   # below this, computed but flagged

# Rim Scoring Value: efficiency (FG% at 0-3 ft) vs. volume (rim attempts
# per 36 minutes).
#
# NOTE this is weighted the OPPOSITE way from Foul-Drawing Value, and
# deliberately so. Drawing a foul has value even when the free throw
# misses. Missing a layup does not -- it's a dead possession, and a
# high-volume, low-efficiency rim finisher is actively costing his team
# points. So efficiency leads here, with volume still mattering enough
# that a rim-pressure creator outranks someone who converts five
# uncontested dunks a month.
RIM_VOLUME_WEIGHT = 0.45  # remainder (0.55) goes to FG% at the rim

# Rim Scoring Value uses TWO thresholds, not one.
#
# A single cutoff at 100 attempts turned out to be badly placed: the
# median rotation player takes 99 rim attempts, so it excluded half the
# league outright -- and it did so unevenly. 62% of Bigs cleared it
# versus only 35% of Guards (median rim attempts 133 vs 79), because
# rim share is itself positional. The metric was quietly answering
# "is this a big?" as much as "can he finish?".
#
# So: compute the value for anyone above a low FLOOR, and use a separate,
# higher threshold purely to FLAG the noisy ones. A 22-minute guard now
# appears with a caveat instead of vanishing, which is more useful than
# silence -- the reader can weigh it themselves.
#
# Statistical cost of the lower floor is real but modest: standard error
# on rim FG% is roughly +/-5 points at 100 attempts and +/-7 at 50.
# Noisier, not meaningless.
RIM_MIN_ATTEMPTS = 40        # below this, too noisy to report at all (~89% of rotation clears)
RIM_LOW_SAMPLE_ATTEMPTS = 100  # below this, computed but flagged as low sample

# Column used for the salary percentile / value score. "cap_hit" is
# generally what front offices care about (accounts for trade kickers,
# stretch provisions where known); falls back to "salary" if unset.
SALARY_FIELD_FOR_VALUE = "cap_hit"

# Column the $-estimator model tries to predict.
SALARY_FIELD_FOR_REGRESSION = "cap_hit"

# ---------------------------------------------------------------------------
# $-estimator prediction intervals
# ---------------------------------------------------------------------------
# The point estimate alone ($22.4M) reads as more precise than a model
# with ~0.63 holdout R^2 deserves. These quantiles define the range
# reported alongside it, via quantile regression (see
# model/dollar_estimate.py). 0.10/0.90 gives a nominal 80% interval:
# roughly 8 of 10 players should have their actual cap hit land inside
# it. The pipeline prints the realized coverage on holdout data so you
# can check that claim rather than take it on faith.
MARKET_VALUE_INTERVAL_LOW = 0.10
MARKET_VALUE_INTERVAL_HIGH = 0.90

# Inner ("leaning") coverage level. The 80% interval above is a
# deliberately high bar -- it only fires when a salary is extreme
# relative to the prediction, which means mid-tier players where the
# model is least precise almost never get a call, even when the point
# estimate points clearly one way.
#
# Example that motivated this: a player with a $15.2M cap hit against a
# $10.0M estimate -- the model's central guess is "overpaid by $5M" --
# still landed inside an 80% interval spanning $2.7M to $21.9M, and so
# came out "Fairly paid." Directionally clear, verdict silent.
#
# So we compute a second, narrower band and report three levels of
# confidence instead of two:
#     outside the 80% band  -> "Overpaid" / "Underpaid"     (confident)
#     outside the 50% band  -> "Leaning overpaid/underpaid" (probable)
#     inside the 50% band   -> "Fairly paid"
MARKET_VALUE_INNER_COVERAGE = 0.50

# Number of folds for cross-conformal calibration. A plain
# train/calibration/test split wastes data -- with only ~170 veterans it
# cost us ~40% of the training set and dropped holdout R^2 from 0.63 to
# 0.43. K-fold cross-conformal instead calibrates on out-of-fold
# predictions, so every player contributes to both training and
# calibration, and the final model is refit on all of them.
MARKET_VALUE_CV_FOLDS = 5

# Model log(salary) rather than raw dollars. NBA salaries are strongly
# right-skewed (a long tail of max deals above a dense floor of minimum
# contracts), which violates the constant-variance assumption behind
# symmetric intervals: a $5M error means something completely different
# for a $2M player than a $50M one. Fitting in log space makes the
# errors roughly proportional instead of absolute, which tightens
# intervals substantially at the low end where most players live.
MARKET_VALUE_LOG_TRANSFORM = True

# ---------------------------------------------------------------------------
# CBA max-contract tiers
# ---------------------------------------------------------------------------
# 2026-27 salary cap, per the NBA's official announcement.
SALARY_CAP = 164_961_000

# Maximum starting salary as a share of the cap, by years of NBA service:
#   <= 6 years   -> 25%
#   7-9 years    -> 30%
#   >= 10 years  -> 35%
# (Actual max figures are computed off a slightly different base than the
# raw cap, so treat these as close approximations rather than exact CBA
# arithmetic -- good enough to identify who is at or near a max deal.)
MAX_CONTRACT_TIERS = [
    (6, 0.25),    # experience <= 6
    (9, 0.30),    # experience 7-9
    (99, 0.35),   # experience >= 10
]

# A player counts as "at the max" if their cap hit reaches this share of
# their tier's maximum. Slightly below 1.0 because cap hits drift from
# the theoretical max via raises, trade kickers, and cap holds.
MAX_CONTRACT_THRESHOLD = 0.92

# The $-estimator's veteran training pool thins out fast in the mid-to-late
# 30s -- survivorship means only a handful of players per season are still
# active much past this age, so there's little or nothing nearby in
# feature space for the model to anchor on. Same caveat as rookie-scale
# extrapolation (model/dollar_estimate.py), just at the opposite end of a
# career: below ROOKIE_SCALE_MAX_EXPERIENCE the model has never seen a
# performance-priced deal, above this age it's rarely seen a deal at all.
# A judgment-call heuristic, not a fitted cutoff -- see app/player_page.py.
EXTREME_VETERAN_AGE_THRESHOLD = 36

# ---------------------------------------------------------------------------
# Playoff split (descriptive only -- see scrapers/bref_playoffs.py)
# ---------------------------------------------------------------------------
# Below this many total playoff minutes, the playoff panel on the player
# page still shows the numbers but flags them as too small a sample to
# read into. A first-round sweep is 4 games; a 20-minute role player in a
# 4-game sweep might log ~80 minutes total, so 150 (roughly 5-6 games at a
# rotation-level 25-30 min/game) is a reasonable "at least saw a series or
# two" line. Deliberately NOT used to exclude anyone from anything, and
# deliberately NOT folded into Value Score / Market Value -- playoff
# samples are too thin league-wide for a ranked composite. See the module
# docstring in scrapers/bref_playoffs.py.
PLAYOFF_LOW_SAMPLE_MP = 150
