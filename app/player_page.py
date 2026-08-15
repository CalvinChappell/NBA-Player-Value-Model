"""
Individual player page, styled after Baseball Savant's player profile:
a compact header, three headline percentile bars (Value Score, Market
Value Surplus, Estimated Market Value), then Box Score / Impact Metrics
/ Production-vs-Salary grouped into two condensed columns, followed by
a full-width Playstyle & Advanced Impact section (OnBall%, rTS%, 3Y
RAPM, PVAL, Net On/Off -- sourced from databallr.com).
"""

import streamlit as st

from app.percentile_bars import render_percentile_bars
from app.theme import TRACK

_DIVIDER_HTML = f"<hr style='margin: 0.25rem 0 0.75rem 0; border-color: {TRACK};'>"


def _fmt(value, kind: str) -> str:
    if value is None or (isinstance(value, float) and value != value):  # NaN check w/o numpy import
        return "--"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "int1":
        return f"{value:.1f}"
    if kind == "money":
        return f"${value:,.0f}"
    if kind == "signed_money":
        sign = "+" if value >= 0 else "-"
        return f"{sign}${abs(value):,.0f}"
    if kind == "signed_int":
        return f"{value:+.0f}"
    if kind == "signed1":
        return f"{value:+.1f}"
    if kind == "pct_raw":
        # Value is already a percent number (e.g. 26.2 meaning 26.2%),
        # unlike "pct" which expects a 0-1 fraction and multiplies by 100.
        return f"{value:.1f}%"
    if kind == "int":
        return f"{value:.0f}"
    return str(value)


def _bar_row(row, metric: str, label: str, kind: str, pos_relative: bool = False) -> tuple:
    """pos_relative=True reads the {metric}_pctile_pos column (rank within
    the player's position group) instead of the league-wide percentile.
    Falls back to league-wide if the position column isn't present, so
    the page still renders against an older CSV.
    """
    raw = row.get(metric)
    pct = None
    if pos_relative:
        pct = row.get(f"{metric}_pctile_pos")
    if pct is None or pct != pct:
        pct = row.get(f"{metric}_pctile")
    pct = None if pct is None or pct != pct else float(pct)
    return (label, _fmt(raw, kind), pct)


