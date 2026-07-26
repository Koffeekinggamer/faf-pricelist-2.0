"""
App login for Streamlit.

Auth order:
  1. app_users table (OrderTrac-synced + local multi-user) when any users exist
  2. Legacy single-user from secrets / env / built-in defaults

password_hash = sha256 hex of the password string.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple

from backend.config import DB_PATH
from backend.users import UserRepository, hash_password


# Fallback only if secrets/env are not set and no DB users yet
_DEFAULT_USER = "Foothills"
_DEFAULT_PASSWORD = "Amish"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_expected_credentials() -> Tuple[str, Optional[str], Optional[str]]:
    """
    Legacy single-user credentials.
    Returns (username, plain_password_or_None, password_hash_or_None).
    """
    try:
        import streamlit as st

        auth = st.secrets.get("auth", None)
        if auth:
            user = str(auth.get("username") or "").strip()
            pw = auth.get("password")
            ph = auth.get("password_hash")
            plain = str(pw) if pw is not None and str(pw) != "" else None
            hashed = str(ph).strip().lower() if ph else None
            if user and (plain or hashed):
                return user, plain, hashed
    except Exception:
        pass

    user = (os.environ.get("FAF_APP_USER") or "").strip()
    plain = os.environ.get("FAF_APP_PASSWORD")
    hashed = (os.environ.get("FAF_APP_PASSWORD_HASH") or "").strip().lower() or None
    if user and (plain or hashed):
        return user, plain if plain else None, hashed

    return _DEFAULT_USER, _DEFAULT_PASSWORD, None


def _user_repo(db_path: Optional[Path] = None) -> UserRepository:
    return UserRepository(db_path or DB_PATH)


def ensure_seed_admin(db_path: Optional[Path] = None) -> None:
    """If app_users is empty, seed admin from legacy credentials."""
    try:
        from backend.db import init_db

        init_db(db_path or DB_PATH)
        repo = _user_repo(db_path)
        user, plain, hashed = get_expected_credentials()
        if repo.count() > 0:
            return
        # Prefer plain password; if only hash is set, store that hash directly
        if plain:
            repo.ensure_admin_seed(username=user, password=plain)
        elif hashed:
            # insert with known hash
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            with repo._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO app_users (
                        username, display_name, password_hash, role, active,
                        must_change_password, source, created_at, updated_at
                    ) VALUES (?, ?, ?, 'admin', 1, 0, 'seed', ?, ?)
                    """,
                    (user, "Foothills Admin", hashed, now, now),
                )
                conn.commit()
        else:
            repo.ensure_admin_seed()
    except Exception:
        pass


def check_login(
    username: str,
    password: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    """Return True if credentials are valid (multi-user DB or legacy single-user)."""
    if not username or not password:
        return False

    ensure_seed_admin(db_path)
    repo = _user_repo(db_path)
    try:
        if repo.count() > 0:
            user = repo.authenticate(username, password)
            return user is not None
    except Exception:
        pass

    # Legacy single-user fallback
    exp_user, exp_plain, exp_hash = get_expected_credentials()
    if username.strip() != exp_user:
        return False
    if exp_hash:
        return _sha256(password) == exp_hash
    if exp_plain is not None:
        return password == exp_plain
    return False


def login_user(
    username: str,
    password: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Authenticate and return a session dict (no password_hash), or None.
    Keys: username, display_name, role, user_id, must_change_password, source
    """
    if not username or not password:
        return None

    ensure_seed_admin(db_path)
    repo = _user_repo(db_path)
    try:
        if repo.count() > 0:
            user = repo.authenticate(username, password)
            if not user:
                return None
            return {
                "user_id": int(user["id"]),
                "username": user["username"],
                "display_name": user.get("display_name") or user["username"],
                "role": user.get("role") or "sales",
                "must_change_password": bool(user.get("must_change_password")),
                "source": user.get("source") or "local",
                "ordertrac_user_guid": user.get("ordertrac_user_guid"),
                "ordertrac_display_name": user.get("ordertrac_display_name"),
            }
    except Exception:
        pass

    # Legacy
    if not check_login(username, password, db_path=db_path):
        return None
    exp_user, _, _ = get_expected_credentials()
    return {
        "user_id": None,
        "username": exp_user,
        "display_name": exp_user,
        "role": "admin",
        "must_change_password": False,
        "source": "legacy",
        "ordertrac_user_guid": None,
        "ordertrac_display_name": None,
    }


def credentials_source_hint() -> str:
    try:
        repo = _user_repo()
        if repo.count() > 0:
            return f"app_users ({repo.count()} accounts)"
    except Exception:
        pass
    try:
        import streamlit as st

        if st.secrets.get("auth"):
            return "secrets.toml"
    except Exception:
        pass
    if os.environ.get("FAF_APP_USER"):
        return "environment"
    return "default"


# re-export for callers that hash passwords
__all__ = [
    "check_login",
    "login_user",
    "ensure_seed_admin",
    "get_expected_credentials",
    "credentials_source_hint",
    "hash_password",
]
