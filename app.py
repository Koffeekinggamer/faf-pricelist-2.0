"""
FAF Pricelist 2.0 — Streamlit entry (scaffold).

Phase 1: Drop Excel → on-screen PDF · Admin backup + multipliers.
See docs/HANDOFF.md before expanding.

Run: streamlit run app.py --server.port 8510
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
FAVICON = ASSETS / "favicon.png"
LOGO = ASSETS / "logo.png"

st.set_page_config(
    page_title="FAF Pricelist 2.0",
    page_icon=str(FAVICON) if FAVICON.is_file() else "🪵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if LOGO.is_file():
    st.logo(str(LOGO), size="large")

# ---------------------------------------------------------------------------
# Login (scaffold — defaults match store floor habit)
# ---------------------------------------------------------------------------
APP_USER = "Foothills"
APP_PASS = "Amish"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("### FAF Pricelist 2.0")
    st.caption("Foothills Amish Furniture · greenfield rebuild")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary", use_container_width=True):
            if u.strip() == APP_USER and p == APP_PASS:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    st.info("Scaffold only — implement Drop → PDF and Admin per **docs/HANDOFF.md**.")
    st.stop()

st.sidebar.title("FAF Pricelist 2.0")
if st.sidebar.button("Sign out"):
    st.session_state.authenticated = False
    st.rerun()

tab_drop, tab_admin = st.tabs(["Drop files", "Admin"])

with tab_drop:
    st.subheader("Drop files")
    st.caption(
        "Target UX: drop builder Excel → **formatted PDF on screen** for the team "
        "(not a parsed row grid). Builder name controls the book title."
    )
    st.file_uploader(
        "Excel pricelist",
        type=["xls", "xlsx", "xlsm"],
        help="Implement parse + PDF generation next",
    )
    st.warning(
        "Not implemented yet in 2.0 scaffold. "
        "See `docs/HANDOFF.md` and optionally reuse import/PDF patterns from `~/FAF-pricebook`."
    )

with tab_admin:
    st.subheader("Admin")
    st.caption("Backup master DB after updates · edit multiplier per builder.")
    st.warning("Scaffold only — wire backup + multipliers next.")
