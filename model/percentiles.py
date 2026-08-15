"""
Turns raw metric values into 0-100 percentile ranks, and rolls the
selected PRODUCTION_METRICS (config.py) up into one composite
"Production Percentile" per player.

Production percentiles are computed only among players who clear
MIN_MINUTES (config.py) -- a bench player who logged 80 minutes
shouldn't be able to post a 99th-percentile OBPM off a hot streak.
Salary percentile is computed across every player with a known cap
hit, regardless of playing time, since that's the actual population
you're being paid relative to.
"""

import numpy as np
import pandas as pd

from config import (
    BOX_SCORE_METRICS,
    DESCRIPTIVE_METRICS,
    MIN_MINUTES,
    PLAYSTYLE_METRICS,
    PRODUCTION_METRIC_WEIGHTS,
    PRODUCTION_METRICS,
    SALARY_FIELD_FOR_VALUE,
    VALUE_METRICS,
)
from model.positions import add_position_groups, exploded_membership


def pct_rank(series: pd.Series) -> pd.Series:
    """0-100 percentile rank of a series, NaNs preserved as NaN. Public so
    other modules (e.g. run_pipeline.py, for value_score/market_value
    percentiles computed after this module runs) can reuse the same logic.
    """
    return series.rank(pct=True, na_option="keep") * 100


_pct_rank = pct_rank  # backwards-compatible alias


def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    qualified = df["MP"] >= MIN_MINUTES

    all_metrics = (
        PRODUCTION_METRICS + DESCRIPTIVE_METRICS + BOX_SCORE_METRICS
        + PLAYSTYLE_METRICS + VALUE_METRICS
    )
    for metric in all_metrics:
        if metric not in df.columns:
            continue
        pct_col = f"{metric}_pctile"
        df[pct_col] = np.nan
        df.loc[qualified, pct_col] = _pct_rank(df.loc[qualified, metric])

    available_pct_cols = [
        f"{m}_pctile" for m in PRODUCTION_METRICS if f"{m}_pctile" in df.columns
    ]

    # Weighted composite rather than a plain mean: BPM is box-score-only
    # and gets less weight than the RAPM-informed EPM/DARKO. See
    # PRODUCTION_METRIC_WEIGHTS in config.py for the reasoning.
    #
    # Weights are renormalized per player over whichever metrics they
    # actually have, so someone missing EPM/DARKO isn't penalized with a
    # partial score -- their BPM just carries the full weight. That does
    # mean a 1-metric player's score is a noisier estimate than a
    # 3-metric player's, which n_production_metrics_available exposes.
    pct_values = df[available_pct_cols].apply(pd.to_numeric, errors="coerce")
    weights = pd.Series(
        {
            col: PRODUCTION_METRIC_WEIGHTS.get(col.replace("_pctile", ""), 0.0)
            for col in available_pct_cols
        }
    )

    present = pct_values.notna()
    weight_matrix = present.mul(weights, axis=1)
    total_weight = weight_matrix.sum(axis=1)

    weighted_sum = (pct_values.fillna(0) * weight_matrix).sum(axis=1)
    df["production_pctile"] = np.where(
        total_weight > 0, weighted_sum / total_weight, np.nan
    )
    df["n_production_metrics_available"] = present.sum(axis=1)

    salary_field = SALARY_FIELD_FOR_VALUE
    df["salary_pctile"] = _pct_rank(df[salary_field])

    df["qualified_min_minutes"] = qualified

    df = add_position_percentiles(df, all_metrics, qualified)
    return df


def add_position_percentiles(df: pd.DataFrame, metrics: list, qualified: pd.Series) -> pd.DataFrame:
    """Adds `{metric}_pctile_pos` -- the same percentiles, but computed
    within position group (Guard / Wing / Big) rather than league-wide.

    League-wide stays the default everywhere in the app; this is the
    alternate lens, so you can ask "is this center a good rebounder for
    a center?" rather than "...compared to point guards?".

    Dual-listed players (see model/positions.py) are ranked in every
    group they belong to, and their reported percentile is the mean of
    those ranks -- a combo forward gets a blend of how he stacks up
    against wings and against bigs.
    """
    df = add_position_groups(df)

    membership = exploded_membership(df)
    if membership.empty:
        for metric in metrics:
            if metric in df.columns:
                df[f"{metric}_pctile_pos"] = np.nan
        return df

    # Only rank qualified players, matching the league-wide behavior.
    qualified_rows = set(df.index[qualified])
    membership = membership[membership["_row"].isin(qualified_rows)]

    for metric in metrics:
        if metric not in df.columns:
            continue
        pos_col = f"{metric}_pctile_pos"
        df[pos_col] = np.nan
        if membership.empty:
            continue

        vals = membership.join(
            df[metric].rename("_value"), on="_row"
        )
        # Rank within each position group, then average across groups
        # for anyone dual-listed.
        vals["_pct"] = vals.groupby("pos_group_single")["_value"].transform(
            lambda s: s.rank(pct=True, na_option="keep") * 100
        )
        per_player = vals.groupby("_row")["_pct"].mean()
        df.loc[per_player.index, pos_col] = per_player.values

    return df
