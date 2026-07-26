"""
Price Book System — Streamlit UI (full product)

Tabs: Search · Drop files · Vendors · Admin
All logic via backend.PriceBookService

Run:  streamlit run pricebook_app.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend import PriceBookService
from backend.auth import login_user
from backend.config import APP_DIR, DEFAULT_MULTIPLIER, DEFAULT_SEARCH_LIMIT

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_FAVICON = APP_DIR / "assets" / "favicon.png"
_LOGO = APP_DIR / "assets" / "logo.png"

# Feature flags — content-accuracy phase (set True to restore later)
SHOW_ORDERTRAC_QUOTE = False  # quote tab + search cart + sidebar badge
SHOW_ORDERTRAC_ADMIN = False  # Admin: OrderTrac connection, user sync, push tools
SHOW_SIMPLE_UI = True  # lean Search/Drop/Vendors; hide pins & bulk tools
SHOW_ADMIN_ADVANCED = False  # Viztech / cleanup / deploy / CLI under Admin
# TRACE restore quoting: SHOW_ORDERTRAC_* = True
# TRACE full UI: SHOW_SIMPLE_UI = False; SHOW_ADMIN_ADVANCED = True

st.set_page_config(

    page_title="FAF Price Book",
    page_icon=str(_FAVICON) if _FAVICON.is_file() else "🪵",
    layout="wide",
    initial_sidebar_state="collapsed",  # floor default: full-width search; open « for sign-out/stats
)

# Brand mark in the sidebar (horse & buggy wordmark)
if _LOGO.is_file():
    st.logo(str(_LOGO), size="large")

# iPad / phone-friendly density
st.markdown(
    """
    <style>
      /* Larger tap targets on touch devices */
      @media (max-width: 900px) {
        .stTextInput input, .stSelectbox div[data-baseweb="select"] {
          min-height: 2.6rem;
          font-size: 1.05rem !important;
        }
        div[data-testid="stDataFrame"] { font-size: 0.95rem; }
        .block-container { padding-top: 1rem; padding-left: 0.8rem; padding-right: 0.8rem; }
        button { min-height: 2.5rem; }
      }
      /* Favorite chip row */
      .faf-fav-row button { margin-right: 0.25rem; margin-bottom: 0.25rem; }
      /* Sidebar brand */
      [data-testid="stSidebar"] img { max-width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _favorites_path() -> Path:
    """Prefer project file locally; fall back to home (Streamlit Cloud is often read-only)."""
    local = APP_DIR / ".floor_favorites.json"
    if local.parent.exists() and os.access(str(APP_DIR), os.W_OK):
        return local
    home = Path.home() / ".faf_pricebook"
    home.mkdir(parents=True, exist_ok=True)
    return home / "floor_favorites.json"

# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------


def _require_login() -> bool:
    """Show login form until authenticated. Returns True when logged in."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style="max-width:420px;margin:4rem auto 1rem auto;text-align:center;">
          <div style="font-size:2rem;font-weight:700;color:#2d4a30;">FAF Price Book</div>
          <div style="color:#555;margin-top:0.25rem;">Foothills Amish Furniture · sign in to continue</div>
          <div style="color:#888;margin-top:0.5rem;font-size:0.9rem;">
            Use your FAF floor login
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_c, col_r = st.columns([1, 1.2, 1])
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

# Force password change for OrderTrac-synced accounts
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
                _svc_tmp = PriceBookService()
                _svc_tmp.init()
                _svc_tmp.set_app_user_password(
                    int(st.session_state["auth_user_id"]), npw, must_change=False
                )
                st.session_state["auth_session"]["must_change_password"] = False
                st.success("Password updated.")
                st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Service (after login)
# ---------------------------------------------------------------------------

# Bump when PriceBookService gains methods that Admin/OrderTrac need.
# Stale @st.cache_resource instances omit new methods until cache is cleared.
_SERVICE_CACHE_VERSION = 3


@st.cache_resource
def get_service(_cache_version: int = _SERVICE_CACHE_VERSION) -> PriceBookService:
    """Cached service; version arg forces rebuild after code deploys."""
    svc = PriceBookService()
    svc.init()
    return svc


def _svc() -> PriceBookService:
    """Return a live service; auto-clear cache if OrderTrac methods are missing."""
    svc = get_service(_SERVICE_CACHE_VERSION)
    if not hasattr(svc, "ordertrac_connection_status"):
        get_service.clear()
        svc = get_service(_SERVICE_CACHE_VERSION)
    return svc


@st.cache_data(ttl=60, show_spinner=False)
def _wood_dropdown_options(vendor_key: str) -> list:
    """
    Woods for the Search dropdown, scoped to the selected builder.

    Builder = All → woods across the whole book.
    Specific builder → only species that appear in that builder's rows.
    """
    svc = _svc()
    v = None if not vendor_key or vendor_key == "All" else vendor_key
    try:
        woods = list(svc.list_species(vendor=v) or [])
    except Exception:
        woods = []
    return woods


svc = _svc()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _bytes(upload) -> bytes:
    data = upload.getvalue() if hasattr(upload, "getvalue") else upload.read()
    if hasattr(upload, "seek"):
        try:
            upload.seek(0)
        except Exception:
            pass
    return data


def _auto_col_widths(
    df: pd.DataFrame,
    *,
    min_px: int = 80,
    max_px: int = 640,
    char_px: float = 8.6,
    pad_px: int = 40,
    overrides: dict[str, int] | None = None,
) -> dict[str, int]:
    """Pixel widths sized to the longest value (and header) in each column."""
    overrides = overrides or {}
    widths: dict[str, int] = {}
    for col in df.columns:
        if col in overrides:
            widths[col] = overrides[col]
            continue
        header_len = len(str(col))
        if df.empty:
            max_len = header_len
        else:
            # Full frame is fine — search is capped at DEFAULT_SEARCH_LIMIT
            max_len = max(
                header_len,
                int(df[col].astype(str).fillna("").str.len().max() or 0),
            )
        widths[col] = min(max_px, max(min_px, int(max_len * char_px) + pad_px))
    return widths


def _dataframe_column_config(
    df: pd.DataFrame,
    *,
    money_cols: set[str] | None = None,
    number_formats: dict[str, str] | None = None,
    help_text: dict[str, str] | None = None,
    overrides: dict[str, int] | None = None,
) -> dict:
    """Build st.column_config with content-based widths so cells aren't clipped."""
    money_cols = money_cols or set()
    number_formats = number_formats or {}
    help_text = help_text or {}
    widths = _auto_col_widths(df, overrides=overrides)
    cfg: dict = {}
    for col, w in widths.items():
        if col in money_cols:
            cfg[col] = st.column_config.NumberColumn(
                col,
                format=number_formats.get(col, "$%.2f"),
                width=w,
                help=help_text.get(col),
            )
        elif col in number_formats:
            cfg[col] = st.column_config.NumberColumn(
                col,
                format=number_formats[col],
                width=w,
                help=help_text.get(col),
            )
        else:
            cfg[col] = st.column_config.TextColumn(
                col,
                width=w,
                help=help_text.get(col),
            )
    return cfg


def _last_backup_hint() -> str:
    try:
        from scripts.backup_db import list_backups
    except Exception:
        backup_dir = Path.home() / "Documents" / "FAF-pricebook-backups"
        if not backup_dir.is_dir():
            return "No backup yet"
        files = sorted(
            backup_dir.glob("master_pricebook-*.db"),
            key=lambda p: p.stat().st_mtime,
        )
        if not files:
            return "No backup yet"
        latest = files[-1]
    else:
        files = list_backups(1)
        if not files:
            return "No backup yet"
        latest = files[0]
    age = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%b %d %I:%M %p")
    return f"{latest.name} · {age}"


def _viztech_state_path() -> Path:
    return Path.home() / "Documents" / "FAF-pricebook-backups" / "viztech_sync_state.json"


def _viztech_sync_hint() -> str:
    """Human-readable last Viztech sync status (Admin only)."""
    path = _viztech_state_path()
    if not path.is_file():
        return "Never run — use Install 30-day schedule or Run full sync below."
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        return f"State file issue ({type(exc).__name__}) — run Check Viztech login to refresh."
    if not isinstance(data, dict):
        return "State file empty — run Check Viztech login to refresh."
    when = data.get("last_success") or data.get("last_check") or data.get("last_run") or "?"
    # ISO → short display
    try:
        if isinstance(when, str) and "T" in when:
            when = when.replace("Z", "+00:00")
            # Python 3.9: fromisoformat may not like all offsets; strip micros if needed
            dt = datetime.fromisoformat(when)
            when = dt.strftime("%b %d %Y %I:%M %p UTC")
    except Exception:
        pass
    mode = data.get("mode") or ""
    summary = data.get("summary") or {}
    stats = summary.get("stats") or {}
    bits = [f"Last: {when}"]
    if mode:
        bits.append(f"mode={mode}")
    if summary:
        bits.append(
            f"ok={summary.get('ok', '?')} err={summary.get('err', '?')} "
            f"skip={summary.get('skip', '?')}"
        )
    if stats.get("rows"):
        bits.append(f"book={stats.get('rows'):,} rows / {stats.get('vendors')} builders")
    if data.get("builders_seen"):
        bits.append(f"builders seen={data['builders_seen']}")
    return " · ".join(bits)


def _load_favorites() -> list[str]:
    path = _favorites_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _save_favorites(names: list[str]) -> None:
    clean = []
    seen = set()
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.add(n)
            clean.append(n)
    path = _favorites_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _ensure_active_quote() -> int:
    """Return active quote id; create a draft if none."""
    qid = st.session_state.get("active_quote_id")
    if qid:
        q = svc.get_quote(int(qid))
        if q:
            return int(qid)
    qid = svc.create_quote(
        customer_name="",
        notes="Draft quote from FAF Price Book",
    )
    st.session_state["active_quote_id"] = int(qid)
    return int(qid)


def _quote_sidebar_badge() -> None:
    qid = st.session_state.get("active_quote_id")
    if not qid:
        return
    try:
        t = svc.quote_totals(int(qid))
        q = svc.get_quote(int(qid)) or {}
        st.sidebar.markdown("---")
        st.sidebar.markdown("##### FAF → OrderTrac quote")
        st.sidebar.caption(
            f"**{q.get('quote_number') or qid}** · {t.get('line_count', 0)} lines"
        )
        st.sidebar.metric("Quote total", f"${t.get('grand_total', 0):,.2f}")
        if q.get("ordertrac_so_id"):
            st.sidebar.caption(f"OrderTrac QUOTE **#{q.get('ordertrac_so_id')}**")
            if q.get("ordertrac_url"):
                st.sidebar.markdown(f"[Open in OrderTrac]({q['ordertrac_url']})")
    except Exception:
        pass


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
    ):
        st.session_state.pop(k, None)
    st.rerun()

