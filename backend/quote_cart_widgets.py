"""Pure helpers for Quote Cart Streamlit widget identity.

County selectbox keys include a nonce so Clear can invalidate a stale browser
selection (Streamlit otherwise restores the prior county after DB tax is cleared).

Qty/notes widgets keep values in session_state by key. After Add merges quantity
in SQLite, those keys can still hold the pre-merge qty; the sidebar write-back
path would then overwrite the DB. Mark dirty + clear so widgets rehydrate from DB.
"""

from __future__ import annotations

from typing import Any, MutableMapping

QUOTE_CART_REFRESH_KEY = "_quote_cart_refresh"


def quote_county_widget_key(quote_id: int, session: MutableMapping[str, Any]) -> str:
    nonce = int(session.get(f"cart_county_nonce_{quote_id}", 0) or 0)
    return f"cart_county_{quote_id}_{nonce}"


def bump_quote_county_widget(quote_id: int, session: MutableMapping[str, Any]) -> str:
    """Rotate county selectbox identity and drop prior county widget values."""
    nonce_key = f"cart_county_nonce_{quote_id}"
    session[nonce_key] = int(session.get(nonce_key, 0) or 0) + 1
    prefix = f"cart_county_{quote_id}"
    for key in list(session):
        if key == nonce_key:
            continue
        if key == prefix or str(key).startswith(prefix + "_"):
            session.pop(key, None)
    return quote_county_widget_key(quote_id, session)


def mark_quote_cart_widgets_dirty(session: MutableMapping[str, Any]) -> None:
    """Force next sidebar render to drop qty/notes keys and rehydrate from DB."""
    session[QUOTE_CART_REFRESH_KEY] = True


def clear_quote_cart_line_widgets(
    session: MutableMapping[str, Any], quote_id: int
) -> None:
    """Drop cart widget keys for a quote so Streamlit re-inits from DB values."""
    prefixes = (
        f"cart_name_{quote_id}",
        f"cart_client_{quote_id}",
        f"cart_county_{quote_id}",
        f"cart_exempt_{quote_id}",
        f"cart_qty_{quote_id}_",
        f"cart_notes_{quote_id}_",
    )
    nonce_key = f"cart_county_nonce_{quote_id}"
    for key in list(session):
        if key == nonce_key:
            continue
        if str(key).startswith(prefixes):
            session.pop(key, None)
