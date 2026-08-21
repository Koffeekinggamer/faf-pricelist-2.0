"""Signed login tokens so a page reload signs the floor user back in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.auth import session_from_user
from backend.config import APP_DIR
from backend.users import UserRepository

COOKIE_NAME = "faf_login"
TTL_SECONDS = 365 * 24 * 60 * 60
_SECRET_FILE = ".login_secret"
_TOKEN_FILE = ".login_token"


def login_secret(*, root: Optional[Path] = None) -> str:
    """Stable HMAC key on this machine. Not a password."""
    env = (os.environ.get("FAF_LOGIN_SECRET") or "").strip()
    if env:
        return env
    base = Path(root) if root is not None else APP_DIR
    path = base / _SECRET_FILE
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    token = secrets.token_hex(32)
    try:
        path.write_text(token + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        return token
    return token


def issue_login_token(
    session: dict,
    *,
    secret: str,
    now: Optional[datetime] = None,
    ttl_seconds: int = TTL_SECONDS,
) -> str:
    """HMAC-signed identity. Role and display name are re-read on restore."""
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    payload = {
        "uid": session.get("user_id"),
        "u": str(session.get("username") or "").strip(),
        "exp": int((stamp + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def restore_login_session(
    token: str,
    *,
    secret: str,
    db_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Return a live session if the token is valid and the user is still active."""
    text = (token or "").strip()
    if "." not in text or not secret:
        return None
    body, sig = text.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    try:
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if exp < int(stamp.timestamp()):
        return None
    username = str(payload.get("u") or "").strip()
    uid = payload.get("uid")
    repo = UserRepository(db_path)
    try:
        user = None
        if uid is not None:
            user = repo.get_by_id(int(uid))
        if user is None and username:
            user = repo.get_by_username(username)
        if not user or not user.get("active"):
            return None
        return session_from_user(user)
    except Exception:
        return None


def persist_token(token: str, *, root: Optional[Path] = None) -> None:
    base = Path(root) if root is not None else APP_DIR
    path = base / _TOKEN_FILE
    path.write_text((token or "").strip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_persisted_token(*, root: Optional[Path] = None) -> str:
    base = Path(root) if root is not None else APP_DIR
    path = base / _TOKEN_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def clear_persisted_token(*, root: Optional[Path] = None) -> None:
    base = Path(root) if root is not None else APP_DIR
    path = base / _TOKEN_FILE
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        try:
            path.write_text("", encoding="utf-8")
        except OSError:
            return
