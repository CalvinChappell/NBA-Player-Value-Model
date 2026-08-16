"""
Interactive front-office-facing view of the player value model.

Run from the project root:
    streamlit run app/streamlit_app.py

Reads outputs/player_value_model.csv (produced by run_pipeline.py). If
that file doesn't exist yet, there's a button to run the pipeline
directly from the app (slow on first run -- it's scraping live).
"""

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import config` works

from config import (  # noqa: E402
    FIRST_APRON,
    OUTPUT_DIR,
    SALARY_CAP,
    SECOND_APRON,
    TAX_LINE,
)
from app.player_page import render_player_page  # noqa: E402
from app.methodology_page import render_methodology_page  # noqa: E402
from app.percentile_bars import pctile_color  # noqa: E402
from app.theme import (  # noqa: E402
    CARD_BACKGROUND,
    TEXT,
    TRACK,
    app_title_bar,
    inject_custom_css,
)
from model.contracts import team_payroll_summary  # noqa: E402

st.set_page_config(
    page_title="NBA Player Value Model",
    layout="wide",
    page_icon="🏀",
    # Nav and filters both live in the main body now, so there's nothing
    # in the sidebar worth opening by default.
    initial_sidebar_state="collapsed",
)
inject_custom_css()

# Prefer the full local CSV; fall back to the public one that's actually
# committed to the repo. On your machine both exist and you get raw
# metric values; on the deployed app only the public file is present, so
# it renders percentiles without shipping gated third-party data.
# See make_public_data.py.
_FULL_PATH = OUTPUT_DIR / "player_value_model.csv"
_PUBLIC_PATH = OUTPUT_DIR / "player_value_model_public.csv"
DATA_PATH = _FULL_PATH if _FULL_PATH.exists() else _PUBLIC_PATH


@st.cache_data
def load_data(path: Path, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


app_title_bar(
    "NBA Player Value Model",
    "Production percentile vs. salary percentile, across every rostered player. "
    "Positive Value Score = outproducing the contract; negative = overpaid relative to production.",
)

if not DATA_PATH.exists():
    # Local-only fallback. The deployed app always has the committed
    # public CSV, so this branch shouldn't fire there -- which matters,
    # because live scraping from a shared cloud IP would get rate-limited
    # by Basketball-Reference and take minutes per visitor.
    st.warning("No data yet -- run the pipeline first.")
    if st.button("Run pipeline now (scrapes live data, takes a few minutes)"):
        with st.spinner("Scraping Basketball-Reference and building the model..."):
            import run_pipeline

            run_pipeline.main()
        st.rerun()
    st.stop()

df = load_data(DATA_PATH, DATA_PATH.stat().st_mtime)

# Freshness + season-pairing disclosure, right under the title where it
# can't be missed. Two things worth stating plainly rather than leaving
# implicit: how current the data is, and that production and salary come
# from two different seasons on purpose (see app/methodology_page.py for
# the full explanation) -- Basketball-Reference's contracts page always
# reports the UPCOMING season's cap hit as of whenever it's scraped, so a
# pipeline run today pairs completed 2025-26 production against 2026-27
# contract figures.
_data_asof = datetime.fromtimestamp(DATA_PATH.stat().st_mtime).strftime("%B %d, %Y")
st.caption(
    f"Data as of {_data_asof}. Production stats (BPM/EPM/DARKO, box score) are from the "
    "completed 2025-26 season; cap hits and contract figures reflect the 2026-27 season. "
    "See the Methodology tab for why those are paired across two different seasons."
)

# ---------------------------------------------------------------------
# Top navigation bar.
#
# Lives in the MAIN body rather than the sidebar: the sidebar is
# collapsed by default on phones, and primary navigation shouldn't be
# hidden behind a control the user has to discover first.
#
# The player search here jumps STRAIGHT to that player's page rather
# than filtering the leaderboard -- searching a name almost always means
# "show me this player," not "narrow the table to one row."
# ---------------------------------------------------------------------
_ALL_PLAYERS = sorted(df["player"].dropna().unique().tolist())

if "view" not in st.session_state:
    st.session_state["view"] = "Leaderboard"

# Handle a click-through from a scatter plot. This MUST run before the
# search selectbox is instantiated below: Streamlit raises if you modify
# a widget's session_state entry after the widget exists in the same
# run. So the chart click stashes the name under a private key, calls
# st.rerun(), and the next run picks it up here -- before any widgets
# are created -- and promotes it to the real search value.
# The table's "View" links navigate to ?player=<name>. Read that here --
# before any widget exists -- and clear it so the param doesn't stick
# around and re-trigger on later interactions.
_qp_player = st.query_params.get("player")
if _qp_player:
    st.query_params.clear()
    if _qp_player in _ALL_PLAYERS:
        st.session_state["_pending_player"] = _qp_player

if "_pending_player" in st.session_state:
    _pending = st.session_state.pop("_pending_player")
    if _pending in _ALL_PLAYERS:
        st.session_state["player_search"] = _pending
        st.session_state["view"] = "Player Page"

# Same constraint in the other direction: the "back to leaderboard"
# button lives on the player page, which renders long after the search
# widget exists, so it can't clear that widget's state directly either.
# It sets this flag and reruns instead.
if st.session_state.pop("_pending_clear", False):
    st.session_state["player_search"] = ""
    st.session_state["view"] = "Leaderboard"

# Same deferred-write pattern again: the "Read Methodology" banner button
# on the Leaderboard renders long after the nav radio widget exists, so it
# can't set st.session_state["view"] directly either.
_pending_view = st.session_state.pop("_pending_view", None)
if _pending_view:
    st.session_state["view"] = _pending_view


def _jump_to_player():
    """Selecting a name in the search box switches to the Player Page.
    Clearing it (picking the blank entry) returns to the Leaderboard.
    """
    if st.session_state.get("player_search"):
        st.session_state["view"] = "Player Page"
    else:
        st.session_state["view"] = "Leaderboard"


nav_col, search_col, compact_col = st.columns([2, 3, 2])
with nav_col:
    st.radio(
        "View",
        ["Leaderboard", "Player Page", "Methodology"],
        horizontal=True,
        key="view",
        label_visibility="collapsed",
    )
with search_col:
    st.selectbox(
        "Search for a player",
        [""] + _ALL_PLAYERS,
        key="player_search",
        on_change=_jump_to_player,
        label_visibility="collapsed",
        placeholder="Search for a player...",
    )
with compact_col:
    # On a phone the full-width tables and tall charts need trimming;
    # Streamlit can't detect viewport width server-side, so rather than
    # guess the device this is an explicit toggle.
    compact_view = st.checkbox(
        "Compact view (mobile)",
        value=False,
        help="Trims the tables to the most important columns and shortens the charts.",
    )

st.markdown(
    f"<hr style='margin: 0.25rem 0 1rem 0; border-color: {TRACK};'>", unsafe_allow_html=True
)

if st.session_state["view"] == "Player Page":
    render_player_page(
        df,
        default_player=st.session_state.get("player_search") or None,
        compact=compact_view,
    )
    st.stop()

if st.session_state["view"] == "Methodology":
    render_methodology_page()
    st.stop()

# --- Methodology callout ------------------------------------------------
# Leaderboard stays the landing view on purpose -- the data itself is the
# strongest first impression, and leading with a page of caveats before
# anyone's seen a number risks reading as a disclaimer rather than a
# feature. But the page it points to matters, so it gets an unmissable
# banner right up top rather than being left to a nav tab someone might
# not click.
_banner_col, _banner_btn_col = st.columns([5, 2])
with _banner_col:
    st.info(
        "New here? The **Methodology & Limitations** page explains how these numbers are "
        "built and what they don't account for -- worth a read before treating any single "
        "figure as a final answer."
    )
with _banner_btn_col:
    st.write("")  # vertical nudge so the button lines up with the info box
    if st.button("Read Methodology →", key="jump_to_methodology"):
        st.session_state["_pending_view"] = "Methodology"
        st.rerun()

# --- Filters -----------------------------------------------------------
# In the MAIN body rather than the sidebar, for the same reason the nav
# is: the sidebar is collapsed by default on phones and easy to miss on
# desktop, and filters are central to how this page gets used, not a
# secondary setting. Wrapped in an expander so they stay one click away
# without pushing the actual content down the page.
_AGGREGATE_TEAM_CODES = {"TOT", "2TM", "3TM", "4TM", "5TM"}


def _active_filter_summary():
    """Short description of what's currently filtered, shown on the
    collapsed expander so active filters aren't invisible."""
    bits = []
    for label, val in [
        ("Contract", st.session_state.get("f_contract", "All")),
        ("Team", st.session_state.get("f_team", "All")),
        ("Position", st.session_state.get("f_posgroup", "All")),
        ("Verdict", st.session_state.get("f_verdict", "All")),
        ("Tier", st.session_state.get("f_tier", "All")),
    ]:
        if val and val != "All":
            # The conclusive-only option has a long explanatory label;
            # abbreviate it so the collapsed header stays readable.
            # Check the "+" variant FIRST -- both start with "Conclusive",
            # so the broader test would swallow it otherwise.
            if str(val).startswith("Conclusive +"):
                val = "Conclusive + Leaning"
            elif str(val).startswith("Conclusive"):
                val = "Conclusive only"
            bits.append(f"{label}: {val}")

    # Confidence is a multiselect, so it's a list rather than a string.
    conf_sel = st.session_state.get("f_conf") or []
    if conf_sel:
        bits.append(f"Confidence: {'/'.join(conf_sel)}")

    name = st.session_state.get("f_search", "")
    if name:
        bits.append(f'Name: "{name}"')
    return "  ·  ".join(bits) if bits else "none active"


with st.expander(f"Filters  ({_active_filter_summary()})", expanded=False):
    fr1 = st.columns(3)
    fr2 = st.columns(3)

    contract_options = ["All"] + sorted(df["contract_type"].dropna().unique().tolist())
    contract_choice = fr1[0].selectbox("Contract type", contract_options, key="f_contract")

    # Position GROUP (Guard / Wing / Big) rather than raw bref position:
    # the raw labels include hyphenated combos like "SG-SF" that fragment
    # the list, and a five-way split leaves thin, noisy pools. Dual-listed
    # players (Guard/Wing, Wing/Big) match either of their groups here.
    if "pos_group" in df.columns:
        group_values = set()
        for g in df["pos_group"].dropna().unique():
            for part in str(g).split("/"):
                if part and part != "--":
                    group_values.add(part)
        pos_group_options = ["All"] + sorted(group_values)
    else:
        pos_group_options = ["All"]
    pos_group_choice = fr1[1].selectbox(
        "Position group",
        pos_group_options,
        key="f_posgroup",
        help="Guard / Wing / Big. Players listed across two groups (e.g. GF) match either.",
    )

    teams = ["All"] + sorted(
        t for t in df["team"].dropna().unique().tolist() if t.upper() not in _AGGREGATE_TEAM_CODES
    )
    team_choice = fr1[2].selectbox("Team", teams, key="f_team")

    # "Conclusive only" is the high-signal view: everyone the model can
    # actually distinguish from fairly paid, in either direction. Usually
    # ~20% of players under contract, which is by design -- an 80%
    # interval is built to contain most of the league.
    _CONCLUSIVE = "Conclusive only (Under + Overpaid)"
    _DIRECTIONAL = "Conclusive + Leaning"
    verdict_options = [
        "All", _CONCLUSIVE, _DIRECTIONAL,
        "Underpaid", "Leaning underpaid", "Fairly paid", "Leaning overpaid", "Overpaid",
    ]
    verdict_choice = fr2[0].selectbox(
        "Value verdict",
        verdict_options,
        key="f_verdict",
        help=(
            "Based on whether a player's cap hit falls outside the $-model's 80% "
            "prediction interval. 'Fairly paid' means the model can't distinguish "
            "them from fair value -- pick 'Conclusive only' to hide those and see "
            "just the calls the model stands behind."
        ),
    )

    tier_options = ["All"]
    if "salary_tier" in df.columns:
        _order = ["Max", "Near-Max", "Mid-Level", "Rookie Scale", "Minimum", "Unknown"]
        present = set(df["salary_tier"].dropna().unique())
        tier_options += [t for t in _order if t in present]
    tier_choice = fr2[1].selectbox(
        "Salary tier",
        tier_options,
        key="f_tier",
        help="CBA-based bands: Max / Near-Max / Mid-Level / Rookie Scale / Minimum.",
    )

    # Player search in the top nav jumps to a player page; this one is a
    # leaderboard filter, which is a different job.
    # Multi-select rather than single-choice: "High or Medium" is the
    # natural way to ask this -- you want the estimates worth trusting,
    # which is usually more than one tier. Empty selection = no filter,
    # so the default state shows everyone.
    conf_choice = fr2[2].multiselect(
        "Estimate confidence",
        ["High", "Medium", "Low", "Unknown"],
        default=[],
        key="f_conf",
        placeholder="All",
        help=(
            "How much to trust this player's $-estimate, based on how wide his "
            "prediction interval is plus whether any inputs were missing or "
            "extrapolated. Independent of the verdict -- a 'Leaning overpaid, Low "
            "confidence' player is a much weaker call than a high-confidence one. "
            "Pick more than one to combine tiers; leave empty for all."
        ),
    )

    fr3 = st.columns(3)
    search = fr3[0].text_input("Filter by name", key="f_search")

    min_minutes = st.slider(
        "Minimum minutes played",
        min_value=0,
        max_value=int(df["MP"].max()) if df["MP"].notna().any() else 3000,
        value=500,
        step=50,
        key="f_minutes",
    )

filtered = df[df["MP"].fillna(0) >= min_minutes]
if contract_choice != "All":
    filtered = filtered[filtered["contract_type"] == contract_choice]
if pos_group_choice != "All" and "pos_group" in filtered.columns:
    # Substring match so dual-listed players ("Guard/Wing") appear under
    # both of their groups.
    filtered = filtered[
        filtered["pos_group"].fillna("").str.contains(pos_group_choice, case=False, na=False)
    ]
if team_choice != "All":
    # Free agents (no contract on file -- see model/merge.py) are excluded
    # when filtering to a specific team: their "team" reflects the last
    # squad they played for, not a guarantee they'll be there next season,
    # so they shouldn't be counted as still belonging to that team.
    is_fa = filtered["is_free_agent"] if "is_free_agent" in filtered.columns else False
    filtered = filtered[(filtered["team"] == team_choice) & (~is_fa)]
if verdict_choice != "All" and "market_value_verdict" in filtered.columns:
    if verdict_choice == _CONCLUSIVE:
        filtered = filtered[filtered["market_value_verdict"].isin(["Underpaid", "Overpaid"])]
    elif verdict_choice == _DIRECTIONAL:
        filtered = filtered[
            filtered["market_value_verdict"].isin(
                ["Underpaid", "Overpaid", "Leaning underpaid", "Leaning overpaid"]
            )
        ]
    else:
        filtered = filtered[filtered["market_value_verdict"] == verdict_choice]
if tier_choice != "All" and "salary_tier" in filtered.columns:
    filtered = filtered[filtered["salary_tier"] == tier_choice]
if conf_choice and "estimate_confidence" in filtered.columns:
    filtered = filtered[filtered["estimate_confidence"].isin(conf_choice)]
if search:
    filtered = filtered[filtered["player"].str.contains(search, case=False, na=False)]

if filtered.empty:
    st.warning("No players match these filters. Widen them to see results.")
    st.stop()

# --- Headline numbers ---------------------------------------------------
# 4-across is fine on a laptop but squeezes badly on a phone, so in
# compact mode these stack into two rows of two.
if compact_view:
    row1 = st.columns(2)
    row2 = st.columns(2)
    headline_cols = [row1[0], row1[1], row2[0], row2[1]]
else:
    headline_cols = st.columns(4)

def _money(v) -> str:
    """Compact $ formatting for headline tiles: $12.4M rather than
    $12,400,000, which doesn't fit in a metric tile."""
    if v is None or pd.isna(v):
        return "--"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{sign}${v / 1_000:.0f}K"
    return f"{sign}${v:.0f}"


# --- Team Payroll ---------------------------------------------------
# Built from the full roster (df), NOT the filtered leaderboard above --
# a team's total cap commitment shouldn't shrink because someone filtered
# to "Verdict: Underpaid". Purely descriptive context; doesn't feed the
# value model anywhere. See model/contracts.team_payroll_summary and the
# season-pairing note above for why cap_hit is a 2026-27 figure.
with st.expander("Team Payroll (2026-27)", expanded=False):
    st.caption(
        "Total roster cap commitment per team against the 2026-27 cap, tax, and apron "
        "lines. Approximate -- doesn't include dead money, cap holds, or other line items "
        "a real front-office cap sheet would track."
    )
    payroll = team_payroll_summary(df)
    if payroll.empty:
        st.info("No payroll data available.")
    else:
        display_payroll = payroll.rename(
            columns={
                "team": "Team",
                "total_payroll": "Total Payroll",
                "players_on_cap": "Players",
                "apron_status": "Status",
            }
        ).copy()
        display_payroll["Total Payroll"] = payroll["total_payroll"].apply(_money)
        st.dataframe(
            display_payroll[["Team", "Total Payroll", "Players", "Status"]],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            f"2026-27 lines -- Cap: ${SALARY_CAP / 1e6:.1f}M · Tax: ${TAX_LINE / 1e6:.1f}M · "
            f"1st Apron: ${FIRST_APRON / 1e6:.1f}M · 2nd Apron: ${SECOND_APRON / 1e6:.1f}M"
        )

# Market Value Surplus leads: it's dollar-denominated (so it doesn't
# inherit the non-linearity of subtracting percentile ranks) and it's
# the number a front office can act on directly.
_has_surplus = "market_value_surplus" in filtered.columns and filtered["market_value_surplus"].notna().any()

headline_cols[0].metric("Players shown", len(filtered))

if _has_surplus:
    surplus = filtered["market_value_surplus"]

    # Only consider players the model can actually distinguish from
    # fairly paid -- i.e. whose cap hit falls OUTSIDE its prediction
    # interval. Ranking on raw surplus alone surfaces players with huge
    # point-estimate gaps that sit entirely inside the model's own
    # uncertainty (typically rookies, whose salaries are CBA-slotted and
    # who sit outside the veterans-only training distribution).
    if "market_value_verdict" in filtered.columns:
        under = filtered[filtered["market_value_verdict"] == "Underpaid"]
        over = filtered[filtered["market_value_verdict"] == "Overpaid"]
    else:
        under = over = filtered

    if not under.empty:
        b = under["market_value_surplus"].idxmax()
        headline_cols[1].metric(
            "Biggest surplus",
            under.loc[b, "player"],
            delta=_money(under.loc[b, "market_value_surplus"]),
            help="Best value among players whose cap hit falls outside the model's prediction interval.",
        )
    else:
        headline_cols[1].metric("Biggest surplus", "-", help="No players outside the model's interval.")

    if not over.empty:
        w = over["market_value_surplus"].idxmin()
        headline_cols[2].metric(
            "Biggest overpay",
            over.loc[w, "player"],
            delta=_money(over.loc[w, "market_value_surplus"]),
            help="Worst value among players whose cap hit falls outside the model's prediction interval.",
        )
    else:
        headline_cols[2].metric("Biggest overpay", "-", help="No players outside the model's interval.")

    n_conclusive = len(under) + len(over)
    # Denominator excludes players with no cap hit on file (free agents,
    # verdict "Unknown") -- they can never be conclusive, so counting
    # them understates the rate and makes the model look less decisive
    # than it is.
    if "market_value_verdict" in filtered.columns:
        n_scored = int((filtered["market_value_verdict"] != "Unknown").sum())
    else:
        n_scored = len(filtered)
    share = (n_conclusive / n_scored * 100) if n_scored else 0

    headline_cols[3].metric(
        "Conclusive calls",
        f"{n_conclusive} of {n_scored}",
        delta=f"{share:.0f}% of players under contract",
        delta_color="off",
        help=(
            "Players whose cap hit falls OUTSIDE the model's 80% prediction interval. "
            "Roughly 20% is the expected rate -- an 80% interval is designed to contain "
            "most players. The rest sit within the model's margin of error, so their "
            "surplus figure shouldn't be read as a finding. Free agents (no cap hit) "
            "are excluded from the denominator."
        ),
    )
else:
    headline_cols[1].metric("Median value score", f"{filtered['value_score'].median():.1f}")
    headline_cols[2].metric(
        "Biggest bargain",
        filtered.loc[filtered["value_score"].idxmax(), "player"] if not filtered.empty else "-",
    )
    headline_cols[3].metric(
        "Biggest overpay",
        filtered.loc[filtered["value_score"].idxmin(), "player"] if not filtered.empty else "-",
    )

# ---------------------------------------------------------------------
# Friendly, Title Case display names for every column that can surface
# in the UI -- table headers, chart axis titles, hover tooltips, and
# color bar legends. Defined once here and reused everywhere so a raw
# field name like "total_guaranteed" or "value_score" can never leak
# through to the user.
#
# Plotly's `labels=` argument applies this to axes, hover fields AND the
# color scale in one shot, so each chart just passes the whole dict.
# ---------------------------------------------------------------------
_COLUMN_LABELS = {
    # Identity
    "player": "Player", "team": "Team", "pos": "Position", "pos_group": "Position Group",
    "AGE": "Age", "experience": "Experience", "contract_type": "Contract Type",
    # Playing time / box score
    "GP": "Games Played", "MP": "Minutes", "MPG": "Minutes Per Game",
    "PPG": "PPG", "RPG": "RPG", "APG": "APG", "SPG": "SPG", "BPG": "BPG",
    "FG_PCT": "FG%", "FG3_PCT": "3P%", "FT_PCT": "FT%",
    # Impact metrics
    "OBPM": "OBPM", "DBPM": "DBPM", "BPM": "BPM", "EPM": "EPM",
    "DARKO": "DARKO", "LEBRON": "LEBRON", "VORP": "VORP",
    "USG_PCT": "Usage %", "TS_PCT": "TS%",
    # databallr playstyle metrics
    "OnBall_Pct": "OnBall %", "rTS_rel": "rTS% (relative true shooting)",
    "OnBall_Pct_pctile": "OnBall % (percentile)",
    "rTS_rel_pctile": "rTS% (percentile)",
    "RAPM_3Y": "3Y RAPM", "PVAL": "PVAL", "NET_ON_OFF": "Net On/Off",
    # Skill value composites
    "FoulDraw_Value": "Foul-Drawing Value", "FTr": "Free Throw Rate",
    "FTA_total": "Free Throw Attempts", "FTA_per36": "FTA per 36",
    "estimated_market_value_inner_low": "Est. Value (inner low)",
    "estimated_market_value_inner_high": "Est. Value (inner high)",
    "Rim_Scoring_Value": "Rim Scoring Value", "FG_PCT_rim": "FG% at Rim",
    "FGA_share_rim": "Rim Shot Share", "rim_FGA_total": "Rim Attempts",
    "rim_FGA_per36": "Rim Attempts per 36", "avg_shot_dist": "Avg Shot Distance",
    # Percentiles / value
    "production_pctile": "Production Percentile",
    "salary_pctile": "Salary Percentile",
    "estimated_market_value_pctile": "Est. Market Value Percentile",
    "value_score": "Value Score", "value_ratio": "Value Ratio",
    "value_score_pctile": "Value Score Percentile",
    # Contract
    "cap_hit": "Cap Hit", "salary": "Salary",
    "estimated_market_value": "Est. Market Value",
    "estimated_market_value_low": "Est. Value (low)",
    "estimated_market_value_high": "Est. Value (high)",
    "market_value_verdict": "Verdict",
    "estimate_confidence": "Confidence", "estimate_rel_width": "Interval Width (x est.)",
    "salary_tier": "Salary Tier", "pct_of_max": "% of Max",
    "is_max_contract": "At Max", "rank_in_salary_tier": "Rank in Tier",
    "n_in_salary_tier": "Players in Tier", "max_salary_for_tier": "Tier Max",
    "market_value_surplus": "Market Value Surplus",
    "years_remaining": "Years Remaining", "total_guaranteed": "Total Guaranteed",
    "bird_rights_status": "Bird Rights", "is_free_agent": "Free Agent",
}

# Shared bronze -> silver -> gold scale (not a named Plotly scale, whose
# direction is easy to get backwards) so every chart below matches the
# player-page bars exactly: bronze = bad/overpaid, gold = good/bargain.
_MEDAL_SCALE = [
    (0.0, "rgb(176,111,62)"),
    (0.5, "rgb(200,200,203)"),
    (1.0, "rgb(212,175,55)"),
]


# Plotly's default toolbar and drag-to-zoom are fiddly on a touchscreen.
# On mobile the chart needs to be roughly square (a wide, short chart on
# a narrow screen squashes the point cloud into an unreadable band), the
# colorbar has to go (it steals ~20% of the width), and the marker/font
# sizes need bumping so they're legible at phone scale.
_CHART_HEIGHT = 460 if compact_view else 550
_CHART_CONFIG = {"displayModeBar": not compact_view, "scrollZoom": False}


def _plot(fig, key: str):
    """Render a scatter and turn a click on any point into a jump to that
    player's page.

    Plotly selection events come back with whatever was passed as
    `custom_data` on the trace, so each scatter carries the player name
    there. We stash the clicked name under a private session_state key
    and rerun -- see the handler near the top of this file for why it
    can't be written straight into the search widget's own state.
    """
    event = st.plotly_chart(
        _themed(fig),
        width="stretch",
        config=_CHART_CONFIG,
        key=key,
        on_select="rerun",
        selection_mode="points",
    )

    points = []
    try:
        points = event.selection.points  # Streamlit >= 1.35
    except AttributeError:
        points = (event or {}).get("selection", {}).get("points", [])

    for pt in points:
        custom = pt.get("customdata")
        if custom:
            st.session_state["_pending_player"] = custom[0]
            st.rerun()


def _hover(cols: list) -> list:
    """Trim hover fields on mobile -- a 7-row tooltip runs off the edge
    of a phone screen and covers the chart you're trying to read.

    Also drops columns that aren't in the data. The deployed build reads
    the public CSV, which has the raw third-party metrics stripped out
    (see make_public_data.py), and Plotly raises rather than skipping if
    you hand it a column that doesn't exist.
    """
    cols = [c for c in cols if c in filtered.columns]
    return cols[:2] if compact_view else cols


def _themed(fig, height=None):
    fig.update_layout(
        height=height or _CHART_HEIGHT,
        plot_bgcolor=CARD_BACKGROUND,
        paper_bgcolor=CARD_BACKGROUND,
        font=dict(color=TEXT),
    )
    if compact_view:
        fig.update_layout(
            # Tight margins: every pixel counts on a 390px-wide screen.
            margin=dict(l=44, r=10, t=10, b=44),
            # The continuous colorbar is the biggest space thief and the
            # legend it provides is explained in the caption anyway.
            coloraxis_showscale=False,
            font=dict(color=TEXT, size=11),
            xaxis=dict(title=dict(font=dict(size=11)), tickfont=dict(size=10), nticks=6),
            yaxis=dict(title=dict(font=dict(size=11)), tickfont=dict(size=10), nticks=6),
            # Touch-friendly hover: one label, not a stacked block that
            # runs off the edge of the screen.
            hovermode="closest",
            hoverlabel=dict(font=dict(size=12)),
            dragmode=False,
        )
        fig.update_traces(marker=dict(size=7, opacity=0.85))
    return fig


# --- Scatter plots --------------------------------------------------
st.subheader("Scatter plots")
st.caption("Click any point to open that player's page.")
tab1, tab2, tab3, tab4 = st.tabs(
    ["Production vs. Salary", "Salary vs. Market Value", "Aging Curve", "Playstyle"]
)

with tab1:
    fig = px.scatter(
        filtered,
        x="salary_pctile",
        y="production_pctile",
        color="value_score",
        color_continuous_scale=_MEDAL_SCALE,
        hover_name="player",
            custom_data=["player"],
        hover_data=_hover(["team", "contract_type", "cap_hit", "BPM", "EPM", "DARKO", "LEBRON"]),
        labels=_COLUMN_LABELS,
    )
    fig.add_shape(type="line", x0=0, y0=0, x1=100, y1=100, line=dict(dash="dash", color="#4B5563"))
    _plot(fig, "scatter_prod_salary")
    st.caption(
        "Bargains sit above the diagonal (producing more than they're paid); "
        "overpays sit below it."
    )

with tab2:
    # Similar in spirit to the production-vs-salary plot, but the y-axis
    # is the $-estimator's *predicted* market value percentile instead of
    # raw production -- so it also reflects age/experience/minutes, not
    # just on-court output. Correlated with tab 1, but not identical:
    # a young, cheap, productive player can rank higher here than on raw
    # production alone, since the model expects their value to keep rising.
    if "estimated_market_value_pctile" in filtered.columns:
        fig = px.scatter(
            filtered,
            x="salary_pctile",
            y="estimated_market_value_pctile",
            color="market_value_surplus",
            color_continuous_scale=_MEDAL_SCALE,
            hover_name="player",
            custom_data=["player"],
            hover_data=_hover(["team", "contract_type", "cap_hit", "estimated_market_value", "AGE"]),
            labels=_COLUMN_LABELS,
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=100, y1=100, line=dict(dash="dash", color="#4B5563"))
        _plot(fig, "scatter_salary_mv")
        st.caption(
            "Same read as the first tab (above the line = paid less than the model thinks "
            "they're worth), but driven by the $-estimator's prediction rather than raw "
            "production percentile."
        )
    else:
        st.info("Est. market value not available -- run the $-estimator step of the pipeline.")

with tab3:
    fig = px.scatter(
        filtered,
        x="AGE",
        y="value_score",
        color="value_score",
        color_continuous_scale=_MEDAL_SCALE,
        hover_name="player",
            custom_data=["player"],
        hover_data=_hover(["team", "contract_type", "cap_hit", "production_pctile"]),
        labels=_COLUMN_LABELS,
    )
    fig.add_shape(
        type="line",
        x0=filtered["AGE"].min() if filtered["AGE"].notna().any() else 18,
        x1=filtered["AGE"].max() if filtered["AGE"].notna().any() else 40,
        y0=0,
        y1=0,
        line=dict(dash="dash", color="#4B5563"),
    )
    _plot(fig, "scatter_aging")
    st.caption("Where value tends to concentrate across the aging curve -- above the dashed line is a bargain at that age.")

with tab4:
    # Prefer raw values (local build), fall back to percentile ranks
    # (deployed build, where make_public_data.py strips the raw
    # databallr values but keeps the percentiles). The chart reads the
    # same either way -- only the axis units change.
    if {"OnBall_Pct", "rTS_rel"}.issubset(filtered.columns):
        x_col, y_col = "OnBall_Pct", "rTS_rel"
        axis_note = ""
    elif {"OnBall_Pct_pctile", "rTS_rel_pctile"}.issubset(filtered.columns):
        x_col, y_col = "OnBall_Pct_pctile", "rTS_rel_pctile"
        axis_note = " Axes are percentile ranks."
    else:
        x_col = y_col = None

    if x_col:
        fig = px.scatter(
            filtered,
            x=x_col,
            y=y_col,
            color="production_pctile",
            color_continuous_scale=_MEDAL_SCALE,
            hover_name="player",
            custom_data=["player"],
            hover_data=_hover(["team", "contract_type", "PVAL", "RAPM_3Y", "NET_ON_OFF"]),
            labels=_COLUMN_LABELS,
        )
        # Reference line: zero for raw rTS% (league average), 50 for the
        # percentile version (median).
        midline = 0 if y_col == "rTS_rel" else 50
        fig.add_shape(
            type="line",
            x0=filtered[x_col].min(), x1=filtered[x_col].max(),
            y0=midline, y1=midline, line=dict(dash="dash", color="#4B5563"),
        )
        _plot(fig, "scatter_playstyle")
        st.caption(
            "Playstyle showcase: high OnBall% + high rTS% = efficient, high-usage shot "
            "creators. Colored by production percentile." + axis_note
        )
    else:
        st.info("databallr playstyle metrics not available -- add data/manual/databallr_metrics.csv and re-run the pipeline.")

# --- Player table -----------------------------------------------------
st.subheader("Player table")
st.caption("Click **View** on any row to open that player's page. Column headers sort.")

# Three curated column groups. "value_score" and "production_pctile" are
# deliberately placed right after the identity columns (player/team/pos)
# on every tab, per Calvin's request that both stay primary,
# front-and-center metrics everywhere -- not just their own dedicated tab.
_BASIC_STATS_COLUMNS = [
    "player", "team", "pos", "market_value_verdict", "estimate_confidence", "market_value_surplus", "value_score",
    "production_pctile", "FoulDraw_Value", "Rim_Scoring_Value",
    "AGE", "experience", "contract_type", "GP", "MP",
    "PPG", "RPG", "APG", "SPG", "BPG", "FG_PCT", "FG3_PCT", "FT_PCT",
]
_ADVANCED_METRICS_COLUMNS = [
    "player", "team", "pos", "market_value_verdict", "estimate_confidence", "market_value_surplus", "value_score",
    "production_pctile", "OBPM", "DBPM", "BPM", "EPM", "DARKO",
    "OnBall_Pct", "rTS_rel", "RAPM_3Y", "PVAL", "NET_ON_OFF", "Rim_Scoring_Value", "FoulDraw_Value",
]
_CONTRACT_COLUMNS = [
    "player", "team", "pos", "market_value_surplus", "market_value_verdict", "estimate_confidence", "salary_tier", "cap_hit", "estimated_market_value",
    "value_score", "production_pctile", "contract_type", "salary_pctile", "value_ratio",
    "years_remaining", "total_guaranteed", "bird_rights_status",
]

_IDENTITY_COLUMNS = ["player", "team", "pos"]
_SORT_CANDIDATES = ["market_value_surplus", "value_score", "production_pctile", "cap_hit", "estimated_market_value"]

# In compact/mobile mode each tab shows only these columns instead of the
# full set above -- enough to answer "who's good and who's overpaid?"
# without horizontal scrolling on a phone. The full data is always still
# one toggle (or one CSV download) away.
_COMPACT_COLUMNS = {
    "basic": ["player", "team", "market_value_verdict", "estimate_confidence", "market_value_surplus", "value_score", "PPG"],
    "advanced": ["player", "team", "market_value_verdict", "production_pctile", "BPM", "EPM", "DARKO"],
    "contract": ["player", "team", "market_value_verdict", "market_value_surplus", "cap_hit"],
}

# Decimal precision per column -- Streamlit's default dataframe renderer
# shows full float precision otherwise (binary floating-point noise and
# all), which is what made the table look like it had "insane" decimals.
# Whole numbers for anything that's genuinely discrete (GP, age, years of
# experience...); 1 decimal for per-game/impact stats (standard box-score
# precision); 3 decimals (thousandths) for shooting percentages, since
# ".502" is the conventional way those are shown; whole-percentile for
# the 0-100 percentile columns; $ with commas, no cents, for money.
_FORMAT_SPEC = {
    "AGE": "{:.0f}", "experience": "{:.0f}", "GP": "{:.0f}", "MP": "{:.0f}", "years_remaining": "{:.0f}",
    "PPG": "{:.1f}", "RPG": "{:.1f}", "APG": "{:.1f}", "SPG": "{:.1f}", "BPG": "{:.1f}",
    "OBPM": "{:.1f}", "DBPM": "{:.1f}", "BPM": "{:.1f}", "EPM": "{:.1f}", "DARKO": "{:.1f}",
    "OnBall_Pct": "{:.1f}", "rTS_rel": "{:+.1f}", "RAPM_3Y": "{:+.1f}", "PVAL": "{:+.1f}", "NET_ON_OFF": "{:+.1f}",
    "FG_PCT": "{:.3f}", "FG3_PCT": "{:.3f}", "FT_PCT": "{:.3f}",
    "Rim_Scoring_Value": "{:.0f}", "FoulDraw_Value": "{:.0f}",
    "FG_PCT_rim": "{:.3f}", "rim_FGA_total": "{:.0f}", "rim_FGA_per36": "{:.1f}",
    "FTA_total": "{:.0f}", "FTA_per36": "{:.1f}", "FTr": "{:.3f}",
    "pct_of_max": "{:.0%}", "rank_in_salary_tier": "{:.0f}",
    "production_pctile": "{:.0f}", "salary_pctile": "{:.0f}",
    "value_score": "{:+.0f}", "value_ratio": "{:.2f}",
    "cap_hit": "${:,.0f}", "estimated_market_value": "${:,.0f}",
    "estimated_market_value_low": "${:,.0f}", "estimated_market_value_high": "${:,.0f}",
    "market_value_surplus": "${:+,.0f}", "total_guaranteed": "${:,.0f}",
}


# The three verdicts map onto the same medal language used for the
# percentile bars and Value Score cells: gold = good value for the team,
# silver = the model can't distinguish this from fair, bronze = poor
# value. Using discrete colors (rather than the continuous scale) keeps
# the three categories visually distinct at a glance.
_VERDICT_COLORS = {
    "Underpaid": "rgb(212,175,55)",           # gold -- confident
    "Leaning underpaid": "rgb(206,188,129)",  # gold/silver blend -- probable
    "Fairly paid": "rgb(200,200,203)",        # silver
    "Leaning overpaid": "rgb(188,156,133)",   # silver/bronze blend -- probable
    "Overpaid": "rgb(176,111,62)",            # bronze -- confident
    "Unknown": None,
}


def _style_table(display_df: pd.DataFrame, medal_columns: dict):
    """Color-code one or more columns with the bronze/silver/gold medal
    scale (same one used everywhere else in the app), and cap every
    numeric column to a sane number of decimals.

    medal_columns: {display_column_name: percentile_series_0_to_100}
    """

    def _make_highlighter(colors):
        return lambda col: [f"background-color: {c}; color: #0B0F1A; font-weight: 600;" if c else "" for c in colors]

    styler = display_df.style
    for col_name, pctiles in medal_columns.items():
        colors = [pctile_color(p) if pd.notna(p) else None for p in pctiles]
        styler = styler.apply(
            lambda col, _colors=colors, _name=col_name: (
                _make_highlighter(_colors)(col) if col.name == _name else ["" for _ in col]
            ),
            axis=0,
        )

    # Discrete medal coloring for the Verdict column.
    if "Verdict" in display_df.columns:
        verdict_colors = [_VERDICT_COLORS.get(v) for v in display_df["Verdict"]]
        styler = styler.apply(
            lambda col, _colors=verdict_colors: (
                _make_highlighter(_colors)(col) if col.name == "Verdict" else ["" for _ in col]
            ),
            axis=0,
        )

    format_dict = {
        _COLUMN_LABELS.get(raw, raw): fmt
        for raw, fmt in _FORMAT_SPEC.items()
        if _COLUMN_LABELS.get(raw, raw) in display_df.columns
    }
    styler = styler.format(format_dict, na_rep="--")
    return styler


def _render_table_tab(base_df: pd.DataFrame, columns: list, key: str):
    if compact_view:
        columns = _COMPACT_COLUMNS.get(key, columns)
    cols_present = [c for c in columns if c in base_df.columns]
    has_pctile = "value_score_pctile" in base_df.columns
    tab_df = base_df[cols_present + (["value_score_pctile"] if has_pctile else [])].copy()

    # Hide rows with no data: if every stat column for this tab (i.e.
    # everything except player/team/pos) is blank, the row is pure noise
    # (e.g. a player who didn't log per-game stats this season).
    identity_cols = [c for c in _IDENTITY_COLUMNS if c in cols_present]
    value_cols = [c for c in cols_present if c not in identity_cols]
    if value_cols:
        tab_df = tab_df[tab_df[value_cols].notna().any(axis=1)]

    sort_options = [c for c in _SORT_CANDIDATES if c in cols_present] or [cols_present[-1]]
    sort_col = st.selectbox(
        "Sort by", sort_options, format_func=lambda c: _COLUMN_LABELS.get(c, c), index=0, key=f"sort_{key}"
    )
    tab_df = tab_df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    value_score_pctiles = tab_df.pop("value_score_pctile") if has_pctile else pd.Series([None] * len(tab_df))
    # production_pctile is already a 0-100 percentile itself, so it colors
    # off its own value -- no separate helper column needed, unlike Value
    # Score (which needs value_score_pctile computed separately since raw
    # value_score isn't itself 0-100).
    production_pctiles = tab_df["production_pctile"] if "production_pctile" in tab_df.columns else None

    display_df = tab_df.rename(columns=_COLUMN_LABELS)

    medal_columns = {}
    if "Value Score" in display_df.columns:
        medal_columns["Value Score"] = value_score_pctiles
    if production_pctiles is not None:
        medal_columns["Production Pctile"] = production_pctiles

    # Skill Value scores are themselves 0-100 composites, so they colour
    # off their own value -- no separate percentile column needed.
    for raw_col, label in (("FoulDraw_Value", "Foul-Drawing Value"),
                           ("Rim_Scoring_Value", "Rim Scoring Value")):
        if label in display_df.columns:
            medal_columns[label] = pd.to_numeric(display_df[label], errors="coerce")

    # Keep a clean copy for the CSV download BEFORE turning the Player
    # column into links -- otherwise the exported file would contain
    # "?player=Ryan Rollins" instead of the name.
    download_df = display_df.copy()

    # Navigation via a link column rather than row selection. Streamlit's
    # row-selection UI adds a checkbox column, and because the dataframe
    # renders to a canvas (glide-data-grid) that checkbox can't be hidden
    # with CSS. Making the Player column itself a LinkColumn means the
    # name IS the click target, with no extra column and no checkbox, and
    # column-header sorting still works.
    #
    # The name is deliberately NOT percent-encoded in the stored value:
    # display_text runs its regex against this raw string, so encoding it
    # here would render accented names as "Nikola%20Joki%C4%87". Browsers
    # encode on navigation anyway, and Streamlit decodes on the way back.
    column_config = {}
    if "Player" in display_df.columns:
        display_df = display_df.copy()
        display_df["Player"] = [f"?player={p}" for p in display_df["Player"]]
        column_config["Player"] = st.column_config.LinkColumn(
            "Player",
            display_text=r"\?player=(.*)",
            help="Click a name to open that player's page",
        )

    st.dataframe(
        _style_table(display_df, medal_columns),
        width="stretch",
        height=420 if compact_view else 600,
        key=f"table_{key}",
        column_config=column_config,
    )
    st.download_button(
        "Download this view as CSV",
        download_df.to_csv(index=False).encode("utf-8"),
        file_name=f"nba_player_value_{key}.csv",
        mime="text/csv",
        key=f"dl_{key}",
    )


basic_tab, advanced_tab, contract_tab = st.tabs(["Basic Stats", "Advanced Metrics", "Contract Info"])
with basic_tab:
    _render_table_tab(filtered, _BASIC_STATS_COLUMNS, "basic")
with advanced_tab:
    _render_table_tab(filtered, _ADVANCED_METRICS_COLUMNS, "advanced")
with contract_tab:
    _render_table_tab(filtered, _CONTRACT_COLUMNS, "contract")

st.download_button(
    "Download full raw data as CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="nba_player_value_filtered_full.csv",
    mime="text/csv",
)
