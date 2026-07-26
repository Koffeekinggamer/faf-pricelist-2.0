"""
FAF Price Book — Streamlit UI (accuracy / PDF phase)

Tabs: Drop files · Admin
- Drop Excel → preview builder catalog → formatted PDF
- Admin: backup DB + per-builder multipliers

OrderTrac / quote / full search UI are preserved in:
  pricebook_app_legacy.py  (TRACE: restore by swapping file names)
Backend OrderTrac code remains in backend/ (no UI).

Run:  streamlit run pricebook_app.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend import PriceBookService
from backend.auth import login_user
from backend.config import APP_DIR, DEFAULT_MULTIPLIER
from backend.pricing import retail_from_wholesale

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_FAVICON = APP_DIR / "assets" / "favicon.png"
_LOGO = APP_DIR / "assets" / "logo.png"

# ---------------------------------------------------------------------------
# Feature flags / TRACE restore
# ---------------------------------------------------------------------------
# Full prior UI (Search, pins, OrderTrac quote tab, etc.):
#   mv pricebook_app.py pricebook_app_slim.py
#   mv pricebook_app_legacy.py pricebook_app.py
# OrderTrac admin connection UI was in legacy Admin tab (SHOW_ORDERTRAC_ADMIN).
# Backend: backend/ordertrac_connect.py, ordertrac_push.py, quotes.py — unchanged.

st.set_page_config(
    page_title="FAF Price Book",
    page_icon=str(_FAVICON) if _FAVICON.is_file() else "🪵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if _LOGO.is_file():
    st.logo(str(_LOGO), size="large")

st.markdown(
    """
    <style>
      @media (max-width: 900px) {
        .stTextInput input, .stSelectbox div[data-baseweb="select"] {
          min-height: 2.6rem;
          font-size: 1.05rem !important;
        }
        div[data-testid="stDataFrame"] { font-size: 0.95rem; }
        .block-container { padding-top: 1rem; padding-left: 0.8rem; padding-right: 0.8rem; }
        button { min-height: 2.5rem; }
      }
      [data-testid="stSidebar"] img { max-width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def _require_login() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style="max-width:420px;margin:4rem auto 1rem auto;text-align:center;">
          <div style="font-size:2rem;font-weight:700;color:#2d4a30;">FAF Price Book</div>
          <div style="color:#555;margin-top:0.25rem;">Foothills Amish Furniture · sign in to continue</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col_c, _ = st.columns([1, 1.2, 1])
    with col_c:
        with st.form("login_form", clear_on_submit=False):
            user = st.text_input("Username", autocomplete="username")
            pw = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )
            if submitted:
                session = login_user(user, pw)
                if session:
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = session["username"]
                    st.session_state["auth_display"] = session.get("display_name")
                    st.session_state["auth_role"] = session.get("role") or "sales"
                    st.session_state["auth_user_id"] = session.get("user_id")
                    st.session_state["auth_session"] = session
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    return False


if not _require_login():
    st.stop()

# Optional force password change (OrderTrac-synced accounts — logic kept)
_auth_sess = st.session_state.get("auth_session") or {}
if _auth_sess.get("must_change_password") and st.session_state.get("auth_user_id"):
    st.warning("You must set a new password before continuing.")
    with st.form("force_pw_change"):
        npw = st.text_input("New password", type="password")
        npw2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Save new password", type="primary"):
            if not npw or len(npw) < 6:
                st.error("Password must be at least 6 characters.")
            elif npw != npw2:
                st.error("Passwords do not match.")
            else:
                _tmp = PriceBookService()
                _tmp.init()
                _tmp.set_app_user_password(
                    int(st.session_state["auth_user_id"]), npw, must_change=False
                )
                st.session_state["auth_session"]["must_change_password"] = False
                st.success("Password updated.")
                st.rerun()
    st.stop()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SERVICE_CACHE_VERSION = 4


@st.cache_resource
def get_service(_cache_version: int = _SERVICE_CACHE_VERSION) -> PriceBookService:
    svc = PriceBookService()
    svc.init()
    return svc


svc = get_service()


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
        return "Backup helper unavailable"


def _rows_to_frame(rows: list[dict], mult: float) -> pd.DataFrame:
    """Build display/export frame with retail from wholesale × mult."""
    if not rows:
        return pd.DataFrame()
    out = []
    for r in rows:
        item = dict(r)
        item["multiplier"] = float(mult)
        bp = item.get("base_price")
        try:
            if bp is not None and bp != "":
                item["adjusted_price"] = retail_from_wholesale(float(bp), float(mult))
        except (TypeError, ValueError):
            pass
        out.append(item)
    return pd.DataFrame(out)


