"""
One-shot diagnostic for Foul-Drawing Value showing "None" for every
player. add_foul_draw_value() (model/value_metrics.py) requires FIVE
columns -- FTr, FT_PCT, FTA_per_g, GP, MP -- and silently blanks the
whole metric for everyone if even one is missing. This checks each one
directly against a fresh scrape, and if FTr specifically is empty, dumps
one raw table row so we can see what Basketball-Reference actually named
the attribute now (this exact failure mode broke playoff_GP earlier in
this project -- a silent bref rename).

Run from the project root: python diagnose_foul_draw.py
"""

import sys

sys.path.insert(0, ".")

from config import SEASON_END_YEAR
from scrapers.bref_advanced import scrape_advanced_stats
from scrapers.bref_pergame import scrape_per_game_stats

print("=" * 70)
print("Advanced stats (source of FTr, GP, MP)")
print("=" * 70)
advanced = scrape_advanced_stats(SEASON_END_YEAR)
for col in ["FTr", "GP", "MP"]:
    if col not in advanced.columns:
        print(f"  {col}: COLUMN MISSING ENTIRELY")
    else:
        n_ok = advanced[col].notna().sum()
        print(f"  {col}: {n_ok}/{len(advanced)} non-null")

print()
print("=" * 70)
print("Per-game stats (source of FT_PCT, FTA_per_g)")
print("=" * 70)
per_game = scrape_per_game_stats(SEASON_END_YEAR)
for col in ["FT_PCT", "FTA_per_g"]:
    if col not in per_game.columns:
        print(f"  {col}: COLUMN MISSING ENTIRELY")
    else:
        n_ok = per_game[col].notna().sum()
        print(f"  {col}: {n_ok}/{len(per_game)} non-null")

# If FTr came back empty, find out what Basketball-Reference is actually
# calling that cell now.
if advanced["FTr"].notna().sum() == 0:
    print()
    print("=" * 70)
    print("FTr is empty -- inspecting raw HTML for the real attribute name")
    print("=" * 70)
    from bs4 import BeautifulSoup

    from scrapers.http import get_html, strip_comments

    url = f"https://www.basketball-reference.com/leagues/NBA_{SEASON_END_YEAR}_advanced.html"
    html = strip_comments(get_html(url))
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "advanced"})
    first_row = None
    for tr in table.find("tbody").find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue
        if tr.find("td", {"data-stat": "player"}):
            first_row = tr
            break
    if first_row is not None:
        print("All data-stat attributes on one real player row:")
        for td in first_row.find_all("td"):
            print(f"  {td.get('data-stat')!r}: {td.get_text(strip=True)!r}")
