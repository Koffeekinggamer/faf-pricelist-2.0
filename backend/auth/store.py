"""User persistence and login — email is the only identifier."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.activity.log_activity import ActivityStore
from backend.app_db import get_app_connection, init_app_db
from backend.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    is_valid_email,
    normalize_email,
    verify_password,
)
from backend.auth.permissions import AuthDenied, require
from backend.auth.roles import Role, SessionUser, email_local_part, parse_role

LOCK_AFTER = 8
WINDOW_MINUTES = 15
LOCK_MINUTES = 15
INVITE_HOURS = 24
RESET_MESSAGE = "If that email is in the system, you’ll get a link."
DISABLED_MESSAGE = "This account is disabled. Contact an admin."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(stamp: datetime | None = None) -> str:
    return (stamp or _now()).isoformat(timespec="seconds")


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_user(row: object) -> SessionUser:
    data = dict(row)  # sqlite3.Row
    return SessionUser(
        id=int(data["id"]),
        email=str(data["email"]),
        name=str(data["name"] or email_local_part(str(data["email"]))),
        role=parse_role(data["role"]),
        active=bool(data["active"]),
        must_change_password=bool(data.get("must_change_password")),
    )


@dataclass
class InviteResult:
    email: str
    role: Role
    temp_password: str | None
    invite_token: str | None
    token_last4: str


class AuthStore:
    def __init__(self, db_path: Path, activity: ActivityStore | None = None) -> None:
        self.db_path = Path(db_path)
        init_app_db(self.db_path)
        self.activity = activity if activity is not None else ActivityStore(self.db_path)

    def count(self) -> int:
        with get_app_connection(self.db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def admin_count(self, *, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        if active_only:
            sql += " AND active = 1"
        with get_app_connection(self.db_path) as conn:
            return int(conn.execute(sql).fetchone()[0])

    def is_last_admin(self, user_id: int) -> bool:
        user = self.get_by_id(user_id)
        if user is None or user.role != "admin" or not user.active:
            return False
        return self.admin_count(active_only=True) <= 1

    def get_by_id(self, user_id: int) -> SessionUser | None:
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_user(row) if row else None

    def get_by_email(self, email: str) -> SessionUser | None:
        needle = normalize_email(email)
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (needle,)).fetchone()
        return _row_user(row) if row else None

    def list_users(self) -> list[SessionUser]:
        with get_app_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY name COLLATE NOCASE, email COLLATE NOCASE"
            ).fetchall()
        return [_row_user(r) for r in rows]

    def list_user_rows(self) -> list[dict[str, object]]:
        with get_app_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, email, name, role, active, last_login_at, created_at
                FROM users
                ORDER BY name COLLATE NOCASE, email COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_user(
        self,
        *,
        email: str,
        password: str,
        role: Role = "admin",
        name: str = "",
        created_by: int | None = None,
        must_change_password: bool = False,
        allow_short_password: bool = False,
    ) -> SessionUser:
        addr = normalize_email(email)
        if not is_valid_email(addr):
            raise AuthDenied("Enter a valid email address.", reason="invalid_email")
        now = _iso()
        hashed = hash_password(password, allow_short=allow_short_password)
        with get_app_connection(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    email, name, role, active, password_hash, created_at, updated_at,
                    created_by, must_change_password
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    addr,
                    name or email_local_part(addr),
                    role,
                    hashed,
                    now,
                    now,
                    created_by,
                    1 if must_change_password else 0,
                ),
            )
            conn.commit()
            uid = int(cur.lastrowid)
        user = self.get_by_id(uid)
        if user is None:
            raise AuthDenied("Could not create user.", reason="error")
        return user

    def create_user(
        self,
        *,
        actor: SessionUser,
        email: str,
        role: Role = "sales",
        password: str | None = None,
        name: str = "",
    ) -> SessionUser:
        require(actor, "users.manage")
        addr = normalize_email(email)
        if not is_valid_email(addr):
            raise AuthDenied("Enter a valid email address.", reason="invalid_email")
        if self.get_by_email(addr):
            raise AuthDenied("That email is already in use.", reason="duplicate")
        parsed = parse_role(role)
        if not password:
            invite = self.create_invite(actor=actor, email=addr, role=parsed, name=name)
            raise AuthDenied(
                f"Invite created for {addr} (token last4 {invite.token_last4}).",
                reason="invite",
            )
        user = self.insert_user(
            email=addr,
            password=password,
            role=parsed,
            name=name,
            created_by=actor.id,
            allow_short_password=True,
        )
        self.activity.log_activity(
            actor,
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            summary=f"Created {user.email} as {user.role}",
        )
        return user

    def create_invite(
        self,
        *,
        actor: SessionUser,
        email: str,
        role: Role = "sales",
        name: str = "",
    ) -> InviteResult:
        require(actor, "users.manage")
        addr = normalize_email(email)
        if not is_valid_email(addr):
            raise AuthDenied("Enter a valid email address.", reason="invalid_email")
        if self.get_by_email(addr):
            raise AuthDenied("That email is already in use.", reason="duplicate")
        token = secrets.token_urlsafe(32)
        last4 = token[-4:]
        expires = _iso(_now() + timedelta(hours=INVITE_HOURS))
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO invites (
                    email, name, role, token_hash, token_last4, expires_at, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    addr,
                    name or email_local_part(addr),
                    role,
                    _token_hash(token),
                    last4,
                    expires,
                    actor.id,
                    _iso(),
                ),
            )
            conn.commit()
        self.activity.log_activity(
            actor,
            action="user.create",
            resource_type="user",
            summary=f"Invited {addr} as {role}",
            metadata={"invite_token": last4},
        )
        return InviteResult(
            email=addr, role=role, temp_password=None, invite_token=token, token_last4=last4
        )

    def accept_invite(self, token: str, password: str, name: str = "") -> SessionUser:
        hashed = _token_hash(token)
        with get_app_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM invites WHERE token_hash = ? AND accepted_at IS NULL",
                (hashed,),
            ).fetchone()
        if not row:
            raise AuthDenied("Invite is invalid or expired.", reason="invite")
        expires = _parse_dt(row["expires_at"])
        if expires is None or expires < _now():
            raise AuthDenied("Invite is invalid or expired.", reason="invite")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AuthDenied(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                reason="password",
            )
        user = self.insert_user(
            email=str(row["email"]),
            password=password,
            role=parse_role(row["role"]),
            name=name or str(row["name"] or ""),
            created_by=int(row["created_by"]) if row["created_by"] is not None else None,
        )
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE invites SET accepted_at = ? WHERE id = ?",
                (_iso(), int(row["id"])),
            )
            conn.commit()
        self.activity.log_activity(
            user,
            action="auth.invite.accept",
            resource_type="user",
            resource_id=str(user.id),
            summary=f"{user.email} accepted invite",
        )
        return user

    def authenticate(self, email: str, password: str) -> SessionUser:
        addr = normalize_email(email)
        if not is_valid_email(addr):
            self.activity.log_activity(
                None,
                action="auth.login.failure",
                status="failure",
                resource_type="auth",
                summary="invalid email",
                metadata={"reason": "invalid_email"},
            )
            raise AuthDenied("Enter a valid email address.", reason="invalid_email")
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (addr,)).fetchone()
        if row is None:
            self.activity.log_activity(
                None,
                action="auth.login.failure",
                status="failure",
                resource_type="auth",
                summary="unknown email",
                metadata={"reason": "bad_password"},
            )
            raise AuthDenied("Incorrect email or password.", reason="bad_password")
        user = _row_user(row)
        if not user.active:
            self.activity.log_activity(
                user,
                action="auth.login.failure",
                status="failure",
                resource_type="auth",
                summary=DISABLED_MESSAGE,
                metadata={"reason": "inactive"},
            )
            raise AuthDenied(DISABLED_MESSAGE, status_code=401, reason="inactive")
        locked_until = _parse_dt(row["locked_until"])
        if locked_until and locked_until > _now():
            self.activity.log_activity(
                user,
                action="auth.login.failure",
                status="failure",
                resource_type="auth",
                summary="account locked",
                metadata={"reason": "locked"},
            )
            raise AuthDenied(
                "This account is locked. Try again in 15 minutes.",
                status_code=401,
                reason="locked",
            )
        if not verify_password(password, str(row["password_hash"] or "")):
            self._record_failure(user, row)
            raise AuthDenied("Incorrect email or password.", reason="bad_password")
        now = _iso()
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE users
                SET failed_login_count = 0, failed_window_started_at = NULL,
                    locked_until = NULL, last_login_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, user.id),
            )
            conn.commit()
        self.activity.log_activity(
            user,
            action="auth.login.success",
            resource_type="auth",
            summary=f"{user.email} signed in",
        )
        return user

    def _record_failure(self, user: SessionUser, row: object) -> None:
        data = dict(row)
        window_start = _parse_dt(data.get("failed_window_started_at"))
        count = int(data.get("failed_login_count") or 0)
        now = _now()
        if window_start is None or now - window_start > timedelta(minutes=WINDOW_MINUTES):
            count = 1
            window_start = now
        else:
            count += 1
        locked = None
        if count >= LOCK_AFTER:
            locked = now + timedelta(minutes=LOCK_MINUTES)
            self.activity.log_activity(
                user,
                action="auth.lockout",
                status="failure",
                resource_type="auth",
                summary=f"{user.email} locked after {count} failures",
            )
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE users
                SET failed_login_count = ?, failed_window_started_at = ?,
                    locked_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    count,
                    _iso(window_start),
                    _iso(locked) if locked else None,
                    _iso(now),
                    user.id,
                ),
            )
            conn.commit()
        self.activity.log_activity(
            user,
            action="auth.login.failure",
            status="failure",
            resource_type="auth",
            summary="bad password",
            metadata={"reason": "bad_password"},
        )

    def logout(self, user: SessionUser | None) -> None:
        if user is None:
            return
        self.activity.log_activity(
            user,
            action="auth.logout",
            resource_type="auth",
            summary=f"{user.email} signed out",
        )

    def set_active(self, actor: SessionUser, user_id: int, active: bool) -> SessionUser:
        require(actor, "users.manage")
        target = self.get_by_id(user_id)
        if target is None:
            raise AuthDenied("User not found.", status_code=404)
        if not active and self.is_last_admin(user_id):
            raise AuthDenied("Cannot disable the last admin.")
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET active = ?, updated_at = ? WHERE id = ?",
                (1 if active else 0, _iso(), user_id),
            )
            conn.commit()
        updated = self.get_by_id(user_id)
        assert updated is not None
        self.activity.log_activity(
            actor,
            action="user.enable" if active else "user.disable",
            resource_type="user",
            resource_id=str(user_id),
            summary=f"{'Enabled' if active else 'Disabled'} {updated.email}",
        )
        return updated

    def set_role(self, actor: SessionUser, user_id: int, role: Role) -> SessionUser:
        require(actor, "users.manage")
        target = self.get_by_id(user_id)
        if target is None:
            raise AuthDenied("User not found.", status_code=404)
        parsed = parse_role(role)
        if target.role == "admin" and parsed != "admin" and self.is_last_admin(user_id):
            raise AuthDenied("Cannot demote the last admin.")
        if actor.id == user_id and parsed != "admin" and self.is_last_admin(user_id):
            raise AuthDenied("Cannot demote yourself as the last admin.")
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (parsed, _iso(), user_id),
            )
            conn.commit()
        updated = self.get_by_id(user_id)
        assert updated is not None
        self.activity.log_activity(
            actor,
            action="user.role.change",
            resource_type="user",
            resource_id=str(user_id),
            summary=f"{updated.email} role {target.role} → {parsed}",
        )
        return updated

    def change_own_password(self, actor: SessionUser, current: str, new_password: str) -> None:
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (actor.id,)).fetchone()
        if row is None or not verify_password(current, str(row["password_hash"] or "")):
            raise AuthDenied("Current password is incorrect.", reason="bad_password")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise AuthDenied(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                reason="password",
            )
        self._write_password(actor.id, new_password, must_change=False)
        self.activity.log_activity(
            actor,
            action="auth.password.change",
            resource_type="auth",
            summary=f"{actor.email} changed password",
        )

    def admin_reset_password(self, actor: SessionUser, user_id: int, new_password: str) -> None:
        require(actor, "users.manage")
        if not new_password:
            raise AuthDenied("Password required.", reason="password")
        target = self.get_by_id(user_id)
        if target is None:
            raise AuthDenied("User not found.", status_code=404)
        self._write_password(user_id, new_password, must_change=True, allow_short=True)
        self.activity.log_activity(
            actor,
            action="user.password.reset.admin",
            resource_type="user",
            resource_id=str(user_id),
            summary=f"Admin reset password for {target.email}",
        )

    def request_password_reset(self, email: str) -> str:
        addr = normalize_email(email)
        self.activity.log_activity(
            None,
            action="auth.password.reset.request",
            resource_type="auth",
            summary="password reset requested",
            metadata={"email": addr} if is_valid_email(addr) else {"reason": "invalid_email"},
        )
        user = self.get_by_email(addr) if is_valid_email(addr) else None
        if user is None:
            return RESET_MESSAGE
        token = secrets.token_urlsafe(32)
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO password_resets (
                    user_id, email, token_hash, token_last4, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.email,
                    _token_hash(token),
                    token[-4:],
                    _iso(_now() + timedelta(hours=24)),
                    _iso(),
                ),
            )
            conn.commit()
        return RESET_MESSAGE

    def complete_password_reset(self, token: str, new_password: str) -> SessionUser:
        hashed = _token_hash(token)
        with get_app_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM password_resets WHERE token_hash = ? AND used_at IS NULL",
                (hashed,),
            ).fetchone()
        if not row:
            raise AuthDenied("Reset link is invalid or expired.", reason="reset")
        expires = _parse_dt(row["expires_at"])
        if expires is None or expires < _now():
            raise AuthDenied("Reset link is invalid or expired.", reason="reset")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise AuthDenied(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                reason="password",
            )
        user = self.get_by_id(int(row["user_id"]))
        if user is None:
            raise AuthDenied("Reset link is invalid or expired.", reason="reset")
        self._write_password(user.id, new_password, must_change=False)
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE password_resets SET used_at = ? WHERE id = ?",
                (_iso(), int(row["id"])),
            )
            conn.commit()
        self.activity.log_activity(
            user,
            action="auth.password.change",
            resource_type="auth",
            summary=f"{user.email} reset password",
        )
        return user

    def set_password_direct(
        self, user_id: int, password: str, *, must_change: bool = False
    ) -> None:
        self._write_password(user_id, password, must_change=must_change)

    def _write_password(
        self, user_id: int, password: str, *, must_change: bool, allow_short: bool = False
    ) -> None:
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, must_change_password = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    hash_password(password, allow_short=allow_short),
                    1 if must_change else 0,
                    _iso(),
                    user_id,
                ),
            )
            conn.commit()

    def require_active(self, user_id: int | None) -> SessionUser:
        if user_id is None:
            raise AuthDenied("Sign in required.", status_code=401, reason="unauthenticated")
        user = self.get_by_id(int(user_id))
        if user is None or not user.active:
            self.activity.log_activity(
                user,
                action="auth.session.denied",
                status="denied",
                resource_type="auth",
                summary="inactive or missing session",
            )
            raise AuthDenied(DISABLED_MESSAGE, status_code=401, reason="inactive")
        return user
