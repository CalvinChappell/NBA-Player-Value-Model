"""
Scrapes Basketball-Reference's league-wide contracts page:
https://www.basketball-reference.com/contracts/players.html

Gives us, per player: current team, this season's salary, salary in each
future contracted season, how many years remain (including this one),
and the total guaranteed money left on the deal.

Two things this page does NOT give us cleanly, and that we approximate:

1. "Cap hit" vs "salary" -- for the vast majority of players these are
   the same number. Cap hit only diverges for things like stretch
   provisions, base-year-compensation trades, or offset language, which
   this page doesn't expose. We set cap_hit = salary and leave a column
   so you can hand-correct specific players in
   data/manual/contract_overrides.csv if it matters for your use case.

2. "Contract type" (rookie scale / rookie extension / vet max / vet MLE /
   two-way etc) and "Bird rights status" aren't published anywhere on
   Basketball-Reference in structured form. We derive a best-effort
   Contract Type from years of experience (see model/value_score.py),
   and we leave Bird Rights Status blank for you to fill in from your own
   front-office records or Spotrac, via the same overrides CSV.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name


def _parse_money(value: str):
    if value is None:
        return None
    value = value.replace("$", "").replace(",", "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def scrape_player_contracts() -> pd.DataFrame:
    url = "https://www.basketball-reference.com/contracts/players.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", {"id": "player-contracts"})
    if table is None:
        raise RuntimeError(f"Could not find a contracts table at {url}.")

    # Basketball-Reference uses generic, season-agnostic data-stat names for
    # this table rather than literal season strings: y1 = this season's
    # salary, y2 = next season, etc, through y6. Confirmed by inspecting a
    # cached copy of the page directly (data-stat attributes don't change
    # even though the on-screen column headers like "2025-26" shift every
    # year). "remain_gtd" is the total guaranteed money column.
    year_cols = ["y1", "y2", "y3", "y4", "y5", "y6"]

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        player_cell = tr.find("td", {"data-stat": "player"})
        if player_cell is None:
            continue
        link = player_cell.find("a")
        player_id = None
        if link is not None and link.get("href"):
            m = re.search(r"/players/./([a-z0-9]+)\.html", link["href"])
            if m:
                player_id = m.group(1)

        team_cell = tr.find("td", {"data-stat": "team_id"})

        # Walk the year cells in order (y1 = this season) so we can tell
        # current salary from future years, and count how many are
        # populated (== years remaining, including this one).
        year_values = []
        for yc in year_cols:
            cell = tr.find("td", {"data-stat": yc})
            year_values.append(_parse_money(cell.get_text(strip=True)) if cell is not None else None)

        guaranteed_cell = tr.find("td", {"data-stat": "remain_gtd"})

        rows.append(
            {
                "player_id": player_id,
                "player": player_cell.get_text(strip=True),
                "team": team_cell.get_text(strip=True) if team_cell is not None else None,
                "salary": year_values[0] if year_values else None,
                "years_remaining": sum(1 for v in year_values if v is not None),
                "total_guaranteed": _parse_money(guaranteed_cell.get_text(strip=True))
                if guaranteed_cell is not None
                else None,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(
            "Parsed zero rows from the contracts table -- Basketball-Reference "
            "may have changed data-stat attribute names. Inspect data/cache/*.html."
        )

    df["cap_hit"] = df["salary"]  # see module docstring re: limitations
    df["name_key"] = df["player"].apply(normalize_name)
    df = df.drop_duplicates(subset=["name_key"], keep="first")
    return df.reset_index(drop=True)


if __name__ == "__main__":
    out = scrape_player_contracts()
    print(out.head(15).to_string())
    print(f"\n{len(out)} contracts parsed.")
