"""
Scrapes Basketball-Reference's draft pages for the last several classes:
https://www.basketball-reference.com/draft/NBA_{year}.html

Basketball-Reference doesn't publish a clean "years of NBA experience"
column anywhere, so we approximate it: pull draft year + pick for every
player drafted in roughly the rookie-scale window, and compute
experience = season_end_year - draft_year.

Undrafted players (two-way signees, G League call-ups, international
free agents) simply won't appear here and will fall back to being
treated as veterans -- correct them in
data/manual/contract_overrides.csv if that matters for your analysis.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name


def scrape_draft_class(draft_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/draft/NBA_{draft_year}.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", {"id": "stats"})
    if table is None:
        return pd.DataFrame(columns=["player", "draft_year", "draft_pick", "name_key"])

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue
        player_cell = tr.find("td", {"data-stat": "player"})
        pick_cell = tr.find("td", {"data-stat": "pick_overall"}) or tr.find(
            "th", {"data-stat": "pick_overall"}
        )
        if player_cell is None:
            continue
        rows.append(
            {
                "player": player_cell.get_text(strip=True),
                "draft_year": draft_year,
                "draft_pick": pick_cell.get_text(strip=True) if pick_cell is not None else None,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["name_key"] = df["player"].apply(normalize_name)
    return df


def scrape_recent_draft_classes(season_end_year: int, num_classes: int = 5) -> pd.DataFrame:
    """Pulls draft classes covering the rookie-scale window (default: the
    5 most recent drafts, which is enough to cover 4-year rookie deals).
    """
    frames = []
    for offset in range(num_classes):
        year = season_end_year - offset
        try:
            frames.append(scrape_draft_class(year))
        except Exception as exc:  # noqa: BLE001 -- keep pipeline going if one page fails
            print(f"  (warning) couldn't scrape draft/{year}: {exc}")
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["player", "draft_year", "draft_pick", "name_key"])
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_recent_draft_classes(SEASON_END_YEAR)
    print(out.head(20).to_string())
    print(f"\n{len(out)} recently-drafted players parsed.")