def _preview_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [
        c
        for c in [
            "part_number",
            "description",
            "collection",
            "species",
            "finish_state",
            "base_price",
            "multiplier",
            "adjusted_price",
            "vendor",
        ]
        if c in df.columns
    ]
    view = df[cols].copy()
    return view.rename(
        columns={
            "part_number": "Part #",
            "description": "Description",
            "collection": "Collection",
            "species": "Wood",
            "finish_state": "Finish",
            "base_price": "Wholesale",
            "multiplier": "Mult",
            "adjusted_price": "Retail",
            "vendor": "Builder",
        }
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("FAF Price Book")
who = st.session_state.get("auth_display") or st.session_state.get("auth_user") or "user"
role = st.session_state.get("auth_role") or "sales"
st.sidebar.caption(f"Signed in as **{who}** · `{role}`")
if st.sidebar.button("Sign out"):
    for k in (
        "authenticated",
        "auth_user",
        "auth_display",
        "auth_role",
        "auth_user_id",
        "auth_session",
        "drop_parsed",
        "drop_filename",
    ):
        st.session_state.pop(k, None)
    st.rerun()

stats = svc.stats()
st.sidebar.metric("Master rows", f"{stats['rows']:,}")
st.sidebar.caption(f"{stats['vendors']} builders · last backup: {_last_backup_hint()}")

st.caption(
    f"**FAF Price Book** · Excel → PDF · {stats['rows']:,} rows · {stats['vendors']} builders"
)

tab_drop, tab_admin = st.tabs(["Drop files", "Admin"])


# ===========================================================================
# DROP FILES — Excel → preview → formatted PDF
# ===========================================================================
with tab_drop:
    st.subheader("Drop a builder price list")
    st.caption(
        "Upload an **Excel** (`.xls` / `.xlsx` / `.xlsm`) file, pick the **builder**, "
        "and the **formatted PDF** appears on screen for the team."
    )

    upload = st.file_uploader(
        "Drop Excel price list",
        type=["xls", "xlsx", "xlsm"],
        accept_multiple_files=False,
        key="drop_one_file",
        help="One builder book at a time",
    )

    if upload is not None:
        sig = (upload.name, int(getattr(upload, "size", 0) or 0))
        if st.session_state.get("drop_sig") != sig:
            with st.spinner(f"Reading {upload.name}…"):
                try:
                    data = _bytes(upload)
                    prepared = svc.prepare_drop_file(
                        data,
                        filename=upload.name,
                        vendor="",
                        multiplier=None,
                        use_workbook_markup=False,
                    )
                except Exception as exc:
                    prepared = {
                        "filename": upload.name,
                        "vendor": Path(upload.name).stem,
                        "error": str(exc),
                        "rows": [],
                        "row_count": 0,
                        "detected_markup": None,
                    }
            st.session_state["drop_sig"] = sig
            st.session_state["drop_parsed"] = prepared
            st.session_state["drop_filename"] = upload.name
            st.session_state.pop("drop_pdf_cache", None)

    prepared = st.session_state.get("drop_parsed")

    if not prepared:
        st.info("Drop an Excel price list above — the PDF will show here for your team.")
    elif prepared.get("error") and not prepared.get("rows"):
        st.error(prepared.get("error") or "Could not read this file.")
        if prepared.get("notes"):
            st.caption(str(prepared.get("notes")))
    else:
        if prepared.get("error"):
            st.warning(prepared["error"])

        default_builder = (
            prepared.get("vendor") or Path(prepared.get("filename", "Builder")).stem
        ).strip()
        detected = prepared.get("detected_markup")
        try:
            saved_mult = svc.get_vendor_multiplier(
                default_builder, default=DEFAULT_MULTIPLIER
            )
        except Exception:
            saved_mult = DEFAULT_MULTIPLIER
        try:
            default_mult = (
                float(detected)
                if detected is not None
                else float(saved_mult or DEFAULT_MULTIPLIER)
            )
        except (TypeError, ValueError):
            default_mult = float(DEFAULT_MULTIPLIER)

        c1, c2 = st.columns([2.4, 1.0])
        with c1:
            builder = st.text_input(
                "Builder",
                value=default_builder,
                key="drop_builder_name",
                help="Title on the PDF — change this and the PDF updates",
            ).strip() or default_builder
        with c2:
            mult = st.number_input(
                "Multiplier",
                min_value=0.1,
                max_value=20.0,
                value=float(default_mult),
                step=0.1,
                key="drop_mult",
                help="Retail = wholesale × this number (shown on the PDF)",
            )

        raw_rows = list(prepared.get("rows") or [])
        if not raw_rows:
            st.warning("No prices found in this workbook.")
        else:
            for r in raw_rows:
                r["vendor"] = builder
            frame = _rows_to_frame(raw_rows, float(mult))
            # Floor PDF: clean retail columns only (not the raw long-form dump)
            pdf_frame = frame.copy()
            keep = [
                c
                for c in (
                    "part_number",
                    "description",
                    "species",
                    "finish_state",
                    "adjusted_price",
                )
                if c in pdf_frame.columns
            ]
            if keep:
                pdf_frame = pdf_frame[keep]

            # Build / cache PDF when builder, mult, or file changes
            pdf_key = (
                st.session_state.get("drop_sig"),
                builder,
                round(float(mult), 4),
            )
            cache = st.session_state.get("drop_pdf_cache") or {}
            if cache.get("key") != pdf_key or not cache.get("bytes"):
                with st.spinner(f"Building PDF for **{builder}**…"):
                    try:
                        pdf_bytes = svc.export_pdf(
                            pdf_frame, title=f"{builder} Price List"
                        )
                    except Exception as exc:
                        pdf_bytes = None
                        st.error(f"PDF generation failed: {exc}")
                if pdf_bytes:
                    st.session_state["drop_pdf_cache"] = {
                        "key": pdf_key,
                        "bytes": pdf_bytes,
                        "builder": builder,
                    }
            else:
                pdf_bytes = cache["bytes"]

            if pdf_bytes:
                safe_name = (
                    "".join(
                        ch if ch.isalnum() or ch in ("-", "_") else "_"
                        for ch in builder
                    )[:48]
                    or "builder"
                )

                st.markdown(f"### {builder}")
                st.caption(
                    f"On-screen PDF for the team · "
                    f"`{prepared.get('filename')}` · mult **{float(mult):g}**"
                )

                # Full-width in-app PDF viewer (no row table)
                try:
                    st.pdf(pdf_bytes, height=720)
                except TypeError:
                    st.pdf(pdf_bytes)
                except Exception:
                    # Fallback embed if st.pdf quirks on some builds
                    import base64

                    b64 = base64.b64encode(pdf_bytes).decode("ascii")
                    st.markdown(
                        f'<iframe src="data:application/pdf;base64,{b64}" '
                        f'width="100%" height="720" style="border:1px solid #ccc;'
                        f'border-radius:8px;"></iframe>',
                        unsafe_allow_html=True,
                    )

                d1, d2 = st.columns(2)
                with d1:
                    st.download_button(
                        "Download PDF",
                        data=pdf_bytes,
                        file_name=f"{safe_name}_price_list.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                with d2:
                    with st.expander("Admin: save into master book"):
                        st.caption(
                            "Optional — stores this builder for multipliers/backup. "
                            "Not shown as a row grid on the floor."
                        )
                        if st.button(
                            "Save into master book",
                            use_container_width=True,
                            key="btn_save_master",
                        ):
                            try:
                                commit_rows = []
                                for src in raw_rows:
                                    r = dict(src)
                                    r["vendor"] = builder
                                    r["multiplier"] = float(mult)
                                    r["source_file"] = (
                                        prepared.get("filename") or "upload"
                                    )
                                    bp = r.get("base_price")
                                    if bp is not None:
                                        try:
                                            r["adjusted_price"] = (
                                                retail_from_wholesale(
                                                    float(bp), float(mult)
                                                )
                                            )
                                        except (TypeError, ValueError):
                                            pass
                                    commit_rows.append(r)
                                result = svc.add_rows(
                                    commit_rows, mode="replace_vendor"
                                )
                                svc.set_vendor_multiplier(
                                    builder,
                                    float(mult),
                                    notes="From Drop files PDF phase",
                                )
                                get_service.clear()
                                st.success(
                                    f"Saved **{builder}** · "
                                    f"inserted {result.get('inserted', result.get('total', 0))} · "
                                    f"deleted prior {result.get('deleted', 0)}"
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not save to master: {exc}")


# ===========================================================================
# ADMIN — backup + multipliers only
# ===========================================================================
with tab_admin:
    st.subheader("Admin")
    s1, s2 = st.columns(2)
    s1.metric("Rows", f"{stats['rows']:,}")
    s2.metric("Builders", stats["vendors"])
    st.caption(f"Database: `{svc.path}`")
    st.caption(f"Last backup: {_last_backup_hint()}")

    # TRACE: OrderTrac connection / user sync / quote push UI lives in
    # pricebook_app_legacy.py (Admin section). Backend modules still present:
    # backend/ordertrac_connect.py, ordertrac_push.py, quotes.py

    st.markdown("##### Backup database")
    st.caption(
        "Snapshot the master price book after you load or update builder lists. "
        "Backups stay on this Mac under Documents/FAF-pricebook-backups."
    )
    bb1, bb2 = st.columns(2)
    with bb1:
        if st.button("Backup DB now", type="primary", use_container_width=True):
            try:
                from scripts.backup_db import backup_now

                dest = backup_now()
                st.success(f"Backed up → `{dest.name}`")
            except Exception as exc:
                st.error(str(exc))
    with bb2:
        st.caption(_last_backup_hint())

    st.divider()
    st.markdown("##### Multiplier per builder")
    st.caption(
        "Edit **Multiplier** (and optional **Phone**), then save to recompute retail "
        "(wholesale × mult)."
    )

    summary = svc.list_vendor_settings()
    if summary is None or (isinstance(summary, pd.DataFrame) and summary.empty):
        # Fall back to vendor summary from catalog
        try:
            vs = svc.vendor_summary() if hasattr(svc, "vendor_summary") else None
        except Exception:
            vs = None
        if vs is not None and not getattr(vs, "empty", True):
            summary = vs
        else:
            vendors = svc.list_vendors()
            summary = pd.DataFrame(
                {
                    "vendor": vendors,
                    "phone": [svc.get_vendor_phone(v) for v in vendors],
                    "saved_mult": [
                        svc.get_vendor_multiplier(v, default=DEFAULT_MULTIPLIER)
                        for v in vendors
                    ],
                    "rows": [None] * len(vendors),
                }
            )

    if isinstance(summary, pd.DataFrame) and not summary.empty:
        edit_df = summary.copy()
        # Normalize columns
        if "vendor" not in edit_df.columns and "Builder" in edit_df.columns:
            edit_df = edit_df.rename(columns={"Builder": "vendor"})
        if "phone" not in edit_df.columns:
            edit_df["phone"] = [
                svc.get_vendor_phone(str(v)) for v in edit_df.get("vendor", [])
            ]
        if "saved_mult" in edit_df.columns:
            edit_df["Multiplier"] = edit_df["saved_mult"].fillna(DEFAULT_MULTIPLIER)
        elif "multiplier" in edit_df.columns:
            edit_df["Multiplier"] = edit_df["multiplier"].fillna(DEFAULT_MULTIPLIER)
        elif "avg_mult" in edit_df.columns:
            edit_df["Multiplier"] = edit_df["avg_mult"].fillna(DEFAULT_MULTIPLIER)
        else:
            edit_df["Multiplier"] = DEFAULT_MULTIPLIER

        edit_df = edit_df.rename(
            columns={
                "vendor": "Builder",
                "phone": "Phone",
                "rows": "Items",
            }
        )
        show_cols = [
            c
            for c in ["Builder", "Phone", "Items", "Multiplier"]
            if c in edit_df.columns
        ]
        # Ensure Items exists
        if "Items" not in edit_df.columns:
            show_cols = [c for c in show_cols if c != "Items"]

        col_cfg = {
            "Builder": st.column_config.TextColumn(disabled=True),
            "Phone": st.column_config.TextColumn("Phone", max_chars=40),
            "Multiplier": st.column_config.NumberColumn(
                "Multiplier",
                min_value=0.1,
                max_value=20.0,
                step=0.1,
                format="%.2f",
            ),
        }
        if "Items" in show_cols:
            col_cfg["Items"] = st.column_config.NumberColumn(
                format="%d", disabled=True
            )
        edited = st.data_editor(
            edit_df[show_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=[c for c in show_cols if c not in ("Phone", "Multiplier")],
            column_config=col_cfg,
            key="admin_mult_editor",
        )

        if st.button(
            "Save multipliers · update retail",
            type="primary",
            use_container_width=True,
        ):
            updated_builders = 0
            updated_rows = 0
            for _, r in edited.iterrows():
                builder = str(r["Builder"])
                phone = str(r.get("Phone") or "").strip()
                mult = float(r["Multiplier"])
                if mult <= 0:
                    continue
                svc.set_vendor_phone(builder, phone)
                svc.set_vendor_multiplier(
                    builder, mult, notes="Updated from Admin multipliers"
                )
                n = svc.reapply_multiplier(mult, vendor=builder)
                updated_builders += 1
                updated_rows += int(n or 0)
            st.success(
                f"Saved **{updated_builders}** builders · "
                f"recomputed **{updated_rows:,}** retail prices"
            )
            get_service.clear()
            st.rerun()
    else:
        st.info("No builders in the master book yet — drop an Excel file and save it first.")

    with st.expander("Remove a builder from the book"):
        vlist = svc.list_vendors()
        if not vlist:
            st.caption("Nothing to remove.")
        else:
            vv = st.selectbox("Builder", vlist, key="admin_del_vendor")
            if st.button("Remove builder", type="secondary"):
                n = svc.delete_by_vendor(vv)
                st.warning(f"Deleted {n:,} rows for {vv}")
                get_service.clear()
                st.rerun()
