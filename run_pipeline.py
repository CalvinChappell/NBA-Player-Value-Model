"""
End-to-end pipeline: scrape -> merge -> percentiles -> value score ->
$ estimate -> write outputs/player_value_model.csv (+ .xlsx).

Run from the project root:
    python run_pipeline.py

First run will be slow (scraping + a rate limiter that waits a few
seconds between Basketball-Reference requests). After that,
config.USE_CACHE=True means re-runs reuse the cached HTML instantly --
delete data/cache/*.html (or flip USE_CACHE off) to force a refresh.

player_value_model.csv is the FULL data -- every raw stat plus every
_pctile column -- because the Streamlit app (and the player page's
percentile bars specifically) needs all of it. If you just want a clean
file to hand someone, use player_value_model_summary.csv instead: same
data, trimmed to the columns in SUMMARY_COLUMNS below.
"""

import pandas as pd

from config import OUTPUT_DIR, SEASON_END_YEAR
from model import contracts, dollar_estimate, merge, percentiles, value_metrics, value_score
from scrapers import external_metrics

SUMMARY_COLUMNS = [
    "player",
    "team",
    "pos",
    "pos_group",
    "AGE",
    "experience",
    "experience_is_estimated",
    "contract_type",
    "GP",
    "MP",
    "PPG",
    "RPG",
    "APG",
    "SPG",
    "BPG",
    "FG_PCT",
    "FG3_PCT",
    "FT_PCT",
    "OBPM",
    "DBPM",
    "BPM",
    "EPM",
    "DARKO",
    "LEBRON",
    "OnBall_Pct",
    "rTS_rel",
    "RAPM_3Y",
    "PVAL",
    "NET_ON_OFF",
    "FTr",
    "FTA_total",
    "FTA_per36",
    "FoulDraw_Value",
    "FG_PCT_rim",
    "FGA_share_rim",
    "rim_FGA_total",
    "rim_FGA_per36",
    "Rim_Scoring_Value",
    "production_pctile",
    "n_production_metrics_available",
    "cap_hit",
    "salary_pctile",
    "value_score",
    "value_ratio",
    "estimated_market_value",
    "estimated_market_value_low",
    "estimated_market_value_high",
    "estimated_market_value_inner_low",
    "estimated_market_value_inner_high",
    "market_value_surplus",
    "market_value_verdict",
    "estimate_confidence",
    "estimate_rel_width",
    "salary_tier",
    "pct_of_max",
    "is_max_contract",
    "rank_in_salary_tier",
    "n_in_salary_tier",
    "years_remaining",
    "total_guaranteed",
    "bird_rights_status",
]


def main():
    external_metrics.write_templates()  # make sure blank templates exist for first-time users

    df = merge.build_master_table(SEASON_END_YEAR)
    # Composite value metrics (Foul-Drawing Value etc) are computed before
    # add_percentiles so that they can themselves be percentile-ranked --
    # each one is a 0-100 score that gets its own bar on the player page.
    df = value_metrics.add_value_metrics(df)
    df = percentiles.add_percentiles(df)
    df = value_score.add_value_score(df)

    try:
        df = dollar_estimate.add_market_value_estimate(df)
    except RuntimeError as exc:
        print(f"(skipping $-estimator: {exc})")
        for col in (
            "estimated_market_value",
            "estimated_market_value_low",
            "estimated_market_value_high",
            "estimated_market_value_inner_low",
            "estimated_market_value_inner_high",
            "market_value_surplus",
            "estimate_rel_width",
        ):
            df[col] = pd.NA
        df["market_value_verdict"] = "Unknown"
        df["estimate_confidence"] = "Unknown"

    # Percentile versions of the derived metrics (value score, market value
    # surplus, estimated market value) -- these only exist after the steps
    # above run, so they can't be computed inside percentiles.add_percentiles.
    # Used for the three headline bars at the top of the player page.
    # Salary tiers (Max / Near-Max / Mid-Level / Rookie Scale / Minimum)
    # and within-tier ranking. Max players are bunched against the CBA
    # ceiling, so ranking them against the whole league is uninformative
    # -- see model/contracts.py.
    df = contracts.add_contract_tiers(df)
    df = contracts.rank_within_tier(df, metric="production_pctile")

    df["value_score_pctile"] = percentiles.pct_rank(df["value_score"])
    df["market_value_surplus_pctile"] = percentiles.pct_rank(df["market_value_surplus"])
    df["estimated_market_value_pctile"] = percentiles.pct_rank(df["estimated_market_value"])

    missing = merge.unmatched_report(df)
    if not missing.empty:
        print(f"\n{len(missing)} players scraped from advanced stats had no contract match.")
        print("(Usually a name-spelling mismatch -- see utils/name_match.py.) Top by minutes:")
        print(missing.head(15).to_string())

    df = df.sort_values("value_score", ascending=False)

    csv_path = OUTPUT_DIR / "player_value_model.csv"
    summary_csv_path = OUTPUT_DIR / "player_value_model_summary.csv"
    summary_xlsx_path = OUTPUT_DIR / "player_value_model_summary.xlsx"

    # Full data -- everything, including every *_pctile column -- is what
    # the Streamlit app reads.
    df.to_csv(csv_path, index=False)

    # Curated, human-readable subset for sharing/emailing.
    cols_present = [c for c in SUMMARY_COLUMNS if c in df.columns]
    df[cols_present].to_csv(summary_csv_path, index=False)
    df[cols_present].to_excel(summary_xlsx_path, index=False)

    print(f"\nWrote {csv_path} (full data, used by the dashboard)")
    print(f"Wrote {summary_csv_path} / {summary_xlsx_path} (curated subset for sharing)")
    print(f"\nTop 10 by value score:")
    print(df[["player", "team", "contract_type", "value_score", "cap_hit"]].head(10).to_string())


if __name__ == "__main__":
    main()
