"""
Baseball-Savant-style horizontal percentile bar charts.

Savant's player pages show every stat as a row: label on the left, a
horizontal bar colored on a bronze (bad) -> silver (average) -> gold
(good) scale filled to the player's percentile, with a dark tick
mark right at the fill's edge (so it's unambiguous exactly where the
bar stops, rather than relying on the color transition alone) and the
percentile number + raw stat value labeled off to the right.

All metrics used in this project are already "higher = better" (PPG,
BPM, EPM, DARKO, etc), so no inversion logic is needed -- pct=0 is
always bronze, pct=100 is always gold.
"""

import plotly.graph_objects as go

from app.theme import CARD_BACKGROUND, TEXT, TICK, TRACK


def pctile_color(pct: float) -> str:
    """Bronze (0, bad) -> silver (50, average) -> gold (100, good) medal scale.

    Public so other modules (e.g. app/streamlit_app.py, to color-code the
    Value Score column in the player table the same way it's colored
    everywhere else) can reuse the exact same scale instead of redefining it.
    """
    if pct is None:
        return "#cccccc"
    pct = max(0.0, min(100.0, pct))
    bronze = (176, 111, 62)
    silver = (200, 200, 203)
    gold = (212, 175, 55)
    if pct <= 50:
        t = pct / 50
        c = tuple(int(bronze[i] + (silver[i] - bronze[i]) * t) for i in range(3))
    else:
        t = (pct - 50) / 50
        c = tuple(int(silver[i] + (gold[i] - silver[i]) * t) for i in range(3))
    return f"rgb({c[0]},{c[1]},{c[2]})"


_pctile_color = pctile_color  # backwards-compatible alias for in-module use


def render_percentile_bars(stats: list[tuple[str, str, float]], height_per_row: int = 34) -> go.Figure:
    """stats: list of (label, formatted_raw_value, percentile_0_to_100_or_None),
    given in the order you want them to appear top-to-bottom.
    """
    # Plotly draws y-categories bottom-to-top, so reverse to get the
    # requested top-to-bottom reading order.
    ordered = list(reversed(stats))
    labels = [s[0] for s in ordered]
    raw_values = [s[1] for s in ordered]
    pctiles = [s[2] if s[2] is not None else 0 for s in ordered]
    colors = [_pctile_color(s[2]) for s in ordered]
    pct_labels = [f"{int(round(s[2]))}" if s[2] is not None else "--" for s in ordered]

    fig = go.Figure()

    # Track (full 0-100 background) behind every bar.
    fig.add_trace(
        go.Bar(
            x=[100] * len(labels),
            y=labels,
            orientation="h",
            marker=dict(color=TRACK),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Colored fill up to each stat's percentile.
    fig.add_trace(
        go.Bar(
            x=pctiles,
            y=labels,
            orientation="h",
            marker=dict(color=colors),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Dark tick mark exactly at the percentile edge -- makes the stopping
    # point unambiguous instead of relying on the color transition alone.
    fig.add_trace(
        go.Scatter(
            x=pctiles,
            y=labels,
            mode="markers",
            marker=dict(symbol="line-ns", size=18, line=dict(width=3, color=TICK)),
            hovertemplate="%{y}: %{x:.0f}th percentile<extra></extra>",
            showlegend=False,
        )
    )

    # Percentile + raw value label, fixed just past the track so it never
    # overlaps the tick mark or fill.
    fig.add_trace(
        go.Scatter(
            x=[103] * len(labels),
            y=labels,
            mode="text",
            # Show "88  (4.2)" when we have the raw value, but just "88"
            # when we don't. The deployed build reads the public CSV,
            # which strips raw values for gated third-party metrics (see
            # make_public_data.py) while keeping percentiles -- rendering
            # "88  (--)" there would look like a bug rather than a
            # deliberate omission.
            text=[
                f"{pl}  ({rv})" if rv not in ("--", "", None) else f"{pl}"
                for pl, rv in zip(pct_labels, raw_values)
            ],
            textposition="middle right",
            textfont=dict(size=13, color=TEXT),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        barmode="overlay",
        height=max(height_per_row * len(labels) + 40, 120),
        margin=dict(l=110, r=90, t=10, b=10),
        xaxis=dict(range=[0, 128], showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, color=TEXT),
        plot_bgcolor=CARD_BACKGROUND,
        paper_bgcolor=CARD_BACKGROUND,
        font=dict(color=TEXT),
    )
    return fig
