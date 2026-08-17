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
metrics, weighted more heavily toward EPM and DARKO, the play-by-play-informed
pair).

A regression model, trained on veteran contracts only (rookie-scale
salaries are CBA-slotted, not performance-priced, so training on them would
teach the wrong relationship), predicts what each player's cap hit "should"
be from their production profile, age, experience, minutes played,
position, and draft pedigree. The gap between a
player's actual cap hit and that prediction is **Market Value Surplus** -- a
dollar figure. It ships with an uncertainty range (an 80% band and a
tighter 50% band) built via cross-conformal prediction, not a bare point
estimate, because a single number implies more precision than a model with
real, measurable error deserves. The pipeline prints realized holdout
coverage each run so that 80% claim is checked against reality rather than
asserted.

For players still on a rookie-scale contract -- who by definition aren't in
the training pool, since rookie-scale pay is CBA-slotted rather than
market-priced -- age and experience are swapped out for a typical veteran's
before predicting. Without that adjustment the model reads "young, early
career" as "cheap," which is true across the veteran training pool (where
the only young players are undrafted or second-round guys on modest deals)
but wrong for an elite player who's simply early in a max-caliber career.
The question becomes "what would a typically-aged veteran with this
production earn," which is the question the model can actually answer with
its training data.

**Value Score** is **Production Percentile** minus how much of a player's
own estimated market value he's actually being paid (also expressed as a
percentile, across the league). That second half is deliberately NOT a
percentile rank of raw salary -- salaries are heavily right-skewed, so a
big-but-still-below-market number (a rookie-scale veteran-caliber salary,
say) lands at a misleadingly high percentile purely because most of the
league makes less, understating just how big a bargain that player actually
is. Comparing pay to that player's own estimated worth instead avoids that
distortion, and keeps Value Score and Market Value Surplus pointed at the
same underlying estimate rather than running two different, sometimes
disagreeing, kinds of math.

**Rim Scoring Value** and **Foul-Drawing Value** are baseball-style
efficiency-times-volume composites for two specific skills, built because
the all-in-one metrics above compress a lot of different ways of scoring
into one number.
        """
    )

    st.markdown(_DIVIDER_HTML, unsafe_allow_html=True)

    st.markdown("#### Why two different seasons show up together")
    st.markdown(
        """
Production stats (BPM, EPM, DARKO, box score, Rim Scoring, Foul Drawing)
come from Basketball-Reference's season-scoped pages, so they're always
the most recently **completed** season -- 2025-26 as of this build.

Cap hits and contract figures come from a different page: Basketball-
Reference's live contracts table, which reports each player's "y1" as
whatever season is **upcoming** relative to the day it's scraped. Since
this pipeline runs after July 1 free agency opens, that's now 2026-27.

So every number on this site is deliberately pairing **what a player just
did** against **what he's now being paid to do next** -- which is a
natural front-office question ("he was elite last year, what's the market
now paying for that?"), but worth knowing explicitly rather than assuming
production and salary are from the same season. `SALARY_CAP`, the CBA
max-contract tiers, and the Team Payroll rollup on the Leaderboard tab
are all set to the matching 2026-27 figures for this reason.
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

Related: minutes played is a real input to the model, so a player coming
off an injury-shortened or otherwise unusual season can show a
lower-than-expected estimate even with strong per-minute production --
the model has less to go on for how a team would actually value his
role/durability that year. This shows up most visibly for a handful of
rookie-scale extension players with short 2025-26 seasons. It's not a
separate bug to fix; it's the same **estimate_confidence** tag (Low /
Medium / High, shown on every player page) doing its job -- these cases
are correctly flagged Low or Medium rather than presented as confident
calls, so read the direction as a hint in those cases, not a finding.

Related: the $-model's training pool of veterans thins out fast past the
mid-30s, so its prediction interval for very late-career players (LeBron
James being the clearest current example) can get extremely wide -- tens
of millions of dollars wide -- simply because there's little precedent to
anchor on. The player page flags this explicitly once age crosses a
threshold, the same way it already flags rookie-scale extrapolation at
the other end of a career. The direction of the estimate is usually still
sound; the dollar range around it isn't.

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
