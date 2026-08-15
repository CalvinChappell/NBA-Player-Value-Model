"""
Name normalization so we can join players across sources that spell/format
names differently (accents, suffixes, "Jr.", periods, etc).

Basketball-Reference is the backbone of this pipeline, so every other
source (EPM, DARKO, LEBRON, manual overrides) gets joined onto it by
normalized name. If you get an unexpected number of unmatched players
after merging, print merge.unmatched_report() to see who didn't line up
and fix the spelling in the source CSV.
"""

import re
from unidecode import unidecode

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = unidecode(name)  # strip accents: Doncic, Jokic, Sabonis, etc.
    name = name.lower().strip()
    name = re.sub(r"[.'`]", "", name)  # drop periods/apostrophes
    name = re.sub(r"[-_]", " ", name)
    name = re.sub(r"\s+", " ", name)
    tokens = [t for t in name.split(" ") if t not in _SUFFIXES]
    return " ".join(tokens)
