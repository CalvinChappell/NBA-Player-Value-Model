"""
Composite "Value" metrics, modeled on baseball's run-value framework
(Batting Run Value, Pitching Run Value, wRC+ and friends).

The shared idea: a rate stat alone is misleading, because a player who
does something well but rarely doesn't help you much, and a player who
does something constantly but badly actively hurts you. So each Value
metric here crosses an EFFICIENCY component (how well?) with a VOLUME
component (how often?), and expresses the result on a 0-100 scale where
higher is better.

Currently implemented:

  Foul-Drawing Value  -- getting to the free throw line, and converting
                         once there.
  Rim Scoring Value   -- finishing inside 3 ft, and how often you get there.

Planned: Off-Dribble Shooting Value, Spot-Up Shooting Value, Rebounding
Value, Defensive Value. All four need NBA.com tracking data (nba_api),
which has to be pulled locally rather than from a cloud IP.

SAMPLE THRESHOLDS
-----------------
Each metric has TWO thresholds rather than one: a floor below which the
value isn't reported at all, and a higher line below which it's reported
but flagged as low-sample.

This came out of a real failure. Rim Scoring originally used a single
100-attempt cutoff, which happened to sit almost exactly at the league
median (99) -- so it silently dropped half the rotation. Worse, it did
so unevenly: 62% of Bigs cleared it against 35% of Guards, because rim
attempt share is itself positional. The metric was partly measuring
"is this a big?" rather than "can he finish?".

Reporting with a caveat beats withholding: the reader can discount a
noisy number themselves, but can't do anything with an absent one.

A note on weighting, since it's a judgment call rather than a derived
constant: Foul-Drawing Value weights volume above efficiency
(_FOUL_DRAW_VOLUME_WEIGHT below). Drawing a foul has value independent
of whether the free throw goes in -- the defender picks up a foul,
the clock stops, the defense can't run in transition, and the offense
gets a set possession. A high-volume, average free throw shooter is
genuinely more valuable than a low-volume, excellent one. The weight is
deliberately not 100/0 though: a player who gets to the line constantly
and bricks it is leaving real points on the floor.
"""

import numpy as np
import pandas as pd

from config import (
    FOUL_DRAW_LOW_SAMPLE_FTA,
    FOUL_DRAW_MIN_FTA,
    FOUL_DRAW_RATE_VS_PER36_WEIGHT,
    FOUL_DRAW_VOLUME_WEIGHT,
    MIN_MINUTES,
    RIM_LOW_SAMPLE_ATTEMPTS,
    RIM_MIN_ATTEMPTS,
    RIM_VOLUME_WEIGHT,
)


def _pct_rank(series: pd.Series) -> pd.Series:
    """0-100 percentile rank, NaNs preserved. Local copy rather than an
    import from model.percentiles to keep this module standalone (it
    runs before percentiles in the pipeline for some metrics).
    """
    return series.rank(pct=True, na_option="keep") * 100


