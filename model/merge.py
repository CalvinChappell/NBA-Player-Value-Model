"""
Joins every source into one master player table:

  Basketball-Reference Advanced stats  (BPM/OBPM/DBPM, GP, MP, Age, Pos, Team)
    + Basketball-Reference Per Game    (PPG, RPG, APG, SPG, BPG, shooting %s)
    + Basketball-Reference Contracts   (salary, cap_hit, years_remaining)
    + Basketball-Reference Draft data  (draft_year -> experience -> rookie/vet)
    + manual EPM / DARKO / LEBRON CSVs (data/manual/*.csv)
    + manual databallr.com CSV         (OnBall%, rTS%, 3Y RAPM, PVAL, Net On/Off)
    + manual contract_overrides.csv    (contract_type, bird_rights, cap_hit fixes)

Everything is joined on a normalized name key. Basketball-Reference's own
player_id (slug) is carried through as the most reliable key for anyone
who wants to join in still more sources later.
"""

import pandas as pd

from config import (
    DRAFT_CLASSES_TO_SCRAPE,
    MANUAL_DIR,
    PLAYOFF_LOW_SAMPLE_MP,
    ROOKIE_SCALE_MAX_EXPERIENCE,
    SEASON_END_YEAR,
    SEASONS_FOR_EXPERIENCE,
)
from scrapers import (
    bref_advanced,
    bref_contracts,
    bref_draft,
    bref_pergame,
    bref_playoffs,
    bref_seasons_played,
    bref_shooting,
    external_metrics,
)
from utils.name_match import normalize_name


_OVERRIDE_COLUMNS = [
    "name_key", "contract_type", "bird_rights_status", "cap_hit_override",
    "team_override", "free_agent_override", "notes",
]


def _load_contract_overrides() -> pd.DataFrame:
    """Manual corrections for cases the scrapers can't resolve reliably.

    team_override exists for a specific, real failure mode: a player who
    got bought out and re-signed elsewhere can show up as TWO rows on
    Basketball-Reference's contracts page (a dead-money charge against
    the old team, plus the new deal), and there's no generic, safe rule
    for picking the right one automatically -- both rows can even show
    the same stale pre-buyout dollar figures (this happened with Bradley
    Beal's 2026 Suns buyout / Clippers re-signing). Hand-correcting one
    player here beats risking a dedup-logic change that could silently
    break someone else's correctly-scraped row.

    free_agent_override exists for a related but distinct failure mode:
    a player whose contracts-page row is simply STALE, not misattributed.
    James Harden declined his $42.3M 2026-27 Clippers player option and
    is a genuine free agent (working out a new deal with Cleveland, who
    traded for him in February) as of this writing -- but the contracts
    page hadn't dropped his old figure yet, so he scraped as if still
    signed for $42.3M. Any non-null value in this column forces cap_hit
    back to NaN for that player wherever it matters (build_master_table's
    is_free_agent flag, and build_payroll_table's payroll total), rather
    than trying to detect staleness automatically -- there's no reliable
    signal on the page itself that distinguishes "still actually signed"
    from "site hasn't updated yet."
    """
    path = MANUAL_DIR / "contract_overrides.csv"
    if not path.exists():
        return pd.DataFrame(columns=_OVERRIDE_COLUMNS)
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=_OVERRIDE_COLUMNS)
    if "team_override" not in df.columns:
        df["team_override"] = pd.NA
    if "free_agent_override" not in df.columns:
        df["free_agent_override"] = pd.NA
    df["name_key"] = df["player"].apply(normalize_name)
    return df.drop(columns=["player"])


