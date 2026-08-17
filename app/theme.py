"""
Shared visual theme: color constants (used by both the Streamlit chrome
via .streamlit/config.toml and the Plotly charts, which don't
automatically inherit Streamlit's theme) and a CSS injector that hides
Streamlit's default chrome so the app reads like a real product instead
of "a Streamlit app" -- no menu hamburger, no "Deploy" button, no
"Made with Streamlit" footer.
"""

import streamlit as st

# Keep these in sync with .streamlit/config.toml -- Streamlit's own theme
# config only styles Streamlit's native widgets, not Plotly figures, so
# charts need these same values passed in explicitly.
#
# Charcoal + muted chartreuse palette (replaces the original navy/gold
# scheme). The bronze/silver/gold percentile-bar scale is intentionally
# untouched by this -- it's a data encoding, not a brand color, so it
# stays the same regardless of the app's chrome.
BACKGROUND = "#1C1E22"
CARD_BACKGROUND = "#26282C"
TEXT = "#F2F2F0"
MUTED_TEXT = "#9BA0A6"
ACCENT = "#A8B93A"
TRACK = "#33363B"  # empty/background portion of a percentile bar, also used for dividers
TICK = "#FFFFFF"  # the marker showing exactly where a bar stops

# NOTE: this template uses a literal {accent} placeholder substituted via
# str.replace() at the bottom -- NOT %-formatting or .format(). CSS is
# full of characters those treat as special: a bare "%" (max-width: 100%)
# breaks %-formatting, and every "{" in a CSS rule breaks .format().
# Both have bitten this file. str.replace() has no special characters.
_HIDE_CHROME_CSS_TEMPLATE = """
<style>
/* Hide Streamlit's branding chrome (main menu, "Deploy" button, the
   "Made with Streamlit" footer, the colored top stripe) so the app
   reads like a product rather than a notebook.

   IMPORTANT: do NOT blanket-hide <header>. The sidebar expand/collapse
   control lives inside it, so hiding the whole header makes the sidebar
   unrecoverable once collapsed -- there's no visible way to reopen it.
   Instead hide the specific chrome elements and make the header itself
   transparent, then explicitly force the sidebar controls visible. */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
[data-testid="stStatusWidget"] {visibility: hidden;}

/* Header stays in the layout (just visually blended into the page) --
   setting height:0 or visibility:hidden on it clips the sidebar
   expand arrow, which makes the sidebar unrecoverable once collapsed. */
[data-testid="stHeader"] {
    background: transparent;
}

/* Belt and braces: force the sidebar open/close controls visible and
   above the page content in both expanded and collapsed states. The
   test IDs have changed across Streamlit versions, so target all the
   known variants. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] {
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
}

.block-container {padding-top: 1.5rem;}

/* small accent underline under the app title */
.app-title-bar {
    border-bottom: 3px solid {accent};
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
}

/* ----------------------------------------------------------------- */
/* Mobile / narrow-screen adjustments.                                */
/*                                                                    */
/* Streamlit renders server-side and has no reliable way to detect    */
/* viewport width in Python, so responsiveness has to be done in CSS  */
/* media queries rather than by branching on device in the app code.  */
/* 640px is the usual phone-portrait breakpoint; 1024px catches       */
/* tablets and small laptop windows.                                  */
/* ----------------------------------------------------------------- */
@media (max-width: 1024px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1rem;
    }
}

@media (max-width: 640px) {
    /* The title is 2rem on desktop, which wraps awkwardly on a phone. */
    .app-title-bar .app-title {font-size: 1.4rem !important;}
    .app-title-bar .app-subtitle {font-size: 0.85rem !important;}

    .block-container {
        padding-left: 0.6rem;
        padding-right: 0.6rem;
    }

    /* st.metric headline numbers: shrink so 2-up doesn't overflow. */
    [data-testid="stMetricValue"] {font-size: 1.1rem !important;}
    [data-testid="stMetricLabel"] {font-size: 0.75rem !important;}

    /* Tab strips (scatter plots, table views) overflow horizontally on
       a phone -- let them scroll instead of wrapping into a jumble. */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto;
        flex-wrap: nowrap;
        scrollbar-width: none;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar {display: none;}
    [data-testid="stTabs"] [data-baseweb="tab"] {
        flex: 0 0 auto;
        padding-left: 0.6rem;
        padding-right: 0.6rem;
        font-size: 0.85rem;
    }

    /* Dataframes: allow touch scrolling without the page fighting it.
       The overflow-x:hidden rule below (which stops the sidebar overlay
       forcing sideways page scroll) must NOT apply here, or the table
       gets clipped at whatever fits the screen and the remaining columns
       become unreachable. */
    [data-testid="stDataFrame"] {
        -webkit-overflow-scrolling: touch;
        overflow-x: auto !important;
        max-width: 100%;
    }
    [data-testid="stDataFrame"] * {
        -webkit-overflow-scrolling: touch;
    }

    /* Don't let the sidebar overlay swallow the whole screen. Streamlit
       renders it as a fixed overlay on narrow viewports, so cap the
       width and let the page stay partly visible behind it. */
    section[data-testid="stSidebar"] {
        min-width: 16rem !important;
        max-width: 78vw !important;
    }
    /* Prevent the overlay from forcing horizontal page scroll. */
    [data-testid="stAppViewContainer"] {overflow-x: hidden;}
}
</style>
"""

_HIDE_CHROME_CSS = _HIDE_CHROME_CSS_TEMPLATE.replace("{accent}", ACCENT)


def inject_custom_css():
    st.markdown(_HIDE_CHROME_CSS, unsafe_allow_html=True)


def app_title_bar(title: str, subtitle: str = ""):
    st.markdown(
        f"""
        <div class="app-title-bar">
            <div class="app-title" style="font-size:2rem; font-weight:800; color:{TEXT}; line-height:1.2;">{title}</div>
            <div class="app-subtitle" style="font-size:0.95rem; color:{MUTED_TEXT};">{subtitle}</div>
            <div class="app-credit" style="font-size:0.75rem; color:{MUTED_TEXT}; margin-top:0.35rem;">Designed by Calvin Chappell</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
