"""
Scrapes Basketball-Reference's PLAYOFF per-game and advanced tables:
https://www.basketball-reference.com/playoffs/NBA_{year}_per_game.html
https://www.basketball-reference.com/playoffs/NBA_{year}_advanced.html

These are the same table layouts as the regular-season pages (bref_pergame.py
/ bref_advanced.py) -- same data-stat attribute names, same "TOT"/"NTM"
aggregate-row-for-traded-players quirk -- just scoped to games that actually
count in the postseason.

IMPORTANT CAVEAT, worth repeating anywhere this data gets displayed: only
16 of 30 teams make the playoffs, and a first-round sweep is 4 games. Most
players in the league have either zero playoff games (team didn't qualify)
or a handful (early exit). Don't fold this into Value Score, Market Value,
or any percentile-ranked composite -- the sample sizes are far too thin for
that, the same lesson the Rim Scoring threshold bug taught with a much
bigger regular-season sample. Show it as descriptive, unranked context only
(see app/player_page.py's Playoff Performance section).

If a season's playoffs haven't happened yet (mid-regular-season pipeline
run) or didn't happen at all, these pages 404 / return an empty table --
scrape_playoff_stats() raises RuntimeError in that case, and callers should
degrade gracefully (see model/merge.py) rather than fail the whole pipeline.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name

_AGGREGATE_TEAM_PATTERN = re.compile(r"^(TOT|\d+TM)$")


def _find_table_by_marker(soup: BeautifulSoup, marker_stat: str):
    for candidate in soup.find_all("table"):
        if candidate.find("td", {"data-stat": marker_stat}):
            return candidate
    return None


def _dedupe_traded_players(df: pd.DataFrame) -> pd.DataFrame:
    """Same aggregate-row logic as bref_advanced.py / bref_pergame.py: keep
    the multi-team "TOT" row (correct season totals) over per-team splits.
    """
    df["_is_aggregate"] = df["team"].fillna("").str.upper().str.match(_AGGREGATE_TEAM_PATTERN)
    df = df.sort_values("_is_aggregate", ascending=False)
    df = df.drop_duplicates(subset=["name_key"], keep="first")
    return df.drop(columns=["_is_aggregate"])


def _scrape_playoff_pergame(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/playoffs/NBA_{season_end_year}_per_game.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = _find_table_by_marker(soup, "pts_per_g")
    if table is None:
        raise RuntimeError(
            f"No playoff per-game table at {url} -- playoffs may not have happened "
            "yet for this season."
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

        rows.append(
            {
                "player": player_cell.get_text(strip=True),
                "team": stat("team_id") or stat("team_name_abbr"),
                # NOT "games" here -- that attribute name is only proven
                # correct on the ADVANCED table (see bref_advanced.py's
                # comment on the "g" -> "games" rename). This per-game
                # table apparently still uses something else for games
                # played, so stat("games") silently returned nothing while
                # every other stat on this same row parsed fine -- which
                # made every playoff participant look like they never made
                # the playoffs (made_playoffs was gated solely on this
                # field). GP is sourced from _scrape_playoff_advanced
                # instead now, which uses the verified-correct name.
                "playoff_MPG": stat("mp_per_g"),
                "playoff_PPG": stat("pts_per_g"),
                "playoff_RPG": stat("trb_per_g"),
                "playoff_APG": stat("ast_per_g"),
                "playoff_SPG": stat("stl_per_g"),
                "playoff_BPG": stat("blk_per_g"),
                "playoff_FG_PCT": stat("fg_pct"),
                "playoff_FG3_PCT": stat("fg3_pct"),
                "playoff_FT_PCT": stat("ft_pct"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Parsed zero rows from the playoff per-game table.")

    numeric_cols = [
        "playoff_MPG", "playoff_PPG", "playoff_RPG", "playoff_APG",
        "playoff_SPG", "playoff_BPG", "playoff_FG_PCT", "playoff_FG3_PCT", "playoff_FT_PCT",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["name_key"] = df["player"].apply(normalize_name)
    df = _dedupe_traded_players(df)
    return df.drop(columns=["team", "player"]).reset_index(drop=True)


def _scrape_playoff_advanced(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/playoffs/NBA_{season_end_year}_advanced.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", {"id": "advanced"}) or _find_table_by_marker(soup, "bpm")
    if table is None:
        raise RuntimeError(
            f"No playoff advanced-stats table at {url} -- playoffs may not have "
            "happened yet for this season."
        )

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue
        player_cell = tr.find("td", {"data-stat": "player"}) or tr.find(
            "td", {"data-stat": "name_display"}
        )
        if player_cell is None:
            continue

        def stat(name, default=None):
            cell = tr.find("td", {"data-stat": name})
            return cell.get_text(strip=True) if cell is not None else default

        rows.append(
            {
                "player": player_cell.get_text(strip=True),
                "team": stat("team_id") or stat("team_name_abbr"),
                # "games" is the verified-correct attribute name here --
                # same one bref_advanced.py uses for the regular-season
                # advanced table (see its comment on the "g" -> "games"
                # rename). This is now the ONLY source of playoff_GP; see
                # the note in _scrape_playoff_pergame for why it moved.
                "playoff_GP": stat("games"),
                "playoff_MP": stat("mp"),
                "playoff_BPM": stat("bpm"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Parsed zero rows from the playoff advanced-stats table.")

    for col in ["playoff_GP", "playoff_MP", "playoff_BPM"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["name_key"] = df["player"].apply(normalize_name)
    df = _dedupe_traded_players(df)
    return df.drop(columns=["team", "player"]).reset_index(drop=True)


def scrape_playoff_stats(season_end_year: int) -> pd.DataFrame:
    """Combined playoff per-game + advanced stats, one row per player who
    appeared in that postseason. Raises RuntimeError if the playoffs haven't
    happened yet for this season -- callers should catch that and degrade
    gracefully (empty playoff columns) rather than fail the pipeline.
    """
    pergame = _scrape_playoff_pergame(season_end_year)
    advanced = _scrape_playoff_advanced(season_end_year)
    return pergame.merge(advanced, on="name_key", how="outer")


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_playoff_stats(SEASON_END_YEAR)
    print(out.head(15).to_string())
    print(f"\n{len(out)} players with playoff stats parsed.")
