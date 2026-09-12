"""Append-only activity log. Actor always comes from the session."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from backend.app_db import get_app_connection, init_app_db

logger = logging.getLogger(__name__)

METADATA_MAX_BYTES = 4096
CLIENT_ERROR_BODY_CAP = 2000

SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|hash|authorization|cookie|token|database_url|"
    r"admin_password|session_secret|nextauth_secret|connection_string|api_key)",
    re.I,
)
CONN_RE = re.compile(
    r"(postgres(ql)?|mysql|mongodb|sqlite|redis)://\S+",
    re.I,
)

ACTION_GROUPS: dict[str, tuple[str, ...]] = {
    "Auth": (
        "auth.login.success",
        "auth.login.failure",
        "auth.logout",
        "auth.lockout",
        "auth.password.change",
        "auth.password.reset.request",
        "auth.invite.accept",
        "auth.session.denied",
    ),
    "Quotes": (
        "quote.create",
        "quote.update",
        "quote.delete",
        "quote.line.add",
        "quote.line.remove",
        "quote.line.qty",
        "quote.line.reset",
        "quote.clear",
        "quote.view.denied",
    ),
    "Tax": ("quote.tax.select", "quote.tax.exempt"),
    "Users": (
        "user.create",
        "user.role.change",
        "user.disable",
        "user.enable",
        "user.password.reset.admin",
    ),
    "Permissions": ("permission.denied",),
    "System": ("system.error", "system.client_error"),
}

PROBLEM_STATUSES = frozenset({"failure", "denied", "error"})


@dataclass(frozen=True)
class ActivityEvent:
    id: int
    created_at: str
    actor_id: int | None
    actor_email: str | None
    actor_role: str | None
    action: str
    status: str
    resource_type: str | None
    resource_id: str | None
    summary: str
    metadata: dict[str, object]
    ip: str | None
    user_agent: str | None
    path: str | None
    error_message: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _token_tail(value: object) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return f"…{text}"
    return f"…{text[-4:]}"


def sanitize_text(value: str) -> str:
    cleaned = CONN_RE.sub("[redacted]", value)
    return cleaned[:CLIENT_ERROR_BODY_CAP]


def sanitize_metadata(raw: Mapping[str, object] | None) -> dict[str, object]:
    clean: dict[str, object] = {}
    if not raw:
        return clean
    for key, value in raw.items():
        name = str(key)
        if SECRET_KEY_RE.search(name) and "token" not in name.lower():
            continue
        if "token" in name.lower():
            clean[name] = _token_tail(value)
            continue
        if isinstance(value, str):
            text = sanitize_text(value)
            if SECRET_KEY_RE.search(name):
                continue
            clean[name] = text
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[name] = value
        else:
            clean[name] = sanitize_text(str(value))
    encoded = json.dumps(clean, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > METADATA_MAX_BYTES:
        return {"truncated": True, "preview": encoded[:400]}
    return clean


def human_action_label(action: str) -> str:
    return action.replace(".", " ").replace("_", " ").strip().capitalize()


def export_activity_csv(events: list[ActivityEvent], *, cap: int = 5000) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "created_at",
            "actor_email",
            "actor_role",
            "action",
            "status",
            "summary",
            "resource_type",
            "resource_id",
        ]
    )
    for event in events[:cap]:
        writer.writerow(
            [
                event.created_at,
                event.actor_email or "",
                event.actor_role or "",
                event.action,
                event.status,
                event.summary,
                event.resource_type or "",
                event.resource_id or "",
            ]
        )
    return buf.getvalue()


class ActivityStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        init_app_db(self.db_path)

    def log_activity(
        self,
        actor: object | None,
        *,
        action: str,
        status: str = "success",
        resource_type: str | None = None,
        resource_id: str | None = None,
        summary: str = "",
        metadata: Mapping[str, object] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Never trust actorId from the client — pass the session user."""
        try:
            actor_id: int | None = None
            actor_email: str | None = None
            actor_role: str | None = None
            if isinstance(actor, Mapping):
                raw_id = actor.get("id") or actor.get("user_id")
                actor_id = int(raw_id) if raw_id is not None else None
                actor_email = str(actor.get("email") or "") or None
                actor_role = str(actor.get("role") or "") or None
            elif actor is not None and hasattr(actor, "id"):
                raw_id = getattr(actor, "id", None)
                actor_id = int(raw_id) if raw_id is not None else None
                actor_email = str(getattr(actor, "email", "") or "") or None
                actor_role = str(getattr(actor, "role", "") or "") or None
            meta = sanitize_metadata(metadata)
            with get_app_connection(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO activity_log (
                        created_at, actor_id, actor_email, actor_role, action, status,
                        resource_type, resource_id, summary, metadata, ip, user_agent,
                        path, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _now(),
                        actor_id,
                        actor_email,
                        actor_role,
                        action,
                        status,
                        resource_type,
                        str(resource_id) if resource_id is not None else None,
                        summary,
                        json.dumps(meta),
                        ip,
                        user_agent,
                        path,
                        sanitize_text(error_message) if error_message else None,
                    ),
                )
                conn.commit()
        except Exception:
            logger.exception("activity log write failed; user action continues")

    def list_events(
        self,
        *,
        actor_id: int | None = None,
        actor_email_contains: str = "",
        unknown_only: bool = False,
        action_group: str = "",
        status: str = "",
        resource_id: str = "",
        problems_only: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[ActivityEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if unknown_only:
            clauses.append("actor_id IS NULL")
        if actor_email_contains:
            clauses.append("lower(actor_email) LIKE ?")
            params.append(f"%{actor_email_contains.strip().lower()}%")
        if action_group and action_group in ACTION_GROUPS:
            marks = ",".join("?" for _ in ACTION_GROUPS[action_group])
            clauses.append(f"action IN ({marks})")
            params.extend(ACTION_GROUPS[action_group])
        if status:
            clauses.append("status = ?")
            params.append(status)
        if problems_only:
            clauses.append("status IN ('failure','denied','error')")
        if resource_id:
            clauses.append("resource_id = ?")
            params.append(str(resource_id))
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.astimezone(timezone.utc).isoformat(timespec="seconds"))
        if until is not None:
            clauses.append("created_at <= ?")
            params.append(until.astimezone(timezone.utc).isoformat(timespec="seconds"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM activity_log
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        """
        params.append(max(1, min(int(limit), 5000)))
        with get_app_connection(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        events: list[ActivityEvent] = []
        for row in rows:
            try:
                meta = json.loads(row["metadata"] or "{}")
            except json.JSONDecodeError:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            events.append(
                ActivityEvent(
                    id=int(row["id"]),
                    created_at=str(row["created_at"]),
                    actor_id=int(row["actor_id"]) if row["actor_id"] is not None else None,
                    actor_email=row["actor_email"],
                    actor_role=row["actor_role"],
                    action=str(row["action"]),
                    status=str(row["status"]),
                    resource_type=row["resource_type"],
                    resource_id=row["resource_id"],
                    summary=str(row["summary"] or ""),
                    metadata=meta,
                    ip=row["ip"],
                    user_agent=row["user_agent"],
                    path=row["path"],
                    error_message=row["error_message"],
                )
            )
        return events

    def report_client_error(
        self,
        actor: object | None,
        *,
        message: str,
        path: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.log_activity(
            actor,
            action="system.client_error",
            status="error",
            resource_type="system",
            summary=sanitize_text(message)[:200],
            metadata=metadata,
            path=path,
            error_message=sanitize_text(message),
        )


def date_preset_bounds(preset: str, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    start = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    if preset == "7":
        start = start - timedelta(days=6)
    elif preset == "30":
        start = start - timedelta(days=29)
    return start, stamp
