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

from backend.upload_quality import rate_drop_parse

DEFAULT_TTL_SECONDS = 24 * 3600
SESSION_SCHEMA_VERSION = 2
_CACHE_DIRNAME = "faf_drop_parse_sessions"
_SAMPLE_SIZE = 8
# Widget type= filters by MIME; macOS often reports xlsx as zip/octet-stream
# and react-dropzone then rejects the drag. Accept first, filter here.
DROP_FILE_EXTS = {".xlsx", ".xls", ".xlsm", ".pdf"}


def is_drop_filename(name: str) -> bool:
    """True when this filename is an Excel/PDF price list we can parse."""
    return Path(name or "").suffix.lower() in DROP_FILE_EXTS


def drop_upload_from_path(path: str | Path) -> DropUpload | None:
    """Read a local Excel/PDF into a DropUpload. None if missing or wrong type."""
    p = Path(path).expanduser()
    if not p.is_file() or not is_drop_filename(p.name):
        return None
    data = p.read_bytes()
    return DropUpload(p.name, data, size=len(data))


class DropSessionGone(Exception):
    """Missing, corrupt, TTL-expired, or batch-mismatched session."""


@dataclass(frozen=True)
class DropReadiness:
    load_ready: bool
    block_code: str = ""
    block_message: str = ""


@dataclass(frozen=True)
class DropLockFields:
    importer: str = ""
    parser_source: str = ""
    locked_parser: str = ""
    layouts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DropLoadBinding:
    file_index: int
    builder: str
    multiplier: float


@dataclass(frozen=True)
class DropBuilderLoadResult:
    builder: str
    filename: str
    status: str
    multiplier: float
    catalog: dict
    parser_id: str = ""
    profile_saved: bool = False
    profile_warning: str = ""
    block_message: str = ""


@dataclass(frozen=True)
class DropLoadBatchResult:
    session_id: str
    results: tuple[DropBuilderLoadResult, ...]
    blocking_warnings: tuple[str, ...] = ()
    master_row_count: int = 0
    session_cleared: bool = False


@dataclass(frozen=True)
class DropFileOutcome:
    """Canonical serializable result for one file in a Drop parse session."""

    filename: str
    kind: str
    suggested_builder: str
    suggested_mult: float
    detected_markup: object
    rows: tuple[dict, ...]
    notes: str
    error: str
    variants: dict
    detected_importer: str
    parser_source: str
    priced_option_count: int
    readiness: DropReadiness
    lock_fields: DropLockFields

    @classmethod
    def from_payload(cls, payload: dict) -> "DropFileOutcome":
        return cls(
            filename=str(payload.get("filename") or ""),
            kind=str(payload.get("kind") or "excel"),
            suggested_builder=str(payload.get("suggested_builder") or payload.get("vendor") or ""),
            suggested_mult=float(payload.get("suggested_mult") or _default_mult()),
            detected_markup=payload.get("detected_markup"),
            rows=tuple(dict(row) for row in (payload.get("rows") or [])),
            notes=str(payload.get("notes") or ""),
            error=str(payload.get("error") or ""),
            variants=dict(payload.get("variants") or {}),
            detected_importer=str(payload.get("detected_importer") or ""),
            parser_source=str(payload.get("parser_source") or ""),
            priced_option_count=int(payload.get("priced_option_count") or 0),
            readiness=_readiness_from_payload(payload),
            lock_fields=_lock_fields_from_payload(payload),
        )

    def to_payload(self) -> dict:
        return {
            "filename": self.filename,
            "kind": self.kind,
            "suggested_builder": self.suggested_builder,
            "suggested_mult": self.suggested_mult,
            "detected_markup": self.detected_markup,
            "rows": [dict(row) for row in self.rows],
            "notes": self.notes,
            "error": self.error,
            "row_count": len(self.rows),
            "variants": dict(self.variants),
            "detected_importer": self.detected_importer,
            "parser_source": self.parser_source,
            "priced_option_count": self.priced_option_count,
            "locked_parser": self.lock_fields.locked_parser,
            "readiness": {
                "load_ready": self.readiness.load_ready,
                "block_code": self.readiness.block_code,
                "block_message": self.readiness.block_message,
            },
            "lock_fields": {
                "importer": self.lock_fields.importer,
                "parser_source": self.lock_fields.parser_source,
                "locked_parser": self.lock_fields.locked_parser,
                "layouts": list(self.lock_fields.layouts),
            },
        }


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
    variants: dict = None
    detected_importer: str = ""
    parser_source: str = ""
    readiness: DropReadiness = DropReadiness(True)
    lock_fields: DropLockFields = DropLockFields()
    quality_percent: int = 0
    quality_deductions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DropParseSessionView:
    session_id: str
    files: tuple[DropFilePreview, ...]
    total_rows: int = 0

    @property
    def load_ready_indexes(self) -> tuple[int, ...]:
        return tuple(f.file_index for f in self.files if f.readiness.load_ready)


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
    detected_importer: str = ""
    parser_source: str = ""
    readiness: DropReadiness = DropReadiness(True)
    lock_fields: DropLockFields = DropLockFields()


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


