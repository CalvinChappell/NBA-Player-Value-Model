"""
One-off diagnostic for the two methodology fixes made to model/dollar_estimate.py
and model/value_score.py (rookie-scale age/experience bias in the $-estimator,
and the Value Score top-of-market compression that let Baylor Scheierman
out-score Victor Wembanyama).

Run AFTER `python3 run_pipeline.py` has produced a fresh
outputs/player_value_model.csv (this needs sklearn, which isn't available in
every environment -- run it in the same venv you ran the pipeline in).

    python3 run_pipeline.py
    python3 diagnose_value_fixes.py

What to look for:
  1. Rookie-scale stars (Wembanyama, Holmgren, Jalen Williams) should now show
     estimated_market_value much closer to -- or above -- their actual cap
     hit, given how elite their production percentiles are. Pre-fix, all
     three showed estimated_market_value BELOW $13M despite 87th-99th
     percentile production, because the model was extrapolating "young +
     low experience -> cheap" from a training pool that excludes every young
     player good enough to still be under this same effect.
  2. Wembanyama's value_score should now clearly exceed Baylor Scheierman's
     (pre-fix: Scheierman 32.2 > Wembanyama 26.5, which is the bug Calvin
     flagged -- a 99.8th-percentile producer should not score below a
     53.9th-percentile one).
  3. Scottie Barnes (a real Veteran, not Rookie Scale, so untouched by fix
     #1) should look about the same as before -- a useful control to confirm
     the fixes didn't just move the "who's underpaid" problem around.
  4. The $-estimator's printed holdout R^2 / coverage (from run_pipeline.py's
     own console output) shouldn't have moved much from the age/experience
     fix alone -- that one only changes what gets FED to the model at
     prediction time for Rookie Scale rows, it doesn't change training.
  5. NEW (Tier 1 features -- GS_PCT, pos_spectrum, draft_pick_filled): R^2
     SHOULD move now, since these add real training signal. Check the
     "Feature importances" printout in run_pipeline.py's console output --
     GS_PCT and draft_pick_filled should show up with non-trivial weight if
     they're pulling their weight. If R^2 barely moves, that's a real
     result too (means role/pedigree don't explain much beyond what
     production/age/experience already captured) -- not a sign anything's
     broken.
"""

import pandas as pd

from config import OUTPUT_DIR

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

CSV_PATH = OUTPUT_DIR / "player_value_model.csv"

WATCH_LIST = [
    "Victor Wembanyama",
    "Chet Holmgren",
    "Jalen Williams",
    "Baylor Scheierman",
    "Scottie Barnes",
]

COLS = [
    "player", "team_contract", "AGE", "experience", "contract_type",
    "cap_hit", "production_pctile", "estimated_market_value",
    "market_value_surplus", "market_value_verdict",
    "salary_pctile", "pay_vs_value_ratio", "pay_vs_value_pctile", "value_score",
]


def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"{CSV_PATH} not found -- run `python3 run_pipeline.py` first.")

    df = pd.read_csv(CSV_PATH)

    missing_cols = [c for c in COLS if c not in df.columns]
    if missing_cols:
        print(f"WARNING: expected columns missing from the output: {missing_cols}")
        print("(pay_vs_value_ratio / pay_vs_value_pctile are new -- if they're missing, "
              "the pipeline ran the OLD code, not the fixed version.)\n")

    cols_present = [c for c in COLS if c in df.columns]

    print("=" * 100)
    print("WATCH LIST -- rookie-scale stars + one veteran control (Scottie Barnes)")
    print("=" * 100)
    watch = df[df["player"].isin(WATCH_LIST)][cols_present]
    print(watch.to_string(index=False))

    wemby = df[df["player"] == "Victor Wembanyama"]
    scheierman = df[df["player"] == "Baylor Scheierman"]
    if not wemby.empty and not scheierman.empty:
        wv = wemby["value_score"].iloc[0]
        sv = scheierman["value_score"].iloc[0]
        print(f"\nWembanyama value_score = {wv:.1f}, Scheierman value_score = {sv:.1f} "
              f"-> {'FIXED (Wemby now ahead)' if wv > sv else 'STILL BROKEN (Scheierman still ahead)'}")

    print("\n" + "=" * 100)
    print("TOP 15 BY VALUE SCORE (eyeball check -- should be believable bargains, not noise)")
    print("=" * 100)
    top = df.sort_values("value_score", ascending=False).head(15)[cols_present]
    print(top.to_string(index=False))

    print("\n" + "=" * 100)
    print("BOTTOM 15 BY VALUE SCORE (eyeball check -- should be believable overpays, not noise)")
    print("=" * 100)
    bottom = df.sort_values("value_score", ascending=True).head(15)[cols_present]
    print(bottom.to_string(index=False))

    if "contract_type" in df.columns:
        print("\n" + "=" * 100)
        print("ROOKIE SCALE estimated_market_value vs cap_hit (all of them, sorted by production)")
        print("=" * 100)
        rookies = df[df["contract_type"] == "Rookie Scale"].sort_values(
            "production_pctile", ascending=False
        )[cols_present]
        print(rookies.head(25).to_string(index=False))

        # app/streamlit_app.py currently excludes Rookie Scale players from
        # the "Biggest surplus"/"Biggest overpay" headline metrics as a
        # workaround for the bias fixed here. If elite rookie-scale
        # producers now show believable (likely large positive) surplus
        # numbers rather than the pre-fix nonsense, that workaround can
        # probably come out -- see the comment above `under = headline_pool[...]`
        # in streamlit_app.py.
        elite_rookies = rookies[rookies["production_pctile"] >= 85]
        if not elite_rookies.empty:
            print("\nElite (85th+ pctile production) Rookie Scale players -- market_value_surplus "
                  "should now read as a large POSITIVE bargain, not a large negative 'overpaid':")
            print(elite_rookies[["player", "production_pctile", "cap_hit", "estimated_market_value",
                                  "market_value_surplus", "market_value_verdict"]].to_string(index=False))


if __name__ == "__main__":
    main()
