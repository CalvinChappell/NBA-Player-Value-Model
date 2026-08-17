"""
CBA contract-tier classification, and why the value model needs it.

THE PROBLEM THIS SOLVES

The $-estimator predicts what the market pays for a given production
profile. But the CBA caps what ANY player can be paid: 25% / 30% / 35%
of the salary cap depending on years of service. So the very best
players in the league are all bunched against a ceiling, and their
salaries stop responding to how good they are.

That breaks the surplus interpretation at the top. A top-5 player and a
merely-very-good All-Star can be paid nearly the same, so the model --
which only ever saw capped salaries in training -- learns that ceiling
as if it were the market's honest valuation, and reports both as
"fairly paid." Their true surplus is invisible, not zero.

The fix isn't to change the model, it's to stop asking it the wrong
question. For players at or near a max, "is he overpaid?" is close to
meaningless (the team had no cheaper option to sign him at). The useful
question is "among players on max deals, where does this one rank?" --
which this module supports by tagging the cohort so it can be ranked
separately.

TIERS PRODUCED

  Max          -- at or near the CBA maximum for their service tier
  Near-Max     -- 75-92% of their tier max; big-money non-max deals
  Mid-Level    -- roughly MLE range up through 75% of max
  Rookie Scale -- slotted rookie contracts (from contract_type)
  Minimum      -- at or near the league minimum
"""

import numpy as np
import pandas as pd

from config import (
    FIRST_APRON,
    MAX_CONTRACT_THRESHOLD,
    MAX_CONTRACT_TIERS,
    SALARY_CAP,
    SECOND_APRON,
    TAX_LINE,
)

# Approximate league minimum. Used only to separate "minimum contract"
# from "mid-level" for display purposes, so precision isn't critical.
_APPROX_MINIMUM = 0.019 * SALARY_CAP

# Lower bound of the Near-Max band, as a share of tier max.
_NEAR_MAX_FLOOR = 0.75


def max_share_for_experience(experience) -> float:
    """Share of the cap this player's max starting salary is worth,
    based on years of NBA service. Falls back to the 25% tier when
    experience is unknown (see scrapers/bref_draft.py -- undrafted
    players have no draft year to subtract from), which is the
    conservative choice: it sets a LOWER max bar, so we won't wrongly
    label someone as being at a max they aren't.
    """
    if experience is None or (isinstance(experience, float) and experience != experience):
        return MAX_CONTRACT_TIERS[0][1]
    for max_years, share in MAX_CONTRACT_TIERS:
        if experience <= max_years:
            return share
    return MAX_CONTRACT_TIERS[-1][1]


def add_contract_tiers(df: pd.DataFrame, salary_field: str = "cap_hit") -> pd.DataFrame:
    """Adds:

      max_salary_for_tier -- this player's approximate CBA maximum
      pct_of_max          -- cap hit as a share of that maximum
      is_max_contract     -- True if at/near the max
      salary_tier         -- Max / Near-Max / Mid-Level / Rookie Scale / Minimum
    """
    df = df.copy()

    experience = pd.to_numeric(df.get("experience"), errors="coerce")
    shares = experience.apply(max_share_for_experience)
    df["max_salary_for_tier"] = shares * SALARY_CAP

    cap_hit = pd.to_numeric(df[salary_field], errors="coerce")
    df["pct_of_max"] = np.where(
        df["max_salary_for_tier"] > 0, cap_hit / df["max_salary_for_tier"], np.nan
    )
    df["is_max_contract"] = df["pct_of_max"] >= MAX_CONTRACT_THRESHOLD

    is_rookie = df.get("contract_type", pd.Series(index=df.index, dtype=object)).eq("Rookie Scale")

    df["salary_tier"] = np.select(
        [
            cap_hit.isna(),
            df["pct_of_max"] >= MAX_CONTRACT_THRESHOLD,
            df["pct_of_max"] >= _NEAR_MAX_FLOOR,
            is_rookie,
            cap_hit <= _APPROX_MINIMUM * 1.15,
        ],
        ["Unknown", "Max", "Near-Max", "Rookie Scale", "Minimum"],
        default="Mid-Level",
    )

    return df