def evaluate_readiness(file_payload: dict) -> DropReadiness:
    """Authoritative per-file Load gate; Christina observes the same facts."""
    error = str(file_payload.get("error") or "").strip()
    rows = list(file_payload.get("rows") or [])
    if error:
        return DropReadiness(False, "parse_error", error)
    if not rows:
        return DropReadiness(False, "zero_rows", "0 rows parsed")

    priced_options = int(file_payload.get("priced_option_count") or 0)
    addon_count = sum(
        1 for row in rows if str(row.get("line_kind") or "item").strip().lower() == "addon"
    )
    if priced_options and addon_count == 0:
        return DropReadiness(
            False,
            "options_missing",
            f"{priced_options} priced option lines found but 0 addon rows parsed",
        )

    items = [row for row in rows if str(row.get("line_kind") or "item").strip().lower() != "addon"]
    expected_finish_states = {
        str(state or "").strip().lower()
        for state in (file_payload.get("expected_finish_states") or [])
        if str(state or "").strip()
    }
    actual_finish_states = {
        str(row.get("finish_state") or "").strip().lower()
        for row in items
        if str(row.get("finish_state") or "").strip()
    }
    option_labels = {
        str(row.get("option_key") or "").strip().lower()
        for row in rows
        if str(row.get("line_kind") or "item").strip().lower() == "addon"
    }
    for state in sorted(expected_finish_states):
        represented = state in actual_finish_states or (
            state == "unfinished" and "unfinished" in option_labels
        )
        if not represented:
            return DropReadiness(
                False,
                "finish_state_missing",
                f"Source promises {state} pricing but no {state} rows or Option parsed",
            )

    missing = sum(1 for row in items if not str(row.get("species") or "").strip())
    if items and missing / len(items) >= 0.5:
        return DropReadiness(
            False,
            "species_quality",
            f"{missing}/{len(items)} sellable rows missing species",
        )

    locked = str(file_payload.get("locked_parser") or "").strip().lower()
    detected = str(file_payload.get("detected_importer") or "").strip().lower()
    if locked and locked not in {"generic", "pdf"} and detected != locked:
        return DropReadiness(
            False,
            "settled_reader_miss",
            f"{locked} did not read this book (fell through to {detected or 'nothing'})",
        )
    return DropReadiness(True)


def _readiness_from_payload(file_payload: dict) -> DropReadiness:
    raw = file_payload.get("readiness")
    if isinstance(raw, DropReadiness):
        return raw
    if isinstance(raw, dict):
        return DropReadiness(
            bool(raw.get("load_ready")),
            str(raw.get("block_code") or ""),
            str(raw.get("block_message") or ""),
        )
    return evaluate_readiness(file_payload)


def _lock_fields_from_payload(file_payload: dict) -> DropLockFields:
    raw = file_payload.get("lock_fields")
    if isinstance(raw, DropLockFields):
        return raw
    if isinstance(raw, dict):
        return DropLockFields(
            importer=str(raw.get("importer") or ""),
            parser_source=str(raw.get("parser_source") or ""),
            locked_parser=str(raw.get("locked_parser") or ""),
            layouts=tuple(str(x) for x in (raw.get("layouts") or ()) if x),
        )
    variants = file_payload.get("variants") or {}
    return DropLockFields(
        importer=str(file_payload.get("detected_importer") or ""),
        parser_source=str(file_payload.get("parser_source") or ""),
        locked_parser=str(file_payload.get("locked_parser") or ""),
        layouts=tuple(str(x) for x in (variants.get("layouts") or ()) if x),
    )


def view_from_payload(payload: dict) -> DropParseSessionView:
    files_out: list[DropFilePreview] = []
    for i, f in enumerate(payload.get("files") or []):
        rows = list(f.get("rows") or [])
        sample = tuple(dict(r) for r in rows[:_SAMPLE_SIZE])
        quality = rate_drop_parse(f)
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
                variants=dict(f.get("variants") or {}),
                detected_importer=str(f.get("detected_importer") or ""),
                parser_source=str(f.get("parser_source") or ""),
                readiness=_readiness_from_payload(f),
                lock_fields=_lock_fields_from_payload(f),
                quality_percent=int(quality.percent),
                quality_deductions=tuple(quality.deductions),
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
                detected_importer=str(f.get("detected_importer") or ""),
                parser_source=str(f.get("parser_source") or ""),
                readiness=_readiness_from_payload(f),
                lock_fields=_lock_fields_from_payload(f),
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
        payload = dict(payload)
        payload["schema_version"] = SESSION_SCHEMA_VERSION
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
        if not isinstance(payload, dict):
            return None
        if int(payload.get("schema_version") or 0) != SESSION_SCHEMA_VERSION:
            return None
        return payload

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
        if int(payload.get("schema_version") or 0) != SESSION_SCHEMA_VERSION:
            return False
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
            if int(payload.get("schema_version") or 0) != SESSION_SCHEMA_VERSION:
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