def render_player_page(df, default_player: str | None = None, compact: bool = False):
    """compact=True trims bar heights and stacks the two stat columns
    into one, so the page stays readable on a phone (see the mobile CSS
    in app/theme.py for the rest of the responsive handling).
    """
    players_sorted = df.sort_values("player")["player"].tolist()
    if not players_sorted:
        st.warning("No players available.")
        return

    # The player search now lives in the top nav bar (app/streamlit_app.py),
    # so this page just renders whoever was picked there. Falls back to the
    # first player alphabetically if nothing was selected yet.
    selected = default_player if default_player in players_sorted else players_sorted[0]

    row = df[df["player"] == selected].iloc[0].to_dict()

    bar_h = 22 if compact else 26
    headline_h = 26 if compact else 30

    # League-wide vs. position-relative percentiles. League-wide is the
    # default (it's what the composite production score and value score
    # are built on); position-relative answers "...but is that good for
    # a center?". See model/positions.py for the Guard/Wing/Big grouping
    # and how dual-listed players are handled.
    pos_group = row.get("pos_group", "--")
    has_pos_pctiles = any(k.endswith("_pctile_pos") for k in row)
    pos_relative = False
    if has_pos_pctiles:
        scope = st.radio(
            "Percentile comparison",
            ["League-wide", f"Position group ({pos_group})"],
            horizontal=True,
            key="pctile_scope",
        )
        pos_relative = scope.startswith("Position")

    # --- Header (compact, single row) -----------------------------------
    # On a phone a 3-across header squeezes the cap hit into an unreadable
    # sliver, so stack name / contract / cap hit vertically instead.
    # Cap hit / market value / surplus are shown as their own tiles just
    # below, so the header only carries identity + contract type.
    _caption = (
        f"{row.get('team', '--')} · {row.get('pos', '--')} "
        f"({row.get('pos_group', '--')}) · Age {_fmt(row.get('AGE'), 'int')} · "
        f"{row.get('contract_type', '--')}"
    )
    st.markdown(f"### {row['player']}")
    st.caption(_caption)

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    # --- Headline verdict ------------------------------------------------
    # Market Value Surplus leads: it's dollar-denominated, so unlike Value
    # Score (a difference of percentile ranks) it doesn't compress the
    # top of the salary distribution, and it's the number a front office
    # can act on. Shown as big metric tiles before the bars.
    surplus = row.get("market_value_surplus")
    est_value = row.get("estimated_market_value")
    cap_hit = row.get("cap_hit")

    # Surplus gets its own full-width row on mobile so the headline
    # number isn't crushed into a third of a phone screen.
    if compact:
        v1, v2 = st.columns(2)
        v3 = st.container()
    else:
        v1, v2, v3 = st.columns(3)

    lo = row.get("estimated_market_value_low")
    hi = row.get("estimated_market_value_high")
    verdict = row.get("market_value_verdict")

    v1.metric("Cap Hit", _fmt(cap_hit, "money"))
    v2.metric(
        "Est. Market Value",
        _fmt(est_value, "money"),
        help="Point estimate from the $-model. See the range below it for the model's uncertainty.",
    )
    if surplus is not None and surplus == surplus:
        # The verdict comes from the prediction interval, not the raw
        # surplus: a gap that sits inside the model's uncertainty band
        # isn't something the model can actually distinguish from zero.
        if verdict == "Underpaid":
            delta_txt, delta_color = "Underpaid", "normal"
        elif verdict == "Overpaid":
            delta_txt, delta_color = "Overpaid", "inverse"
        else:
            delta_txt, delta_color = "Within model range", "off"
        v3.metric(
            "Market Value Surplus",
            _fmt(surplus, "signed_money"),
            delta=delta_txt,
            delta_color=delta_color,
        )
    else:
        v3.metric("Market Value Surplus", "--")

    # Max-contract players sit against the CBA ceiling, so the surplus
    # number is structurally misleading for them -- say so explicitly
    # rather than letting the reader over-interpret it.
    tier = row.get("salary_tier")
    if tier in ("Max", "Near-Max"):
        rank = row.get("rank_in_salary_tier")
        n_tier = row.get("n_in_salary_tier")
        rank_txt = ""
        if rank is not None and rank == rank and n_tier is not None and n_tier == n_tier:
            rank_txt = (
                f" Among the {int(n_tier)} players on {tier.lower()} deals, he ranks "
                f"**#{int(rank)}** by production."
            )
        st.info(
            f"**{tier} contract** ({_fmt(row.get('pct_of_max', 0) * 100, 'int')}% of his "
            f"CBA tier maximum). Salaries are capped, so the surplus figure understates "
            f"elite players -- no team could have paid him more.{rank_txt}"
        )

    # Rookie-scale players are predicted by a model trained only on
    # veterans, so their estimate is extrapolation outside the training
    # distribution -- and their salary is CBA-slotted rather than
    # market-set, which inflates surplus mechanically.
    if row.get("contract_type") == "Rookie Scale":
        st.warning(
            "**Rookie-scale contract.** The $-model is trained on veterans only, so this "
            "estimate extrapolates outside its training data -- minutes played tend to "
            "inflate it. Treat the surplus as indicative at best."
        )

    if lo is not None and lo == lo and hi is not None and hi == hi:
        if verdict == "Fairly paid":
            st.caption(
                f"Model's 80% range: **{_fmt(lo, 'money')} – {_fmt(hi, 'money')}**. "
                f"This cap hit falls inside that range, so the surplus above is within "
                "the model's margin of error -- read it as fairly paid, not as a bargain."
            )
        else:
            st.caption(
                f"Model's 80% range: **{_fmt(lo, 'money')} – {_fmt(hi, 'money')}**. "
                f"This cap hit falls outside that range, so the gap is a call the model "
                "actually supports."
            )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    # --- Headline: Market Value Surplus / Value Score / Est. Market Value --
    headline_rows = [
        _bar_row(row, "market_value_surplus", "Market Value Surplus", "signed_money"),
        _bar_row(row, "value_score", "Value Score", "signed_int"),
        _bar_row(row, "estimated_market_value", "Est. Market Value", "money"),
    ]
    st.plotly_chart(
        render_percentile_bars(headline_rows, height_per_row=headline_h),
        width="stretch",
        config={"displayModeBar": False},
    )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    # --- Two-column condensed stat groups --------------------------------
    # Side-by-side on desktop; stacked full-width on mobile, since two
    # half-width bar charts on a phone are unreadably narrow.
    if compact:
        left = st.container()
        right = st.container()
    else:
        left, right = st.columns(2)

    with left:
        st.markdown("**Box Score** (per game)")
        box_score_rows = [
            _bar_row(row, "PPG", "PTS", "int1", pos_relative),
            _bar_row(row, "RPG", "REB", "int1", pos_relative),
            _bar_row(row, "APG", "AST", "int1", pos_relative),
            _bar_row(row, "SPG", "STL", "int1", pos_relative),
            _bar_row(row, "BPG", "BLK", "int1", pos_relative),
            _bar_row(row, "FG_PCT", "FG%", "pct", pos_relative),
            _bar_row(row, "FG3_PCT", "3P%", "pct", pos_relative),
            _bar_row(row, "FT_PCT", "FT%", "pct", pos_relative),
        ]
        st.plotly_chart(
            render_percentile_bars(box_score_rows, height_per_row=bar_h),
            width="stretch",
            config={"displayModeBar": False},
        )

    with right:
        st.markdown("**Impact Metrics**")
        advanced_rows = [
            _bar_row(row, "OBPM", "OBPM", "int1", pos_relative),
            _bar_row(row, "DBPM", "DBPM", "int1", pos_relative),
            _bar_row(row, "BPM", "BPM", "int1", pos_relative),
            _bar_row(row, "EPM", "EPM", "int1", pos_relative),
            _bar_row(row, "DARKO", "DARKO", "int1", pos_relative),
        ]
        st.plotly_chart(
            render_percentile_bars(advanced_rows, height_per_row=bar_h),
            width="stretch",
            config={"displayModeBar": False},
        )

        st.markdown("**Production vs. Salary**")
        # production_pctile and salary_pctile are already 0-100 percentiles
        # (not raw stats), so build these two rows directly instead of via
        # _bar_row -- there's no "production_pctile_pctile" column to look up.
        production_pctile = row.get("production_pctile")
        production_pctile = float(production_pctile) if production_pctile == production_pctile else None
        salary_pctile = row.get("salary_pctile")
        salary_pctile = float(salary_pctile) if salary_pctile == salary_pctile else None
        value_rows = [
            ("Production", _fmt(production_pctile, "int"), production_pctile),
            ("Salary", _fmt(row.get("cap_hit"), "money"), salary_pctile),
        ]
        st.plotly_chart(
            render_percentile_bars(value_rows, height_per_row=bar_h),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    # --- Playstyle & Advanced Impact (databallr.com) ----------------------
    st.markdown("**Playstyle & Advanced Impact**")
    playstyle_rows = [
        _bar_row(row, "OnBall_Pct", "OnBall %", "pct_raw", pos_relative),
        _bar_row(row, "rTS_rel", "rTS%", "signed1", pos_relative),
        _bar_row(row, "RAPM_3Y", "3Y RAPM", "signed1", pos_relative),
        _bar_row(row, "PVAL", "PVAL", "signed1", pos_relative),
        _bar_row(row, "NET_ON_OFF", "Net On/Off", "signed1", pos_relative),
    ]
    st.plotly_chart(
        render_percentile_bars(playstyle_rows, height_per_row=bar_h),
        width="stretch",
        config={"displayModeBar": False},
    )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    # --- Skill Value scores (model/value_metrics.py) ----------------------
    # Baseball-style efficiency x volume composites. Each is a 0-100
    # score in its own right, so the bar shows the score and its
    # percentile rank among qualified players.
    st.markdown("**Skill Value Scores**")
    value_metric_rows = [
        _bar_row(row, "Rim_Scoring_Value", "Rim Scoring", "int", pos_relative),
        _bar_row(row, "FoulDraw_Value", "Foul Drawing", "int", pos_relative),
    ]
    st.plotly_chart(
        render_percentile_bars(value_metric_rows, height_per_row=bar_h),
        width="stretch",
        config={"displayModeBar": False},
    )

    def _is_true(v) -> bool:
        return v is True or v == "True" or v == 1

    notes = []

    rim_att = row.get("rim_FGA_total")
    if _is_true(row.get("Rim_low_sample")):
        notes.append(
            f"⚠️ **Rim Scoring** rests on a small sample "
            f"({_fmt(rim_att, 'int')} attempts inside 3 ft)."
        )
    elif rim_att is not None and rim_att == rim_att:
        notes.append(
            f"**Rim Scoring** = FG% inside 3 ft (55%) + rim attempts per 36 (45%), "
            f"on {_fmt(rim_att, 'int')} attempts. Efficiency leads here because a "
            "missed layup is a dead possession."
        )

    fta_total = row.get("FTA_total")
    if _is_true(row.get("FoulDraw_low_sample")):
        notes.append(
            f"⚠️ **Foul Drawing** rests on a small sample "
            f"({_fmt(fta_total, 'int')} free throw attempts)."
        )
    elif fta_total is not None and fta_total == fta_total:
        notes.append(
            f"**Foul Drawing** = trips to the line (60%) + FT% (40%), on "
            f"{_fmt(fta_total, 'int')} attempts. Volume leads here because drawing "
            "a foul has value even when the free throw misses."
        )

    for note in notes:
        st.caption(note)
