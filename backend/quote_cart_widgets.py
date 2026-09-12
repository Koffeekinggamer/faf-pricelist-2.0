"""Pure helpers for Quote Cart Streamlit widget identity.

County selectbox keys include a nonce so Clear can invalidate a stale browser
selection (Streamlit otherwise restores the prior county after DB tax is cleared).
"""

from __future__ import annotations

from typing import Any, MutableMapping


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
