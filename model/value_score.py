"""
The headline number: Value Score = Production Percentile - Salary Percentile.

Range is roughly -100 to +100:
  +50 or higher  -> playing like a top-tier producer on a bargain contract
  around 0       -> paid about what they're producing
  -50 or lower   -> being paid like a star but not producing like one

We also compute a ratio version and a couple of convenience filters
(rookie scale vs veteran, position group) since Calvin wants to slice
the table interactively.
"""

import numpy as np
import pandas as pd


def add_value_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["value_score"] = df["production_pctile"] - df["salary_pctile"]

    # Ratio version: >1 means producing more (percentile-wise) than paid;
    # guard against divide-by-zero for minimum-salary players.
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
