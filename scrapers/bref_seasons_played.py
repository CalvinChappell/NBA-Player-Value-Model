"""
Derives NBA experience by counting how many seasons a player actually
appears in, rather than subtracting their draft year.

WHY THIS EXISTS

scrapers/bref_draft.py computes experience = season_end_year -
draft_year, which works fine for drafted players and not at all for
anyone else. Undrafted players -- two-way signees, G League call-ups,
international free agents who signed outside the draft -- were never in
a draft class, so they have no draft_year to subtract from and their
experience comes out blank. Julian Champagnie is a typical case: several
seasons in the league, no draft row, experience shows as "None".

That blank propagates further than it looks. `experience` is a feature
in the $-estimator (median-filled when missing, so those players get
assigned a fabricated career length), and it determines which CBA max
tier a player falls into (25% / 30% / 35%), which drives the
salary_tier classification.

THE APPROACH

Scrape the last N seasons' Advanced stats pages -- which we already know
how to parse -- and count how many distinct seasons each player shows up
in. A player appearing in 4 of them has ~4 years of experience.

CAVEAT worth knowing: this counts SEASONS PLAYED, which isn't identical
to years of service. A player who missed an entire season injured, or
spent a year overseas mid-career, will be undercounted. For drafted
players the draft-year math is more accurate, so merge.py prefers it and
only falls back to this count when draft_year is missing. That keeps the
better number where it exists and fills the gap where it doesn't.

COST: one cached request per season scraped (see config.USE_CACHE), so
it's slow once and instant thereafter.
"""

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name


def _players_in_season(season_end_year: int) -> set:
    """Normalized name keys of everyone who appeared in a given season."""
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_advanced.html"
    try:
        html = strip_comments(get_html(url))
    except Exception as exc:  # noqa: BLE001 -- a missing season shouldn't kill the run
        print(f"  (skipping {season_end_year}: {exc})")
        return set()

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "advanced"})
    if table is None:
        return set()

    names = set()
    body = table.find("tbody")
    if body is None:
        return set()

    for tr in body.find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue
        cell = tr.find("td", {"data-stat": "name_display"}) or tr.find(
            "td", {"data-stat": "player"}
        )
        if cell is None:
            continue
        name = cell.get_text(strip=True)
        if name:
            names.add(normalize_name(name))
    return names


def scrape_seasons_played(season_end_year: int, num_seasons: int = 20) -> pd.DataFrame:
    """Returns [name_key, seasons_played] counting appearances across the
    current season and the `num_seasons - 1` seasons before it.
    """
    counts: dict = {}
    for year in range(season_end_year, season_end_year - num_seasons, -1):
        for name_key in _players_in_season(year):
            counts[name_key] = counts.get(name_key, 0) + 1

    if not counts:
        return pd.DataFrame(columns=["name_key", "seasons_played"])

    return pd.DataFrame(
        {"name_key": list(counts.keys()), "seasons_played": list(counts.values())}
    )


if __name__ == "__main__":
    from config import SEASON_END_YEAR

    out = scrape_seasons_played(SEASON_END_YEAR)
    print(out.sort_values("seasons_played", ascending=False).head(20).to_string())
    print(f"\n{len(out)} players counted.")
