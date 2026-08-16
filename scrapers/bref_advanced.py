"""
Scrapes Basketball-Reference's season Advanced stats table:
https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html

Gives us, per player for the season: Age, Team, Pos, GP, MP (total
minutes), OBPM, DBPM, BPM, VORP -- everything BPM-family plus playing
time, straight from a source that doesn't require a login or JS
rendering.

Players traded mid-season show up multiple times (one aggregate "season
total" row + one row per team they played for). We keep only the
aggregate row so each player appears once.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name

_AGGREGATE_TEAM_PATTERN = re.compile(r"^(TOT|\d+TM)$")


def scrape_advanced_stats(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_advanced.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", {"id": "advanced"}) or soup.find(
        "table", {"id": re.compile("advanced")}
    )
    if table is None:
        raise RuntimeError(
            f"Could not find the advanced-stats table at {url}. "
            "Basketball-Reference may have changed its page layout."
        )

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue  # repeated header row inserted every ~20 rows

        player_cell = tr.find("td", {"data-stat": "player"}) or tr.find(
            "td", {"data-stat": "name_display"}
        )
        if player_cell is None:
            continue

        def stat(name, default=None):
            cell = tr.find("td", {"data-stat": name})
            return cell.get_text(strip=True) if cell is not None else default

        link = player_cell.find("a")
        player_id = None
        if link is not None and link.get("href"):
            m = re.search(r"/players/./([a-z0-9]+)\.html", link["href"])
            if m:
                player_id = m.group(1)

        rows.append(
            {
                "player_id": player_id,
                "player": player_cell.get_text(strip=True),
                "team": stat("team_id") or stat("team_name_abbr"),
                "pos": stat("pos"),
                "age": stat("age"),
                "GP": stat("games"),  # bref renamed this from "g" to "games" at some point
                "MP": stat("mp"),
                "OBPM": stat("obpm"),
                "DBPM": stat("dbpm"),
                "BPM": stat("bpm"),
                "VORP": stat("vorp"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Parsed zero rows from the advanced-stats table -- check the cached HTML.")

    numeric_cols = ["age", "GP", "MP", "OBPM", "DBPM", "BPM", "VORP"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={"age": "AGE"})

    # Collapse traded players down to one row: prefer the multi-team
    # aggregate row (team == "TOT"/"2TM"/"3TM"...) over the per-team splits,
    # since that row has the correct season-total GP/MP/OBPM/DBPM/BPM/VORP.
    df["_is_aggregate"] = df["team"].fillna("").str.upper().str.match(_AGGREGATE_TEAM_PATTERN)
    df["name_key"] = df["player"].apply(normalize_name)

    # But "team" itself shouldn't be left as "TOT"/"2TM"/"3TM" -- that's
    # useless for filtering ("which team is this guy actually on?").
    # Basketball-Reference lists the aggregate row first, then each
    # per-team stint in chronological order, so the LAST non-aggregate
    # row for a given player is their most recent team -- i.e. the one
    # they'll suit up for going into next season. Use that instead.
    most_recent_team = (
        df[~df["_is_aggregate"]].groupby("name_key", sort=False)["team"].last()
    )

    df = df.sort_values("_is_aggregate", ascending=False)
    df = df.drop_duplicates(subset=["name_key"], keep="first")
    df = df.drop(columns=["_is_aggregate"])

    df["team"] = df["name_key"].map(most_recent_team).fillna(df["team"])

    return df.reset_index(drop=True)


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_advanced_stats(SEASON_END_YEAR)
    print(out.head(15).to_string())
    print(f"\n{len(out)} players parsed.")