"""
Loader for the "premium" all-in-one metrics: EPM (dunksandthrees.com),
DARKO (apanalytics), and LEBRON (bball-index.com).

Why these aren't auto-scraped: all three sites render their player
tables client-side (React/Shiny) with virtualized scrolling, and two of
the three gate full-league data behind a paid subscription. There's no
stable public API to hit. Trying to scrape them with a headless browser
would be brittle and likely to break the moment they ship a front-end
change -- not something worth building "vibes-first" into a model you
want to trust.

Instead: export or copy the player table from each site into a CSV with
two columns, `player` and the metric name, and drop it in
data/manual/. Templates are provided -- just overwrite them with real
data. Anything you don't have yet is skipped gracefully; the pipeline
still runs with whatever subset of metrics you've collected.
"""

import pandas as pd

from config import MANUAL_DIR
from utils.name_match import normalize_name

_SOURCES = {
    "EPM": ("epm.csv", "EPM"),
    "DARKO": ("darko.csv", "DARKO"),
    "LEBRON": ("lebron.csv", "LEBRON"),
}


def load_manual_metric(metric_key: str) -> pd.DataFrame:
    """Returns a DataFrame with columns [name_key, <metric_key>], or an
    empty DataFrame (with those columns) if the file doesn't exist yet.
    """
    filename, col = _SOURCES[metric_key]
    path = MANUAL_DIR / filename
    if not path.exists():
        return pd.DataFrame(columns=["name_key", metric_key])

    df = pd.read_csv(path)
    if "player" not in df.columns or col not in df.columns:
        raise ValueError(
            f"{path} must have columns 'player' and '{col}'. Found: {list(df.columns)}"
        )
    df["name_key"] = df["player"].apply(normalize_name)
    df[metric_key] = pd.to_numeric(df[col], errors="coerce")
    return df[["name_key", metric_key]]


def load_all_manual_metrics() -> pd.DataFrame:
    """Outer-joins whatever manual metric files exist into one frame keyed
    by name_key. Safe to call even if zero files exist yet.
    """
    merged = None
    for metric_key in _SOURCES:
        df = load_manual_metric(metric_key)
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on="name_key", how="outer")
    return merged if merged is not None else pd.DataFrame(columns=["name_key"])


# ---------------------------------------------------------------------------
# databallr.com playstyle/impact metrics: OnBall%, rTS% (relative true
# shooting), 3Y RAPM, PVAL (Possession Value RAPM), and Net On/Off. Unlike
# EPM/DARKO/LEBRON above, this one file carries five metrics at once (see
# data/manual/databallr_metrics.csv), pulled via browser extraction since
# databallr's API requires a signed request. Free account, no subscription
# gate -- see README for how to refresh this file.
# ---------------------------------------------------------------------------

_DATABALLR_FILE = "databallr_metrics.csv"
_DATABALLR_METRICS = ["OnBall_Pct", "rTS_rel", "RAPM_3Y", "PVAL", "NET_ON_OFF"]


def load_databallr_metrics() -> pd.DataFrame:
    """Returns a DataFrame with columns [name_key, OnBall_Pct, rTS_rel,
    RAPM_3Y, PVAL, NET_ON_OFF], or an empty DataFrame (with those columns)
    if the file doesn't exist yet.
    """
    path = MANUAL_DIR / _DATABALLR_FILE
    if not path.exists():
        return pd.DataFrame(columns=["name_key"] + _DATABALLR_METRICS)

    df = pd.read_csv(path)
    missing = [c for c in ["player"] + _DATABALLR_METRICS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing expected columns: {missing}")

    df["name_key"] = df["player"].apply(normalize_name)
    for col in _DATABALLR_METRICS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["name_key"] + _DATABALLR_METRICS]


def write_templates():
    """Writes starter CSV templates into data/manual/ if they don't
    already exist, so it's obvious what format to paste data into.
    """
    for metric_key, (filename, col) in _SOURCES.items():
        path = MANUAL_DIR / filename
        if path.exists():
            continue
        pd.DataFrame(
            {
                "player": ["Nikola Jokic", "Victor Wembanyama"],
                col: [9.8, 7.5],
            }
        ).to_csv(path, index=False)


if __name__ == "__main__":
    write_templates()
    print(f"Templates written to {MANUAL_DIR}")
    print(load_all_manual_metrics())