def rank_within_tier(df: pd.DataFrame, metric: str = "production_pctile") -> pd.DataFrame:
    """Adds `rank_in_salary_tier` -- where each player stands on `metric`
    among others in the same salary tier.

    This is the point of the whole module: comparing a max player to the
    league tells you little (of course he's well paid, he's a star), but
    comparing him to the other ~30 max players tells you whether his team
    is getting good value for a max slot.
    """
    df = df.copy()
    if metric not in df.columns or "salary_tier" not in df.columns:
        df["rank_in_salary_tier"] = np.nan
        return df

    values = pd.to_numeric(df[metric], errors="coerce")
    df["rank_in_salary_tier"] = (
        values.groupby(df["salary_tier"]).rank(ascending=False, method="min")
    )
    df["n_in_salary_tier"] = df.groupby("salary_tier")["salary_tier"].transform("size")
    return df


def team_payroll_summary(df: pd.DataFrame, salary_field: str = "cap_hit") -> pd.DataFrame:
    """Per-team payroll rollup against the cap, tax, and both apron lines.

    Descriptive only -- not used anywhere in the value model itself, just
    for the dashboard's Team Payroll section.

    IMPORTANT: groups by `team_contract`, NOT the `team` column everything
    else in this app uses. `team` comes from Basketball-Reference's
    ADVANCED STATS page and reflects who a player played for during the
    completed 2025-26 season. `cap_hit`, on the other hand, is a 2026-27
    figure -- Basketball-Reference's contracts page always reports the
    *upcoming* season's salary (see the season-pairing note in
    app/methodology_page.py). Those two columns agree for anyone who
    stayed put, but for anyone who changed teams this offseason, `team`
    is simply wrong for this purpose: their new salary would get
    attributed to their OLD team, and their new team would get no credit
    for it at all. `team_contract` comes from the live contracts page
    itself, which reports each player's CURRENT team as of when it was
    scraped -- the column that actually matches what `cap_hit` is
    measuring. Falls back to `team` only if `team_contract` is missing.

    Excludes free agents (no cap_hit on file at all).

    Real team cap sheets involve dead money, cap holds, and other line
    items this pipeline doesn't track -- treat totals as approximate,
    same spirit as the max-contract tiering above.
    """
    is_fa = (
        df["is_free_agent"]
        if "is_free_agent" in df.columns
        else pd.Series(False, index=df.index)
    )
    team_df = df[~is_fa].copy()

    if "team_contract" in team_df.columns:
        team_df["_team"] = team_df["team_contract"].where(
            team_df["team_contract"].notna(), team_df.get("team")
        )
    else:
        team_df["_team"] = team_df.get("team")

    team_df["_cap_hit"] = pd.to_numeric(team_df[salary_field], errors="coerce")
    team_df = team_df[team_df["_team"].notna() & team_df["_cap_hit"].notna()]

    if team_df.empty:
        return pd.DataFrame(
            columns=["team", "total_payroll", "players_on_cap", "apron_status"]
        )

    grouped = (
        team_df.groupby("_team")
        .agg(total_payroll=("_cap_hit", "sum"), players_on_cap=("_cap_hit", "count"))
        .reset_index()
        .rename(columns={"_team": "team"})
    )

    grouped["apron_status"] = np.select(
        [
            grouped["total_payroll"] > SECOND_APRON,
            grouped["total_payroll"] > FIRST_APRON,
            grouped["total_payroll"] > TAX_LINE,
            grouped["total_payroll"] > SALARY_CAP,
        ],
        ["Second Apron", "First Apron", "Tax", "Over Cap"],
        default="Under Cap",
    )

    return grouped.sort_values("total_payroll", ascending=False).reset_index(drop=True)
