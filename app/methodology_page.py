"""
Methodology & Limitations page.

The rest of the app makes confident-looking claims (a dollar figure, a
verdict, a percentile bar). This page is the deliberate counterweight: how
those numbers are actually built, and -- more importantly -- what they
don't account for. A reader who can't find this page has no way to tell a
well-calibrated estimate from an overconfident one; putting it one nav
click away, rather than in a code comment, is the point.
"""

import streamlit as st

from app.theme import MUTED_TEXT, TRACK

_DIVIDER_HTML = f"<hr style='margin: 0.25rem 0 1.25rem 0; border-color: {TRACK};'>"


def render_methodology_page():
    st.markdown("### Methodology & Limitations")
    st.caption(
        "How the numbers on this site are built, and what they don't account for. "
        "Read this before treating any single figure as a final answer."
    )
    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    st.markdown("#### How it works")
    st.markdown(
        """
Every rostered player gets a **Production Percentile** (a weighted blend of
BPM, EPM, and DARKO -- box-score-only vs. play-by-play-informed impact
metrics, weighted toward the latter two) and a **Salary Percentile** (cap
hit relative to the rest of the league). **Value Score** is the gap between
them.

Separately, a regression model predicts each veteran's cap hit from their
production profile. The gap between a player's actual cap hit and that
prediction is **Market Value Surplus** -- the dollar-denominated version of
the same idea. It ships with an uncertainty range (an 80% band and a
tighter 50% band) built via cross-conformal prediction, not a bare point
estimate, because a single number implies more precision than a model with
real, measurable error deserves. The pipeline prints realized holdout
coverage each run so that 80% claim is checked against reality rather than
asserted.

**Rim Scoring Value** and **Foul-Drawing Value** are baseball-style
efficiency-times-volume composites for two specific skills, built because
the all-in-one metrics above compress a lot of different ways of scoring
into one number.
        """
    )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    st.markdown("#### Limitations")
    st.markdown(
        """
**No standalone defensive metric.** BPM/EPM/DARKO all fold defense into a
single all-in-one number, and all three are known to underrate defenders
whose value doesn't show up in blocks and steals -- point-of-attack
containment, rotations, discouraging drives. A rim protector or lockdown
wing can be undervalued here in a way this site currently has no way to
flag. A standalone Defensive Value metric (mirroring Rim Scoring / Foul
Drawing) is the most important thing not yet built.

**No aging curve.** Every number on this site is a single-season snapshot:
this year's production against this year's salary. It says nothing about
whether that surplus will still exist in year two of a four-year deal.
The player page shows age and a rough **Ascending / Prime / Descending**
band as context, but that's an age cutoff, not a fitted trajectory --
building a real one requires multiple years of history per player and a
correction for survivorship bias (players who declined tend to leave the
league, which biases a naive "average performance by age" curve upward at
the old end). That's a separate project, not a label.

**Regular season only, with a new descriptive-only playoff split.** The
Playoff Performance panel on each player page shows raw playoff per-game
numbers next to regular-season ones, but deliberately isn't folded into
Value Score, Market Value, or any percentile ranking. Only 16 of 30 teams
qualify in a given year, and a first-round sweep is 4 games -- nowhere
near enough of a sample to rank players against each other on, even though
it's genuinely useful to *see* next to the regular-season line.

**Contract mechanics are simplified.** Cap hit is treated as equal to
salary. Real cap hits can diverge via stretch provisions, base-year
compensation, trade kickers, and incentives -- none of which are modeled.
There's no first/second-apron awareness, and years remaining doesn't
distinguish guaranteed years from team/player options.

**No fit or scheme context.** Statistical surplus doesn't know whether a
player duplicates a skill the roster already has, clashes with a coaching
system, or solves a specific tactical problem. That judgment has to come
from the reader, not the model.

**No backtest shown yet.** The $-model's holdout accuracy is printed to
the console each pipeline run, but there's no in-app record of how it
would have called last summer's free agent class in hindsight. That's the
next thing worth adding to build trust in the numbers, not just assert it.
        """
    )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)
    st.caption(
        f'<span style="color:{MUTED_TEXT};">Data sourced from Basketball-Reference '
        "(box score, advanced stats, contracts, playoffs) plus manually imported "
        "EPM, DARKO, and databallr metrics. Raw values from subscription-gated "
        "sources are never published -- only their percentile ranks. See the "
        "project README for the full data pipeline.</span>",
        unsafe_allow_html=True,
    )