def add_foul_draw_value(df: pd.DataFrame) -> pd.DataFrame:
    """Adds:

      FTA_total          -- season free throw attempts (FTA/g * GP)
      FTA_per36          -- free throw attempts per 36 minutes
      FoulDraw_Value     -- 0-100 composite, volume-weighted
      FoulDraw_low_sample -- True if under the attempt threshold

    Requires FTr (free throw rate, from the advanced-stats scrape),
    FT_PCT and FTA_per_g (per-game scrape), GP and MP.
    """
    df = df.copy()

    required = ["FTr", "FT_PCT", "FTA_per_g", "GP", "MP"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        # Degrade gracefully rather than exploding: the pipeline should
        # still run for anyone with an older cached scrape that predates
        # these columns being collected.
        df["FTA_total"] = np.nan
        df["FTA_per36"] = np.nan
        df["FoulDraw_Value"] = np.nan
        df["FoulDraw_low_sample"] = False
        return df

    df["FTA_total"] = pd.to_numeric(df["FTA_per_g"], errors="coerce") * pd.to_numeric(
        df["GP"], errors="coerce"
    )

    # Trips to the line per 36 minutes -- the "how often does this guy
    # actually get to the line?" measure, normalized for playing time so
    # a starter isn't rewarded purely for playing more minutes than a
    # bench player.
    mp = pd.to_numeric(df["MP"], errors="coerce")
    df["FTA_per36"] = np.where(mp > 0, df["FTA_total"] / mp * 36.0, np.nan)

    # Percentiles are computed among rotation players only, for the same
    # reason production percentiles are (see model/percentiles.py): a
    # 40-minute cameo shouldn't be able to define the top of the scale.
    eligible = (df["MP"] >= MIN_MINUTES) & (df["FTA_total"] >= FOUL_DRAW_MIN_FTA)

    per36_pctile = pd.Series(np.nan, index=df.index)
    ftr_pctile = pd.Series(np.nan, index=df.index)
    efficiency_pctile = pd.Series(np.nan, index=df.index)
    per36_pctile.loc[eligible] = _pct_rank(df.loc[eligible, "FTA_per36"])
    ftr_pctile.loc[eligible] = _pct_rank(df.loc[eligible, "FTr"])
    efficiency_pctile.loc[eligible] = _pct_rank(df.loc[eligible, "FT_PCT"])

    # Volume is itself a blend: mostly actual line trips (FTA/36), partly
    # foul-drawing rate relative to shot attempts (FTr). See the comment
    # on FOUL_DRAW_RATE_VS_PER36_WEIGHT in config.py for why FTr alone
    # produced bad results (low-usage players outranking high-volume ones).
    rw = FOUL_DRAW_RATE_VS_PER36_WEIGHT
    volume_pctile = rw * per36_pctile + (1 - rw) * ftr_pctile

    w = FOUL_DRAW_VOLUME_WEIGHT
    df["FoulDraw_Value"] = w * volume_pctile + (1 - w) * efficiency_pctile

    # Flag rather than drop: players below the attempt threshold still get
    # a value if they have the underlying stats, but it's marked so you
    # can see at a glance that it rests on a small sample.
    # Flagged (not excluded) between the floor and the low-sample line.
    df["FoulDraw_low_sample"] = (
        (df["FTA_total"] < FOUL_DRAW_LOW_SAMPLE_FTA) & df["FTA_total"].notna()
    )

    return df


def add_rim_scoring_value(df: pd.DataFrame) -> pd.DataFrame:
    """Adds:

      rim_FGA_total   -- season field goal attempts from 0-3 ft
      rim_FGA_per36   -- rim attempts per 36 minutes
      Rim_Scoring_Value -- 0-100 composite, efficiency-weighted
      Rim_low_sample  -- True if under the attempt threshold

    Requires FG_PCT_rim and FGA_share_rim (shooting-page scrape),
    FGA_per_g (per-game scrape), GP and MP.

    Unlike Foul-Drawing Value, efficiency outweighs volume here -- see
    RIM_VOLUME_WEIGHT in config.py. A missed layup is a dead possession;
    a missed free throw at least came with a foul on the defense.
    """
    df = df.copy()

    required = ["FG_PCT_rim", "FGA_share_rim", "FGA_per_g", "GP", "MP"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        df["rim_FGA_total"] = np.nan
        df["rim_FGA_per36"] = np.nan
        df["Rim_Scoring_Value"] = np.nan
        df["Rim_low_sample"] = False
        return df

    fga_total = pd.to_numeric(df["FGA_per_g"], errors="coerce") * pd.to_numeric(
        df["GP"], errors="coerce"
    )
    # The shooting page gives the SHARE of attempts from 0-3 ft, not a
    # count, so multiply back out by total FGA.
    df["rim_FGA_total"] = fga_total * pd.to_numeric(df["FGA_share_rim"], errors="coerce")

    mp = pd.to_numeric(df["MP"], errors="coerce")
    df["rim_FGA_per36"] = np.where(mp > 0, df["rim_FGA_total"] / mp * 36.0, np.nan)

    eligible = (df["MP"] >= MIN_MINUTES) & (df["rim_FGA_total"] >= RIM_MIN_ATTEMPTS)

    volume_pctile = pd.Series(np.nan, index=df.index)
    efficiency_pctile = pd.Series(np.nan, index=df.index)
    volume_pctile.loc[eligible] = _pct_rank(df.loc[eligible, "rim_FGA_per36"])
    efficiency_pctile.loc[eligible] = _pct_rank(df.loc[eligible, "FG_PCT_rim"])

    w = RIM_VOLUME_WEIGHT
    df["Rim_Scoring_Value"] = w * volume_pctile + (1 - w) * efficiency_pctile

    df["Rim_low_sample"] = (
        (df["rim_FGA_total"] < RIM_LOW_SAMPLE_ATTEMPTS) & df["rim_FGA_total"].notna()
    )

    return df


def add_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Entry point -- runs every composite value metric in this module."""
    df = add_foul_draw_value(df)
    df = add_rim_scoring_value(df)

    # Report coverage so the thresholds stay honest. If one of these
    # starts excluding a large share of the rotation -- or excluding one
    # position group far more than another -- that's a sign the cutoff
    # is doing something other than filtering noise.
    rotation = df["MP"] >= MIN_MINUTES
    n_rot = int(rotation.sum())
    if n_rot:
        for col, label in (("Rim_Scoring_Value", "Rim Scoring"),
                           ("FoulDraw_Value", "Foul Drawing")):
            if col in df.columns:
                have = int(df.loc[rotation, col].notna().sum())
                flagged_col = col.replace("_Scoring_Value", "_low_sample").replace(
                    "FoulDraw_Value", "FoulDraw_low_sample"
                )
                flagged = (
                    int(df.loc[rotation & df[col].notna(), flagged_col].sum())
                    if flagged_col in df.columns else 0
                )
                print(
                    f"  {label}: {have}/{n_rot} rotation players scored "
                    f"({have / n_rot * 100:.0f}%), {flagged} flagged low-sample"
                )
    return df
