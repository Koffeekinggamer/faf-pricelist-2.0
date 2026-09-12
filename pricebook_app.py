"""
FAF Price Book — Streamlit UI (content-accuracy phase)

Tabs: Search · Drop files · Vendors · Admin
Verify retail prices and builder catalogs. OrderTrac UI is hidden.

OrderTrac modules remain in backend/ for later restore (flags below).

Run:  streamlit run pricebook_app.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend import PriceBookService
from backend.auth import login_user
from backend.builder_profiles import (
    exclusive_option_conflicts,
    load_builder_profile,
    profile_writes_allowed,
)
from backend.config import (
    APP_DIR,
    DATA_DIR,
    DEFAULT_MULTIPLIER,
    DEFAULT_SEARCH_LIMIT,
    THIN_CATALOG_MAX_ROWS,
)
from backend.county_sales_tax import CountyTaxRate, county_tax_options
from backend.drop_parse_session import (
    DropLoadBinding,
    DropSessionGone,
    DropUpload,
    drop_upload_from_path,
)
from backend.dropzone_widget import render_dropzone
from backend.login_session import (
    COOKIE_NAME,
    TTL_SECONDS,
    clear_persisted_token,
    issue_login_token,
    load_persisted_token,
    login_secret,
    persist_token,
    restore_login_session,
)
from backend.option_labels import option_widget_key
from backend.product_descriptions import floor_part_number
from backend.standardize import mixed_wood_label

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_FAVICON = APP_DIR / "assets" / "favicon.png"
_LOGO = APP_DIR / "assets" / "logo.png"

# Feature flags — content-accuracy phase (set True to restore later)
SHOW_ORDERTRAC_QUOTE = False  # quote tab + search cart + sidebar badge
SHOW_ORDERTRAC_ADMIN = False  # Admin: OrderTrac connection, user sync, push tools
SHOW_SIMPLE_UI = True  # lean Search/Drop/Vendors; hide pins & bulk tools
SHOW_ADMIN_ADVANCED = True  # cleanup tools under Admin
SHOW_VIZTECH = False  # hide Viztech sync UI — manual Drop only while verifying data
# TRACE restore quoting: SHOW_ORDERTRAC_* = True
# TRACE Viztech: SHOW_VIZTECH = True
# TRACE full UI: SHOW_SIMPLE_UI = False; SHOW_ADMIN_ADVANCED = True

st.set_page_config(
    page_title="FAF Price Book",
    page_icon=str(_FAVICON) if _FAVICON.is_file() else "🪵",
    layout="wide",
    initial_sidebar_state="expanded",  # persistent Quote Cart; Streamlit stacks on narrow screens
)

# Brand mark in the sidebar (horse & buggy wordmark)
if _LOGO.is_file():
    st.logo(str(_LOGO), size="large")

# iPad / phone-friendly density
st.markdown(
    """
    <style>
      /* White app surface with dark, high-contrast text. */
      .stApp {
        background: #ffffff;
        color: #1f2937;
      }
      [data-testid="stHeader"] { background: rgba(255, 255, 255, 0.96); }
      [data-testid="stSidebar"] { background: #f3f4f6; color: #1f2937; }
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] span,
      [data-testid="stSidebar"] li { color: #1f2937; }
      .stApp a { color: #244a2e; }
      .stApp a:hover { color: #17351f; }
      .stApp [data-testid="stCaptionContainer"],
      .stApp [data-testid="stMarkdownContainer"] p {
        color: #374151;
      }
      /* Button labels are markdown <p>s — do not paint them body-gray. */
      .stApp [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
      .stApp [data-testid="stFormSubmitButton"] [data-testid="stMarkdownContainer"] p,
      .stApp [data-testid="stDownloadButton"] [data-testid="stMarkdownContainer"] p,
      .stApp [data-testid="stLinkButton"] [data-testid="stMarkdownContainer"] p,
      [data-testid="stSidebar"] [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
      [data-testid="stSidebar"] [data-testid="stButton"] span {
        color: inherit !important;
      }
      .stApp div[data-baseweb="input"] > div,
      .stApp div[data-baseweb="select"] > div,
      .stApp textarea {
        background: #ffffff;
        color: #17233a;
      }
      .stApp input,
      .stApp textarea {
        color: #17233a !important;
        caret-color: #17233a;
      }
      .stApp input::placeholder,
      .stApp textarea::placeholder {
        color: #667085 !important;
        opacity: 1;
      }
      .stApp [data-baseweb="select"] span {
        color: #17233a;
      }
      /* Primary = white on forest green. kind= is not always on the DOM. */
      .stApp button[data-testid^="stBaseButton-primary"],
      .stApp button[data-testid^="stBaseButton-primary"] *,
      .stApp button[data-testid^="stBaseButton-primary"] [data-testid="stMarkdownContainer"] p {
        color: #ffffff !important;
      }
      .stApp [data-testid="stDataFrame"] {
        background: #ffffff;
        border-radius: 0.45rem;
      }
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
      /* Option checkbox panel */
      .faf-option-panel-title {
        font-weight: 600;
        color: #244a2e;
        font-size: 0.95rem;
        margin-bottom: 0.15rem;
      }
      .faf-option-selected {
        margin-top: 0.35rem;
        padding: 0.35rem 0.55rem;
        background: #f3f4f6;
        border-left: 3px solid #2f5638;
        border-radius: 4px;
        font-size: 0.9rem;
        color: #1f2937;
      }
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
# Login gate — cookie + local token so a reload signs the user back in
# ---------------------------------------------------------------------------


def _apply_auth_session(session: dict) -> None:
    st.session_state["authenticated"] = True
    st.session_state["auth_user"] = session["username"]
    st.session_state["auth_display"] = session.get("display_name")
    st.session_state["auth_role"] = session.get("role") or "sales"
    st.session_state["auth_user_id"] = session.get("user_id")
    st.session_state["auth_session"] = session
    st.session_state.pop("auth_forget", None)


def _write_login_cookie(token: str) -> None:
    assignment = (
        f"{COOKIE_NAME}={token}; path=/; max-age={TTL_SECONDS}; SameSite=Lax"
        if token
        else f"{COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax"
    )
    html = f"""
    <script>
    (function () {{
      var c = {json.dumps(assignment)};
      try {{ document.cookie = c; }} catch (e) {{}}
      try {{ window.parent.document.cookie = c; }} catch (e) {{}}
    }})();
    </script>
    """
    st.components.v1.html(html, height=0, width=0)


def _browser_login_token() -> str:
    try:
        cookies = st.context.cookies
        if cookies is None:
            return ""
        return str(cookies.get(COOKIE_NAME) or "")
    except Exception:
        return ""


def _client_is_local_browser() -> bool:
    """True for localhost reloads. LAN iPads keep their own cookie."""
    try:
        ip = str(getattr(st.context, "ip_address", None) or "")
    except Exception:
        ip = ""
    if ip in {"127.0.0.1", "::1", "localhost"}:
        return True
    try:
        headers = st.context.headers
        host = str(headers.get("Host") or headers.get("host") or "")
    except Exception:
        host = ""
    return host.startswith("localhost") or host.startswith("127.0.0.1")


def _remember_login(session: dict) -> None:
    token = issue_login_token(session, secret=login_secret())
    st.session_state["_login_cookie_write"] = token
    if profile_writes_allowed() and _client_is_local_browser():
        try:
            persist_token(token)
        except OSError:
            pass


def _forget_login() -> None:
    st.session_state["_login_cookie_write"] = ""
    st.session_state["auth_forget"] = True
    if profile_writes_allowed() and _client_is_local_browser():
        clear_persisted_token()


_pending_login_cookie = st.session_state.pop("_login_cookie_write", None)
if _pending_login_cookie is not None:
    _write_login_cookie(_pending_login_cookie)


def _require_login() -> bool:
    """Show login form until authenticated. Returns True when logged in."""
    if st.session_state.get("authenticated"):
        return True

    if not st.session_state.get("auth_forget"):
        token = _browser_login_token()
        if not token and profile_writes_allowed() and _client_is_local_browser():
            token = load_persisted_token()
        if token:
            session = restore_login_session(token, secret=login_secret())
            if session:
                _apply_auth_session(session)
                return True

    st.markdown(
        """
        <div style="max-width:420px;margin:4rem auto 1rem auto;text-align:center;">
          <div style="font-size:2rem;font-weight:700;color:#244a2e;">FAF Price Book</div>
          <div style="color:#1f2937;margin-top:0.25rem;">Foothills Amish Furniture · sign in to continue</div>
          <div style="color:#4b5563;margin-top:0.5rem;font-size:0.9rem;">
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
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submitted:
                session = login_user(user, pw)
                if session:
                    _apply_auth_session(session)
                    _remember_login(session)
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
_SERVICE_CACHE_VERSION = 8


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
def _vendors_with_catalog_images() -> set[str]:
    try:
        return set(_svc().vendors_with_catalog_images() or set())
    except Exception:
        return set()


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


def _catalog_stamp() -> str:
    """Bust Option/Wood caches when the live catalog changes."""
    try:
        s = _svc().stats()
        return f"{s.get('rows', 0)}:{s.get('source_files', 0)}"
    except Exception:
        return "0"


@st.cache_data(ttl=60, show_spinner=False)
def _option_dropdown_options(vendor_key: str, catalog_stamp: str = "") -> list:
    """
    Live Options for the selected builder only — not a static list.

    Builder = All → empty (no cross-vendor option soup).
    Specific builder → whatever that builder's catalog currently has
    (addon charges + that builder's option_key / option-like species).
    ``catalog_stamp`` refreshes the list after Drop / re-import.
    """
    if not vendor_key or vendor_key == "All":
        return []
    svc = _svc()
    try:
        return list(svc.list_option_keys(vendor=vendor_key) or [])
    except Exception:
        return []


def _option_checkbox_key(vendor_key: str, option_label: str) -> str:
    """Stable Streamlit widget key for an Option checkbox (per builder)."""
    return option_widget_key(vendor_key, option_label)


def _option_qty_key(vendor_key: str, option_label: str) -> str:
    """Session key for Extra Drawers/Doors quantity."""
    return _option_checkbox_key(vendor_key, option_label) + "_qty"


def _enforce_single_select_options(
    vendor_key: str,
    option_label: str,
    opt_list: list[str],
) -> None:
    """Alternatives (FN Chair's Cat. 1/2/3) replace each other instead of stacking."""
    if not st.session_state.get(_option_checkbox_key(vendor_key, option_label)):
        return
    profile = load_builder_profile(vendor_key)
    for other in exclusive_option_conflicts(profile, option_label, list(opt_list)):
        st.session_state[_option_checkbox_key(vendor_key, other)] = False


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


def _python_executable() -> str:
    """Python for subprocess scripts — works on Mac (.venv) and Fly/Docker."""
    venv_py = APP_DIR / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _is_macos_host() -> bool:
    return sys.platform == "darwin"


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


@st.cache_data(ttl=3600, show_spinner=False, max_entries=512)
def _catalog_thumb_uri(rel_path: str, mtime: float) -> str | None:
    """Inline data URI for a catalog photo.

    ImageColumn only renders URLs or data URIs, so on-disk paths must be
    embedded. `mtime` busts the cache when a photo is re-extracted.
    """
    path = Path(rel_path)
    if not path.is_absolute():
        path = next(
            (candidate for candidate in (APP_DIR / path, DATA_DIR / path) if candidate.is_file()),
            APP_DIR / path,
        )
    if not path.is_file():
        return None
    try:
        from base64 import b64encode
        from io import BytesIO

        from PIL import Image

        with Image.open(path) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((160, 160))
            buf = BytesIO()
            thumb.save(buf, format="JPEG", quality=80, optimize=True)
        return "data:image/jpeg;base64," + b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _catalog_thumb(raw) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    rel = str(raw).strip()
    if not rel:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = next(
            (candidate for candidate in (APP_DIR / path, DATA_DIR / path) if candidate.is_file()),
            APP_DIR / path,
        )
    if not path.is_file():
        return None
    return _catalog_thumb_uri(str(path if path.is_absolute() else rel), path.stat().st_mtime)


def _dataframe_column_config(
    df: pd.DataFrame,
    *,
    money_cols: set[str] | None = None,
    number_formats: dict[str, str] | None = None,
    help_text: dict[str, str] | None = None,
    overrides: dict[str, int] | None = None,
    image_cols: set[str] | None = None,
) -> dict:
    """Build st.column_config with content-based widths so cells aren't clipped."""
    money_cols = money_cols or set()
    number_formats = number_formats or {}
    help_text = help_text or {}
    image_cols = image_cols or set()
    widths = _auto_col_widths(df, overrides=overrides)
    cfg: dict = {}
    for col, w in widths.items():
        if col in image_cols:
            cfg[col] = st.column_config.ImageColumn(
                col,
                width=w,
                help=help_text.get(col),
            )
        elif col in money_cols:
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
        st.sidebar.caption(f"**{q.get('quote_number') or qid}** · {t.get('line_count', 0)} lines")
        st.sidebar.metric("Quote total", f"${t.get('grand_total', 0):,.2f}")
        if q.get("ordertrac_so_id"):
            st.sidebar.caption(f"OrderTrac QUOTE **#{q.get('ordertrac_so_id')}**")
            if q.get("ordertrac_url"):
                st.sidebar.markdown(f"[Open in OrderTrac]({q['ordertrac_url']})")
    except Exception:
        pass


def _quote_option_summary(raw) -> str:
    try:
        options = json.loads(str(raw or "{}"))
    except (TypeError, ValueError):
        return ""
    if not isinstance(options, dict):
        return ""
    selected = options.get("selections", options)
    if not isinstance(selected, dict):
        selected = {}
    bits = [
        f"{name} ×{int(qty)}" if float(qty or 1) > 1 else str(name)
        for name, qty in selected.items()
        if name and name != "stain"
    ]
    stain = options.get("stain")
    if stain:
        bits.append(f"Stain: {stain}")
    return " · ".join(bits)


def _quote_county_widget_key(quote_id: int) -> str:
    """Stable-per-generation key so Clear can invalidate a stale selectbox."""
    from backend.quote_cart_widgets import quote_county_widget_key

    return quote_county_widget_key(quote_id, st.session_state)


def _bump_quote_county_widget(quote_id: int) -> str:
    """Rotate county selectbox identity; prevents Streamlit restoring old county."""
    from backend.quote_cart_widgets import bump_quote_county_widget

    return bump_quote_county_widget(quote_id, st.session_state)


def _reset_quote_sidebar_widget_state(quote_id: int) -> None:
    prefixes = (
        f"cart_name_{quote_id}",
        f"cart_client_{quote_id}",
        f"cart_county_{quote_id}",
        f"cart_exempt_{quote_id}",
        f"cart_qty_{quote_id}_",
        f"cart_notes_{quote_id}_",
    )
    # Rotate county widget first so a stale browser value cannot rehydrate.
    _bump_quote_county_widget(quote_id)
    for key in list(st.session_state):
        if key.startswith(prefixes):
            # Keep the nonce + the fresh (empty) county key slot unused.
            if key == f"cart_county_nonce_{quote_id}":
                continue
            st.session_state.pop(key, None)


def _render_quote_cart_sidebar() -> None:
    """Persistent Streamlit cart backed by the existing quote tables."""
    qid = _ensure_active_quote()
    _refresh = st.session_state.pop("_quote_cart_refresh", False)
    if _refresh:
        _reset_quote_sidebar_widget_state(qid)
    quote = svc.get_quote(qid) or {}
    lines = svc.quote_lines(qid)
    totals = svc.quote_totals(qid)

    with st.sidebar.expander("Quote Cart", expanded=True):
        name = st.text_input(
            "Quote name",
            value=quote.get("quote_name") or f"Quote {datetime.now():%Y-%m-%d}",
            key=f"cart_name_{qid}",
        )
        client = st.text_input(
            "Client name (optional)",
            value=quote.get("customer_name") or "",
            key=f"cart_client_{qid}",
        )
        if name != (quote.get("quote_name") or "") or client != (
            quote.get("customer_name") or ""
        ):
            svc.update_quote(
                qid,
                quote_name=name.strip() or f"Quote {datetime.now():%Y-%m-%d}",
                customer_name=client.strip(),
            )

        st.caption(
            f"**{totals.get('line_count', 0)}** lines · "
            f"**{totals.get('item_count', 0)}** items"
        )

        if lines is None or lines.empty:
            st.info("Select a catalog row in Search, then Add to quote.")
        else:
            for _, line in lines.iterrows():
                line_id = int(line["id"])
                part = str(line.get("part_number") or "")
                desc = str(line.get("description") or "")
                with st.container(border=True):
                    st.markdown(f"**{part or desc}**")
                    if part and desc:
                        st.caption(desc)
                    config_bits = [
                        str(line.get("species") or ""),
                        str(line.get("finish_state") or ""),
                        str(line.get("dimensions") or ""),
                        _quote_option_summary(line.get("options_json")),
                    ]
                    st.caption(" · ".join(bit for bit in config_bits if bit))
                    qty = st.number_input(
                        "Qty",
                        min_value=1,
                        value=max(1, int(float(line.get("qty") or 1))),
                        step=1,
                        key=f"cart_qty_{qid}_{line_id}",
                    )
                    notes = st.text_input(
                        "Notes",
                        value=str(line.get("notes") or ""),
                        key=f"cart_notes_{qid}_{line_id}",
                        placeholder="Optional line note",
                    )
                    if float(qty) != float(line.get("qty") or 1) or notes != str(
                        line.get("notes") or ""
                    ):
                        svc.update_quote_line(line_id, qty=float(qty), notes=notes)
                        st.rerun()
                    st.caption(
                        f"${float(line.get('unit_retail') or 0):,.2f} each · "
                        f"**${float(line.get('line_total') or 0):,.2f}**"
                    )
                    reset_col, remove_col = st.columns(2)
                    if reset_col.button(
                        "Reset options",
                        key=f"cart_reset_{qid}_{line_id}",
                        use_container_width=True,
                    ):
                        svc.reset_quote_line_options(line_id)
                        st.session_state["_quote_cart_refresh"] = True
                        st.rerun()
                    if remove_col.button(
                        "Remove",
                        key=f"cart_remove_{qid}_{line_id}",
                        use_container_width=True,
                    ):
                        svc.delete_quote_line(line_id)
                        st.rerun()

        st.markdown("##### Delivery tax")
        tax_options = list(county_tax_options())
        selected_key = (
            f"{quote.get('tax_state')}:{quote.get('tax_county')}"
            if quote.get("tax_state") and quote.get("tax_county")
            else ""
        )
        selected_index = next(
            (i for i, row in enumerate(tax_options, start=1) if row.key == selected_key),
            0,
        )
        selected_tax = st.selectbox(
            "County",
            options=[None, *tax_options],
            index=selected_index,
            format_func=lambda row: (
                "Select delivery county" if row is None else row.display_label
            ),
            key=_quote_county_widget_key(qid),
            help="Type a county or state name to filter. Rates are destination-based.",
        )
        tax_exempt = st.checkbox(
            "Tax exempt",
            value=bool(quote.get("tax_exempt")),
            key=f"cart_exempt_{qid}",
        )
        selected_rate = selected_tax.rate_pct if isinstance(selected_tax, CountyTaxRate) else 0.0
        selected_state = selected_tax.state if isinstance(selected_tax, CountyTaxRate) else None
        selected_county = selected_tax.county if isinstance(selected_tax, CountyTaxRate) else None
        if (
            float(quote.get("tax_pct") or 0) != float(selected_rate)
            or quote.get("tax_state") != selected_state
            or quote.get("tax_county") != selected_county
            or bool(quote.get("tax_exempt")) != tax_exempt
        ):
            svc.update_quote(
                qid,
                tax_pct=selected_rate,
                tax_state=selected_state,
                tax_county=selected_county,
                tax_exempt=tax_exempt,
            )
            totals = svc.quote_totals(qid)
        if tax_exempt:
            st.caption("Exempt · selected destination retained")
        elif selected_tax is None:
            st.caption("Select delivery county · tax $0.00")

        st.markdown(f"Merchandise subtotal: **${totals.get('subtotal', 0):,.2f}**")
        tax_label = "Exempt" if tax_exempt else (
            f"{selected_rate:g}%" if selected_tax is not None else "not selected"
        )
        st.markdown(
            f"Tax ({tax_label}): **${totals.get('tax_amount', 0):,.2f}**"
        )
        st.markdown(f"### Client total: ${totals.get('grand_total', 0):,.2f}")

        if st.session_state.get(f"cart_clear_pending_{qid}"):
            st.warning("Clear every line and the delivery tax selection?")
            yes, no = st.columns(2)
            if yes.button(
                "Confirm clear",
                type="primary",
                key=f"cart_clear_yes_{qid}",
                use_container_width=True,
            ):
                svc.clear_quote(qid, confirmed=True)
                st.session_state.pop(f"cart_clear_pending_{qid}", None)
                _bump_quote_county_widget(qid)
                st.session_state["_quote_cart_refresh"] = True
                st.rerun()
            if no.button(
                "Keep quote",
                key=f"cart_clear_no_{qid}",
                use_container_width=True,
            ):
                st.session_state.pop(f"cart_clear_pending_{qid}", None)
                st.rerun()
        elif st.button(
            "Clear quote",
            key=f"cart_clear_{qid}",
            disabled=(
                bool(lines is None or lines.empty)
                and selected_tax is None
                and not tax_exempt
            ),
            use_container_width=True,
        ):
            st.session_state[f"cart_clear_pending_{qid}"] = True
            st.rerun()


st.sidebar.title("FAF Price Book")
who = st.session_state.get("auth_display") or st.session_state.get("auth_user") or "user"
role = st.session_state.get("auth_role") or "sales"
st.sidebar.caption(f"Signed in as **{who}** · `{role}`")
if st.sidebar.button("Sign out"):
    _forget_login()
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
st.sidebar.caption(f"{stats['vendors']} vendors")
_render_quote_cart_sidebar()
if SHOW_ORDERTRAC_QUOTE:
    _quote_sidebar_badge()
# Viztech sync status lives under Admin only (hidden from floor sidebar)

# ---------------------------------------------------------------------------
# Home dashboard strip
# ---------------------------------------------------------------------------

if SHOW_SIMPLE_UI:
    st.caption(f"**FAF Price Book** · {stats['rows']:,} rows · {stats['vendors']} builders")
    if int(stats.get("rows") or 0) == 0:
        st.error(
            "**This copy has an empty catalog** (0 builders). "
            "Live data is on https://faf-pricebook.fly.dev — pull it with "
            "`./scripts/pull_db_from_fly.sh` (or Actions → **Pull Fly DB**), "
            "then restart the app. Do not commit `*.db`."
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

# ===========================================================================
# NAV — segmented control so Drop is not trapped in an st.tabs panel
# (Streamlit's file_uploader drag-drop is unreliable inside tabs).
# ===========================================================================

_NAV = ["Search", "Drop files", "Vendors", "Admin"]
if SHOW_ORDERTRAC_QUOTE:
    _NAV = ["Search", "OrderTrac quote", "Drop files", "Vendors", "Admin"]
nav = st.segmented_control(
    "Section",
    options=_NAV,
    default="Search",
    key="faf_nav",
    label_visibility="collapsed",
)
if not nav:
    nav = "Search"
tab_quote = "OrderTrac quote" if SHOW_ORDERTRAC_QUOTE else None

# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------
if nav == "Search":
    st.subheader("Find a price")

    # Apply pin / clear BEFORE any widgets with keys sq/sv/sf exist
    # (Streamlit forbids changing those keys after the widgets are created)
    _pending_pin = st.session_state.pop("_pin_select", None)
    if _pending_pin is not None:
        st.session_state["sq"] = ""
        st.session_state["sv"] = _pending_pin
        st.session_state["sf"] = "finished"
        st.session_state["so_panel_open"] = False
    if st.session_state.pop("_clear_search", False):
        st.session_state["sq"] = ""

    all_vendors = svc.list_vendors()
    favorites = [v for v in _load_favorites() if v in all_vendors]

    # Pinned-builders rail
    if "pin_panel_open" not in st.session_state:
        st.session_state["pin_panel_open"] = False
    pins_open = bool(st.session_state["pin_panel_open"])

    if pins_open:
        search_col, pin_col = st.columns([3.1, 1.4], gap="medium")
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

        vendors = ["All"] + all_vendors
        # Put favorites first after All for faster floor pick in dropdown only
        if favorites:
            rest = [v for v in all_vendors if v not in favorites]
            vendors = ["All"] + favorites + rest

        if SHOW_SIMPLE_UI:
            f1, f2 = st.columns([1.5, 1.3])
            f3 = None
        else:
            f1, f2, f3 = st.columns([1.5, 1.3, 0.9])
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
                "Mixed woods show as Wood/Wood. "
                "Multi-wood price tiers match if they include the wood you pick.",
            )
            if vf != "All" and len(wood_opts) <= 1:
                st.caption("No wood options parsed for this builder.")
        # Finish dropdown hidden — always show a builder's finished options only.
        ff = "finished"
        if f3 is not None:
            with f3:
                st.write("")  # align with selectboxes
                st.write("")
                if vf != "All":
                    if vf in favorites:
                        if st.button("Unpin", key="unpin_builder", use_container_width=True):
                            _save_favorites([x for x in favorites if x != vf])
                            st.rerun()
                    else:
                        if st.button("Pin builder", key="pin_builder", use_container_width=True):
                            _save_favorites(favorites + [vf])
                            st.rerun()

        # Option — hidden until the floor opts in (keeps Search clean).
        opt_list = _option_dropdown_options(vf if vf else "All", _catalog_stamp())
        # Migrate legacy select / multiselect session value into checkbox keys once.
        if "so" in st.session_state:
            cur = st.session_state.pop("so")
            legacy = []
            if isinstance(cur, str) and cur not in ("", "All"):
                legacy = [cur]
            elif isinstance(cur, list):
                legacy = [x for x in cur if x and x != "All"]
            for opt in legacy:
                if opt in opt_list:
                    st.session_state[_option_checkbox_key(vf, opt)] = True

        # Auto-open the panel only when this builder already has checks saved.
        prechecked = [
            opt for opt in opt_list if st.session_state.get(_option_checkbox_key(vf, opt))
        ]
        if "so_panel_open" not in st.session_state and prechecked:
            st.session_state["so_panel_open"] = True

        of_list: list[str] = []
        option_qty: dict[str, int] = {}
        if vf != "All" and opt_list:
            show_opts = st.checkbox(
                "Options",
                key="so_panel_open",
                help="This builder's live options from the catalog — not a "
                "fixed list. Leave off for base retail.",
            )
            if show_opts:
                with st.container(border=True):
                    head_l, head_r = st.columns([4.5, 1.2])
                    with head_l:
                        st.markdown(
                            '<div class="faf-option-panel-title">Check options to stack '
                            "upcharges "
                            "<span title='Each checked option adds its charge to "
                            "eligible items.' "
                            "style='cursor:help;opacity:0.65;font-size:0.85em'>ⓘ</span>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    with head_r:
                        if st.button(
                            "Clear",
                            key="so_clear_options",
                            use_container_width=True,
                            help="Uncheck all Options",
                        ):
                            for opt in opt_list:
                                st.session_state[_option_checkbox_key(vf, opt)] = False
                                st.session_state[_option_qty_key(vf, opt)] = 1
                            st.rerun()
                    n_cols = 2 if len(opt_list) <= 6 else 3
                    cb_cols = st.columns(n_cols)
                    for i, opt in enumerate(opt_list):
                        with cb_cols[i % n_cols]:
                            checked = st.checkbox(
                                opt,
                                key=_option_checkbox_key(vf, opt),
                                on_change=_enforce_single_select_options,
                                args=(vf, opt, opt_list),
                            )
                            if checked:
                                of_list.append(opt)
                                if PriceBookService._option_qty_allowed(opt):
                                    qkey = _option_qty_key(vf, opt)
                                    if qkey not in st.session_state:
                                        st.session_state[qkey] = 1
                                    qty = st.number_input(
                                        "How many?",
                                        min_value=1,
                                        max_value=20,
                                        step=1,
                                        key=qkey,
                                        help="Charge × count — how many drawers, "
                                        "drawer bottoms, or openings to price.",
                                    )
                                    option_qty[opt] = int(qty)
                    if of_list:
                        bits = []
                        for o in of_list:
                            q = option_qty.get(o, 1)
                            bits.append(f"{o} ×{q}" if q > 1 else o)
                        st.markdown(
                            '<div class="faf-option-selected"><strong>Selected:</strong> '
                            + " · ".join(bits)
                            + "</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("None checked — base retail (no option upcharge).")
            elif prechecked:
                # Panel closed but prior checks remain — remind without taking space.
                st.caption(
                    f"Options off · {len(prechecked)} saved "
                    f"({', '.join(prechecked[:3])}{'…' if len(prechecked) > 3 else ''}) "
                    "— turn **Options** on to apply."
                )
        elif vf == "All":
            pass  # no option chrome until a builder is chosen
        elif vf != "All" and not opt_list:
            st.caption("No options parsed for this builder.")

        q_col, clear_col = st.columns([5.5, 1.0], gap="small")
        with q_col:
            q = st.text_input(
                "Search the master book",
                placeholder="Part # or product words…",
                key="sq",
                label_visibility="collapsed",
            )
        with clear_col:
            has_query = bool((st.session_state.get("sq") or "").strip())
            if st.button(
                "Clear",
                key="sq_clear",
                use_container_width=True,
                disabled=not has_query,
                help="Clear the search box",
            ):
                st.session_state["_clear_search"] = True
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
                    option_key=of_list or None,
                    option_qty=option_qty or None,
                    limit=DEFAULT_SEARCH_LIMIT,
                )
                empty_reason = "none" if results.empty else ""
            except Exception as exc:
                results = pd.DataFrame()
                empty_reason = "error"
                st.error(f"Search failed: {exc}")
        display = results.copy()
        # When a wood is selected, show only that wood in the Wood column —
        # hide the rest of the multi-wood tier (e.g. Barnwood / Brown Maple → Barnwood).
        if not display.empty and "species" in display.columns:
            display = display.copy()
            if wf and wf != "All":
                # Selected mix shows as Wood/Wood; a single wood hides the rest
                # of a multi-wood tier (e.g. Barnwood / Brown Maple → Barnwood).
                display["species"] = wf
            else:
                display["species"] = display["species"].map(lambda s: mixed_wood_label(s) or s)

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
                if vf != "All":
                    st.info(
                        "No hits for this builder — try clearing the **Wood** or "
                        "**Option** filter, or the search box."
                    )
                else:
                    st.info(
                        "No hits — try fewer words, Boolean **OR**, or check the "
                        "**Builder** / **Wood** / **Option** filters."
                    )
        else:
            hit_note = f"**{len(display):,}** hits"
            if len(display) >= DEFAULT_SEARCH_LIMIT:
                hit_note += f" (showing first {DEFAULT_SEARCH_LIMIT})"
            st.markdown(
                f"{hit_note} · "
                f"<span style='color:#244a2e;font-weight:700'>Retail is what the customer pays</span>",
                unsafe_allow_html=True,
            )
            # Floor view: retail only (wholesale/mult managed on Vendors tab)
            display = display.copy()
            if "part_number" in display.columns:
                display["part_number"] = [
                    floor_part_number(value) for value in display["part_number"].tolist()
                ]
            show_cols = [
                c
                for c in [
                    "image_path",
                    "part_number",
                    "description",
                    "vendor",
                    "option_key",
                    "species",
                    "finish_state",
                    "adjusted_price",
                ]
                if c in display.columns
            ]
            # Keep Image in place for any builder that has photos, so the column
            # doesn't appear and vanish as the search narrows to un-photographed SKUs.
            has_images = False
            if "image_path" in show_cols:
                # Blank (not None) for un-photographed SKUs — ImageColumn prints
                # the literal "None" otherwise.
                thumbs = [_catalog_thumb(raw) or "" for raw in display["image_path"].tolist()]
                display = display.copy()
                display["image_path"] = thumbs
                photo_vendors = _vendors_with_catalog_images()
                shown_vendors = (
                    set(display["vendor"].dropna().astype(str))
                    if "vendor" in display.columns
                    else set()
                )
                has_images = any(thumbs) or bool(shown_vendors & photo_vendors)
                if not has_images:
                    show_cols = [c for c in show_cols if c != "image_path"]
            if (
                "part_number" in show_cols
                and display["part_number"].fillna("").astype(str).str.strip().eq("").all()
            ):
                show_cols = [c for c in show_cols if c != "part_number"]
            if (
                "option_key" in show_cols
                and display["option_key"].fillna("").astype(str).str.strip().eq("").all()
            ):
                show_cols = [c for c in show_cols if c != "option_key"]
            # When Option(s) are applied, surface the per-item upcharge detail
            # (matched category / "approx") from notes so the floor can verify.
            option_applied = (
                bool(of_list)
                and "option_key" in display.columns
                and display["option_key"].fillna("").astype(str).str.strip().ne("").any()
                and "collection" in display.columns
                and (display["collection"].astype(str) != "Addons").any()
            )
            if option_applied and "notes" in display.columns and "notes" not in show_cols:
                show_cols = show_cols + ["notes"]
            view = display[show_cols].rename(
                columns={
                    "image_path": "Image",
                    "part_number": "Part #",
                    "description": "Description",
                    "vendor": "Builder",
                    "collection": "Collection",
                    "option_key": "Option",
                    "species": "Wood",
                    "finish_state": "Finish",
                    "adjusted_price": "RETAIL",
                    "notes": "Option detail",
                }
            )
            if wf and wf != "All":
                st.caption(
                    f"Wood filter: **{wf}** · Wood column shows only this selection "
                    f"(other woods in the builder’s price tier are hidden)."
                )
            if option_applied:
                opt_label = ", ".join(of_list)
                st.caption(
                    f"**RETAIL includes {opt_label}** — upcharge(s) already "
                    f"added to each eligible item’s price."
                )
            # Keep descriptions compact; taller rows make long text wrap.
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config=_dataframe_column_config(
                    view,
                    money_cols={"RETAIL"},
                    number_formats={"RETAIL": "$%.0f"},
                    image_cols={"Image"} if has_images else set(),
                    help_text={
                        "RETAIL": "Customer price — wholesale × mult, rolled up to next even dollar",
                        "Wood": "Wood species / option — use the Wood dropdown above to pick one",
                        "Option": "Addon charge or finish/size option",
                        "Image": "Catalog photo for this SKU",
                        "Part #": "Factory SKU when the book has one",
                    },
                    overrides={
                        "Image": 72,
                        "Part #": 110,
                        "Description": 230,
                        "Option": 90,
                        "Wood": 160,
                        "Finish": 100,
                        "RETAIL": 100,
                    },
                ),
                height=480,
                row_height=64,
            )

            if "id" in results.columns and not results.empty:
                st.markdown("##### Add configured row to quote")
                st.caption(
                    "The retail, wood, finish, size, and checked Options are snapshotted now. "
                    "The Quote Cart stays in the sidebar while you keep searching."
                )
                labels = []
                row_by_label = {}
                for row_index, (_, result_row) in enumerate(results.head(80).iterrows()):
                    rid = int(result_row["id"])
                    part = str(result_row.get("part_number") or "")[:28]
                    desc = str(result_row.get("description") or "")[:36]
                    retail = float(result_row.get("adjusted_price") or 0)
                    label = f"#{rid} · {part} · ${retail:,.0f} · {desc}"
                    if label in row_by_label:
                        label = f"{label} · row {row_index + 1}"
                    labels.append(label)
                    row_by_label[label] = dict(result_row)
                aq1, aq2, aq3, aq4 = st.columns([3.0, 0.7, 1.4, 1.1])
                with aq1:
                    pick = st.selectbox(
                        "Catalog row",
                        labels,
                        key="add_quote_pick",
                        label_visibility="collapsed",
                    )
                with aq2:
                    add_qty = st.number_input(
                        "Qty", min_value=1, value=1, step=1, key="add_quote_qty"
                    )
                with aq3:
                    _def_stain = st.session_state.get("quote_stain_default", "")
                    add_stain = st.text_input(
                        "Stain (optional)",
                        value=_def_stain,
                        key="add_quote_stain",
                        placeholder="Stain / OCS…",
                    )
                    separate_line = st.checkbox(
                        "Add as separate line",
                        key="add_quote_separate",
                    )
                with aq4:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Add to quote",
                        type="primary",
                        key="btn_add_to_quote",
                        use_container_width=True,
                    ):
                        try:
                            qid = _ensure_active_quote()
                            configured = dict(row_by_label[pick])
                            rid = int(configured["id"])
                            wood_sel = None if wf == "All" else wf
                            finish_sel = None if ff == "All" else ff
                            stain_sel = (add_stain or "").strip()
                            if wood_sel:
                                configured["species"] = wood_sel
                            if finish_sel:
                                configured["finish_state"] = finish_sel
                            option_snapshot = {
                                "selections": {
                                    option: int(option_qty.get(option, 1))
                                    for option in of_list
                                },
                                "stain": stain_sel,
                            }
                            svc.add_quote_cart_line(
                                qid,
                                configured,
                                options=option_snapshot,
                                qty=float(add_qty),
                                notes=f"Stain: {stain_sel}" if stain_sel else "",
                                separate_line=separate_line,
                            )
                            if stain_sel:
                                st.session_state["quote_stain_default"] = stain_sel
                            quote_name = (svc.get_quote(qid) or {}).get("quote_name")
                            st.success(f"Added FAF #{rid} to **{quote_name or 'quote'}**.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not add line: {exc}")

    # ---- Separate pinned-builders column (collapsible) ----
    if pin_col is not None:
        with pin_col:
            head_l, head_r = st.columns([5.0, 1.0], vertical_alignment="center")
            with head_l:
                st.markdown("#### Pinned")
            with head_r:
                if st.button(
                    "‹",
                    key="hide_pin_panel",
                    use_container_width=True,
                    help="Hide pinned builders",
                ):
                    st.session_state["pin_panel_open"] = False
                    st.rerun()
            st.caption("Tap builder to filter · manage pins on **Vendors**")
            if not favorites:
                st.info("No pins yet. Tick **Pinned** on the **Vendors** tab.")
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

if SHOW_ORDERTRAC_QUOTE and nav == "OrderTrac quote":
    # ---------------------------------------------------------------------------
    # ORDERTRAC QUOTE — FAF price book is source; OrderTrac is destination
    # ---------------------------------------------------------------------------
    if True:
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
                        st.markdown(f"[Open this quote in OrderTrac]({quote['ordertrac_url']})")

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
                    if st.session_state.get("quote_finish_default", "finished") == "finished"
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

                        note_out = _re.sub(r"(?im)^Wood:.*$", "", note_out).strip()
                        note_out = _re.sub(r"(?im)^Stain:.*$", "", note_out).strip()
                        note_out = _re.sub(r"(?im)^Finish:.*$", "", note_out).strip()
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
                                cleaned = _re.sub(r"(?i)\s*Stain:\s*[^·|\n]*", "", old_notes).strip(
                                    " ·|\n"
                                )
                                new_notes = (
                                    f"{cleaned} · Stain: {stain_default}".strip(" ·")
                                    if stain_default and cleaned
                                    else (f"Stain: {stain_default}" if stain_default else cleaned)
                                )
                                svc.update_quote_line(
                                    lid,
                                    species=wood_default or lr.get("species"),
                                    finish_state=finish_default or lr.get("finish_state"),
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
                                if str(erow.get("finish_state") or "finished") == "finished"
                                else 1,
                                key=f"q_efin_{qid}",
                            )
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("Update line", key=f"q_upd_line_{qid}"):
                                nnotes = str(erow.get("notes") or "")
                                nnotes = _re.sub(r"(?i)\s*Stain:\s*[^·|\n]*", "", nnotes).strip(
                                    " ·"
                                )
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
                ot_ix = ot_user_opts.index(default_ot) if default_ot in ot_user_opts else 0

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
                        with st.spinner("Creating OrderTrac QUOTE from FAF pricelist lines…"):
                            try:
                                result = _save_header_and_push("create")
                                if result.get("ok"):
                                    st.success(
                                        f"OrderTrac **QUOTE #{result.get('sales_order_id')}** "
                                        f"created from FAF **{quote.get('quote_number')}** "
                                        f"({result.get('lines_added', '?')} lines)."
                                    )
                                    if result.get("url"):
                                        st.markdown(f"[Open OrderTrac quote]({result['url']})")
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
                        with st.spinner("Adding new FAF lines onto linked OrderTrac quote…"):
                            try:
                                result = _save_header_and_push("append")
                                if result.get("ok"):
                                    st.success(
                                        f"OrderTrac **QUOTE #{result.get('sales_order_id')}** updated · "
                                        f"added {result.get('lines_added', 0)}, "
                                        f"already present {result.get('lines_skipped', 0)}."
                                    )
                                    if result.get("url"):
                                        st.markdown(f"[Open OrderTrac quote]({result['url']})")
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
                            if quote.get("status") in ("draft", "sent", "won", "lost", "archived")
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


def _render_catalog_image_uploader(svc: PriceBookService) -> None:
    """R6/R7: PDF + single-image upload after a successful pricebook Load."""
    prompt = bool(st.session_state.get("drop_image_prompt"))
    if prompt:
        st.markdown("Do you want to add pdf of images?")
        yes, not_now = st.columns(2)
        with yes:
            if st.button("Yes", key="drop_image_yes", type="primary"):
                st.session_state["drop_image_prompt"] = False
                st.session_state["drop_image_focus"] = True
                st.rerun()
        with not_now:
            if st.button("Not now", key="drop_image_not_now"):
                st.session_state["drop_image_prompt"] = False
                st.session_state["drop_image_focus"] = False
                st.rerun()

    vendors = list(svc.list_vendors() or [])
    hinted = list(st.session_state.get("drop_image_builders") or [])
    for name in hinted:
        if name and name not in vendors:
            vendors.append(name)
    if not vendors:
        vendors = hinted or [""]

    expanded = bool(st.session_state.get("drop_image_focus"))
    with st.expander("Catalog images — PDF or single photo", expanded=expanded):
        default_v = st.session_state.get("drop_image_vendor") or (vendors[0] if vendors else "")
        idx = vendors.index(default_v) if default_v in vendors else 0
        builder = st.selectbox("Builder", vendors, index=idx, key="drop_img_builder")
        pdf = st.file_uploader(
            "Catalog PDF of images",
            type=["pdf"],
            key="drop_img_pdf",
        )
        if pdf is not None and st.button("Attach PDF images", key="drop_img_pdf_go"):
            result = svc.ingest_catalog_pdf_images(
                vendor=str(builder),
                pdf_bytes=pdf.getvalue(),
                filename=pdf.name,
            )
            if result.get("ok"):
                st.success(
                    f"Matched {result.get('matched_count', 0)} SKU photo(s) as drafts. "
                    f"Christina findings below."
                )
            else:
                st.error(result.get("error") or "PDF attach failed.")
            if result.get("viztech", {}).get("log"):
                st.caption(result["viztech"]["log"])
            for review in result.get("reviews") or []:
                st.caption(
                    f"{review.get('part_number')}: {review.get('verdict')} — "
                    + "; ".join(review.get("findings") or [])
                )

        st.markdown("##### Single image")
        items = st.text_input(
            "Item(s)",
            key="drop_img_items",
            placeholder="1010 or 1010, 1021",
            help="Exact catalog part number(s) for this builder.",
        )
        notes = st.text_input("Notes", key="drop_img_notes")
        descriptor = st.text_input(
            "Descriptor",
            key="drop_img_desc",
            help="Editable. Saving rebinds and reruns Christina.",
        )
        photo = st.file_uploader(
            "Photo",
            type=["jpg", "jpeg", "png", "webp"],
            key="drop_img_photo",
        )
        if photo is not None and st.button("Save image", key="drop_img_save"):
            keys = [p.strip() for p in re.split(r"[,\s]+", items or "") if p.strip()]
            result = svc.ingest_single_catalog_image(
                vendor=str(builder),
                items=keys,
                image_bytes=photo.getvalue(),
                filename=photo.name,
                descriptor=descriptor,
                notes=notes,
            )
            st.session_state["drop_img_last"] = result
            if result.get("ok"):
                st.success("Saved as draft. Search shows it after Christina pass or override.")
            else:
                st.error(result.get("error") or "Save failed.")

        last = st.session_state.get("drop_img_last") or {}
        for review in last.get("reviews") or []:
            st.caption(
                f"{review.get('part_number')}: {review.get('verdict')} — "
                + "; ".join(review.get("findings") or [])
            )
            sku = str(review.get("part_number") or "")
            if review.get("verdict") == "flag" and sku:
                reason = st.text_input(
                    f"Override reason for {sku}",
                    key=f"drop_img_ovr_{sku}",
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Override", key=f"drop_img_ovr_btn_{sku}"):
                        out = svc.override_catalog_image(
                            vendor=str(builder),
                            part_number=sku,
                            reason=reason,
                        )
                        if out.get("ok"):
                            st.success(f"{sku} is Search-visible.")
                        else:
                            st.error(out.get("error") or "Override failed.")
                with c2:
                    if st.button("Remove", key=f"drop_img_rm_{sku}"):
                        svc.remove_catalog_image(vendor=str(builder), part_number=sku)
                        st.warning(f"Removed {sku} photo.")


# ---------------------------------------------------------------------------
# IMPORT — multi-file drop with per-builder multiplier
# ---------------------------------------------------------------------------
if nav == "Drop files":
    st.subheader("Drop builder price lists")
    if SHOW_SIMPLE_UI:
        st.caption(
            "Upload Excel or PDF · set **builder** + **multiplier**. "
            "A **new** builder is added to the book. "
            "Re-drop of an existing builder replaces **that** catalog only. "
            "Parse looks for that builder's woods, stains, upcharges, and layout."
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
    if not SHOW_SIMPLE_UI:
        st.caption(
            "Large Drop: use **http://127.0.0.1:8501** on the Mac (not the Cloudflare "
            "tunnel). Parsed rows stay on disk so the browser session doesn’t disconnect "
            "while you set multipliers. Every file in a drop or folder is checked for "
            "catalog typos and light grammar (`Occasonial` → `Occasional`)."
        )

    zone_file = render_dropzone(key="faf_dropzone_main")
    local_file = st.text_input(
        "Or paste the file path",
        key="drop_local_file",
        placeholder="/Users/you/Downloads/Builder_2026.xlsx",
    )
    if not SHOW_SIMPLE_UI:
        st.caption(
            "If the file will not land, **click Browse** (or use the folder path). "
            "macOS sometimes blocks a drag when it labels Excel as a zip."
        )
    rejected_names: list[str] = []
    uploads = []
    disk_file = zone_file
    local_raw = str(local_file or "").strip()
    if local_raw:
        from_path = drop_upload_from_path(local_raw)
        if from_path is None:
            p = Path(local_raw).expanduser()
            if not p.is_file():
                st.error(f"File not found: `{p}`")
            else:
                rejected_names.append(p.name)
        else:
            disk_file = from_path
    if rejected_names:
        st.warning("Not an Excel/PDF price list — skipped: " + ", ".join(rejected_names))
    if uploads or disk_file:
        names = [getattr(u, "name", "") for u in uploads]
        if disk_file:
            names.append(disk_file.filename)
        st.caption("Received **" + "**, **".join(n for n in names if n) + "**")
    if SHOW_SIMPLE_UI:
        folder_path = ""
    else:
        folder_path = st.text_input(
            "Or a folder on this Mac",
            key="drop_folder_path",
            placeholder="/Users/…/builder-pricelists",
            help="Reads every Excel/PDF in that folder and subfolders. "
            "Same typo/grammar pass as a file drop.",
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
                or k.startswith("drop_pending_mult_")
                or k.startswith("drop_wb_")
                or k.startswith("m27_")
                or k.startswith("m17_")
            ):
                del st.session_state[k]

    def _bind_builder_mult(rows: list, vendor: str, mult: float, source: str) -> list:
        """Ephemeral bind for preview/commit — never writes the Drop parse session."""
        from backend.pricing import retail_from_wholesale

        out = []
        for src in rows:
            r = dict(src)
            r["vendor"] = vendor
            r["source_file"] = source
            r["multiplier"] = mult
            bp = r.get("base_price")
            if bp is not None:
                try:
                    r["adjusted_price"] = retail_from_wholesale(bp, mult)
                except (TypeError, ValueError):
                    pass
            out.append(r)
        return out

    # Flash message after load (survives rerun so sidebar stats refresh)
    if st.session_state.get("drop_load_msg"):
        st.success(st.session_state.pop("drop_load_msg"))
        warning = st.session_state.pop("drop_load_warning", "")
        if warning:
            st.error(warning)
        log = st.session_state.pop("drop_load_log", None)
        if log:
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)

    _render_catalog_image_uploader(svc)

    folder_uploads: list[DropUpload] = []
    folder_root = Path(str(folder_path or "").strip()).expanduser()
    if str(folder_path or "").strip():
        if not folder_root.is_dir():
            st.warning(f"Folder not found: `{folder_root}`")
        else:
            found = svc.discover_batch_files(folder_root, recursive=True)
            if not found:
                st.warning(f"No Excel/PDF price lists in `{folder_root}`.")
            else:
                st.caption(f"Folder: {len(found)} file(s) — each will get the typo/grammar pass.")
                for p in found:
                    folder_uploads.append(
                        DropUpload(
                            str(p.relative_to(folder_root)),
                            b"",
                            size=p.stat().st_size,
                        )
                    )

    if not uploads and not folder_uploads and disk_file is None:
        # Clear Drop parse session when the uploader is emptied (CONTEXT: Clear).
        sid = st.session_state.pop("drop_session_id", None)
        if sid:
            svc.clear_drop_parse_session(sid)
            st.session_state.pop("drop_vendor_overrides", None)
            _clear_drop_widget_state()
        if not SHOW_SIMPLE_UI:
            st.info("Drop one or more builder price files above to begin.")
    else:
        force_reparse = bool(st.session_state.pop("drop_force_reparse", False))
        prior_sid = st.session_state.get("drop_session_id")

        def _upload_size(up) -> int | None:
            s = int(getattr(up, "size", 0) or 0)
            return s if s > 0 else None

        def _folder_bytes() -> dict[str, bytes]:
            data_by_name: dict[str, bytes] = {}
            if folder_root.is_dir():
                for p in svc.discover_batch_files(folder_root, recursive=True):
                    data_by_name[str(p.relative_to(folder_root))] = p.read_bytes()
            return data_by_name

        def _drop_idents(with_bytes: bool) -> list:
            out = []
            for up in uploads or []:
                size = _upload_size(up)
                data = _bytes(up) if with_bytes else b""
                if with_bytes and size is None:
                    size = len(data)
                out.append(DropUpload(up.name, data, size=size))
            folder_data = _folder_bytes() if with_bytes else {}
            for fu in folder_uploads:
                data = folder_data.get(fu.filename, b"") if with_bytes else b""
                out.append(DropUpload(fu.filename, data, size=fu.size))
            if disk_file is not None:
                if with_bytes:
                    out.append(disk_file)
                else:
                    out.append(DropUpload(disk_file.filename, b"", size=disk_file.size))
            return out

        sizes_ok = all(_upload_size(up) is not None for up in uploads)
        session = None
        # Reuse path: identity only (no byte read) when sizes known and session fresh.
        if prior_sid and not force_reparse and sizes_ok:
            try:
                session = svc.ensure_drop_parse_session(
                    _drop_idents(False),
                    session_id=prior_sid,
                    prefer_workbook_markup=prefer_wb_markup,
                    force=False,
                )
            except ValueError:
                session = None

        if session is None:
            progress = st.progress(0.0, text="Reading files…")
            try:
                session = svc.ensure_drop_parse_session(
                    _drop_idents(True),
                    session_id=prior_sid,
                    prefer_workbook_markup=prefer_wb_markup,
                    force=force_reparse,
                    progress=lambda p, t: progress.progress(p, text=t),
                    vendor_overrides=st.session_state.get("drop_vendor_overrides") or {},
                )
            except Exception as exc:
                progress.empty()
                st.error(f"Drop parse failed: {exc}"[:400])
                session = None

        if session is not None:
            if st.session_state.get("drop_session_id") != session.session_id:
                _clear_drop_widget_state()
                st.session_state["drop_session_id"] = session.session_id
                for f in session.files:
                    st.session_state.setdefault(f"drop_vend_{f.file_index}", f.suggested_builder)
                    st.session_state.setdefault(
                        f"drop_mult_{f.file_index}", float(f.suggested_mult)
                    )

            r1, r2 = st.columns([1, 3])
            with r1:
                if st.button("Re-parse", key="drop_reparse_btn"):
                    st.session_state["drop_vendor_overrides"] = {
                        f.filename: (
                            st.session_state.get(f"drop_vend_{f.file_index}") or f.suggested_builder
                        )
                        for f in session.files
                    }
                    st.session_state["drop_force_reparse"] = True
                    st.rerun()
            with r2:
                st.caption(
                    "Parsed rows stay on disk (Drop parse session). "
                    "Set the builder name, then Re-parse to use that factory's "
                    "named parser. Multiplier binds when you load."
                )

            st.markdown("### Per-file builder & multiplier")
            st.caption(
                "Set the retail multiplier **per builder**. "
                "Example: Genuine Oak **1.7**, most others **2.7**."
            )

            ready_indexes: list[int] = []

            for f in session.files:
                i = f.file_index
                name = f.filename
                default_vend = (f.suggested_builder or Path(name).stem).strip()
                default_mult = float(f.suggested_mult or DEFAULT_MULTIPLIER)

                vend_key = f"drop_vend_{i}"
                mult_key = f"drop_mult_{i}"
                pending_mult = st.session_state.pop(f"drop_pending_mult_{i}", None)
                if pending_mult is not None:
                    st.session_state[mult_key] = float(pending_mult)
                if vend_key not in st.session_state:
                    st.session_state[vend_key] = default_vend
                if mult_key not in st.session_state:
                    st.session_state[mult_key] = float(default_mult)

                with st.container(border=True):
                    h1, h2 = st.columns([2, 1])
                    with h1:
                        st.markdown(f"**{name}**")
                        if f.error and not f.row_count:
                            st.error(str(f.error))
                        elif f.notes:
                            st.caption(str(f.notes)[:480])
                    variants = getattr(f, "variants", None) or {}
                    if variants and (
                        variants.get("woods") or variants.get("addons") or variants.get("stains")
                    ):
                        bits = []
                        if variants.get("woods"):
                            bits.append("Woods: " + ", ".join(variants["woods"][:8]))
                        if variants.get("stains"):
                            bits.append("Stains: " + ", ".join(variants["stains"][:6]))
                        if variants.get("addons"):
                            bits.append("Upcharges: " + ", ".join(variants["addons"][:6]))
                        if variants.get("customizations"):
                            bits.append("Options: " + ", ".join(variants["customizations"][:6]))
                        st.caption("Smart parse · " + " · ".join(bits))
                    with h2:
                        st.metric("Parsed rows", f"{int(f.row_count):,}")
                        importer = (getattr(f, "detected_importer", "") or "").strip()
                        source = (getattr(f, "parser_source", "") or "").strip()
                        if importer and source == "saved":
                            st.caption(f"Parser **{importer}** · locked")
                        elif importer:
                            st.caption(f"Parser **{importer}** · locks on Load")
                        else:
                            st.caption((f.kind or "excel").upper())

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
                        det_f = None
                        if f.detected_markup is not None:
                            try:
                                det_f = float(f.detected_markup)
                            except (TypeError, ValueError):
                                det_f = None
                        if det_f is not None:
                            st.caption(f"Workbook markup sheet: **{det_f:g}**")
                            if st.button(
                                f"Use workbook {det_f:g}",
                                key=f"drop_wb_{i}",
                            ):
                                st.session_state[f"drop_pending_mult_{i}"] = float(det_f)
                                st.rerun()
                        else:
                            st.caption("No markup sheet found")
                        if SHOW_SIMPLE_UI:
                            if st.button("Use 2.7", key=f"m27_{i}"):
                                st.session_state[f"drop_pending_mult_{i}"] = 2.7
                                st.rerun()
                        else:
                            b_a, b_b = st.columns(2)
                            with b_a:
                                if st.button("2.7", key=f"m27_{i}"):
                                    st.session_state[f"drop_pending_mult_{i}"] = 2.7
                                    st.rerun()
                            with b_b:
                                if st.button("1.7", key=f"m17_{i}"):
                                    st.session_state[f"drop_pending_mult_{i}"] = 1.7
                                    st.rerun()

                    vend_final = (vend_edit or default_vend).strip()
                    mult_final = float(mult_edit)
                    # Preview only — bind sample rows in memory (session stays wholesale)
                    sample_rows = _bind_builder_mult(list(f.sample), vend_final, mult_final, name)

                    if f.row_count:
                        if sample_rows:
                            sample = pd.DataFrame(sample_rows[:6])
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
                                    "Wholesale": st.column_config.NumberColumn(format="$%.2f"),
                                    "RETAIL": st.column_config.NumberColumn(
                                        format="$%.0f",
                                        help="Rolled up to next even dollar",
                                    ),
                                    "Mult": st.column_config.NumberColumn(format="%.2f"),
                                },
                            )
                        st.caption(
                            f"Retail preview uses x{mult_final:g} on sample only · "
                            f"**{f.row_count:,}** wholesale rows in session"
                        )
                        q_pct = int(getattr(f, "quality_percent", 0) or 0)
                        q_notes = list(getattr(f, "quality_deductions", ()) or ())
                        st.markdown(f"**Upload quality {q_pct}%**")
                        if q_notes:
                            st.caption(" · ".join(q_notes[:4]))
                        readiness = getattr(f, "readiness", None)
                        if readiness is None or readiness.load_ready:
                            ready_indexes.append(i)
                        else:
                            st.error(
                                readiness.block_message
                                or "This builder is blocked until its named parser reads the book."
                            )
                    elif f.error:
                        st.warning("This file will be skipped until it parses cleanly.")

            st.divider()
            st.markdown("### Load into master price book")
            if not ready_indexes:
                st.warning("No files with parsed rows yet.")
            else:
                # Summary from session metadata + widget edits (no full rows in UI)
                summary_rows = []
                by_vendor_idx: dict = {}
                for i in ready_indexes:
                    f = session.files[i]
                    vend = (st.session_state.get(f"drop_vend_{i}") or f.suggested_builder).strip()
                    mult = float(st.session_state.get(f"drop_mult_{i}") or f.suggested_mult)
                    by_vendor_idx[vend] = i
                    summary_rows.append(
                        {
                            "Builder": vend,
                            "File": f.filename,
                            "Rows": f.row_count,
                            "Multiplier": mult,
                        }
                    )
                if len(by_vendor_idx) < len(ready_indexes):
                    st.warning(
                        "Two or more files map to the **same builder name**. "
                        "They will be combined into one catalog for that builder."
                    )

                st.caption(
                    "Loading **adds** a new builder, or **replaces that builder only** "
                    "if the name already exists. Other builders stay."
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

                _load_n = len(by_vendor_idx)
                _load_label = (
                    f"Standardize & load {_load_n} builder{'' if _load_n == 1 else 's'} into master"
                )
                if st.button(
                    _load_label,
                    type="primary",
                    use_container_width=True,
                    key="drop_load_master",
                ):
                    bindings = [
                        DropLoadBinding(
                            file_index=i,
                            builder=(
                                st.session_state.get(f"drop_vend_{i}")
                                or session.files[i].suggested_builder
                            ).strip(),
                            multiplier=float(
                                st.session_state.get(f"drop_mult_{i}")
                                or session.files[i].suggested_mult
                            ),
                        )
                        for i in by_vendor_idx.values()
                    ]
                    try:
                        with st.spinner("Loading builders…"):
                            batch_result = svc.commit_drop_load(
                                session.session_id,
                                bindings,
                                mode=commit_mode,
                            )
                    except DropSessionGone:
                        st.error("Drop parse session expired — click Re-parse and try again.")
                    else:
                        results_log = []
                        for item in batch_result.results:
                            catalog = item.catalog or {}
                            if item.status == "loaded":
                                status = (
                                    f"ok · parser {item.parser_id or 'generic'}"
                                    if not item.profile_warning
                                    else f"loaded · PROFILE WARNING: {item.profile_warning}"
                                )
                            elif item.status == "unchanged":
                                status = "unchanged · skipped"
                            elif item.status == "blocked":
                                status = f"blocked: {item.block_message}"
                            else:
                                status = f"error: {item.block_message}"
                            results_log.append(
                                {
                                    "Builder": item.builder,
                                    "File": item.filename,
                                    "Mult": item.multiplier,
                                    "Inserted": catalog.get("inserted", 0),
                                    "Updated": catalog.get("updated", 0),
                                    "Removed old": catalog.get("deleted", 0),
                                    "Total": catalog.get("total", 0),
                                    "Status": status[:160],
                                }
                            )
                        ok_n = sum(
                            1
                            for item in batch_result.results
                            if item.status in {"loaded", "unchanged"}
                        )
                        if batch_result.session_cleared:
                            st.session_state.pop("drop_session_id", None)
                            st.session_state.pop("drop_vendor_overrides", None)
                            _clear_drop_widget_state()
                        saved_n = sum(1 for item in batch_result.results if item.profile_saved)
                        st.session_state["drop_load_msg"] = (
                            f"Loaded or skipped **{ok_n}** of **{len(bindings)}** builder(s). "
                            f"Master now has **{batch_result.master_row_count:,}** rows. "
                            f"Named parser saved for **{saved_n}** builder(s)."
                        )
                        if batch_result.blocking_warnings:
                            st.session_state["drop_load_warning"] = " | ".join(
                                batch_result.blocking_warnings
                            )
                        st.session_state["drop_load_log"] = results_log
                        loaded_builders = [
                            item.builder
                            for item in batch_result.results
                            if item.status in {"loaded", "unchanged"} and item.builder
                        ]
                        if loaded_builders:
                            st.session_state["drop_image_prompt"] = True
                            st.session_state["drop_image_builders"] = loaded_builders
                            st.session_state["drop_image_vendor"] = loaded_builders[0]
                        st.rerun()

# ---------------------------------------------------------------------------
# VENDORS — edit multipliers
# ---------------------------------------------------------------------------
if nav == "Vendors":
    st.subheader("Modify builder multipliers")

    summary = svc.vendor_summary()
    if summary.empty:
        st.info("No builders in master yet — import files under **Drop files** first.")
    else:
        favorites = [v for v in _load_favorites() if v]
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
        edit_df["phone"] = edit_df["phone"].fillna("").astype(str).replace({"nan": "", "None": ""})
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
        quality_by = {r["vendor"]: r for r in (svc.list_upload_quality() or [])}
        edit_df["Quality"] = edit_df["Builder"].map(
            lambda name: int((quality_by.get(str(name)) or {}).get("percent") or 0)
        )
        edit_df["Pinned"] = edit_df["Builder"].astype(str).isin(set(favorites))
        # Pinned builders first so the floor can spot them quickly
        edit_df = edit_df.sort_values(
            by=["Pinned", "Builder"],
            ascending=[False, True],
            kind="mergesort",
        ).reset_index(drop=True)
        show_cols = [
            c
            for c in [
                "Pinned",
                "Builder",
                "Phone",
                "Items",
                "Collections",
                "Quality",
                "Multiplier",
            ]
            if c in edit_df.columns
        ]
        edited = st.data_editor(
            edit_df[show_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            # Lock stats columns; Pinned + Phone + Multiplier are editable
            disabled=["Builder", "Items", "Collections", "Quality"],
            column_config={
                "Pinned": st.column_config.CheckboxColumn(
                    "Pinned",
                    help="Pin for Search — pinned builders sort first in the Builder menu",
                    default=False,
                    width="small",
                ),
                "Builder": st.column_config.TextColumn(disabled=True),
                "Phone": st.column_config.TextColumn(
                    "Phone",
                    help="Builder main phone — edit then Save",
                    width="medium",
                    max_chars=40,
                ),
                "Items": st.column_config.NumberColumn(format="%d", disabled=True),
                "Collections": st.column_config.NumberColumn(format="%d", disabled=True),
                "Quality": st.column_config.ProgressColumn(
                    "Quality",
                    help="Last upload capture score: Options, wood, descriptions, SKUs, prices, parser lock",
                    min_value=0,
                    max_value=100,
                    format="%d%%",
                    width="small",
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

        # Pins save immediately (same list Search uses); mult/phone still need Save.
        if "Pinned" in edited.columns and "Builder" in edited.columns:
            new_pins = [
                str(b).strip()
                for b, pinned in zip(edited["Builder"], edited["Pinned"])
                if pinned and str(b).strip()
            ]
            if set(new_pins) != set(favorites):
                _save_favorites(new_pins)
                st.session_state.pop("vendor_mult_editor", None)
                st.toast(
                    f"Pins updated · {len(new_pins)} builder{'s' if len(new_pins) != 1 else ''}",
                )
                st.rerun()

        misses = [
            f"{r['vendor']} {r['percent']}% — {'; '.join(r['deductions'][:3])}"
            for r in quality_by.values()
            if r.get("percent", 100) < 100 and r.get("deductions")
        ]
        if misses:
            with st.expander(f"Quality notes · {len(misses)} builder(s) under 100%"):
                for line in misses:
                    st.caption(line)

        st.caption(
            "**Quality** = 0–100% upload capture (Options 30, wood 25, descriptions 15, "
            "SKUs 10, prices 10, parser lock 10). "
            "**Pinned** = quick picks on Search (Builder menu). "
            "Toggle the checkbox — pins save right away. "
            "Phone & multiplier still need **Save** below."
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
if nav == "Admin":
    st.subheader("Admin / data quality")
    s1, s2 = st.columns(2)
    s1.metric("Rows", f"{stats['rows']:,}")
    s2.metric("Builders", stats["vendors"])
    st.caption(f"Last backup: {_last_backup_hint()}")
    if SHOW_VIZTECH:
        st.caption(f"Viztech sync: {_viztech_sync_hint()}")

    st.markdown("### Thin catalogs")
    st.caption(
        f"Builders with fewer than **{THIN_CATALOG_MAX_ROWS}** sellable rows "
        "(ADR-0007). Judson chooses keep / replace (Drop) / ignore — no auto-ignore."
    )
    try:
        thin_df = svc.list_thin_catalogs()
    except Exception as e:
        thin_df = pd.DataFrame()
        st.error(f"Could not load thin catalogs: {e}")
    if thin_df is not None and not thin_df.empty:
        show_thin = [
            c
            for c in ("vendor", "rows", "collections", "source_files", "phone", "saved_mult")
            if c in thin_df.columns
        ]
        st.dataframe(thin_df[show_thin], use_container_width=True, hide_index=True)
        st.caption(
            f"**{len(thin_df)}** thin builders · CLI: "
            "`python -m backend.cli thin-catalogs` · "
            "`./scripts/ready_catalog.sh --no-pull`"
        )
    elif int(stats.get("rows") or 0) == 0:
        st.warning(
            "Master price book is empty — pull Fly DB on Mac "
            "(`./scripts/pull_db_from_fly.sh`) before triaging thins."
        )
    else:
        st.info(f"No thin catalogs (no builders under {THIN_CATALOG_MAX_ROWS} rows).")

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
                if st.button(
                    "Check OrderTrac session",
                    use_container_width=True,
                    help="Pings OrderTrac with the saved session. Does not create quotes or users.",
                ):
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
                            st.caption("Skipped: " + ", ".join(sync_result["skipped"][:12]))
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
                st.dataframe(users_df[show_cols], use_container_width=True, hide_index=True)
            else:
                st.info(
                    "No users yet — seed admin is created on first login, or run OrderTrac sync."
                )

            with st.expander("Create / reset a user"):
                cu1, cu2 = st.columns(2)
                with cu1:
                    nu = st.text_input("Username", key="new_user_name")
                    nd = st.text_input("Display name", key="new_user_disp")
                    nr = st.selectbox("Role", ["sales", "floor", "admin"], key="new_user_role")
                with cu2:
                    npw = st.text_input("Password", type="password", key="new_user_pw")
                    if st.button(
                        "Create user",
                        key="btn_create_user",
                        help="Adds a local FAF login with the username, password, and role on the left.",
                    ):
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
                    rpw = st.text_input("New password", type="password", key="reset_user_pw")
                    if st.button(
                        "Reset password",
                        key="btn_reset_pw",
                        help="Sets a new password for the selected user. They must change it on next login.",
                    ):
                        row = users_df[users_df["username"] == ru].iloc[0]
                        _ot_svc.set_app_user_password(int(row["id"]), rpw, must_change=True)
                        st.success(f"Password reset for {ru} (must change on next login).")

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
                        x for x in udf["ordertrac_display_name"].dropna().tolist() if str(x).strip()
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
            if st.button(
                "Push to OrderTrac as QUOTE",
                type="primary",
                key="btn_ot_push",
                help="Creates a new OrderTrac Quote (not a sale) from the FAF row IDs above.",
            ):
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
                            st.success(f"OrderTrac QUOTE {result.get('sales_order_id')} created.")
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

    # TRACE: Viztech block — set SHOW_VIZTECH = True to restore
    # (check login / full sync / 30-day LaunchAgent). Hidden while verifying
    # catalog accuracy via manual Drop imports.
    if SHOW_VIZTECH:
        st.markdown("##### Viztech monthly update")
        st.caption(
            "Downloads builder pricelists from **viztechfurniture.com** and updates the book "
            "(keeps builders Viztech doesn’t have · FN Chair = Level One only). "
            "Scheduled LaunchAgents are **Mac-only**; Run/Check work on Fly when Viztech "
            "secrets are configured."
        )
        st.info(_viztech_sync_hint())
        vz1, vz2, vz3 = st.columns(3)
        with vz1:
            if st.button(
                "Check Viztech login",
                use_container_width=True,
                help="Logs into Viztech and lists builders. Dry-run only — does not import or change the book.",
            ):
                import subprocess

                py = _python_executable()
                script = APP_DIR / "scripts" / "viztech_sync.py"
                with st.spinner("Logging into Viztech…"):
                    proc = subprocess.run(
                        [py, str(script), "--dry-run"],
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

                py = _python_executable()
                script = APP_DIR / "scripts" / "viztech_sync.py"
                with st.spinner("Syncing Viztech → FAF (download + import). Leave this tab open…"):
                    proc = subprocess.run(
                        [py, str(script)],
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
            if st.button(
                "Install 30-day schedule",
                use_container_width=True,
                help="Installs a Mac LaunchAgent that runs Viztech sync about every 30 days. Floor Mac only.",
            ):
                if not _is_macos_host():
                    st.warning(
                        "30-day schedule uses a macOS LaunchAgent — run this on the "
                        "floor Mac, not on Fly."
                    )
                else:
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
    b1, b2, b3 = st.columns([1, 1, 1])
    with b1:
        if st.button(
            "Backup DB now",
            type="primary",
            use_container_width=True,
            help="Copies the live SQLite book to Documents/FAF-pricebook-backups. Does not change Search.",
        ):
            try:
                from scripts.backup_db import backup_now

                dest = backup_now()
                st.success(f"Saved `{dest.name}`")
            except Exception as exc:
                st.error(f"Backup failed: {exc}")
    with b2:
        if st.button(
            "Install weekly backup (Sunday 6 AM)",
            use_container_width=True,
            help="Installs a Mac LaunchAgent that snapshots the live book every Sunday at 6:00 AM. Floor Mac only, not Fly.",
        ):
            if not _is_macos_host():
                st.warning(
                    "Weekly backup schedule uses a macOS LaunchAgent — install on the "
                    "floor Mac, not on Fly."
                )
            else:
                import subprocess

                install = Path(__file__).resolve().parent / "scripts" / "install_weekly_backup.sh"
                rc = subprocess.call(["/bin/zsh", str(install)])
                if rc == 0:
                    st.success("Weekly LaunchAgent installed (Sunday 6:00 AM).")
                else:
                    st.error("Install failed — run scripts/install_weekly_backup.sh in Terminal.")
    with b3:
        db_path = Path(str(svc.path))
        if db_path.is_file() and db_path.stat().st_size > 0:
            st.download_button(
                "Download master DB",
                data=db_path.read_bytes(),
                file_name="master_pricebook.db",
                mime="application/x-sqlite3",
                use_container_width=True,
                help="Downloads the live SQLite file to this computer. Does not change the book. Gitignored — keep off GitHub.",
            )
        else:
            st.caption("No DB file to download.")
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
        if st.button(
            "Restore selected backup",
            type="secondary",
            help="Replaces the live price book with the selected snapshot. Check the box first. Current live book is backed up before restore.",
        ):
            if not confirm:
                st.warning("Check the confirmation box first.")
            else:
                idx = labels.index(pick)
                try:
                    live = restore_from(backups[idx], also_backup_current=True)
                    # Clear cached service so next load reopens DB connection state
                    get_service.clear()
                    st.success(f"Restored `{backups[idx].name}` → `{live.name}`. Reloading…")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Restore failed: {exc}")
    else:
        st.caption("No backups yet — click **Backup DB now**.")

    st.markdown("##### Maintenance")
    st.caption(
        "Duplicate scan verifies wood, size/description, and wholesale before "
        "anything can be deleted. One SKU × species is the catalog — not a "
        "duplicate. Queen vs Full sharing a part number is kept. Cleanup only "
        "removes verified copies of the same sellable row."
    )
    m1, m2, m3 = st.columns(3)
    with m1:
        if st.button(
            "Re-standardize master",
            help="Re-runs spelling, SKU, and human-description cleanup on every row. Does not delete rows or change prices.",
        ):
            report = svc.standardize_master()
            st.write(report)
            st.success("Standardize complete")
    with m2:
        if st.button(
            "Scan duplicates",
            help="Lists verified copy rows (same SKU, wood, size/description, wholesale). Does not delete anything.",
        ):
            dups = svc.find_duplicates(50)
            if dups.empty:
                st.success("No verified duplicate copies.")
            else:
                st.dataframe(dups, use_container_width=True)
    with m3:
        if st.button(
            "Dry-run cleanup",
            help="Shows how many verified duplicate copies would be removed if you execute. Makes no changes.",
        ):
            report = svc.cleanup_duplicates(dry_run=True)
            st.write(report)

    if st.button(
        "Execute cleanup (keep newest)",
        type="primary",
        help="Deletes verified duplicate copies and keeps the newest row. One SKU × wood is not a duplicate. Cannot undo except by restore.",
    ):
        report = svc.cleanup_duplicates(dry_run=False)
        st.success(report)
        st.rerun()

    st.markdown("##### Source files in master")
    sources = svc.list_source_files()
    if sources:
        src = st.selectbox("Source file", sources)
        if st.button(
            "Delete all rows from this source",
            help="Removes every catalog row that came from the selected Excel/PDF filename. Other builders stay. Restore a backup to undo.",
        ):
            n = svc.delete_by_source(src)
            st.warning(f"Removed {n:,} rows")
