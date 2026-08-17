"""
The headline number: Value Score = Production Percentile - Pay-vs-Worth
Percentile.

Range is roughly -100 to +100:
  +50 or higher  -> playing like a top-tier producer on a bargain contract
  around 0       -> paid about what they're producing
  -50 or lower   -> being paid like a star but not producing like one

WHY THIS ISN'T "Production Percentile - Salary Percentile" ANYMORE
--------------------------------------------------------------------
The original version subtracted `salary_pctile` -- a percentile rank of
each player's raw cap hit against the whole league. That broke down at
the top of the market: NBA salaries are heavily right-skewed (a dense
floor of minimum-ish deals, a long thin tail of max contracts), so a
big-but-not-max number like a rookie-scale year-4 salary still lands at a
HIGH percentile purely because most of the league makes far less --
even though, in market terms, it's a steep discount. That's what let
Baylor Scheierman (modest production, modest pay) out-score Victor
Wembanyama (99th-percentile production, but a "big-sounding" rookie-scale
salary that ranked ~73rd percentile of all salaries and got treated as
"paid like a star"): percentile-of-raw-dollars can't tell "significant
dollar figure" apart from "actually paid close to what you're worth."

The fix: replace the pay side with a percentile rank of
`cap_hit / estimated_market_value` -- how much of a player's own
estimated true worth he's actually being paid, rather than how his raw
dollar figure stacks up against everyone else's. A rookie-scale star
being paid 35% of his estimated market value now correctly registers as
one of the biggest bargains in the league, regardless of how large that
35% looks in absolute dollars. This also makes Value Score and Market
Value Surplus consistent with each other -- both now trace back to the
same estimated_market_value model instead of Value Score running its own
separate (and, at the top of the market, misleading) percentile logic.

`salary_pctile` itself is untouched and still shown on the player page --
"how much is this guy paid, league-wide" is a legitimate, separate stat
from "is he paid what he's worth," and this file isn't the place to
redefine it.

Falls back to the old production_pctile - salary_pctile formula if
estimated_market_value isn't available (e.g. the $-estimator couldn't
fit -- see run_pipeline.py's fallback branch), so Value Score degrades
gracefully instead of going all-NaN.

We also compute a ratio version and a couple of convenience filters
(rookie scale vs veteran, position group) since Calvin wants to slice
the table interactively.
"""

import numpy as np
import pandas as pd

from config import SALARY_FIELD_FOR_VALUE
from model.percentiles import pct_rank


def add_value_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "estimated_market_value" in df.columns and df["estimated_market_value"].notna().any():
        safe_estimate = df["estimated_market_value"].replace(0, np.nan)
        pay_vs_value_ratio = df[SALARY_FIELD_FOR_VALUE] / safe_estimate
        df["pay_vs_value_ratio"] = pay_vs_value_ratio
        df["pay_vs_value_pctile"] = pct_rank(pay_vs_value_ratio)
        df["value_score"] = df["production_pctile"] - df["pay_vs_value_pctile"]
    else:
        df["pay_vs_value_ratio"] = np.nan
        df["pay_vs_value_pctile"] = np.nan
        df["value_score"] = df["production_pctile"] - df["salary_pctile"]

    # Ratio version: >1 means producing more (percentile-wise) than paid;
    # guard against divide-by-zero for minimum-salary players. Deliberately
    # still paired with salary_pctile (not pay_vs_value_pctile) since it's
    # displayed alongside salary_pctile in the app's Advanced tab and should
    # stay internally consistent with that column.
    safe_salary_pctile = df["salary_pctile"].replace(0, np.nan)
    df["value_ratio"] = df["production_pctile"] / safe_salary_pctile

    df["is_rookie_scale"] = df["contract_type"].eq("Rookie Scale")
    return df


def filter_players(
    df: pd.DataFrame,
    contract_type: str | None = None,  # "Rookie Scale", "Veteran", or None for all
    position: str | None = None,
    min_minutes_only: bool = True,
) -> pd.DataFrame:
    out = df
    if min_minutes_only:
        out = out[out["qualified_min_minutes"]]
    if contract_type:
        out = out[out["contract_type"] == contract_type]
    if position:
        out = out[out["pos"] == position]
    return out
