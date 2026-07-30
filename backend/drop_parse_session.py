"""Drop parse session — parse-once batch cache behind an opaque session id.

See CONTEXT.md **Drop parse session**. Commit / fingerprint / add_rows stay outside.
"""

from __future__ import annotations

import hashlib
import pickle
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

DEFAULT_TTL_SECONDS = 24 * 3600
_CACHE_DIRNAME = "faf_drop_parse_sessions"
_SAMPLE_SIZE = 8


class DropSessionGone(Exception):
    """Missing, corrupt, TTL-expired, or batch-mismatched session."""


@dataclass(frozen=True)
class DropUpload:
    filename: str
    data: bytes
    size: int | None = None

    def identity(self) -> tuple[str, int]:
        return (self.filename, int(self.size if self.size is not None else len(self.data)))


@dataclass(frozen=True)
class DropFilePreview:
    file_index: int
    filename: str
    kind: str
    suggested_builder: str
    suggested_mult: float
    detected_markup: float | None
    row_count: int
    sample: tuple[dict, ...]
    error: str
    notes: str


@dataclass(frozen=True)
class DropParseSessionView:
    session_id: str
    files: tuple[DropFilePreview, ...]
    total_rows: int = 0


@dataclass(frozen=True)
class DropFileWholesale:
    file_index: int
    filename: str
    suggested_builder: str
    suggested_mult: float
    detected_markup: float | None
    rows: list[dict]
    error: str
    row_count: int


def batch_key(
    uploads: Sequence[DropUpload],
    *,
    prefer_workbook_markup: bool,
) -> str:
    ident = (tuple(u.identity() for u in uploads), bool(prefer_workbook_markup))
    raw = repr(ident).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:32]


def wholesale_row(src: dict) -> dict:
    """Strip authoritative retail/mult bind; keep post-Standardize wholesale."""
    r = dict(src)
    r.pop("adjusted_price", None)
    # Keep multiplier if present as hint only — commit rebinds. Prefer clear.
    r.pop("multiplier", None)
    return r


# Back-compat alias for early call sites / tests
_wholesale_row = wholesale_row


def view_from_payload(payload: dict) -> DropParseSessionView:
    files_out: list[DropFilePreview] = []
    for i, f in enumerate(payload.get("files") or []):
        rows = list(f.get("rows") or [])
        sample = tuple(dict(r) for r in rows[:_SAMPLE_SIZE])
        files_out.append(
            DropFilePreview(
                file_index=i,
                filename=str(f.get("filename") or ""),
                kind=str(f.get("kind") or "excel"),
                suggested_builder=str(f.get("suggested_builder") or ""),
                suggested_mult=float(f.get("suggested_mult") or _default_mult()),
                detected_markup=f.get("detected_markup"),
                row_count=int(f.get("row_count") or len(rows)),
                sample=sample,
                error=str(f.get("error") or ""),
                notes=str(f.get("notes") or ""),
            )
        )
    return DropParseSessionView(
        session_id=str(payload.get("session_id") or ""),
        files=tuple(files_out),
        total_rows=int(sum(f.row_count for f in files_out)),
    )


def _default_mult() -> float:
    try:
        from backend.config import DEFAULT_MULTIPLIER

        return float(DEFAULT_MULTIPLIER)
    except Exception:
        return 2.7


def wholesale_from_payload(payload: dict) -> list[DropFileWholesale]:
    out: list[DropFileWholesale] = []
    for i, f in enumerate(payload.get("files") or []):
        rows = [dict(r) for r in (f.get("rows") or [])]
        out.append(
            DropFileWholesale(
                file_index=i,
                filename=str(f.get("filename") or ""),
                suggested_builder=str(f.get("suggested_builder") or ""),
                suggested_mult=float(f.get("suggested_mult") or _default_mult()),
                detected_markup=f.get("detected_markup"),
                rows=rows,
                error=str(f.get("error") or ""),
                row_count=int(f.get("row_count") or len(rows)),
            )
        )
    return out


class DiskDropParseStore:
    """Local-substitutable session store (disk pickle; injectable root)."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else Path(tempfile.gettempdir()) / _CACHE_DIRNAME
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
        return self.root / f"{safe}.pkl"

    def save(self, session_id: str, payload: dict) -> Path:
        path = self.path_for(session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(path)
        return path

    def load(self, session_id: str) -> Optional[dict]:
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        try:
            payload = pickle.loads(path.read_bytes())
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def delete(self, session_id: str) -> None:
        self.path_for(session_id).unlink(missing_ok=True)

    def is_fresh(
        self,
        payload: dict,
        *,
        batch: str,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        now: Optional[float] = None,
    ) -> bool:
        if payload.get("batch_key") != batch:
            return False
        saved = float(payload.get("saved_at") or 0)
        t = time.time() if now is None else now
        if t - saved > ttl_seconds:
            return False
        return True

    def purge_expired(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> int:
        now = time.time()
        n = 0
        for p in self.root.glob("*.pkl"):
            try:
                payload = pickle.loads(p.read_bytes())
            except Exception:
                p.unlink(missing_ok=True)
                n += 1
                continue
            if not isinstance(payload, dict):
                p.unlink(missing_ok=True)
                n += 1
                continue
            saved = float(payload.get("saved_at") or 0)
            if now - saved > ttl_seconds:
                p.unlink(missing_ok=True)
                n += 1
        return n


def new_session_id() -> str:
    return "dps_" + uuid.uuid4().hex[:24]