def build_master_table(season_end_year: int = SEASON_END_YEAR) -> pd.DataFrame:
    print("Scraping Basketball-Reference advanced stats...")
    advanced = bref_advanced.scrape_advanced_stats(season_end_year)

    print("Scraping Basketball-Reference contracts...")
    contracts = bref_contracts.scrape_player_contracts()

    print("Scraping Basketball-Reference per-game (box score) stats...")
    per_game = bref_pergame.scrape_per_game_stats(season_end_year)

    print("Scraping Basketball-Reference shooting (shot-distance) stats...")
    shooting = bref_shooting.scrape_shooting_stats(season_end_year)

    print(f"Scraping {DRAFT_CLASSES_TO_SCRAPE} draft classes (for experience / rookie-scale flag)...")
    draft = bref_draft.scrape_recent_draft_classes(season_end_year, num_classes=DRAFT_CLASSES_TO_SCRAPE)

    print(f"Counting seasons played across {SEASONS_FOR_EXPERIENCE} seasons (covers undrafted players)...")
    seasons = bref_seasons_played.scrape_seasons_played(
        season_end_year, num_seasons=SEASONS_FOR_EXPERIENCE
    )

    print("Scraping Basketball-Reference playoff stats (per-game + advanced)...")
    try:
        playoffs = bref_playoffs.scrape_playoff_stats(season_end_year)
    except RuntimeError as exc:
        # Playoffs haven't happened yet for this season (or scrape failed) --
        # degrade to an empty playoff split rather than fail the whole
        # pipeline. The player page shows "no playoff data" in this case.
        print(f"  (skipping playoff split: {exc})")
        playoffs = pd.DataFrame(columns=["name_key"])

    print("Loading manual EPM / DARKO / LEBRON CSVs (if present)...")
    external = external_metrics.load_all_manual_metrics()

    print("Loading databallr playstyle/impact metrics (if present)...")
    databallr = external_metrics.load_databallr_metrics()

    overrides = _load_contract_overrides()

    advanced["name_key"] = advanced["player"].apply(normalize_name)

    df = advanced.merge(
        contracts.drop(columns=["player"]), on="name_key", how="left", suffixes=("", "_contract")
    )
    df = df.merge(
        per_game.drop(columns=["player"]), on="name_key", how="left", suffixes=("", "_pergame")
    )
    df = df.merge(shooting, on="name_key", how="left", suffixes=("", "_shooting"))
    if not playoffs.empty:
        df = df.merge(playoffs, on="name_key", how="left")
    else:
        for col in (
            "playoff_GP", "playoff_MPG", "playoff_PPG", "playoff_RPG", "playoff_APG",
            "playoff_SPG", "playoff_BPG", "playoff_FG_PCT", "playoff_FG3_PCT",
            "playoff_FT_PCT", "playoff_MP", "playoff_BPM",
        ):
            df[col] = pd.NA
    df = df.merge(
        draft[["name_key", "draft_year", "draft_pick"]] if not draft.empty else draft,
        on="name_key",
        how="left",
    )
    if not seasons.empty:
        df = df.merge(seasons, on="name_key", how="left")
    else:
        df["seasons_played"] = pd.NA
    if not external.empty:
        df = df.merge(external, on="name_key", how="left")
    else:
        for col in ("EPM", "DARKO", "LEBRON"):
            df[col] = pd.NA

    if not databallr.empty:
        df = df.merge(databallr, on="name_key", how="left")
    else:
        for col in ("OnBall_Pct", "rTS_rel", "RAPM_3Y", "PVAL", "NET_ON_OFF"):
            df[col] = pd.NA

    if not overrides.empty:
        df = df.merge(overrides, on="name_key", how="left")
    else:
        for col in ("contract_type", "bird_rights_status", "cap_hit_override", "team_override", "notes"):
            df[col] = pd.NA

    # Experience + rookie/vet classification (see config.ROOKIE_SCALE_MAX_EXPERIENCE
    # for the cutoff, and the module docstring in scrapers/bref_draft.py for caveats).
    # Prefer draft-year math (accurate years of service for drafted
    # players); fall back to counted seasons for undrafted players, who
    # have no draft row at all. See scrapers/bref_seasons_played.py.
    _from_draft = season_end_year - df["draft_year"]
    _from_seasons = pd.to_numeric(df.get("seasons_played"), errors="coerce")
    df["experience"] = _from_draft.where(_from_draft.notna(), _from_seasons)
    df["experience_is_estimated"] = _from_draft.isna() & _from_seasons.notna()
    df["contract_type"] = df["contract_type"].where(
        df["contract_type"].notna(),
        df["experience"].apply(
            lambda x: "Rookie Scale"
            if pd.notna(x) and x <= ROOKIE_SCALE_MAX_EXPERIENCE
            else "Veteran"
        ),
    )

    # Manual cap_hit correction wins if present, else fall back to the
    # Basketball-Reference salary figure.
    df["cap_hit"] = df["cap_hit_override"].where(df["cap_hit_override"].notna(), df["cap_hit"])

    # free_agent_override wins over everything else -- a stale contracts-
    # page row (see _load_contract_overrides) shouldn't count as a real
    # deal no matter what cap_hit_override says. Clearing cap_hit to NaN
    # here is sufficient: is_free_agent below is derived from cap_hit, so
    # this single line fixes the flag, the leaderboard, and the player
    # page all at once.
    if "free_agent_override" in df.columns:
        df.loc[df["free_agent_override"].notna(), "cap_hit"] = pd.NA

    # Same idea for team_contract: a manual team_override wins if present.
    # See _load_contract_overrides for why this exists (buyout/re-signing
    # cases where Basketball-Reference's contracts page shows a stale or
    # duplicate team for a player).
    if "team_contract" in df.columns:
        df["team_contract"] = df["team_override"].where(
            df["team_override"].notna(), df["team_contract"]
        )

    # Free agent flag: the contracts page only lists players with a signed
    # deal, so anyone who played this season (has advanced stats) but has
    # no cap_hit at all -- and no manual override supplying one -- almost
    # certainly doesn't have a contract on file, i.e. is an impending or
    # actual free agent (e.g. LeBron once his current deal runs out).
    # "team" for these players still reflects the last team they suited up
    # for (see scrapers/bref_advanced.py), which is correct info to show,
    # but they shouldn't count as "on" that team when filtering by team --
    # there's no guarantee they'll actually be there next season.
    df["is_free_agent"] = df["cap_hit"].isna()

    # Descriptive-only playoff split -- see scrapers/bref_playoffs.py and
    # config.PLAYOFF_LOW_SAMPLE_MP. made_playoffs distinguishes "team didn't
    # qualify / player didn't appear" from a real (if thin) playoff sample.
    #
    # Checks playoff_MP too, not just playoff_GP, deliberately: a bug once
    # had playoff_GP silently failing to parse (wrong data-stat attribute
    # name on that specific table) while playoff_MP/PPG/RPG/BPM all parsed
    # fine from a different table -- which made every playoff participant,
    # Finals runs included, look like they'd never made the playoffs at
    # all. Requiring EITHER field means one bad attribute name on one table
    # can't erase a player's playoff appearance from the whole feature.
    df["made_playoffs"] = (
        (df["playoff_GP"].notna() & (df["playoff_GP"] > 0)) | df["playoff_MP"].notna()
    )
    df["playoff_low_sample"] = df["made_playoffs"] & (
        df["playoff_MP"].isna() | (df["playoff_MP"] < PLAYOFF_LOW_SAMPLE_MP)
    )

    return df


