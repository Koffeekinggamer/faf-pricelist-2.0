"""
FAF Price Book multi-user accounts.

Users can be:
  - local (created in Admin)
  - ordertrac (synced from OrderTrac sales-user list)

Passwords are stored as sha256 hex (same scheme as legacy auth).
Roles: admin | sales | floor
"""

from __future__ import annotations

import hashlib
import re
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from backend.db import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    return hash_password(password) == password_hash.lower()


def slug_username(display_name: str, email: str = "") -> str:
    """Build a login username from OT display name or email."""
    if email and "@" in email:
        local = email.split("@", 1)[0].strip().lower()
        local = re.sub(r"[^a-z0-9._-]+", "", local)
        if local:
            return local
    # "Miller, Judson" → judson.miller
    name = (display_name or "").strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        parts = [first, last]
    else:
        parts = name.split()
    parts = [re.sub(r"[^a-z0-9]+", "", p.lower()) for p in parts if p]
    parts = [p for p in parts if p]
    if not parts:
        return "user"
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}"
    return parts[0]


def temp_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserRepository:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    def count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0])

    def list_users(self, *, active_only: bool = False) -> pd.DataFrame:
        q = """
            SELECT id, username, display_name, email, role, active,
                   must_change_password, ordertrac_user_guid, ordertrac_display_name,
                   source, last_login_at, created_at, updated_at
            FROM app_users
        """
        if active_only:
            q += " WHERE active = 1"
        q += " ORDER BY display_name COLLATE NOCASE, username COLLATE NOCASE"
        with self._conn() as conn:
            return pd.read_sql_query(q, conn)

    def get_by_username(self, username: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE lower(username) = lower(?)",
                (username.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def get_by_id(self, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str = "",
        email: str = "",
        role: str = "sales",
        source: str = "local",
        ordertrac_user_guid: str = "",
        ordertrac_display_name: str = "",
        must_change_password: bool = True,
        active: bool = True,
    ) -> int:
        username = username.strip()
        if not username:
            raise ValueError("username required")
        if role not in ("admin", "sales", "floor"):
            role = "sales"
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO app_users (
                    username, display_name, email, password_hash, role, active,
                    must_change_password, ordertrac_user_guid, ordertrac_display_name,
                    source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    display_name or username,
                    email or None,
                    hash_password(password),
                    role,
                    1 if active else 0,
                    1 if must_change_password else 0,
                    ordertrac_user_guid or None,
                    ordertrac_display_name or None,
                    source,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_user(self, user_id: int, **fields) -> None:
        allowed = {
            "display_name",
            "email",
            "role",
            "active",
            "must_change_password",
            "ordertrac_user_guid",
            "ordertrac_display_name",
            "source",
            "last_login_at",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "active":
                v = 1 if v else 0
            if k == "must_change_password":
                v = 1 if v else 0
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        sets.append("updated_at = ?")
        vals.append(_now())
        vals.append(user_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE app_users SET {', '.join(sets)} WHERE id = ?", vals
            )
            conn.commit()

    def set_password(
        self, user_id: int, password: str, *, must_change: bool = False
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE app_users
                SET password_hash = ?, must_change_password = ?, updated_at = ?
                WHERE id = ?
                """,
                (hash_password(password), 1 if must_change else 0, _now(), user_id),
            )
            conn.commit()

    def record_login(self, user_id: int) -> None:
        self.update_user(user_id, last_login_at=_now())

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        user = self.get_by_username(username)
        if not user:
            return None
        if not user.get("active"):
            return None
        if not verify_password(password, user.get("password_hash") or ""):
            return None
        self.record_login(int(user["id"]))
        # refresh without password_hash for session
        safe = {k: v for k, v in user.items() if k != "password_hash"}
        safe["last_login_at"] = _now()
        return safe

    def ensure_admin_seed(
        self,
        username: str = "Foothills",
        password: str = "Amish",
    ) -> Optional[int]:
        """Create default admin if no users exist."""
        if self.count() > 0:
            return None
        return self.create_user(
            username=username,
            password=password,
            display_name="Foothills Admin",
            role="admin",
            source="seed",
            must_change_password=False,
        )

    def upsert_from_ordertrac(
        self,
        *,
        display_name: str,
        ordertrac_user_guid: str,
        email: str = "",
        role: str = "sales",
        default_password: Optional[str] = None,
    ) -> dict:
        """
        Create or update a FAF user from an OrderTrac sales user.
        Returns {action, user_id, username, temp_password?}.
        """
        display_name = (display_name or "").strip()
        guid = (ordertrac_user_guid or "").strip()
        if not display_name and not guid:
            raise ValueError("display_name or guid required")

        with self._conn() as conn:
            existing = None
            if guid:
                existing = conn.execute(
                    "SELECT * FROM app_users WHERE ordertrac_user_guid = ?",
                    (guid,),
                ).fetchone()
            if not existing and display_name:
                existing = conn.execute(
                    """
                    SELECT * FROM app_users
                    WHERE lower(ordertrac_display_name) = lower(?)
                       OR lower(display_name) = lower(?)
                    """,
                    (display_name, display_name),
                ).fetchone()

        if existing:
            existing = dict(existing)
            # Don't demote an existing admin via OT sync unless they're still admin in OT
            new_role = role
            if (existing.get("role") == "admin") and role != "admin":
                new_role = "admin"
            self.update_user(
                int(existing["id"]),
                display_name=display_name or existing.get("display_name"),
                email=email or existing.get("email") or "",
                ordertrac_user_guid=guid or existing.get("ordertrac_user_guid") or "",
                ordertrac_display_name=display_name,
                source="ordertrac",
                role=new_role,
                active=True,
            )
            return {
                "action": "updated",
                "user_id": int(existing["id"]),
                "username": existing["username"],
                "role": new_role,
            }

        base = slug_username(display_name, email)
        username = base
        n = 2
        while self.get_by_username(username):
            username = f"{base}{n}"
            n += 1

        pw = default_password or temp_password(10)
        uid = self.create_user(
            username=username,
            password=pw,
            display_name=display_name or username,
            email=email,
            role=role,
            source="ordertrac",
            ordertrac_user_guid=guid,
            ordertrac_display_name=display_name,
            must_change_password=True,
        )
        return {
            "action": "created",
            "user_id": uid,
            "username": username,
            "temp_password": pw,
        }

    # ----- integration metadata -----
    def set_integration(
        self,
        key: str,
        *,
        status: str,
        last_error: str = "",
        meta: Optional[dict] = None,
        ok: bool = False,
    ) -> None:
        import json

        now = _now()
        meta_json = json.dumps(meta or {})
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO integrations (key, status, last_ok_at, last_error, meta_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    status = excluded.status,
                    last_ok_at = CASE WHEN ? THEN excluded.last_ok_at ELSE integrations.last_ok_at END,
                    last_error = excluded.last_error,
                    meta_json = excluded.meta_json,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    status,
                    now if ok else None,
                    last_error or None,
                    meta_json,
                    now,
                    1 if ok else 0,
                ),
            )
            # Fix last_ok_at on success when row existed with null from insert branch
            if ok:
                conn.execute(
                    "UPDATE integrations SET last_ok_at = ? WHERE key = ?",
                    (now, key),
                )
            conn.commit()

    def get_integration(self, key: str) -> Optional[dict]:
        import json

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM integrations WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["meta"] = json.loads(d.get("meta_json") or "{}")
            except Exception:
                d["meta"] = {}
            return d
