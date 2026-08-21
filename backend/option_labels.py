"""Stable Search Option widget keys.

Streamlit slugs punctuation away, so ``For 36"and 42" H`` and
``For 36"and 42" H.`` used to share one checkbox key and crash the floor.
The digest keeps one widget per exact catalog label. Do not merge labels
that only differ by punctuation — their charges can differ.
"""

from __future__ import annotations

import hashlib
import re


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "x"


def option_widget_key(vendor: str, option_label: str, *, kind: str = "cb") -> str:
    """Unique Streamlit key for one builder + exact Option label."""
    digest = hashlib.sha1((option_label or "").encode("utf-8")).hexdigest()[:8]
    return f"so_{kind}_{_slug(vendor)}_{_slug(option_label)}_{digest}"