def build_payroll_table() -> pd.DataFrame:
    """Every player with a signed 2026-27 contract, independent of whether
    they have 2025-26 production stats.

    build_master_table() anchors on Basketball-Reference's ADVANCED stats
    table and left-joins contracts onto it -- the right shape for the
    leaderboard, since there's no point ranking someone with no production
    data. It's the wrong shape for Team Payroll: anyone who has a signed
    contract but zero 2025-26 stats never enters that anchor table at all,
    so their cap hit silently never counts toward any team's total. Two
    real populations hit this every season: incoming rookies (signed for
    2026-27, no NBA games played yet) and players who missed all of
    2025-26 to injury but still hold real, often enormous, 2026-27
    contracts -- e.g. Tyrese Haliburton, Kyrie Irving, Damian Lillard, and
    Fred VanVleet all had season-ending injuries in 2025 and all vanish
    from build_master_table() as a result, despite combining for close to
    $150M in signed 2026-27 salary.

    This sources straight off the contracts page instead, so every signed
    player counts toward their team's total regardless of whether they
    played last season. Still subject to the same team_override /
    cap_hit_override corrections as build_master_table (see
    _load_contract_overrides) -- including the Beal/Lillard/KCP/Prosper
    stale-team cases, where the contracts page itself lists a player under
    an old team alongside their new one with an identical dollar figure.
    """
    contracts = bref_contracts.scrape_player_contracts()
    overrides = _load_contract_overrides()

    df = contracts.merge(overrides, on="name_key", how="left")

    df["cap_hit"] = df["cap_hit_override"].where(df["cap_hit_override"].notna(), df["cap_hit"])
    df["team_contract"] = df["team_override"].where(df["team_override"].notna(), df["team"])

    # Drop anyone flagged as a stale contracts-page row (see
    # _load_contract_overrides) -- they're a free agent right now, not
    # signed anywhere, and shouldn't count toward any team's total.
    if "free_agent_override" in df.columns:
        df = df[df["free_agent_override"].isna()]

    return df[["name_key", "player", "team_contract", "cap_hit"]]


def unmatched_report(df: pd.DataFrame) -> pd.DataFrame:
    """Players with advanced stats but no contract match -- usually a
    name-spelling mismatch (accents, suffixes) or a player who's since
    left the league. Use this to spot-check joins.
    """
    return df[df["salary"].isna()][["player", "team", "MP"]].sort_values("MP", ascending=False)


if __name__ == "__main__":
    master = build_master_table()
    print(f"\n{len(master)} players in master table.")
    missing = unmatched_report(master)
    if not missing.empty:
        print(f"\n{len(missing)} players with no contract match (top by minutes):")
        print(missing.head(20).to_string())
