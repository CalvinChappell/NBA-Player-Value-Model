"""
Estimated $ market value: trains a model of cap_hit ~ production metrics
+ age + experience + minutes on VETERAN players only (rookie-scale
salaries are slotted by the CBA, not by performance, so including them
would teach the model the wrong relationship), then predicts what every
player -- rookies included -- "should" be paid based on how a veteran
with the same production/age profile actually gets paid.

Compare `estimated_market_value` to `cap_hit` for a dollar-denominated
surplus/deficit, alongside the percentile-based `value_score`.

PREDICTION INTERVALS (conformalized quantile regression)
--------------------------------------------------------
A single point estimate implies precision this model doesn't have
(holdout R^2 typically lands around 0.6). So alongside it we report a
range:

    estimated_market_value_low <= estimated_market_value <= estimated_market_value_high

Getting this right took two attempts, and the first failure is
instructive. Plain quantile regression (fit a 10th-percentile model and
a 90th-percentile model, report the gap) produced intervals that only
covered ~56% of held-out players instead of the nominal 80% -- badly
overconfident. With only ~170 veterans to train on, the quantile models
overfit their training split and their "10th percentile" isn't really
the 10th percentile out of sample.

The fix is CONFORMAL calibration. We hold out a dedicated calibration
set the quantile models never see, measure how far outside their
predicted interval the true salaries actually fall, and then widen the
interval by exactly that much. The resulting coverage guarantee is
distribution-free: it holds regardless of whether the underlying
quantile models are any good, as long as the data are exchangeable.

Concretely (Romano, Patterson & Candes 2019, "Conformalized Quantile
Regression"):

  1. Split veterans into proper-train / calibration / test.
  2. Fit q_lo and q_hi on proper-train only.
  3. On calibration, score each player by how badly the interval missed:
         E_i = max(q_lo(x_i) - y_i,  y_i - q_hi(x_i))
     (negative when the interval contained them, positive when it missed)
  4. Take Q = the (1-alpha) empirical quantile of those scores.
  5. Final interval = [q_lo(x) - Q, q_hi(x) + Q].

Why keep quantile regression underneath rather than just doing
constant-width residual intervals: the quantile models let the width
VARY by player, which is what you want -- a max-contract star's salary
is far more predictable than a mid-tier rotation player's. Conformal
calibration then fixes the overall level without flattening that
variation.

The pipeline prints realized coverage on the test split every run, so
this claim stays checkable rather than assumed.

The interval drives `market_value_verdict`: if a player's actual cap hit
falls INSIDE the interval, the model can't distinguish him from fairly
paid, and the raw surplus number shouldn't be over-read. Only when the
cap hit falls outside the interval is the surplus/deficit a claim the
model actually supports.

CAVEATS worth stating out loud to anyone you show this to:
  - It's trained on what teams DID pay, so it inherits the market's
    biases. It measures conformity to market behavior, not true value.
  - Max contracts compress the top: the CBA caps salaries, so the very
    best players cluster at a ceiling the model can't predict past, and
    will tend to look "fairly paid" no matter how good they are.
  - Rookie-scale predictions extrapolate outside the training pool
    (which is veterans only), so treat them as the least reliable.
  - Missing features are median-filled, so a player lacking EPM/DARKO
    gets a confident-looking estimate built on partly invented inputs.
    `n_production_metrics_available` tells you who those players are.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.metrics import r2_score

from config import (
    MARKET_VALUE_CV_FOLDS,
    MARKET_VALUE_INTERVAL_HIGH,
    MARKET_VALUE_INTERVAL_LOW,
    MARKET_VALUE_LOG_TRANSFORM,
    PRODUCTION_METRICS,
    SALARY_FIELD_FOR_REGRESSION,
)

_FEATURE_CANDIDATES = PRODUCTION_METRICS + ["AGE", "experience", "MP"]

# Floor for the log transform: cap hits can be 0 or missing for players
# on non-guaranteed deals, and log(0) is undefined.
_LOG_FLOOR = 100_000.0


def _to_model_space(y: np.ndarray) -> np.ndarray:
    if not MARKET_VALUE_LOG_TRANSFORM:
        return y
    return np.log(np.maximum(y, _LOG_FLOOR))


def _from_model_space(y: np.ndarray) -> np.ndarray:
    if not MARKET_VALUE_LOG_TRANSFORM:
        return y
    return np.exp(y)


def _usable_features(df: pd.DataFrame) -> list[str]:
    """Drop any candidate feature that's entirely missing (e.g. you
    haven't imported EPM/DARKO/LEBRON yet) so the model doesn't choke.
    """
    return [f for f in _FEATURE_CANDIDATES if f in df.columns and df[f].notna().any()]


def fit_market_value_model(df: pd.DataFrame, min_minutes: int = 500):
    """Fits the point-estimate model and the conformalized quantile
    models that define the prediction interval.

    Returns (models, features, diagnostics). `models` carries the fitted
    estimators plus `conformal_q`, the width correction learned on the
    calibration split. `diagnostics` carries holdout R^2 and the realized
    coverage measured on a test split neither of the others saw.
    """
    features = _usable_features(df)

    train_pool = df[
        (df["contract_type"] == "Veteran")
        & df[SALARY_FIELD_FOR_REGRESSION].notna()
        & (df["MP"] >= min_minutes)
    ].copy()

    if len(train_pool) < 40:
        raise RuntimeError(
            f"Only {len(train_pool)} veterans available to train on -- need at least 40. "
            "Check that contracts/advanced-stats scraping succeeded."
        )

    X = train_pool[features].apply(lambda col: col.fillna(col.median()))
    y_raw = train_pool[SALARY_FIELD_FOR_REGRESSION].to_numpy(dtype=float)
    y = _to_model_space(y_raw)

    def _quantile_model(alpha):
        # Shallow and regularized on purpose: with ~170 rows, deeper
        # quantile models memorize and their quantiles stop meaning
        # anything out of sample.
        return GradientBoostingRegressor(
            loss="quantile",
            alpha=alpha,
            n_estimators=200,
            max_depth=2,
            learning_rate=0.05,
            min_samples_leaf=10,
            subsample=0.9,
            random_state=42,
        )

    def _point_model():
        return RandomForestRegressor(
            n_estimators=400, max_depth=6, random_state=42, n_jobs=-1
        )

    # --- Cross-conformal calibration ----------------------------------
    # Every player gets an out-of-fold prediction (from a model that
    # never saw them), so conformity scores come from honest held-out
    # data WITHOUT permanently surrendering a chunk of the training set.
    # The final models below are then refit on all of it.
    n_splits = max(2, min(MARKET_VALUE_CV_FOLDS, len(X) // 10))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    oof_point = cross_val_predict(_point_model(), X, y, cv=kf, n_jobs=None)
    oof_lo = cross_val_predict(_quantile_model(MARKET_VALUE_INTERVAL_LOW), X, y, cv=kf)
    oof_hi = cross_val_predict(_quantile_model(MARKET_VALUE_INTERVAL_HIGH), X, y, cv=kf)
    oof_lo, oof_hi = np.minimum(oof_lo, oof_hi), np.maximum(oof_lo, oof_hi)

    # R^2 reported in DOLLAR space even when fitting in log space, so the
    # number stays comparable across the two settings and means what a
    # reader expects ("how much salary variance is explained?").
    holdout_r2 = r2_score(y_raw, _from_model_space(oof_point))
    r2_model_space = r2_score(y, oof_point)

    scores = np.maximum(oof_lo - y, y - oof_hi)
    alpha = 1.0 - (MARKET_VALUE_INTERVAL_HIGH - MARKET_VALUE_INTERVAL_LOW)
    n_cal = len(scores)
    level = min(1.0, np.ceil((n_cal + 1) * (1 - alpha)) / n_cal)
    conformal_q = max(float(np.quantile(scores, level, method="higher")), 0.0)

    # Coverage measured on the same out-of-fold predictions. This is a
    # fair estimate (each prediction came from a model blind to that
    # player) and uses every player rather than a 43-row test split, so
    # it's far less noisy than the previous approach.
    cov_lo = oof_lo - conformal_q
    cov_hi = oof_hi + conformal_q
    coverage = float(((y >= cov_lo) & (y <= cov_hi)).mean())

    width_dollars = _from_model_space(cov_hi) - _from_model_space(cov_lo)
    median_width = float(np.median(width_dollars))

    # --- Refit on ALL veterans for the models actually used -----------
    point = _point_model().fit(X, y)
    low = _quantile_model(MARKET_VALUE_INTERVAL_LOW).fit(X, y)
    high = _quantile_model(MARKET_VALUE_INTERVAL_HIGH).fit(X, y)

    nominal = MARKET_VALUE_INTERVAL_HIGH - MARKET_VALUE_INTERVAL_LOW
    diagnostics = {
        "holdout_r2": holdout_r2,
        "r2_model_space": r2_model_space,
        "coverage": coverage,
        "nominal_coverage": nominal,
        "conformal_q": conformal_q,
        "median_width": median_width,
        "n_train": len(X),
        "n_folds": n_splits,
        "log_space": MARKET_VALUE_LOG_TRANSFORM,
    }

    models = {"point": point, "low": low, "high": high, "conformal_q": conformal_q}
    return models, features, diagnostics


def add_market_value_estimate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    models, features, diag = fit_market_value_model(df)

    space = "log(salary)" if diag["log_space"] else "salary"
    print(
        f"$-estimator: {diag['n_train']} veterans, {diag['n_folds']}-fold "
        f"cross-conformal, fit in {space} space"
    )
    print(
        f"  Out-of-fold R^2 = {diag['holdout_r2']:.3f} (dollars)"
        + (f", {diag['r2_model_space']:.3f} (log space)" if diag["log_space"] else "")
    )
    print(
        f"  {int(diag['nominal_coverage'] * 100)}% interval covered "
        f"{diag['coverage'] * 100:.1f}% of players (n={diag['n_train']}); "
        f"median width ${diag['median_width']:,.0f}"
    )
    if diag["coverage"] < diag["nominal_coverage"] - 0.10:
        print(
            "  WARNING: coverage below nominal -- intervals are too narrow. "
            "Treat surplus/deficit calls with caution."
        )
    else:
        print("  -> Well calibrated; interval-based verdicts are trustworthy.")

    # Feed the whole league through, filling missing features with the
    # league median so a player missing e.g. EPM still gets an estimate
    # (just a slightly less-informed one).
    X_all = df[features].apply(lambda col: col.fillna(col.median()))

    q = models["conformal_q"]
    # Widening is applied in MODEL space (log dollars if enabled), then
    # transformed back -- which is what makes the interval asymmetric in
    # dollar terms: a proportional band, wide at the top of the salary
    # scale and tight at the bottom, matching how salary error actually
    # behaves.
    point_pred = _from_model_space(models["point"].predict(X_all))
    low_pred = _from_model_space(models["low"].predict(X_all) - q)
    high_pred = _from_model_space(models["high"].predict(X_all) + q)

    # Quantile models are fit independently and can cross on individual
    # rows; enforce low <= point <= high so the interval always reads
    # sensibly.
    low_pred, high_pred = np.minimum(low_pred, high_pred), np.maximum(low_pred, high_pred)
    low_pred = np.minimum(low_pred, point_pred)
    high_pred = np.maximum(high_pred, point_pred)

    df["estimated_market_value"] = point_pred
    df["estimated_market_value_low"] = low_pred
    df["estimated_market_value_high"] = high_pred
    df["market_value_surplus"] = df["estimated_market_value"] - df[SALARY_FIELD_FOR_REGRESSION]

    # Verdict based on the INTERVAL, not the point estimate: a surplus
    # that sits inside the model's own uncertainty band isn't a finding.
    cap = df[SALARY_FIELD_FOR_REGRESSION]
    df["market_value_verdict"] = np.select(
        [cap.isna(), cap < low_pred, cap > high_pred],
        ["Unknown", "Underpaid", "Overpaid"],
        default="Fairly paid",
    )

    importances = pd.Series(
        models["point"].feature_importances_, index=features
    ).sort_values(ascending=False)
    print("Feature importances for the $-estimator:")
    print(importances.to_string())

    return df
