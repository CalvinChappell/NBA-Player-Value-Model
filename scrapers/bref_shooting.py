"""
Scrapes Basketball-Reference's season Shooting table:
https://www.basketball-reference.com/leagues/NBA_{year}_shooting.html

This is the shot-distance breakdown: what share of a player's field goal
attempts come from each distance band, and how well they shoot from each.
Distance bands are 0-3 ft (the rim), 3-10, 10-16, 16 ft to the three
point line, and threes.

Two things this feeds:

1. Rim Scoring Value (model/value_metrics.py) -- 0-3 ft FG% crossed with
   0-3 ft attempt volume.
2. The zone-based shot chart on the player page, which needs the same
   per-band shares.

Note on the table's HTML: Basketball-Reference nests this one under
multi-level headers, and (like several of their tables) serves it inside
an HTML comment. scrapers/http.strip_comments handles the latter. Rather
than trusting the table's id attribute -- which has bitten us before on
the contracts and advanced pages -- we find the table by looking for a
cell we know must exist: data-stat="fg_pct_00_03".
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name

_AGGREGATE_TEAM_PATTERN = re.compile(r"^(TOT|\d+TM)$")

# data-stat -> our column name. The "pct_fga_*" columns are the SHARE of
# a player's attempts from that band (0-1), not attempt counts; actual
# counts have to be derived from total FGA (see model/value_metrics.py).
_FIELDS = {
    "avg_dist_fga": "avg_shot_dist",
    "fg_pct_00_03": "FG_PCT_rim",
    "fg_pct_03_10": "FG_PCT_short",
    "fg_pct_10_16": "FG_PCT_mid",
    "fg_pct_16_xx": "FG_PCT_long_two",
    "pct_fga_00_03": "FGA_share_rim",
    "pct_fga_03_10": "FGA_share_short",
    "pct_fga_10_16": "FGA_share_mid",
    "pct_fga_16_xx": "FGA_share_long_two",
    "pct_fga_fg3a": "FGA_share_three",
}


def scrape_shooting_stats(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_shooting.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = None
    for candidate in soup.find_all("table"):
        if candidate.find("td", {"data-stat": "fg_pct_00_03"}):
            table = candidate
            break

    if table is None:
        raise RuntimeError(
            f"Could not find the shooting table at {url} (no cell with "
            "data-stat='fg_pct_00_03'). Basketball-Reference may have renamed "
            "these stats -- inspect the cached HTML in data/cache/."
        )

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue

        player_cell = tr.find("td", {"data-stat": "name_display"}) or tr.find(
            "td", {"data-stat": "player"}
        )
        if player_cell is None:
            continue

        def stat(name, default=None):
            cell = tr.find("td", {"data-stat": name})
            return cell.get_text(strip=True) if cell is not None else default

        record = {
            "player": player_cell.get_text(strip=True),
            "team": stat("team_id") or stat("team_name_abbr"),
        }
        for data_stat, col in _FIELDS.items():
            record[col] = stat(data_stat)
        rows.append(record)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Parsed zero rows from the shooting table -- check the cached HTML.")

    for col in _FIELDS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Same multi-team dedup as the other bref scrapers: keep the season
    # aggregate row for traded players, drop the per-team splits.
    df["_is_aggregate"] = df["team"].fillna("").str.upper().str.match(_AGGREGATE_TEAM_PATTERN)
    df["name_key"] = df["player"].apply(normalize_name)
    df = df.sort_values("_is_aggregate", ascending=False)
    df = df.drop_duplicates(subset=["name_key"], keep="first")
    df = df.drop(columns=["_is_aggregate", "team", "player"])

    return df.reset_index(drop=True)


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_shooting_stats(SEASON_END_YEAR)
    print(out.head(15).to_string())
    print(f"\n{len(out)} players parsed.")
