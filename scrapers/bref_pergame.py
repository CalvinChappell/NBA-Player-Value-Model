"""
Scrapes Basketball-Reference's season Per Game stats table:
https://www.basketball-reference.com/leagues/NBA_{year}_per_game.html

Gives us the basic box-score numbers that don't show up on the Advanced
stats page: points, rebounds, assists, steals, blocks, and shooting
percentages, all per-game. These feed the "basic stats" section of the
Savant-style player page (config.BOX_SCORE_METRICS in config.py).

Rather than guessing the table's id attribute (which bit us on the
contracts page -- Basketball-Reference doesn't always name tables what
you'd expect), we find the right table by looking for a cell we KNOW
must be there: data-stat="pts_per_g". That's stable regardless of what
the table itself is called.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name

_AGGREGATE_TEAM_PATTERN = re.compile(r"^(TOT|\d+TM)$")


def scrape_per_game_stats(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_per_game.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = None
    for candidate in soup.find_all("table"):
        if candidate.find("td", {"data-stat": "pts_per_g"}):
            table = candidate
            break

    if table is None:
        raise RuntimeError(
            f"Could not find the per-game stats table at {url} (no cell with "
            "data-stat='pts_per_g' found anywhere). Basketball-Reference may "
            "have renamed this stat -- inspect the cached HTML in data/cache/."
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
                "MPG": stat("mp_per_g"),
                "PPG": stat("pts_per_g"),
                "RPG": stat("trb_per_g"),
                "APG": stat("ast_per_g"),
                "SPG": stat("stl_per_g"),
                "BPG": stat("blk_per_g"),
                "FG_PCT": stat("fg_pct"),
                "FG3_PCT": stat("fg3_pct"),
                "FT_PCT": stat("ft_pct"),
                # Raw free-throw volume: used both as the sample-size gate
                # and (via FTr on the advanced page) the volume component
                # of Foul-Drawing Value. See model/value_metrics.py.
                "FTA_per_g": stat("fta_per_g"),
                # Total field goal attempts -- needed to turn the shooting
                # page's per-distance attempt SHARES into actual attempt
                # counts (see model/value_metrics.py, Rim Scoring Value).
                "FGA_per_g": stat("fga_per_g"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Parsed zero rows from the per-game stats table -- check the cached HTML.")

    numeric_cols = [
        "MPG", "PPG", "RPG", "APG", "SPG", "BPG",
        "FG_PCT", "FG3_PCT", "FT_PCT", "FTA_per_g", "FGA_per_g",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Same multi-team dedup logic as bref_advanced.py: keep the aggregate
    # "season total" row for anyone traded mid-season, drop the per-team splits.
    df["_is_aggregate"] = df["team"].fillna("").str.upper().str.match(_AGGREGATE_TEAM_PATTERN)
    df["name_key"] = df["player"].apply(normalize_name)
    df = df.sort_values("_is_aggregate", ascending=False)
    df = df.drop_duplicates(subset=["name_key"], keep="first")
    df = df.drop(columns=["_is_aggregate", "team"])  # team already carried from advanced stats

    return df.reset_index(drop=True)


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_per_game_stats(SEASON_END_YEAR)
    print(out.head(15).to_string())
    print(f"\n{len(out)} players parsed.")
