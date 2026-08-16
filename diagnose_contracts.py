"""
One-shot diagnostic for the Team Payroll discrepancies against Spotrac.

Run from the project root: python diagnose_contracts.py

Two checks, both aimed at finding every player affected by the same class
of bug we found with Bradley Beal (a buyout/re-signing leaving two
conflicting rows on Basketball-Reference's contracts page), rather than
relying on spotting them team-by-team by eye:

1. DUPLICATE CONTRACT ROWS -- players who appear more than once on the
   contracts page (before our drop_duplicates(keep="first") step). Any
   name here is a case where we're silently picking one of two (or more)
   conflicting salary/team figures, and "first row in page order" has no
   guarantee of being the *current*, correct one. This is the likely
   cause of teams where our total is HIGHER than Spotrac's Active number
   despite equal or fewer players (ATL, ORL, NOP, CLE in the screenshot).

2. UNMATCHED PLAYERS -- players with regular-season stats but no contract
   match at all, i.e. currently counted as free agents. Sorted by minutes
   played, so real signed players wrongly falling out of the join (name
   mismatches: Jr./Sr./II, accents, nicknames) sort to the top instead of
   genuine free agents. This is the likely cause of teams where our total
   is LOWER than Spotrac's (OKC, HOU, WAS, SAC, BOS, etc.) -- some of
   these "free agents" are actually signed players we're just failing to
   attach a contract to.

Both use the same cached HTML / scraper code as the real pipeline, so
results reflect exactly what's feeding the app right now.
"""

import sys

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, ".")

from scrapers.bref_contracts import _parse_money
from scrapers.http import get_html, strip_comments
from utils.name_match import normalize_name


def find_duplicate_contract_rows() -> pd.DataFrame:
    url = "https://www.basketball-reference.com/contracts/players.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "player-contracts"})
    if table is None:
        raise RuntimeError(f"Could not find a contracts table at {url}.")

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        player_cell = tr.find("td", {"data-stat": "player"})
        if player_cell is None:
            continue
        team_cell = tr.find("td", {"data-stat": "team_id"})
        y1_cell = tr.find("td", {"data-stat": "y1"})
        rows.append(
            {
                "player": player_cell.get_text(strip=True),
                "team": team_cell.get_text(strip=True) if team_cell is not None else None,
                "y1_salary": _parse_money(y1_cell.get_text(strip=True)) if y1_cell is not None else None,
            }
        )

    df = pd.DataFrame(rows)
    df["name_key"] = df["player"].apply(normalize_name)

    dupes = df[df.duplicated("name_key", keep=False)].copy()
    if dupes.empty:
        return dupes

    spread = dupes.groupby("name_key")["y1_salary"].transform(
        lambda s: (s.max() - s.min()) if s.notna().any() else 0
    )
    dupes["salary_spread"] = spread
    dupes = dupes.sort_values(["salary_spread", "name_key"], ascending=[False, True])
    return dupes[["player", "team", "y1_salary", "salary_spread"]]


def find_unmatched_signed_looking_players() -> pd.DataFrame:
    from model.merge import build_master_table, unmatched_report

    master = build_master_table()
    missing = unmatched_report(master)
    return missing


if __name__ == "__main__":
    print("=" * 70)
    print("CHECK 1: Players with duplicate/conflicting rows on the contracts page")
    print("=" * 70)
    dupes = find_duplicate_contract_rows()
    if dupes.empty:
        print("None found -- no duplicate name_key rows on the contracts page.")
    else:
        n_players = dupes["player"].nunique()
        print(f"{n_players} players have multiple contract-page rows.\n")
        print(dupes.to_string(index=False))
        print(
            "\nAny row here with salary_spread > 0 is a real conflict: our "
            "scraper is picking ONE of these values, and page order (not "
            "recency) decides which. Cross-check the top of this list "
            "against contract_overrides.csv -- these are the highest-"
            "priority team_override / cap_hit_override candidates."
        )

    print()
    print("=" * 70)
    print("CHECK 2: Players with stats but no contract match (top by minutes)")
    print("=" * 70)
    missing = find_unmatched_signed_looking_players()
    print(f"{len(missing)} total unmatched players.\n")
    print(missing.head(40).to_string(index=False))
    print(
        "\nAnyone here who you know is actually signed (not a real free "
        "agent) is a name-matching failure -- check utils/name_match.py "
        "normalization against the exact spelling on the contracts page "
        "for that player."
    )
