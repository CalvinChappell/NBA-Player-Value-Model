"""
Builds the PUBLIC version of the model output for deployment.

WHY THIS EXISTS

The deployed app can't scrape on every page load (Basketball-Reference
would rate-limit a shared cloud IP, and it'd be slow), so it reads a
committed CSV instead. But the full output contains raw metric values
from third-party sources with real access restrictions:

  - EPM      (dunksandthrees.com -- full-league data is subscription-gated)
  - DARKO    (apanalytics -- R Shiny app, no public API)
  - LEBRON   (bball-index.com -- subscriber-only)
  - OnBall%, rTS%, 3Y RAPM, PVAL, Net On/Off (databallr.com -- the
    site's API requires a signed request)

Using those locally for personal research is one thing. Committing the
full league's values to a public GitHub repo is republishing someone
else's dataset, which is a different act.

WHAT THIS SCRIPT DOES

Strips the raw values from those sources while KEEPING the percentile
ranks derived from them. A percentile is a relative summary, not the
underlying data -- you can see that a player is in the 88th percentile
for EPM without the repo handing anyone dunksandthrees' actual numbers.

Everything sourced from Basketball-Reference (freely accessible: BPM,
box score, shooting splits, contracts) and everything computed here
(Value Score, market value estimates, Rim Scoring Value, Foul-Drawing
Value) stays intact. So the deployed app looks and behaves the same --
the percentile bars still render, the composite scores are unchanged --
it just doesn't ship the gated source data.

USAGE

    python run_pipeline.py        # builds the full local CSV
    python make_public_data.py    # builds the public CSV to commit

The app prefers the full file when it's present (your machine) and falls
back to the public one (deployed), so you keep the complete view locally
without any config switching.
"""

import pandas as pd

from config import OUTPUT_DIR

# Raw values from gated/third-party sources. Their `_pctile` companions
# are deliberately NOT listed here -- those are kept.
RESTRICTED_RAW_COLUMNS = [
    # Manual imports (EPM / DARKO / LEBRON)
    "EPM",
    "DARKO",
    "LEBRON",
    # databallr.com playstyle + impact metrics
    "OnBall_Pct",
    "rTS_rel",
    "RAPM_3Y",
    "PVAL",
    "NET_ON_OFF",
]

FULL_PATH = OUTPUT_DIR / "player_value_model.csv"
PUBLIC_PATH = OUTPUT_DIR / "player_value_model_public.csv"


def build_public_csv() -> pd.DataFrame:
    if not FULL_PATH.exists():
        raise SystemExit(
            f"{FULL_PATH} not found. Run `python run_pipeline.py` first."
        )

    df = pd.read_csv(FULL_PATH)
    dropped = [c for c in RESTRICTED_RAW_COLUMNS if c in df.columns]
    kept_pctiles = [f"{c}_pctile" for c in dropped if f"{c}_pctile" in df.columns]

    public = df.drop(columns=dropped)
    public.to_csv(PUBLIC_PATH, index=False)

    print(f"Wrote {PUBLIC_PATH}")
    print(f"  {len(public)} rows, {len(public.columns)} columns")
    print(f"  Dropped {len(dropped)} restricted raw columns: {', '.join(dropped)}")
    print(f"  Kept {len(kept_pctiles)} derived percentile columns: {', '.join(kept_pctiles)}")
    print()
    print("Commit outputs/player_value_model_public.csv; keep the full CSV local.")
    return public


if __name__ == "__main__":
    build_public_csv()
