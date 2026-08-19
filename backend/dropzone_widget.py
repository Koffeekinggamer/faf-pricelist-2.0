"""HTML5 Drop zone — files go to Python without Streamlit's file_uploader."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import streamlit.components.v1 as components

from backend.drop_parse_session import DropUpload, is_drop_filename

_DIR = Path(__file__).resolve().parent.parent / "frontend" / "faf_dropzone"
_dropzone = components.declare_component("faf_dropzone", path=str(_DIR))


def render_dropzone(*, key: str = "faf_dropzone") -> Optional[DropUpload]:
    """Show the drop target. Returns a DropUpload when a file lands."""
    payload = _dropzone(key=key, default=None)
    return drop_upload_from_payload(payload)


def drop_upload_from_payload(payload) -> Optional[DropUpload]:
    """Decode the component JSON {name, data_b64, size} into a DropUpload."""
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or "").strip()
    raw_b64 = payload.get("data_b64") or ""
    if not name or not raw_b64 or not is_drop_filename(name):
        return None
    try:
        data = base64.b64decode(raw_b64, validate=False)
    except (ValueError, TypeError):
        return None
    if not data:
        return None
    return DropUpload(name, data, size=len(data))