stats = svc.stats()
st.sidebar.metric("Master rows", f"{stats['rows']:,}")
st.sidebar.caption(
    f"{stats['vendors']} vendors · {stats['collections']} collections"
)
if SHOW_ORDERTRAC_QUOTE:
    _quote_sidebar_badge()
# Viztech sync status lives under Admin only (hidden from floor sidebar)

# ---------------------------------------------------------------------------
# Home dashboard strip
# ---------------------------------------------------------------------------

if SHOW_SIMPLE_UI:
    st.caption(
        f"**FAF Price Book** · accuracy mode · "
        f"{stats['rows']:,} rows · {stats['vendors']} builders"
    )
else:
    d1, d2, d3 = st.columns([1, 1, 2.2])
    d1.metric("Price rows", f"{stats['rows']:,}")
    d2.metric("Builders", f"{stats['vendors']}")
    with d3:
        st.caption("Store")
        st.markdown(
            "<div style='font-size:1.35rem;font-weight:600;line-height:1.3;"
            "color:inherit;padding-top:0.15rem;'>Foothills Amish Furniture</div>",
            unsafe_allow_html=True,
        )
    st.info(
        "**Content accuracy mode** — quoting & OrderTrac are hidden. "
        "Use **Search**, **Drop files**, and **Vendors** to verify and rebuild the catalog."
    )

# ===========================================================================
# TABS
# ===========================================================================

if SHOW_ORDERTRAC_QUOTE:
    tab_search, tab_quote, tab_import, tab_vendors, tab_admin = st.tabs(
        [
            "Search",
            "OrderTrac quote",
            "Drop files",
            "Vendors",
            "Admin",
        ]
    )
else:
    tab_search, tab_import, tab_vendors, tab_admin = st.tabs(
        [
            "Search",
            "Drop files",
            "Vendors",
            "Admin",
        ]
    )
    tab_quote = None

# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------
with tab_search:
    st.subheader("Find a price")

    # Apply pin selection BEFORE any widgets with keys sq/sv/sf exist
    # (Streamlit forbids changing those keys after the widgets are created)
    _pending_pin = st.session_state.pop("_pin_select", None)
    if _pending_pin is not None:
        st.session_state["sq"] = ""
        st.session_state["sv"] = _pending_pin
        st.session_state["sf"] = "finished"

    all_vendors = svc.list_vendors()
    favorites = [v for v in _load_favorites() if v in all_vendors]

    # Pinned-builders rail (off in simple accuracy UI)
    if "pin_panel_open" not in st.session_state:
        st.session_state["pin_panel_open"] = False
    pins_open = bool(st.session_state["pin_panel_open"]) and not SHOW_SIMPLE_UI

    if pins_open:
        search_col, pin_col = st.columns([3.4, 1.15], gap="large")
    else:
        search_col = st.container()
        pin_col = None

    with search_col:
        if not pins_open:
            # Compact control to reopen the pin rail
            t1, t2 = st.columns([5.5, 1.2])
            with t2:
                n_pins = len(favorites)
                label = f"Pins ({n_pins}) ›" if n_pins else "Pins ›"
                if st.button(
                    label,
                    key="show_pin_panel",
                    use_container_width=True,
                    help="Show pinned builders column",
                ):
                    st.session_state["pin_panel_open"] = True
                    st.rerun()
        q = st.text_input(
            "Search the master book",
            placeholder="Part # or product words…",
            key="sq",
            label_visibility="collapsed",
        )

        vendors = ["All"] + all_vendors
        # Put favorites first after All for faster floor pick in dropdown only
        if favorites:
            rest = [v for v in all_vendors if v not in favorites]
            vendors = ["All"] + favorites + rest

        f1, f2, f3, f4 = st.columns([1.45, 1.25, 0.95, 0.85])
        with f1:
            vf = st.selectbox("Builder", vendors, key="sv")
        with f2:
            # Wood — only species used by the selected builder (or whole book if All)
            wood_list = _wood_dropdown_options(vf if vf else "All")
            wood_opts = ["All"] + [w for w in wood_list if w and w != "All"]
            # Keep session value valid when Builder changes
            if "sw" in st.session_state and st.session_state["sw"] not in wood_opts:
                st.session_state["sw"] = "All"
            wf = st.selectbox(
                "Wood",
                options=wood_opts,
                key="sw",
                help="Only woods available for the selected builder. "
                "Multi-wood price tiers match if they include the wood you pick.",
            )
            if vf != "All" and len(wood_opts) <= 1:
                st.caption("No wood options parsed for this builder.")
        with f3:
            # Floor default: finished only
            finish_opts = ["finished", "All", "unfinished"]
            ff = st.selectbox("Finish", finish_opts, index=0, key="sf")
        with f4:
            if not SHOW_SIMPLE_UI:
                st.write("")  # align with selectboxes
                st.write("")
                if vf != "All":
                    if vf in favorites:
                        if st.button(
                            "Unpin", key="unpin_builder", use_container_width=True
                        ):
                            _save_favorites([x for x in favorites if x != vf])
                            st.rerun()
                    else:
                        if st.button(
                            "Pin builder", key="pin_builder", use_container_width=True
                        ):
                            _save_favorites(favorites + [vf])
                            st.rerun()

        # Don't dump the whole book when search is empty — unless a builder is chosen
        if not (q or "").strip() and vf == "All":
            results = pd.DataFrame()
            empty_reason = "type"
        else:
            try:
                results = svc.search(
                    q,
                    vendor=None if vf == "All" else vf,
                    collection=None,  # Collection filter hidden on floor UI
                    finish_state=None if ff == "All" else ff,
                    species=None if wf == "All" else wf,
                    limit=DEFAULT_SEARCH_LIMIT,
                )
                empty_reason = "none" if results.empty else ""
            except Exception as exc:
                results = pd.DataFrame()
                empty_reason = "error"
                st.error(f"Search failed: {exc}")
        display = results.copy()
        # With a wood filter, show that wood (not the full multi-wood tier string)
        if not display.empty and wf and wf != "All" and "species" in display.columns:
            display = display.copy()
            display["species"] = wf

        # Floor table emphasizes RETAIL
        if display.empty:
            if empty_reason == "type":
                st.info(
                    "Type a part number or product words above — or pick a **Builder** "
                    "to browse (or use **Pinned** on the right)."
                )
            elif empty_reason == "error":
                pass  # error already shown
            else:
                if ff == "finished" and vf != "All":
                    st.info(
                        "No **finished** hits for this builder — try **Finish → All** "
                        "(or **unfinished**), or clear the search box."
                    )
                else:
                    st.info(
                        "No hits — try fewer words, Boolean **OR**, or check "
                        "**Builder** / **Finish** filters."
                    )
        else:
            hit_note = f"**{len(display):,}** hits"
            if len(display) >= DEFAULT_SEARCH_LIMIT:
                hit_note += f" (showing first {DEFAULT_SEARCH_LIMIT})"
            st.markdown(
                f"{hit_note} · "
                f"<span style='color:#2d4a30;font-weight:700'>Retail is what the customer pays</span>",
                unsafe_allow_html=True,
            )
            # Floor view: retail only (wholesale/mult managed on Vendors tab)
            show_cols = [
                c
                for c in [
                    "collection",
                    "part_number",
                    "description",
                    "vendor",
                    "species",
                    "finish_state",
                    "adjusted_price",
                ]
                if c in display.columns
            ]
            view = display[show_cols].rename(
                columns={
                    "part_number": "Part #",
                    "description": "Description",
                    "vendor": "Builder",
                    "collection": "Collection",
                    "species": "Wood",
                    "finish_state": "Finish",
                    "adjusted_price": "RETAIL",
                }
            )
            if wf and wf != "All":
                st.caption(
                    f"Wood filter: **{wf}** · multi-wood tiers that include this wood use the same retail price."
                )
            # Content-based widths so headers + values fully show (scrolls if needed)
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config=_dataframe_column_config(
                    view,
                    money_cols={"RETAIL"},
                    number_formats={"RETAIL": "$%.0f"},
                    help_text={
                        "RETAIL": "Customer price — wholesale × mult, rolled up to next even dollar",
                        "Wood": "Wood species / option — use the Wood dropdown above to pick one",
                    },
                    overrides={
                        "Part #": 110,
                        "Wood": 160,
                        "Finish": 100,
                        "RETAIL": 100,
                    },
                ),
                height=480,
            )

            if SHOW_ORDERTRAC_QUOTE:
                if "id" in results.columns and not results.empty:
                    st.markdown("##### Add to OrderTrac quote (from FAF price)")
                    st.caption(
                        "Selections come from **this FAF price book** (retail = wholesale × mult). "
                        "Build the cart here, then open **OrderTrac quote** tab → "
                        "**Create OrderTrac quote**."
                    )
                    labels = []
                    id_by_label = {}
                    for _, r in results.head(80).iterrows():
                        rid = int(r["id"])
                        part = str(r.get("part_number") or "")[:28]
                        desc = str(r.get("description") or "")[:36]
                        retail = float(r.get("adjusted_price") or 0)
                        lab = f"#{rid} · {part} · ${retail:,.0f} · {desc}"
                        labels.append(lab)
                        id_by_label[lab] = rid
                    aq1, aq2, aq3, aq4 = st.columns([3.2, 0.8, 1.4, 1.2])
                    with aq1:
                        pick = st.selectbox(
                            "FAF catalog line",
                            labels,
                            key="add_quote_pick",
                            label_visibility="collapsed",
                        )
                    with aq2:
                        add_qty = st.number_input(
                            "Qty", min_value=0.5, value=1.0, step=1.0, key="add_quote_qty"
                        )
                    with aq3:
                        # Prefer quote defaults, then free type
                        _def_stain = st.session_state.get(
                            "quote_stain_default", "Michael's Cherry (OCS-113)"
                        )
                        add_stain = st.text_input(
                            "Stain",
                            value=_def_stain,
                            key="add_quote_stain",
                            placeholder="Stain name / OCS…",
                        )
                    with aq4:
                        st.write("")
                        st.write("")
                        if st.button(
                            "Add from FAF → quote",
                            type="primary",
                            key="btn_add_to_quote",
                            use_container_width=True,
                        ):
                            try:
                                qid = _ensure_active_quote()
                                rid = id_by_label[pick]
                                # Prefer Search wood filter; else quote default wood
                                wood_sel = (
                                    None
                                    if wf == "All"
                                    else wf
                                ) or st.session_state.get("quote_wood_default")
                                finish_sel = (
                                    None if ff == "All" else ff
                                ) or st.session_state.get(
                                    "quote_finish_default", "finished"
                                )
                                stain_sel = (add_stain or "").strip() or st.session_state.get(
                                    "quote_stain_default", ""
                                )
                                svc.add_quote_line_from_id(
                                    qid,
                                    rid,
                                    qty=float(add_qty),
                                    species_override=wood_sel,
                                    finish_override=finish_sel,
                                    stain=stain_sel,
                                )
                                if stain_sel:
                                    st.session_state["quote_stain_default"] = stain_sel
                                if wood_sel:
                                    st.session_state["quote_wood_default"] = wood_sel
                                qn = (svc.get_quote(qid) or {}).get("quote_number")
                                st.success(
                                    f"Added FAF #{rid} → **{qn}** "
                                    f"({wood_sel or 'wood?'} / {stain_sel or 'stain?'})"
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not add line: {exc}")

    # ---- Separate pinned-builders column (collapsible) ----
    if pin_col is not None:
        with pin_col:
            head_l, head_r = st.columns([3.2, 1.0])
            with head_l:
                st.markdown("##### Pinned builders")
            with head_r:
                if st.button(
                    "‹ Hide",
                    key="hide_pin_panel",
                    use_container_width=True,
                    help="Collapse pinned builders column",
                ):
                    st.session_state["pin_panel_open"] = False
                    st.rerun()
            st.caption("Tap to filter search · pin from the Builder menu")
            if not favorites:
                st.info("No pins yet. Choose a **Builder**, then **Pin builder**.")
            else:
                for i, name in enumerate(favorites[:24]):
                    active = (
                        st.session_state.get("sv") == name
                        and not (st.session_state.get("sq") or "").strip()
                    )
                    label = f"● {name}" if active else name
                    if st.button(
                        label,
                        key=f"fav_pick_{i}",
                        use_container_width=True,
                        type="primary" if active else "secondary",
                    ):
                        # Defer widget key updates to next run (before widgets instantiate)
                        st.session_state["_pin_select"] = name
                        st.rerun()
                if st.button("Clear pins", key="clear_all_pins", use_container_width=True):
                    _save_favorites([])
                    st.rerun()

if SHOW_ORDERTRAC_QUOTE and tab_quote is not None:
    # ---------------------------------------------------------------------------
    # ORDERTRAC QUOTE — FAF price book is source; OrderTrac is destination
    # ---------------------------------------------------------------------------
    with tab_quote:
        st.subheader("OrderTrac quote (from FAF Price Book)")
        st.markdown(
            """
    **Flow:** **Search** FAF prices → **Add from FAF → quote** → review here →
    **Create OrderTrac quote** (type stays **Quote**, never a sale).

    Prices always come from the FAF master book (wholesale × mult). OrderTrac
    receives custom lines with FAF id, wood, stain, finish, and retail.
    """
        )

        # ---- Quote picker / new ----
        qlist = svc.list_quotes(limit=50)
        q_options = ["— New FAF quote —"]
        q_id_map = {"— New FAF quote —": None}
        if qlist is not None and not qlist.empty:
            for _, qr in qlist.iterrows():
                ot_tag = ""
                if qr.get("ordertrac_so_id"):
                    ot_tag = f" · OT #{qr.get('ordertrac_so_id')}"
                lab = (
                    f"{qr.get('quote_number')} · "
                    f"{qr.get('customer_name') or '(no customer)'} · "
                    f"{int(qr.get('line_count') or 0)} lines · "
                    f"${float(qr.get('lines_subtotal') or 0):,.0f}{ot_tag}"
                )
                q_options.append(lab)
                q_id_map[lab] = int(qr["id"])

        active = st.session_state.get("active_quote_id")
        default_ix = 0
        if active:
            for i, lab in enumerate(q_options):
                if q_id_map.get(lab) == int(active):
                    default_ix = i
                    break

        qc1, qc2, qc3 = st.columns([2.5, 1, 1])
        with qc1:
            q_pick = st.selectbox(
                "FAF quote (staging for OrderTrac)",
                q_options,
                index=min(default_ix, len(q_options) - 1),
                key="quote_open_pick",
            )
        with qc2:
            st.write("")
            st.write("")
            if st.button("Open / create", type="primary", use_container_width=True):
                if q_pick == "— New FAF quote —" or q_id_map.get(q_pick) is None:
                    st.session_state["active_quote_id"] = svc.create_quote(
                        notes="FAF Price Book → OrderTrac quote"
                    )
                else:
                    st.session_state["active_quote_id"] = q_id_map[q_pick]
                st.rerun()
        with qc3:
            st.write("")
            st.write("")
            if st.button("New blank quote", use_container_width=True):
                st.session_state["active_quote_id"] = svc.create_quote(
                    notes="FAF Price Book → OrderTrac quote"
                )
                st.rerun()

        qid = st.session_state.get("active_quote_id")
        if not qid:
            st.info(
                "1) Create a quote · 2) **Search** tab → **Add from FAF → quote** · "
                "3) Come back here → **Create OrderTrac quote**."
            )
        else:
            quote = svc.get_quote(int(qid))
            if not quote:
                st.warning("Quote not found — create a new one.")
                st.session_state.pop("active_quote_id", None)
            else:
                # OrderTrac link banner
                if quote.get("ordertrac_url") or quote.get("ordertrac_so_id"):
                    so = quote.get("ordertrac_so_id") or "—"
                    st.success(
                        f"Linked to OrderTrac **QUOTE #{so}** · "
                        f"pushed {quote.get('ordertrac_pushed_at') or '—'}"
                    )
                    if quote.get("ordertrac_url"):
                        st.markdown(
                            f"[Open this quote in OrderTrac]({quote['ordertrac_url']})"
                        )

                # ---- Customer / header ----
                st.markdown(
                    f"##### FAF {quote.get('quote_number')} · `{quote.get('status')}` "
                    f"→ OrderTrac destination"
                )
                h1, h2 = st.columns(2)
                with h1:
                    cust = st.text_input(
                        "Customer name",
                        value=quote.get("customer_name") or "",
                        key=f"q_cust_{qid}",
                    )
                    phone = st.text_input(
                        "Phone",
                        value=quote.get("customer_phone") or "",
                        key=f"q_phone_{qid}",
                    )
                    email = st.text_input(
                        "Email",
                        value=quote.get("customer_email") or "",
                        key=f"q_email_{qid}",
                    )
                with h2:
                    notes = st.text_area(
                        "Notes",
                        value=quote.get("notes") or "",
                        height=100,
                        key=f"q_notes_{qid}",
                    )
                    d1, d2 = st.columns(2)
                    with d1:
                        disc = st.number_input(
                            "Discount %",
                            min_value=0.0,
                            max_value=100.0,
                            value=float(quote.get("discount_pct") or 0),
                            step=1.0,
                            key=f"q_disc_{qid}",
                        )
                    with d2:
                        tax = st.number_input(
                            "Tax %",
                            min_value=0.0,
                            max_value=20.0,
                            value=float(quote.get("tax_pct") or 0),
                            step=0.25,
                            key=f"q_tax_{qid}",
                        )

                # ---- Adjustable wood / stain (apply to quote + lines) ----
                st.markdown("##### Wood & stain (adjustable)")
                st.caption(
                    "Change these anytime. Use **Apply to all lines** so every cart line "
                    "and OrderTrac push use the same wood/stain."
                )
                # Common woods from catalog + free entry
                try:
                    _woods = list(svc.list_species(vendor=None) or [])
                except Exception:
                    _woods = []
                _core_woods = [
                    "Red Oak",
                    "QSWO",
                    "White Oak",
                    "Brown Maple",
                    "Cherry",
                    "Hickory",
                    "Walnut",
                    "Soft Maple",
                    "Hard Maple",
                    "Rustic Cherry",
                    "Wormy Maple",
                ]
                wood_choices = []
                for w in _core_woods + _woods:
                    if w and w not in wood_choices:
                        wood_choices.append(w)
                if "Other / type below…" not in wood_choices:
                    wood_choices.append("Other / type below…")

                _common_stains = [
                    "Michael's Cherry (OCS-113)",
                    "Asbury (OCS-111)",
                    "Espresso (OCS-228)",
                    "Washington (OCS-109)",
                    "S-2 (OCS-104)",
                    "Natural",
                    "Clear",
                    "Custom / type below…",
                ]

                # Session defaults (do not pass value= with key= — breaks editing)
                if "quote_wood_default" not in st.session_state:
                    st.session_state["quote_wood_default"] = "Red Oak"
                if "quote_stain_default" not in st.session_state:
                    st.session_state["quote_stain_default"] = "Michael's Cherry (OCS-113)"

                cur_wood = st.session_state["quote_wood_default"]
                wood_ix = (
                    wood_choices.index(cur_wood)
                    if cur_wood in wood_choices
                    else len(wood_choices) - 1
                )
                cur_stain = st.session_state["quote_stain_default"]
                stain_ix = (
                    _common_stains.index(cur_stain)
                    if cur_stain in _common_stains
                    else len(_common_stains) - 1
                )

                wcol1, wcol2 = st.columns(2)
                with wcol1:
                    wood_pick = st.selectbox(
                        "Wood",
                        wood_choices,
                        index=wood_ix,
                        key=f"q_wood_pick_{qid}",
                    )
                    if wood_pick == "Other / type below…":
                        wood_default = st.text_input(
                            "Custom wood",
                            key=f"q_wood_custom_{qid}",
                            placeholder="Type wood species…",
                        )
                    else:
                        wood_default = wood_pick
                with wcol2:
                    stain_pick = st.selectbox(
                        "Stain",
                        _common_stains,
                        index=stain_ix,
                        key=f"q_stain_pick_{qid}",
                    )
                    if stain_pick == "Custom / type below…":
                        stain_default = st.text_input(
                            "Custom stain",
                            key=f"q_stain_custom_{qid}",
                            placeholder="Type stain name / OCS code…",
                        )
                    else:
                        stain_default = stain_pick

                wood_default = (wood_default or "").strip()
                stain_default = (stain_default or "").strip()
                if wood_default:
                    st.session_state["quote_wood_default"] = wood_default
                if stain_default:
                    st.session_state["quote_stain_default"] = stain_default

                finish_default = st.selectbox(
                    "Finish",
                    ["finished", "unfinished"],
                    index=0
                    if st.session_state.get("quote_finish_default", "finished")
                    == "finished"
                    else 1,
                    key=f"q_finish_{qid}",
                )
                st.session_state["quote_finish_default"] = finish_default

                hs1, hs2, hs3 = st.columns(3)
                with hs1:
                    if st.button("Save customer / rates", key=f"q_save_hdr_{qid}"):
                        note_out = (notes or "").strip()
                        # Replace existing Wood/Stain lines or append
                        import re as _re

                        note_out = _re.sub(
                            r"(?im)^Wood:.*$", "", note_out
                        ).strip()
                        note_out = _re.sub(
                            r"(?im)^Stain:.*$", "", note_out
                        ).strip()
                        note_out = _re.sub(
                            r"(?im)^Finish:.*$", "", note_out
                        ).strip()
                        spec_lines = []
                        if wood_default:
                            spec_lines.append(f"Wood: {wood_default}")
                        if stain_default:
                            spec_lines.append(f"Stain: {stain_default}")
                        if finish_default:
                            spec_lines.append(f"Finish: {finish_default}")
                        if spec_lines:
                            note_out = (note_out + "\n" + "\n".join(spec_lines)).strip()
                        svc.update_quote(
                            int(qid),
                            customer_name=cust.strip(),
                            customer_phone=phone.strip(),
                            customer_email=email.strip(),
                            notes=note_out,
                            discount_pct=float(disc),
                            tax_pct=float(tax),
                        )
                        st.success("Quote header saved (including wood/stain).")
                        st.rerun()
                with hs2:
                    if st.button(
                        "Apply wood/stain to all lines",
                        type="primary",
                        key=f"q_apply_ws_{qid}",
                        help="Update every line's wood, finish, and stain",
                    ):
                        try:
                            import re as _re

                            _lines = svc.quote_lines(int(qid))
                            n_upd = 0
                            for _, lr in _lines.iterrows():
                                lid = int(lr["id"])
                                old_notes = str(lr.get("notes") or "")
                                cleaned = _re.sub(
                                    r"(?i)\s*Stain:\s*[^·|\n]*", "", old_notes
                                ).strip(" ·|\n")
                                new_notes = (
                                    f"{cleaned} · Stain: {stain_default}".strip(" ·")
                                    if stain_default and cleaned
                                    else (
                                        f"Stain: {stain_default}"
                                        if stain_default
                                        else cleaned
                                    )
                                )
                                svc.update_quote_line(
                                    lid,
                                    species=wood_default or lr.get("species"),
                                    finish_state=finish_default
                                    or lr.get("finish_state"),
                                    notes=new_notes,
                                )
                                n_upd += 1
                            # Keep header notes in sync
                            note_out = (notes or "").strip()
                            note_out = _re.sub(r"(?im)^Wood:.*$", "", note_out).strip()
                            note_out = _re.sub(r"(?im)^Stain:.*$", "", note_out).strip()
                            note_out = _re.sub(r"(?im)^Finish:.*$", "", note_out).strip()
                            bits = []
                            if wood_default:
                                bits.append(f"Wood: {wood_default}")
                            if stain_default:
                                bits.append(f"Stain: {stain_default}")
                            if finish_default:
                                bits.append(f"Finish: {finish_default}")
                            if bits:
                                note_out = (note_out + "\n" + "\n".join(bits)).strip()
                            svc.update_quote(
                                int(qid),
                                notes=note_out,
                                customer_name=cust.strip(),
                                customer_phone=phone.strip(),
                                customer_email=email.strip(),
                                discount_pct=float(disc),
                                tax_pct=float(tax),
                            )
                            st.success(
                                f"Applied **{wood_default}** / **{stain_default}** / "
                                f"**{finish_default}** to {n_upd} line(s)."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with hs3:
                    st.caption(
                        f"Active: **{wood_default or '—'}** · "
                        f"**{stain_default or '—'}** · **{finish_default}**"
                    )

                # ---- Lines ----
                lines = svc.quote_lines(int(qid))
                totals = svc.quote_totals(int(qid))
                tcols = st.columns(4)
                tcols[0].metric("Lines", totals.get("line_count", 0))
                tcols[1].metric("Subtotal", f"${totals.get('subtotal', 0):,.2f}")
                tcols[2].metric("Tax", f"${totals.get('tax_amount', 0):,.2f}")
                tcols[3].metric("**TOTAL**", f"${totals.get('grand_total', 0):,.2f}")

                if lines is None or lines.empty:
                    st.info(
                        "No FAF lines yet. Go to **Search**, pick a price, then "
                        "**Add from FAF → quote**."
                    )
                else:
                    show = lines.copy()
                    # Friendly columns
                    keep = [
                        c
                        for c in [
                            "id",
                            "line_no",
                            "qty",
                            "part_number",
                            "description",
                            "vendor",
                            "species",
                            "finish_state",
                            "unit_base",
                            "unit_retail",
                            "line_discount_pct",
                            "line_total",
                            "notes",
                            "pricebook_id",
                        ]
                        if c in show.columns
                    ]
                    show = show[keep].rename(
                        columns={
                            "line_no": "#",
                            "part_number": "Part #",
                            "description": "Description",
                            "vendor": "Builder",
                            "species": "Wood",
                            "finish_state": "Finish",
                            "unit_base": "Wholesale",
                            "unit_retail": "Retail each",
                            "line_discount_pct": "Disc %",
                            "line_total": "Line total",
                            "pricebook_id": "FAF id",
                        }
                    )
                    st.dataframe(
                        show.drop(columns=["id"], errors="ignore"),
                        use_container_width=True,
                        hide_index=True,
                        height=min(420, 80 + 36 * len(show)),
                    )

                    # Edit one line
                    with st.expander("Edit or remove a line"):
                        line_ids = lines["id"].tolist()
                        labels_l = []
                        for _, r in lines.iterrows():
                            labels_l.append(
                                f"id {int(r['id'])} · {r.get('part_number') or ''} · "
                                f"{r.get('species') or ''} · qty {r.get('qty')} · "
                                f"${float(r.get('line_total') or 0):,.2f}"
                            )
                        lab_to_id = dict(zip(labels_l, line_ids))
                        elab = st.selectbox("Line", labels_l, key=f"q_edit_line_{qid}")
                        erow = lines[lines["id"] == lab_to_id[elab]].iloc[0]
                        e1, e2, e3 = st.columns(3)
                        with e1:
                            eqty = st.number_input(
                                "Qty",
                                min_value=0.0,
                                value=float(erow.get("qty") or 1),
                                step=1.0,
                                key=f"q_eqty_{qid}",
                            )
                        with e2:
                            eretail = st.number_input(
                                "Retail each",
                                min_value=0.0,
                                value=float(erow.get("unit_retail") or 0),
                                step=1.0,
                                key=f"q_eretail_{qid}",
                            )
                        with e3:
                            edisc = st.number_input(
                                "Line disc %",
                                min_value=0.0,
                                max_value=100.0,
                                value=float(erow.get("line_discount_pct") or 0),
                                step=1.0,
                                key=f"q_edisc_{qid}",
                            )
                        e4, e5, e6 = st.columns(3)
                        with e4:
                            ewood = st.text_input(
                                "Wood",
                                value=str(erow.get("species") or ""),
                                key=f"q_ewood_{qid}",
                            )
                        with e5:
                            # extract stain from notes if present
                            import re as _re

                            _sn = str(erow.get("notes") or "")
                            _sm = _re.search(r"(?i)Stain:\s*([^·|\n]+)", _sn)
                            _stain0 = (
                                _sm.group(1).strip()
                                if _sm
                                else st.session_state.get("quote_stain_default", "")
                            )
                            estain = st.text_input(
                                "Stain",
                                value=_stain0,
                                key=f"q_estain_{qid}",
                            )
                        with e6:
                            efin = st.selectbox(
                                "Finish",
                                ["finished", "unfinished"],
                                index=0
                                if str(erow.get("finish_state") or "finished")
                                == "finished"
                                else 1,
                                key=f"q_efin_{qid}",
                            )
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("Update line", key=f"q_upd_line_{qid}"):
                                nnotes = str(erow.get("notes") or "")
                                nnotes = _re.sub(
                                    r"(?i)\s*Stain:\s*[^·|\n]*", "", nnotes
                                ).strip(" ·")
                                if (estain or "").strip():
                                    nnotes = (
                                        f"{nnotes} · Stain: {estain.strip()}".strip(" ·")
                                        if nnotes
                                        else f"Stain: {estain.strip()}"
                                    )
                                svc.update_quote_line(
                                    int(lab_to_id[elab]),
                                    qty=float(eqty),
                                    unit_retail=float(eretail),
                                    line_discount_pct=float(edisc),
                                    species=(ewood or "").strip() or erow.get("species"),
                                    finish_state=efin,
                                    notes=nnotes,
                                )
                                st.success("Line updated (qty, price, wood, stain, finish).")
                                st.rerun()
                        with b2:
                            if st.button("Remove line", key=f"q_del_line_{qid}"):
                                svc.delete_quote_line(int(lab_to_id[elab]))
                                st.warning("Line removed.")
                                st.rerun()

                    # Custom line
                    with st.expander("Add custom line (not in catalog)"):
                        cdesc = st.text_input("Description", key=f"q_cdesc_{qid}")
                        c2, c3, c4 = st.columns(3)
                        with c2:
                            cqty = st.number_input(
                                "Qty", min_value=0.5, value=1.0, key=f"q_cqty_{qid}"
                            )
                        with c3:
                            cprice = st.number_input(
                                "Retail each", min_value=0.0, value=0.0, key=f"q_cprice_{qid}"
                            )
                        with c4:
                            cvend = st.text_input("Builder", key=f"q_cvend_{qid}")
                        if st.button("Add custom line", key=f"q_add_custom_{qid}"):
                            if not cdesc.strip():
                                st.error("Description required.")
                            else:
                                svc.add_custom_quote_line(
                                    int(qid),
                                    description=cdesc.strip(),
                                    qty=float(cqty),
                                    unit_retail=float(cprice),
                                    vendor=cvend.strip(),
                                )
                                st.success("Custom line added.")
                                st.rerun()

                # ---- Primary: Create in OrderTrac ----
                st.markdown("##### Create in OrderTrac")
                st.caption(
                    "This is the main action: FAF prices → new OrderTrac **Quote** "
                    "(not a sale). Requires OrderTrac session "
                    "(`python scripts/ordertrac_login.py` if expired)."
                )
                # Salesperson for OT SO User field
                ot_user_opts = ["Miller, Judson"]
                try:
                    udf = svc.list_app_users(active_only=True)
                    if (
                        udf is not None
                        and not udf.empty
                        and "ordertrac_display_name" in udf.columns
                    ):
                        names = [
                            x
                            for x in udf["ordertrac_display_name"].dropna().tolist()
                            if str(x).strip()
                        ]
                        if names:
                            ot_user_opts = names
                except Exception:
                    pass
                sess = st.session_state.get("auth_session") or {}
                default_ot = sess.get("ordertrac_display_name") or ot_user_opts[0]
                if default_ot not in ot_user_opts:
                    ot_user_opts = [default_ot] + ot_user_opts
                ot_ix = (
                    ot_user_opts.index(default_ot) if default_ot in ot_user_opts else 0
                )

                otu1, otu2 = st.columns([2, 1])
                with otu1:
                    ot_user = st.selectbox(
                        "OrderTrac sales user (on the quote)",
                        ot_user_opts,
                        index=ot_ix,
                        key=f"q_ot_user_{qid}",
                    )
                with otu2:
                    ot_loc = st.selectbox(
                        "Location",
                        ["Landrum", "Foothills Cabinets"],
                        key=f"q_ot_loc_{qid}",
                    )

                has_lines = lines is not None and not lines.empty
                linked = bool(quote.get("ordertrac_guid") or quote.get("ordertrac_so_id"))

                def _save_header_and_push(mode: str):
                    svc.update_quote(
                        int(qid),
                        customer_name=cust.strip(),
                        customer_phone=phone.strip(),
                        customer_email=email.strip(),
                        notes=notes,
                        discount_pct=float(disc),
                        tax_pct=float(tax),
                    )
                    return svc.push_quote_to_ordertrac(
                        int(qid),
                        ot_user_display=ot_user,
                        location=ot_loc,
                        mode=mode,
                    )

                b_create, b_append = st.columns(2)
                with b_create:
                    if st.button(
                        "Create OrderTrac quote from FAF",
                        type="primary",
                        use_container_width=True,
                        disabled=not has_lines,
                        key=f"q_create_ot_{qid}",
                        help="New OrderTrac QUOTE with all FAF cart lines",
                    ):
                        with st.spinner(
                            "Creating OrderTrac QUOTE from FAF pricelist lines…"
                        ):
                            try:
                                result = _save_header_and_push("create")
                                if result.get("ok"):
                                    st.success(
                                        f"OrderTrac **QUOTE #{result.get('sales_order_id')}** "
                                        f"created from FAF **{quote.get('quote_number')}** "
                                        f"({result.get('lines_added', '?')} lines)."
                                    )
                                    if result.get("url"):
                                        st.markdown(
                                            f"[Open OrderTrac quote]({result['url']})"
                                        )
                                    st.rerun()
                                else:
                                    st.error(
                                        result.get("error")
                                        or "Create incomplete — check session / lines"
                                    )
                                    st.json(result)
                            except Exception as e:
                                st.error(str(e))
                with b_append:
                    if st.button(
                        "Add FAF lines → linked OrderTrac quote",
                        use_container_width=True,
                        disabled=not (has_lines and linked),
                        key=f"q_append_ot_{qid}",
                        help="Open the linked OrderTrac quote and add any new FAF lines not already there",
                    ):
                        with st.spinner(
                            "Adding new FAF lines onto linked OrderTrac quote…"
                        ):
                            try:
                                result = _save_header_and_push("append")
                                if result.get("ok"):
                                    st.success(
                                        f"OrderTrac **QUOTE #{result.get('sales_order_id')}** updated · "
                                        f"added {result.get('lines_added', 0)}, "
                                        f"already present {result.get('lines_skipped', 0)}."
                                    )
                                    if result.get("url"):
                                        st.markdown(
                                            f"[Open OrderTrac quote]({result['url']})"
                                        )
                                    st.rerun()
                                else:
                                    st.error(
                                        result.get("error")
                                        or "Add incomplete — check session / link"
                                    )
                                    st.json(result)
                            except Exception as e:
                                st.error(str(e))

                if not has_lines:
                    st.warning(
                        "Add FAF catalog lines from **Search → Add from FAF → quote** first."
                    )
                elif not linked:
                    st.caption(
                        "After the first create, you can add more items from Search and use "
                        "**Add FAF lines → linked OrderTrac quote**."
                    )

                # ---- Secondary: Export / delete ----
                st.markdown("##### Local export")
                x1, x2, x3 = st.columns(3)
                with x1:
                    try:
                        pdf_bytes = svc.export_quote_pdf(int(qid))
                        st.download_button(
                            "Download PDF",
                            data=pdf_bytes,
                            file_name=f"{quote.get('quote_number') or 'quote'}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.caption(f"PDF: {e}")
                with x2:
                    try:
                        xls_bytes = svc.export_quote_excel(int(qid))
                        st.download_button(
                            "Download Excel",
                            data=xls_bytes,
                            file_name=f"{quote.get('quote_number') or 'quote'}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.caption(f"Excel: {e}")
                with x3:
                    if st.button(
                        "Delete FAF quote",
                        use_container_width=True,
                    ):
                        svc.delete_quote(int(qid))
                        st.session_state.pop("active_quote_id", None)
                        st.warning("FAF quote deleted (OrderTrac copy unchanged).")
                        st.rerun()

                # Status
                s1, s2 = st.columns(2)
                with s1:
                    new_status = st.selectbox(
                        "Status",
                        ["draft", "sent", "won", "lost", "archived"],
                        index=["draft", "sent", "won", "lost", "archived"].index(
                            quote.get("status")
                            if quote.get("status")
                            in ("draft", "sent", "won", "lost", "archived")
                            else "draft"
                        ),
                        key=f"q_status_{qid}",
                    )
                with s2:
                    st.write("")
                    st.write("")
                    if st.button("Update status", key=f"q_status_btn_{qid}"):
                        svc.update_quote(int(qid), status=new_status)
                        st.success(f"Status → {new_status}")
                        st.rerun()

# ---------------------------------------------------------------------------
# IMPORT — multi-file drop with per-builder multiplier
# ---------------------------------------------------------------------------
with tab_import:
    st.subheader("Drop builder price lists")
    if SHOW_SIMPLE_UI:
        st.caption(
            "Upload Excel or PDF · set **builder** + **multiplier** · replaces that builder’s catalog."
        )
    else:
        st.markdown(
            """
Upload one or many **Excel** (`.xlsx` / `.xls` / `.xlsm`) or **PDF** files.

For **each file** you set:
1. **Builder name** (auto-detected from filename — edit if needed)
2. **Multiplier** for that builder only (saved on the vendor; used for retail)

The system will **standardize** rows (long-form: SKU × wood/option × finish) and
**replace that builder’s catalog** so you never get duplicate builders.
            """
        )

    uploads = st.file_uploader(
        "Drop Excel or PDF price lists here",
        type=["xlsx", "xls", "xlsm", "pdf"],
        accept_multiple_files=True,
        key="drop_files",
        help="You can select multiple files at once.",
    )

    commit_mode = "replace_vendor"
    if SHOW_SIMPLE_UI:
        prefer_wb_markup = False
    else:
        prefer_wb_markup = st.checkbox(
            "Prefer workbook Markup sheet when mult not set manually",
            value=False,
            key="drop_use_wb_markup",
            help="If unchecked, uses each builder’s saved mult, else 2.7.",
        )

    def _clear_drop_widget_state() -> None:
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and (
                k.startswith("drop_vend_")
                or k.startswith("drop_mult_")
                or k.startswith("drop_wb_")
                or k.startswith("m27_")
                or k.startswith("m17_")
            ):
                del st.session_state[k]

    def _apply_vendor_mult(rows: list, vendor: str, mult: float, source: str) -> list:
        """Return deep-copied rows with vendor/mult/retail applied (never mutate cache)."""
        out = []
        for src in rows:
            r = dict(src)
            r["vendor"] = vendor
            r["source_file"] = source
            r["multiplier"] = mult
            bp = r.get("base_price")
            if bp is not None:
                try:
                    from backend.pricing import retail_from_wholesale

                    r["adjusted_price"] = retail_from_wholesale(bp, mult)
                except (TypeError, ValueError):
                    pass
            out.append(r)
        return out

    # Flash message after load (survives rerun so sidebar stats refresh)
    if st.session_state.get("drop_load_msg"):
        st.success(st.session_state.pop("drop_load_msg"))
        log = st.session_state.pop("drop_load_log", None)
        if log:
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)

    if not uploads:
        st.info("Drop one or more builder price files above to begin.")
    else:
        # Signature: names + sizes + markup preference. Index keys stay stable while
        # this set is unchanged. Do not use filename as widget key (special chars).
        upload_sig = (
            tuple((f.name, int(getattr(f, "size", 0) or 0)) for f in uploads),
            bool(prefer_wb_markup),
        )
        cache_key = "drop_parse_cache"

        if st.session_state.get("drop_file_keys") != upload_sig:
            _clear_drop_widget_state()
            parsed: list[dict] = []
            progress = st.progress(0.0, text="Reading files…")
            n_up = max(len(uploads), 1)
            for i, up in enumerate(uploads):
                progress.progress(i / n_up, text=f"Parsing {up.name}…")
                try:
                    data = _bytes(up)
                    prepared = svc.prepare_drop_file(
                        data,
                        filename=up.name,
                        vendor="",
                        multiplier=None,
                        use_workbook_markup=prefer_wb_markup,
                    )
                except Exception as exc:
                    prepared = {
                        "filename": up.name,
                        "vendor": Path(up.name).stem,
                        "multiplier": float(DEFAULT_MULTIPLIER),
                        "detected_markup": None,
                        "rows": [],
                        "notes": "",
                        "error": f"Parse failed: {exc}"[:400],
                        "row_count": 0,
                        "kind": "pdf"
                        if up.name.lower().endswith(".pdf")
                        else "excel",
                    }
                # Keep only what we need; never store raw bytes in session
                parsed.append(
                    {
                        "filename": up.name,
                        "vendor": prepared.get("vendor") or Path(up.name).stem,
                        "multiplier": float(
                            prepared.get("multiplier") or DEFAULT_MULTIPLIER
                        ),
                        "detected_markup": prepared.get("detected_markup"),
                        "rows": list(prepared.get("rows") or []),
                        "notes": prepared.get("notes") or "",
                        "error": prepared.get("error") or "",
                        "row_count": int(prepared.get("row_count") or 0),
                        "kind": prepared.get("kind") or "excel",
                    }
                )
            progress.progress(1.0, text="Done parsing")
            st.session_state[cache_key] = parsed
            st.session_state["drop_file_keys"] = upload_sig

        parsed_list: list = st.session_state.get(cache_key) or []
        # Align list length with current uploads if cache is stale/partial
        if len(parsed_list) != len(uploads):
            st.session_state.pop(cache_key, None)
            st.session_state.pop("drop_file_keys", None)
            st.warning("Parse cache out of sync — re-reading files…")
            st.rerun()

        st.markdown("### Per-file builder & multiplier")
        st.caption(
            "Set the retail multiplier **per builder**. "
            "Example: Genuine Oak **1.7**, most others **2.7**."
        )

        ready_payloads = []

        for i, up in enumerate(uploads):
            prep = parsed_list[i] if i < len(parsed_list) else {}
            name = up.name
            default_vend = (prep.get("vendor") or Path(name).stem).strip()
            saved = svc.get_vendor_multiplier(
                default_vend, default=float(DEFAULT_MULTIPLIER)
            )
            default_mult = float(
                prep.get("multiplier") or saved or DEFAULT_MULTIPLIER
            )

            vend_key = f"drop_vend_{i}"
            mult_key = f"drop_mult_{i}"
            # Init session defaults once — never pass value= with an existing key
            if vend_key not in st.session_state:
                st.session_state[vend_key] = default_vend
            if mult_key not in st.session_state:
                st.session_state[mult_key] = float(default_mult)

            with st.container(border=True):
                h1, h2 = st.columns([2, 1])
                with h1:
                    st.markdown(f"**{name}**")
                    if prep.get("error") and not prep.get("row_count"):
                        st.error(str(prep["error"]))
                    elif prep.get("notes"):
                        st.caption(str(prep.get("notes", ""))[:200])
                with h2:
                    kind = (prep.get("kind") or "excel").upper()
                    st.metric(
                        "Parsed rows", f"{int(prep.get('row_count') or 0):,}"
                    )
                    st.caption(kind)

                c1, c2, c3 = st.columns([1.6, 1.0, 1.0])
                with c1:
                    vend_edit = st.text_input(
                        "Builder name",
                        key=vend_key,
                        help="One catalog per builder name",
                    )
                with c2:
                    mult_edit = st.number_input(
                        "Multiplier for this builder",
                        min_value=0.1,
                        max_value=20.0,
                        step=0.1,
                        key=mult_key,
                        help="Retail = wholesale × this number",
                    )
                with c3:
                    detected = prep.get("detected_markup")
                    if detected is not None:
                        try:
                            det_f = float(detected)
                        except (TypeError, ValueError):
                            det_f = None
                    else:
                        det_f = None
                    if det_f is not None:
                        st.caption(f"Workbook markup sheet: **{det_f:g}**")
                        if st.button(
                            f"Use workbook {det_f:g}",
                            key=f"drop_wb_{i}",
                        ):
                            st.session_state[mult_key] = float(det_f)
                            st.rerun()
                    else:
                        st.caption("No markup sheet found")
                    if SHOW_SIMPLE_UI:
                        if st.button("Use 2.7", key=f"m27_{i}"):
                            st.session_state[mult_key] = 2.7
                            st.rerun()
                    else:
                        b_a, b_b = st.columns(2)
                        with b_a:
                            if st.button("2.7", key=f"m27_{i}"):
                                st.session_state[mult_key] = 2.7
                                st.rerun()
                        with b_b:
                            if st.button("1.7", key=f"m17_{i}"):
                                st.session_state[mult_key] = 1.7
                                st.rerun()

                vend_final = (vend_edit or default_vend).strip()
                mult_final = float(mult_edit)
                cached_rows = list(prep.get("rows") or [])
                rows = _apply_vendor_mult(
                    cached_rows, vend_final, mult_final, name
                )

                if rows:
                    sample = pd.DataFrame(rows[:6])
                    show = [
                        c
                        for c in [
                            "vendor",
                            "part_number",
                            "description",
                            "species",
                            "finish_state",
                            "base_price",
                            "multiplier",
                            "adjusted_price",
                        ]
                        if c in sample.columns
                    ]
                    st.dataframe(
                        sample[show].rename(
                            columns={
                                "base_price": "Wholesale",
                                "adjusted_price": "RETAIL",
                                "multiplier": "Mult",
                                "part_number": "Part #",
                                "species": "Wood / option",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Wholesale": st.column_config.NumberColumn(
                                format="$%.2f"
                            ),
                            "RETAIL": st.column_config.NumberColumn(
                                format="$%.0f",
                                help="Rolled up to next even dollar",
                            ),
                            "Mult": st.column_config.NumberColumn(format="%.2f"),
                        },
                    )
                    try:
                        rets = [
                            float(r["adjusted_price"])
                            for r in rows
                            if r.get("adjusted_price") is not None
                        ]
                        if rets:
                            st.caption(
                                f"Retail range after x{mult_final:g} (even $): "
                                f"**${min(rets):,.0f}** – **${max(rets):,.0f}** · "
                                f"{len(rows):,} sellable rows"
                            )
                    except Exception:
                        pass

                    ready_payloads.append(
                        {
                            "filename": name,
                            "vendor": vend_final,
                            "multiplier": mult_final,
                            "rows": rows,
                        }
                    )
                elif prep.get("error"):
                    st.warning(
                        "This file will be skipped until it parses cleanly."
                    )

        st.divider()
        st.markdown("### Load into master price book")
        if not ready_payloads:
            st.warning("No files with parsed rows yet.")
        else:
            by_vendor: dict = {}
            for p in ready_payloads:
                by_vendor[p["vendor"]] = p
            if len(by_vendor) < len(ready_payloads):
                st.warning(
                    "Two or more files map to the **same builder name**. "
                    "Only the last file for each builder will be kept "
                    "(one catalog per builder)."
                )

            summary_rows = [
                {
                    "Builder": p["vendor"],
                    "File": p["filename"],
                    "Rows": len(p["rows"]),
                    "Multiplier": p["multiplier"],
                }
                for p in by_vendor.values()
            ]
            st.caption(
                "Loading **replaces each builder’s whole catalog** "
                "(one builder = one book)."
            )
            st.dataframe(
                pd.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Multiplier": st.column_config.NumberColumn(format="%.2f"),
                    "Rows": st.column_config.NumberColumn(format="%d"),
                },
            )

            if st.button(
                f"Standardize & load {len(by_vendor)} builder(s) into master",
                type="primary",
                use_container_width=True,
                key="drop_load_master",
            ):
                results_log = []
                bar = st.progress(0.0, text="Loading…")
                items = list(by_vendor.values())
                for i, p in enumerate(items):
                    bar.progress(
                        i / max(len(items), 1),
                        text=f"Loading {p['vendor']}…",
                    )
                    try:
                        result = svc.add_rows(p["rows"], mode=commit_mode)
                        svc.set_vendor_multiplier(
                            p["vendor"],
                            float(p["multiplier"]),
                            notes=f"Set from drop import of {p['filename']}",
                        )
                        svc.reapply_multiplier(
                            float(p["multiplier"]), vendor=p["vendor"]
                        )
                        results_log.append(
                            {
                                "Builder": p["vendor"],
                                "File": p["filename"],
                                "Mult": p["multiplier"],
                                "Inserted": result.get("inserted", 0),
                                "Updated": result.get("updated", 0),
                                "Removed old": result.get("deleted", 0),
                                "Total": result.get("total", 0),
                                "Status": "ok",
                            }
                        )
                    except Exception as exc:
                        results_log.append(
                            {
                                "Builder": p["vendor"],
                                "File": p["filename"],
                                "Mult": p["multiplier"],
                                "Inserted": 0,
                                "Updated": 0,
                                "Removed old": 0,
                                "Total": 0,
                                "Status": f"error: {exc}"[:120],
                            }
                        )
                bar.progress(1.0, text="Done")
                ok_n = sum(1 for r in results_log if r.get("Status") == "ok")
                st.session_state.pop(cache_key, None)
                st.session_state.pop("drop_file_keys", None)
                _clear_drop_widget_state()
                st.session_state["drop_load_msg"] = (
                    f"Loaded **{ok_n}** of **{len(items)}** builder(s). "
                    f"Master now has **{svc.row_count():,}** rows."
                )
                st.session_state["drop_load_log"] = results_log
                # Rerun so sidebar metrics reflect the new master row count
                st.rerun()

# ---------------------------------------------------------------------------
# VENDORS — edit multipliers
# ---------------------------------------------------------------------------
with tab_vendors:
    st.subheader("Modify builder multipliers")

    summary = svc.vendor_summary()
    if summary.empty:
        st.info("No builders in master yet — import files under **Drop files** first.")
    else:
        edit_df = summary[
            [
                c
                for c in [
                    "vendor",
                    "phone",
                    "rows",
                    "collections",
                    "saved_mult",
                    "avg_mult",
                ]
                if c in summary.columns
            ]
        ].copy()
        if "phone" not in edit_df.columns:
            edit_df["phone"] = ""
        edit_df["phone"] = (
            edit_df["phone"].fillna("").astype(str).replace({"nan": "", "None": ""})
        )
        # Prefer saved_mult; fall back to avg_mult
        edit_df["Multiplier"] = edit_df.apply(
            lambda r: float(
                r["saved_mult"]
                if pd.notna(r.get("saved_mult"))
                else (r.get("avg_mult") or DEFAULT_MULTIPLIER)
            ),
            axis=1,
        )
        edit_df = edit_df.rename(
            columns={
                "vendor": "Builder",
                "phone": "Phone",
                "rows": "Items",
                "collections": "Collections",
            }
        )
        show_cols = [
            c
            for c in [
                "Builder",
                "Phone",
                "Items",
                "Collections",
                "Multiplier",
            ]
            if c in edit_df.columns
        ]
        edited = st.data_editor(
            edit_df[show_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            # Lock stats columns; Phone + Multiplier are editable
            disabled=["Builder", "Items", "Collections"],
            column_config={
                "Builder": st.column_config.TextColumn(disabled=True),
                "Phone": st.column_config.TextColumn(
                    "Phone",
                    help="Builder main phone — edit then Save",
                    width="medium",
                    max_chars=40,
                ),
                "Items": st.column_config.NumberColumn(format="%d", disabled=True),
                "Collections": st.column_config.NumberColumn(
                    format="%d", disabled=True
                ),
                "Multiplier": st.column_config.NumberColumn(
                    "Multiplier",
                    min_value=0.1,
                    max_value=20.0,
                    step=0.1,
                    format="%.2f",
                    help="Edit this — then click Save below",
                    disabled=False,
                ),
            },
            key="vendor_mult_editor",
        )

        if not SHOW_SIMPLE_UI:
            st.caption(
                "Quick tips: set **2.7** for most Amish builders · **1.7** for Genuine Oak. "
                "**Phone** is next to each builder for the floor."
            )

        if st.button(
            "Save phone & multipliers · update retail",
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
                    builder,
                    mult,
                    notes="Updated from Vendors tab",
                )
                n = svc.reapply_multiplier(mult, vendor=builder)
                updated_builders += 1
                updated_rows += int(n or 0)
            st.success(
                f"Saved phone + mult for **{updated_builders}** builders · "
                f"recomputed **{updated_rows:,}** retail prices"
            )
            st.rerun()

        if not SHOW_SIMPLE_UI:
            if st.button("Set all to 2.7", use_container_width=True):
                for v in svc.list_vendors():
                    svc.set_vendor_multiplier(v, 2.7, notes="Bulk set 2.7")
                    svc.reapply_multiplier(2.7, vendor=v)
                st.success("All builders set to 2.7")
                st.rerun()

            st.markdown("##### Check a price after mult change")
            vlist = svc.list_vendors()
            cv1, cv2 = st.columns([1.2, 2])
            with cv1:
                check_v = st.selectbox("Builder", vlist, key="vcheck")
            with cv2:
                sample = svc.search("", vendor=check_v, finish_state="finished", limit=5)
                if sample.empty:
                    sample = svc.search("", vendor=check_v, limit=5)
                if not sample.empty:
                    s = sample.iloc[0]
                    st.write(
                        f"**{s.get('part_number')}** · {s.get('description') or ''} · "
                        f"{s.get('species') or ''}  \n"
                        f"Wholesale **${float(s.get('base_price') or 0):,.2f}** × "
                        f"**{float(s.get('multiplier') or 0):.2f}** = "
                        f"Retail **${float(s.get('adjusted_price') or 0):,.2f}**"
                    )

        vlist = svc.list_vendors()
        if vlist:
            with st.expander("Remove a builder from the book", expanded=False):
                vv = st.selectbox("Builder to remove", vlist, key="vv_del")
                if st.button("Remove builder from book", type="secondary"):
                    n = svc.delete_by_vendor(vv)
                    st.warning(f"Deleted {n:,} rows for {vv}")
                    st.rerun()

# ---------------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------------
with tab_admin:
    st.subheader("Admin / data quality")
    s1, s2 = st.columns(2)
    s1.metric("Rows", f"{stats['rows']:,}")
    s2.metric("Builders", stats["vendors"])
    st.caption(f"Database: `{svc.path}`")
    st.caption(f"Last backup: {_last_backup_hint()}")
    st.caption(f"Viztech sync: {_viztech_sync_hint()}")

    # TRACE: Admin OrderTrac block — set SHOW_ORDERTRAC_ADMIN = True to restore
    # (connection, sync users, FAF users, create/reset user, push FAF→OrderTrac)
    if SHOW_ORDERTRAC_ADMIN:
        # ----- OrderTrac connection + user sync (admins) -----
        st.divider()
        st.markdown("### OrderTrac connection")
        st.caption(
            "Link the company OrderTrac account so FAF can create staff logins from "
            "OrderTrac sales users and push quotes. Credentials live in "
            "`.streamlit/secrets.toml` → `[ordertrac]` (never in git)."
        )
        _is_admin = (st.session_state.get("auth_role") or "") == "admin"
        if not _is_admin:
            st.info("Only **admin** users can manage OrderTrac connection and FAF accounts.")
        else:
            # Always use live service (clears stale cache if methods missing)
            _ot_svc = _svc()
            ot = _ot_svc.ordertrac_connection_status()
            oc1, oc2, oc3 = st.columns(3)
            oc1.metric("Secrets configured", "Yes" if ot.get("configured") else "No")
            oc2.metric("Session file", "Yes" if ot.get("session_exists") else "No")
            oc3.metric("FAF users", ot.get("faf_user_count") or 0)
            st.caption(
                f"OrderTrac user: `{ot.get('username') or '—'}` · "
                f"{ot.get('base_url')} · session `{ot.get('session_file')}`"
            )
            integ = ot.get("integration") or {}
            if integ.get("status"):
                st.caption(
                    f"Last integration status: **{integ.get('status')}** · "
                    f"ok at {integ.get('last_ok_at') or '—'} · "
                    f"{integ.get('last_error') or ''}"
                )

            otb1, otb2, otb3 = st.columns(3)
            with otb1:
                if st.button("Check OrderTrac session", use_container_width=True):
                    with st.spinner("Checking OrderTrac…"):
                        chk = _ot_svc.ordertrac_check_session()
                    if chk.get("ok"):
                        st.success("OrderTrac session is alive.")
                    else:
                        st.error(chk.get("error") or "Session dead")
                        st.info("Re-login: `python scripts/ordertrac_login.py`")
            with otb2:
                if st.button(
                    "Sync users from OrderTrac",
                    type="primary",
                    use_container_width=True,
                    help="Creates FAF logins for each OrderTrac sales user (UserGUID list)",
                ):
                    with st.spinner("Fetching OrderTrac users and creating FAF accounts…"):
                        sync_result = _ot_svc.sync_users_from_ordertrac(default_role="sales")
                    if sync_result.get("ok"):
                        st.success(
                            f"Synced · OT users: {sync_result.get('ot_count')} · "
                            f"created: {len(sync_result.get('created') or [])} · "
                            f"updated: {len(sync_result.get('updated') or [])}"
                        )
                        if sync_result.get("created"):
                            st.warning(
                                "New accounts — share temp passwords once, then users change them:"
                            )
                            for c in sync_result["created"]:
                                st.code(
                                    f"{c['username']}  /  {c.get('temp_password', '')}",
                                    language=None,
                                )
                        if sync_result.get("skipped"):
                            st.caption(
                                "Skipped: " + ", ".join(sync_result["skipped"][:12])
                            )
                    else:
                        st.error(sync_result.get("error") or "Sync failed")
                        st.info("Need live session: `python scripts/ordertrac_login.py`")
            with otb3:
                st.caption(
                    "CLI: `python scripts/ordertrac_sync_users.py` · "
                    "`python scripts/ordertrac_sync_users.py --check`"
                )

            st.markdown("##### FAF users")
            try:
                users_df = _ot_svc.list_app_users()
            except Exception as e:
                users_df = pd.DataFrame()
                st.error(f"Could not load users: {e}")
            if users_df is not None and not users_df.empty:
                show_cols = [
                    c
                    for c in (
                        "username",
                        "display_name",
                        "role",
                        "active",
                        "source",
                        "ordertrac_display_name",
                        "must_change_password",
                        "last_login_at",
                    )
                    if c in users_df.columns
                ]
                st.dataframe(
                    users_df[show_cols], use_container_width=True, hide_index=True
                )
            else:
                st.info(
                    "No users yet — seed admin is created on first login, or run OrderTrac sync."
                )

            with st.expander("Create / reset a user"):
                cu1, cu2 = st.columns(2)
                with cu1:
                    nu = st.text_input("Username", key="new_user_name")
                    nd = st.text_input("Display name", key="new_user_disp")
                    nr = st.selectbox(
                        "Role", ["sales", "floor", "admin"], key="new_user_role"
                    )
                with cu2:
                    npw = st.text_input("Password", type="password", key="new_user_pw")
                    if st.button("Create user", key="btn_create_user"):
                        if not nu or not npw:
                            st.error("Username and password required.")
                        else:
                            try:
                                uid = _ot_svc.create_app_user(
                                    username=nu.strip(),
                                    password=npw,
                                    display_name=nd.strip() or nu.strip(),
                                    role=nr,
                                    source="local",
                                    must_change_password=False,
                                )
                                st.success(f"Created user id={uid} ({nu})")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                st.markdown("**Reset password**")
                if users_df is not None and not users_df.empty:
                    unames = users_df["username"].tolist()
                    ru = st.selectbox("User", unames, key="reset_user_sel")
                    rpw = st.text_input(
                        "New password", type="password", key="reset_user_pw"
                    )
                    if st.button("Reset password", key="btn_reset_pw"):
                        row = users_df[users_df["username"] == ru].iloc[0]
                        _ot_svc.set_app_user_password(
                            int(row["id"]), rpw, must_change=True
                        )
                        st.success(
                            f"Password reset for {ru} (must change on next login)."
                        )

            st.markdown("##### Push FAF lines → OrderTrac QUOTE")
            st.caption(
                "Creates a new **Quote** in OrderTrac (not a sale) with custom lines "
                "from FAF pricebook IDs. Vendor map: `config/ordertrac_vendor_map.json`."
            )
            push_ids = st.text_input(
                "FAF pricebook IDs (comma-separated)",
                value="479060,479078,482875,482881",
                key="ot_push_ids",
                help="Example Barkman dining set IDs from FAF master",
            )
            pq1, pq2, pq3 = st.columns(3)
            with pq1:
                push_qtys = st.text_input("Qtys (optional)", value="1,2,4,2", key="ot_push_qtys")
            with pq2:
                push_wood = st.text_input("Wood", value="Red Oak", key="ot_push_wood")
            with pq3:
                push_stain = st.text_input(
                    "Stain", value="Michael's Cherry (OCS-113)", key="ot_push_stain"
                )
            ot_user_opts = []
            try:
                udf = _ot_svc.list_app_users(active_only=True)
                if not udf.empty and "ordertrac_display_name" in udf.columns:
                    ot_user_opts = [
                        x
                        for x in udf["ordertrac_display_name"].dropna().tolist()
                        if str(x).strip()
                    ]
            except Exception:
                pass
            if not ot_user_opts:
                ot_user_opts = ["Miller, Judson"]
            push_user = st.selectbox(
                "OrderTrac sales user",
                options=ot_user_opts,
                index=0,
                key="ot_push_user",
            )
            if st.button("Push to OrderTrac as QUOTE", type="primary", key="btn_ot_push"):
                try:
                    ids = [int(x.strip()) for x in push_ids.split(",") if x.strip()]
                    qtys = (
                        [float(x.strip()) for x in push_qtys.split(",") if x.strip()]
                        if push_qtys.strip()
                        else None
                    )
                    rows = []
                    for i in ids:
                        r = _ot_svc.get_row(i)
                        if not r:
                            st.error(f"Missing FAF id {i}")
                            rows = []
                            break
                        rows.append(r)
                    if rows:
                        with st.spinner("Pushing quote to OrderTrac (browser automation)…"):
                            result = _ot_svc.push_rows_to_ordertrac(
                                rows,
                                qtys=qtys,
                                wood=push_wood.strip(),
                                stain=push_stain.strip(),
                                ot_user_display=push_user,
                                location="Landrum",
                                project=f"FAF push {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                                customer_name="FAF Floor Quote",
                            )
                        if result.get("ok"):
                            st.success(
                                f"OrderTrac QUOTE {result.get('sales_order_id')} created."
                            )
                            if result.get("url"):
                                st.markdown(f"[Open in OrderTrac]({result['url']})")
                        else:
                            st.error(result.get("error") or "Push incomplete")
                            st.json(result)
                except Exception as e:
                    st.error(str(e))

            handoff = Path.home() / "Documents" / "ordertrac-session" / "faf-login-handoff.txt"
            if handoff.is_file():
                st.caption(f"Staff login handoff file: `{handoff}`")


    st.markdown("##### Viztech monthly update")
    st.caption(
        "Every **~30 days** this Mac downloads builder pricelists from "
        "**viztechfurniture.com** and updates the book "
        "(keeps builders Viztech doesn’t have · FN Chair = Level One only)."
    )
    st.info(_viztech_sync_hint())
    vz1, vz2, vz3 = st.columns(3)
    with vz1:
        if st.button("Check Viztech login", use_container_width=True):
            import subprocess

            py = APP_DIR / ".venv" / "bin" / "python"
            script = APP_DIR / "scripts" / "viztech_sync.py"
            with st.spinner("Logging into Viztech…"):
                proc = subprocess.run(
                    [str(py), str(script), "--dry-run"],
                    cwd=str(APP_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            if proc.returncode == 0:
                st.success("Viztech login OK — builders listed.")
                get_service.clear()
            else:
                st.error("Check failed — see logs below.")
            if proc.stdout:
                st.code(proc.stdout[-2500:])
            if proc.stderr:
                st.code(proc.stderr[-1500:])
    with vz2:
        if st.button(
            "Run full Viztech sync now",
            type="primary",
            use_container_width=True,
            help="Downloads all pricelists and re-imports (can take 10–30+ minutes)",
        ):
            import subprocess

            py = APP_DIR / ".venv" / "bin" / "python"
            script = APP_DIR / "scripts" / "viztech_sync.py"
            with st.spinner(
                "Syncing Viztech → FAF (download + import). Leave this tab open…"
            ):
                proc = subprocess.run(
                    [str(py), str(script)],
                    cwd=str(APP_DIR),
                    capture_output=True,
                    text=True,
                    timeout=14400,
                )
            if proc.returncode == 0:
                get_service.clear()
                st.success("Viztech sync finished. Reloading stats…")
                st.rerun()
            else:
                st.error("Sync failed — check output / viztech-sync.err")
            if proc.stdout:
                st.code(proc.stdout[-4000:])
            if proc.stderr:
                st.code(proc.stderr[-2000:])
    with vz3:
        if st.button("Install 30-day schedule", use_container_width=True):
            import subprocess

            install = (
                Path(__file__).resolve().parent
                / "scripts"
                / "install_viztech_monthly_sync.sh"
            )
            rc = subprocess.call(["/bin/zsh", str(install)])
            if rc == 0:
                st.success("LaunchAgent installed — runs every ~30 days.")
            else:
                st.error(
                    "Install failed — run scripts/install_viztech_monthly_sync.sh in Terminal."
                )

    st.markdown("##### Backup DB")
    st.caption(
        "Saves a snapshot under **Documents/FAF-pricebook-backups**. "
        "Weekly auto-backup: run `scripts/install_weekly_backup.sh` once on this Mac."
    )
    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("Backup DB now", type="primary", use_container_width=True):
            try:
                from scripts.backup_db import backup_now

                dest = backup_now()
                st.success(f"Saved `{dest.name}`")
            except Exception as exc:
                st.error(f"Backup failed: {exc}")
    with b2:
        if st.button("Install weekly backup (Sunday 6 AM)", use_container_width=True):
            import subprocess
            import sys

            install = Path(__file__).resolve().parent / "scripts" / "install_weekly_backup.sh"
            rc = subprocess.call(["/bin/zsh", str(install)])
            if rc == 0:
                st.success("Weekly LaunchAgent installed (Sunday 6:00 AM).")
            else:
                st.error("Install failed — run scripts/install_weekly_backup.sh in Terminal.")
    try:
        from scripts.backup_db import list_backups, restore_from

        backups = list_backups(30)
    except Exception:
        backups = []

    if backups:
        st.markdown("##### Restore from backup")
        labels = [
            f"{p.name}  ·  {datetime.fromtimestamp(p.stat().st_mtime).strftime('%b %d %I:%M %p')}"
            for p in backups
        ]
        pick = st.selectbox("Backup file", labels, key="restore_pick")
        confirm = st.checkbox(
            "I understand restore replaces the live price book",
            key="restore_confirm",
        )
        if st.button("Restore selected backup", type="secondary"):
            if not confirm:
                st.warning("Check the confirmation box first.")
            else:
                idx = labels.index(pick)
                try:
                    live = restore_from(backups[idx], also_backup_current=True)
                    # Clear cached service so next load reopens DB connection state
                    get_service.clear()
                    st.success(
                        f"Restored `{backups[idx].name}` → `{live.name}`. "
                        "Reloading…"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Restore failed: {exc}")
    else:
        st.caption("No backups yet — click **Backup DB now**.")

    st.markdown("##### Maintenance")
    m1, m2, m3 = st.columns(3)
    with m1:
        if st.button("Re-standardize master"):
            report = svc.standardize_master()
            st.write(report)
            st.success("Standardize complete")
    with m2:
        if st.button("Scan duplicates"):
            dups = svc.find_duplicates(50)
            if dups.empty:
                st.success("No duplicate identity groups.")
            else:
                st.dataframe(dups, use_container_width=True)
    with m3:
        if st.button("Dry-run cleanup"):
            report = svc.cleanup_duplicates(dry_run=True)
            st.write(report)

    if st.button("Execute cleanup (keep newest)", type="primary"):
        report = svc.cleanup_duplicates(dry_run=False)
        st.success(report)
        st.rerun()

    st.markdown("##### Source files in master")
    sources = svc.list_source_files()
    if sources:
        src = st.selectbox("Source file", sources)
        if st.button("Delete all rows from this source"):
            n = svc.delete_by_source(src)
            st.warning(f"Removed {n:,} rows")

    st.markdown("##### Deploy")
    st.caption(
        "Permanent hosting: Streamlit Community Cloud from GitHub "
        "`Koffeekinggamer/pricebook-system` · main file `pricebook_app.py`. "
        "See **DEPLOY.md**. Public tunnel (this Mac on): `scripts/public_tunnel.sh`."
    )

    st.markdown("##### CLI")
    st.code(
        """
source ~/FAF-pricebook/.venv/bin/activate
python -m backend.cli stats
python -m backend.cli search "oak nightstand"
python scripts/backup_db.py backup
python scripts/backup_db.py list
python scripts/backup_db.py restore --file master_pricebook-YYYYMMDD-HHMMSS.db
python scripts/viztech_sync.py --dry-run
python scripts/viztech_sync.py
        """.strip()
    )

st.caption(
    "FAF Price Book · Search · Drop files · Vendors · Admin · "
    "one builder = one catalog · Viztech sync every ~30 days"
)
