"""Email+password login. Replaces the shared Foothills/Amish username gate."""

from __future__ import annotations

from pathlib import Path

from backend.auth.bootstrap import bootstrap_users
from backend.auth.passwords import hash_password, is_valid_email, normalize_email
from backend.auth.permissions import AuthDenied, can, require
from backend.auth.roles import SessionUser
from backend.auth.session import session_from_user, user_from_session
from backend.auth.store import AuthStore
from backend.config import resolve_app_db_path


def ensure_seed_admin(db_path: Path | None = None) -> None:
    """Empty users table → admin from ADMIN_EMAIL / secrets / local default."""
    try:
        bootstrap_users(resolve_app_db_path(catalog_path=db_path))
    except Exception:
        pass


def _store(db_path: Path | None = None) -> AuthStore:
    return AuthStore(resolve_app_db_path(catalog_path=db_path))


def login_user(
    email: str,
    password: str,
    *,
    db_path: Path | None = None,
) -> dict[str, object] | None:
    """Authenticate by email. Returns a session dict or None."""
    if not email or not password:
        return None
    ensure_seed_admin(db_path)
    try:
        user = _store(db_path).authenticate(normalize_email(email), password)
    except AuthDenied:
        return None
    return session_from_user(user)


def check_login(email: str, password: str, *, db_path: Path | None = None) -> bool:
    return login_user(email, password, db_path=db_path) is not None


def credentials_source_hint() -> str:
    try:
        store = _store()
        if store.count() > 0:
            return f"app users ({store.count()} accounts)"
    except Exception:
        pass
    return "email + password"


__all__ = [
    "AuthDenied",
    "AuthStore",
    "SessionUser",
    "can",
    "check_login",
    "credentials_source_hint",
    "ensure_seed_admin",
    "hash_password",
    "is_valid_email",
    "login_user",
    "normalize_email",
    "require",
    "session_from_user",
    "user_from_session",
]
