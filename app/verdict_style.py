"""
Shared Verdict/Confidence visual language.

Used by both the leaderboard table (app/streamlit_app.py, via a pandas
Styler) and the player page headline tile (app/player_page.py, via a
custom HTML badge). Lives in its own module because streamlit_app.py
already imports player_page.py -- either file importing these constants
from the other would be a circular import.

Why this exists at all: a Low-confidence "Overpaid"/"Underpaid" used to
render identically to a High-confidence one -- same fully-saturated
badge, same bold weight -- even though "Overpaid" (vs. "Leaning
overpaid") is supposed to mean "the model is confident enough in THIS
estimate to call it." Real case that flagged it: Christian Braun (Low
confidence, wide 80% interval, but his cap hit still cleared the top of
that wide band by about $1M) showed a plain "Overpaid" badge
indistinguishable from a tight, well-supported one.

Fix, in two parts that both consumers apply:
  1. Fade the badge toward white and lighten its font-weight as
     confidence drops (CONFIDENCE_BLEND / CONFIDENCE_WEIGHT).
  2. Spell the caveat out in the badge text itself for the two
     "confident" verdicts specifically when confidence is Low
     (LOW_CONFIDENCE_SUFFIX) -- "Leaning" verdicts already hedge in the
     word, so they're left alone.

The two consumers render this differently because they have different
capabilities: the leaderboard is a pandas Styler rendered through
st.dataframe's canvas grid (glide-data-grid), which only honors
background-color / color / font-weight -- no border-style. The player
page is plain HTML, so it can add a dashed vs. solid border on top of
the same fade.

Every badge fill stays a solid, opaque color (never literal
transparency) at every confidence tier -- the app runs a dark theme
(see app/theme.py: BACKGROUND #1C1E22), so a truly "hollow" badge with
a dark outline/text and nothing behind it would be unreadable against
that chrome. The fade is carried by how PALE the fill gets, not by
removing it; the badge border is always drawn at full verdict-color
strength (regardless of tier) so it stays legible against both a pale
Low-confidence fill and the app's dark background, with only its line
style (solid vs. dashed) changing for Low confidence.
"""

# Same bronze/silver/gold medal scale used for the percentile bars and
# Value Score cells elsewhere in the app.
VERDICT_COLORS = {
    "Underpaid": (212, 175, 55),           # gold -- confident
    "Leaning underpaid": (206, 188, 129),  # gold/silver blend -- probable
    "Fairly paid": (200, 200, 203),        # silver
    "Leaning overpaid": (188, 156, 133),   # silver/bronze blend -- probable
    "Overpaid": (176, 111, 62),            # bronze -- confident
}

LOW_CONFIDENCE_SUFFIX = " (low confidence)"

# How far a badge's fill blends toward white, and how bold its text is,
# as the model's confidence in that specific estimate drops.
CONFIDENCE_BLEND = {"High": 0.0, "Medium": 0.55, "Low": 0.82, "Unknown": 0.55}
CONFIDENCE_WEIGHT = {"High": 700, "Medium": 600, "Low": 400, "Unknown": 500}


def rgb(color: tuple) -> str:
    return f"rgb({color[0]},{color[1]},{color[2]})"


def lighten(color: tuple, amount: float) -> tuple:
    """Blend an (r, g, b) tuple toward white by `amount` (0..1)."""
    r, g, b = color
    return (
        round(r + (255 - r) * amount),
        round(g + (255 - g) * amount),
        round(b + (255 - b) * amount),
    )


def verdict_base(v):
    """Undo the low-confidence suffix so a color lookup still matches."""
    if isinstance(v, str) and v.endswith(LOW_CONFIDENCE_SUFFIX):
        return v[: -len(LOW_CONFIDENCE_SUFFIX)]
    return v


def verdict_text(verdict: str, confidence) -> str:
    """The label to display: the raw verdict, with the low-confidence
    caveat appended for the two "confident" verdicts (never for a
    "Leaning" one, which already hedges in the word itself)."""
    if verdict in ("Overpaid", "Underpaid") and confidence == "Low":
        return f"{verdict}{LOW_CONFIDENCE_SUFFIX}"
    return verdict
