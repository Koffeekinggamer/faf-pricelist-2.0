"""Disk-backed Drop-files parse cache (ADR-style seam for Streamlit disconnects).

Storing tens of thousands of parsed rows in ``st.session_state`` forces Streamlit
to re-pickle/shuttle that payload on every widget rerun (multiplier tweaks,
builder rename, Load). Behind Cloudflare tunnels or Fly proxies that often
surfaces as "Connection error" / disconnect mid Drop.

Cache the heavy ``rows`` lists on disk; keep only a path + light metadata in
session state.
"""

from __future__ import annotations

import hashlib
import pickle
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

_CACHE_DIRNAME = "faf_drop_parse_cache"


def cache_dir(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(tempfile.gettempdir()) / _CACHE_DIRNAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def sig_key(upload_sig: Any) -> str:
    raw = repr(upload_sig).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:32]


def cache_path(upload_sig: Any, *, root: Optional[Path] = None) -> Path:
    return cache_dir(root) / f"{sig_key(upload_sig)}.pkl"


def save_parsed(
    upload_sig: Any,
    parsed: list[dict],
    *,
    root: Optional[Path] = None,
) -> Path:
    path = cache_path(upload_sig, root=root)
    payload = {
        "saved_at": time.time(),
        "upload_sig": upload_sig,
        "parsed": parsed,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(path)
    return path


def load_parsed(
    upload_sig: Any,
    *,
    root: Optional[Path] = None,
    path: Optional[str | Path] = None,
) -> Optional[list[dict]]:
    p = Path(path) if path else cache_path(upload_sig, root=root)
    if not p.is_file():
        return None
    try:
        payload = pickle.loads(p.read_bytes())
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    parsed = payload.get("parsed")
    return parsed if isinstance(parsed, list) else None


def clear(
    upload_sig: Any | None = None,
    *,
    root: Optional[Path] = None,
    path: Optional[str | Path] = None,
) -> None:
    if path:
        Path(path).unlink(missing_ok=True)
        return
    if upload_sig is not None:
        cache_path(upload_sig, root=root).unlink(missing_ok=True)


def session_meta(path: Path, parsed: list[dict]) -> dict:
    """Light object safe to keep in st.session_state."""
    return {
        "path": str(path),
        "file_count": len(parsed),
        "total_rows": int(sum(int(p.get("row_count") or 0) for p in parsed)),
    }
