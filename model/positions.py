"""
Collapses Basketball-Reference's position labels into three broad
groups -- Guard, Wing, Big -- for position-relative percentile ranking.

Why not use the raw PG/SG/SF/PF/C labels: they're noisy. Basketball-
Reference assigns a single primary position based on where a player
logged the most minutes, which routinely disagrees with how a team
actually uses someone, and the five-way split leaves thin pools (there
are far fewer true centers than guards, so a center's percentile is
computed against a much smaller and more variable group).

Three groups is the usual compromise in public analytics work: big
enough pools to be stable, granular enough that you aren't comparing a
point guard's rebounding to a center's.

DUAL-LISTING: players whose listed position straddles two groups (the
"GF" / "G-F" and "FC" / "F-C" style labels, plus hyphenated combos like
"SG-SF") belong to BOTH groups rather than being forced into one. A
combo forward genuinely should be measured against both wings and bigs
-- which comparison flatters them, and which exposes them, is itself
informative. Their position-relative percentile is the average of their
rank in each pool they belong to.
"""

import pandas as pd

GUARD = "Guard"
WING = "Wing"
BIG = "Big"

POSITION_GROUPS = [GUARD, WING, BIG]

# Numeric encoding for position_spectrum() below -- a single continuous
# "how big is this guy positionally" score, since regression models need a
# number, not the "Guard"/"Guard/Wing" style label position_group_label()
# produces for display.
_SPECTRUM_SCORE = {GUARD: 0.0, WING: 1.0, BIG: 2.0}

# Single positions -> one group.
_PRIMARY_MAP = {
    "PG": [GUARD],
    "SG": [GUARD],
    "G": [GUARD],
    "SF": [WING],
    "F": [WING],
    "PF": [BIG],
    "C": [BIG],
}

# Explicit combo labels -> two groups (the dual-listing cases).
_COMBO_MAP = {
    "GF": [GUARD, WING],
    "G-F": [GUARD, WING],
    "FG": [GUARD, WING],
    "F-G": [GUARD, WING],
    "FC": [WING, BIG],
    "F-C": [WING, BIG],
    "CF": [WING, BIG],
    "C-F": [WING, BIG],
}


def position_groups(pos) -> list:
    """Returns the list of position groups a player belongs to.

    Handles single positions ("PG"), explicit combos ("GF", "F-C"), and
    Basketball-Reference's hyphenated multi-position labels ("SG-SF",
    "PF-C"), which it emits for players who split time. Returns an empty
    list for missing/unrecognized input so callers can skip cleanly.
    """
    if pos is None or (isinstance(pos, float) and pos != pos):
        return []

    raw = str(pos).strip().upper()
    if not raw:
        return []

    if raw in _COMBO_MAP:
        return list(_COMBO_MAP[raw])
    if raw in _PRIMARY_MAP:
        return list(_PRIMARY_MAP[raw])

    # Hyphenated combos: map each side, then dedupe while preserving
    # the canonical Guard -> Wing -> Big ordering. "PF-C" collapses to
    # just [Big] since both sides land in the same group; "SG-SF"
    # correctly yields [Guard, Wing].
    if "-" in raw:
        found = set()
        for part in raw.split("-"):
            part = part.strip()
            for g in _PRIMARY_MAP.get(part, []):
                found.add(g)
        return [g for g in POSITION_GROUPS if g in found]

    return []


def position_spectrum(pos) -> float:
    """Numeric Guard(0) -> Wing(1) -> Big(2) score, averaged across groups
    for dual-listed combo positions (e.g. a G/F combo scores 0.5). NaN for
    missing/unrecognized position labels.

    Used as a $-estimator regression feature (model/dollar_estimate.py):
    positional scarcity affects pay in ways BPM/EPM/DARKO don't capture on
    their own, and this reuses the same Guard/Wing/Big grouping already
    used for position-relative percentiles rather than introducing a
    second, inconsistent position scheme.
    """
    groups = position_groups(pos)
    if not groups:
        return float("nan")
    return sum(_SPECTRUM_SCORE[g] for g in groups) / len(groups)


def position_group_label(pos) -> str:
    """Human-readable group label for display, e.g. "Guard" or
    "Guard/Wing" for dual-listed players. "--" if unknown.
    """
    groups = position_groups(pos)
    if not groups:
        return "--"
    return "/".join(groups)


def add_position_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Adds a `pos_group` display column ("Guard", "Guard/Wing", ...)."""
    df = df.copy()
    if "pos" not in df.columns:
        df["pos_group"] = "--"
        return df
    df["pos_group"] = df["pos"].apply(position_group_label)
    return df


def exploded_membership(df: pd.DataFrame) -> pd.DataFrame:
    """Long-format (row_index, group) frame -- one row per player per
    group they belong to, so dual-listed players appear twice. Used to
    compute within-group percentiles.
    """
    records = []
    for idx, pos in df["pos"].items():
        for group in position_groups(pos):
            records.append({"_row": idx, "pos_group_single": group})
    return pd.DataFrame(records, columns=["_row", "pos_group_single"])
