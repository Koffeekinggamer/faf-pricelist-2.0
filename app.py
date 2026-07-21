"""
FAF Pricelist 2.0 — Phase 1

- Login: Foothills / Amish
- Drop Excel → formatted PDF on screen (not a row dump)
- Builder name on the book
- Admin: backup DB + multipliers

Port: 8510  (./run.sh)
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

import streamlit as st

from backend.config import APP_PASSWORD, APP_USERNAME, DB_PATH, DEFAULT_MULTIPLIER
from backend.service import CatalogService

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

st.markdown(
    """
    <style>
      @media (max-width: 900px) {
        .stTextInput input, .stNumberInput input {
          min-height: 2.6rem; font-size: 1.05rem !important;
        }
        button { min-height: 2.5rem; }
      }
      [data-testid="stSidebar"] img { max-width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@st.cache_resource
def get_service() -> CatalogService:
    svc = CatalogService()
    svc.init()
    return svc


def _bytes(upload) -> bytes:
    data = upload.getvalue() if hasattr(upload, "getvalue") else upload.read()
    return data if isinstance(data, (bytes, bytearray)) else bytes(data)


def _last_backup_hint() -> str:
    try:
        from scripts.backup_db import list_backups

        files = list_backups(1)
        if not files:
            return "No backup yet"
        latest = files[0]
        age = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%b %d %I:%M %p")
        return f"{latest.name} · {age}"
    except Exception:
        return "—"


def _show_pdf(pdf_bytes: bytes, height: int = 720) -> None:
    try:
        st.pdf(pdf_bytes, height=height)
        return
    except TypeError:
        try:
            st.pdf(pdf_bytes)
            return
        except Exception:
            pass
    except Exception:
        pass
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" '
        f'height="{height}" style="border:1px solid #ccc;border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown(
        """
        <div style="max-width:420px;margin:3rem auto 1rem;text-align:center;">
          <div style="font-size:1.85rem;font-weight:700;color:#2d4a30;">FAF Pricelist 2.0</div>
          <div style="color:#555;margin-top:0.35rem;">Foothills Amish Furniture</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        with st.form("login"):
            u = st.text_input("Username", autocomplete="username")
            p = st.text_input("Password", type="password", autocomplete="current-password")
            if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                if (
                    u.strip().lower() == APP_USERNAME.strip().lower()
                    and p == APP_PASSWORD
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    st.stop()

svc = get_service()
stats = svc.stats()

st.sidebar.title("FAF Pricelist 2.0")
st.sidebar.caption("Signed in")
st.sidebar.metric("Master rows", f"{stats['rows']:,}")
st.sidebar.caption(f"{stats['vendors']} builders")
st.sidebar.caption(f"Backup: {_last_backup_hint()}")
if st.sidebar.button("Sign out"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

st.caption(
    f"**FAF Pricelist 2.0** · Excel → PDF · "
    f"{stats['rows']:,} rows · {stats['vendors']} builders"
)

tab_drop, tab_admin = st.tabs(["Drop files", "Admin"])


# ===========================================================================
# DROP — Excel → on-screen PDF
# ===========================================================================
with tab_drop:
    st.subheader("Drop a builder price list")
    st.caption(
        "Upload Excel (`.xls` / `.xlsx` / `.xlsm`). Set the **builder** name — "
        "the **formatted PDF** appears on screen for the team (not a row table)."
    )

    upload = st.file_uploader(
        "Drop Excel price list",
        type=["xls", "xlsx", "xlsm"],
        accept_multiple_files=False,
        key="drop_file",
    )

    if upload is not None:
        sig = (upload.name, int(getattr(upload, "size", 0) or 0))
        if st.session_state.get("drop_sig") != sig:
            with st.spinner(f"Reading {upload.name}…"):
                prepared = svc.prepare_excel(
                    _bytes(upload),
                    filename=upload.name,
                    vendor="",
                    multiplier=None,
                )
            st.session_state["drop_sig"] = sig
            st.session_state["drop_parsed"] = prepared
            st.session_state.pop("drop_pdf_cache", None)

    prepared = st.session_state.get("drop_parsed")

    if not prepared:
        st.info("Drop an Excel price list above — the PDF will show here.")
    elif prepared.get("error") and not prepared.get("rows"):
        st.error(prepared.get("error") or "Could not read this file.")
        if prepared.get("notes"):
            st.caption(prepared["notes"])
    else:
        if prepared.get("error"):
            st.warning(prepared["error"])

        default_builder = (prepared.get("vendor") or "Builder").strip()
        try:
            default_mult = float(
                prepared.get("detected_markup")
                or svc.get_multiplier(default_builder)
                or DEFAULT_MULTIPLIER
            )
        except (TypeError, ValueError):
            default_mult = float(DEFAULT_MULTIPLIER)

        c1, c2 = st.columns([2.4, 1.0])
        with c1:
            builder = (
                st.text_input(
                    "Builder",
                    value=default_builder,
                    key="builder_name",
                    help="Title on the PDF — change it and the book updates",
                ).strip()
                or default_builder
            )
        with c2:
            mult = st.number_input(
                "Multiplier",
                min_value=0.1,
                max_value=20.0,
                value=float(default_mult),
                step=0.1,
                key="builder_mult",
                help="Retail = wholesale × mult (even-dollar round up)",
            )

        raw_rows = list(prepared.get("rows") or [])
        if not raw_rows:
            st.warning("No prices found in this workbook.")
        else:
            frame = svc.rows_frame(raw_rows, float(mult), builder)
            pdf_cols = [
                c
                for c in (
                    "part_number",
                    "description",
                    "species",
                    "finish_state",
                    "adjusted_price",
                )
                if c in frame.columns
            ]
            pdf_frame = frame[pdf_cols] if pdf_cols else frame

            pdf_key = (st.session_state.get("drop_sig"), builder, round(float(mult), 4))
            cache = st.session_state.get("drop_pdf_cache") or {}
            if cache.get("key") != pdf_key or not cache.get("bytes"):
                with st.spinner(f"Building PDF for **{builder}**…"):
                    try:
                        pdf_bytes = svc.export_pdf(
                            pdf_frame, title=f"{builder} Price List"
                        )
                        st.session_state["drop_pdf_cache"] = {
                            "key": pdf_key,
                            "bytes": pdf_bytes,
                        }
                    except Exception as exc:
                        pdf_bytes = None
                        st.error(f"PDF failed: {exc}")
            else:
                pdf_bytes = cache["bytes"]

            if pdf_bytes:
                st.markdown(f"### {builder}")
                st.caption(
                    f"On-screen PDF · `{prepared.get('filename')}` · "
                    f"mult **{float(mult):g}** · "
                    f"engine `{prepared.get('engine', '?')}`"
                )
                _show_pdf(pdf_bytes, height=720)

                safe = (
                    "".join(
                        ch if ch.isalnum() or ch in "-_" else "_" for ch in builder
                    )[:48]
                    or "builder"
                )
                d1, d2 = st.columns(2)
                with d1:
                    st.download_button(
                        "Download PDF",
                        data=pdf_bytes,
                        file_name=f"{safe}_price_list.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                with d2:
                    with st.expander("Save into master book"):
                        st.caption(
                            "Optional — stores this builder for multipliers & backup. "
                            "Replaces any existing rows for this builder name."
                        )
                        if st.button("Save into master book", use_container_width=True):
                            try:
                                result = svc.save_builder(
                                    builder,
                                    raw_rows,
                                    float(mult),
                                    source_file=prepared.get("filename") or "",
                                )
                                get_service.clear()
                                st.success(
                                    f"Saved **{builder}** · "
                                    f"inserted {result.get('inserted', 0)} · "
                                    f"removed prior {result.get('deleted', 0)}"
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))


# ===========================================================================
# ADMIN — backup + multipliers
# ===========================================================================
with tab_admin:
    st.subheader("Admin")
    a1, a2 = st.columns(2)
    a1.metric("Rows", f"{stats['rows']:,}")
    a2.metric("Builders", stats["vendors"])
    st.caption(f"Database: `{DB_PATH}`")
    st.caption(f"Last backup: {_last_backup_hint()}")

    st.markdown("##### Backup database")
    st.caption(
        "Snapshot the master book after you load or update builder lists. "
        "Stored under Documents/FAF-pricelist-2.0-backups."
    )
    if st.button("Backup DB now", type="primary", use_container_width=True):
        try:
            from scripts.backup_db import backup_now

            dest = backup_now()
            st.success(f"Backed up → `{dest}`")
        except Exception as exc:
            st.error(str(exc))

    st.divider()
    st.markdown("##### Multiplier per builder")
    st.caption(
        "Edit **Multiplier** (and phone), then save. "
        "Retail is recomputed as wholesale × mult (even-dollar). "
        "Typical: **2.7** · Genuine Oak often **1.7**."
    )

    table = svc.vendor_table()
    if table.empty:
        st.info("No builders saved yet — drop an Excel file and use **Save into master book**.")
    else:
        edited = st.data_editor(
            table,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["Builder", "Items"],
            column_config={
                "Builder": st.column_config.TextColumn(disabled=True),
                "Phone": st.column_config.TextColumn(max_chars=40),
                "Items": st.column_config.NumberColumn(format="%d", disabled=True),
                "Multiplier": st.column_config.NumberColumn(
                    min_value=0.1, max_value=20.0, step=0.1, format="%.2f"
                ),
            },
            key="mult_editor",
        )
        if st.button(
            "Save multipliers · update retail",
            type="primary",
            use_container_width=True,
        ):
            n_b = 0
            n_r = 0
            for _, r in edited.iterrows():
                name = str(r["Builder"])
                phone = str(r.get("Phone") or "").strip()
                m = float(r["Multiplier"])
                if m <= 0:
                    continue
                svc.set_phone(name, phone)
                n_r += svc.reapply_multiplier(name, m)
                n_b += 1
            get_service.clear()
            st.success(f"Saved **{n_b}** builders · recomputed **{n_r:,}** retail prices")
            st.rerun()

    with st.expander("Remove a builder"):
        vlist = svc.list_vendors()
        if not vlist:
            st.caption("Nothing to remove.")
        else:
            vv = st.selectbox("Builder", vlist, key="del_v")
            if st.button("Remove builder", type="secondary"):
                n = svc.delete_vendor(vv)
                get_service.clear()
                st.warning(f"Deleted {n:,} rows for {vv}")
                st.rerun()
