"""First-admin bootstrap. Never lock out the first operator."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from backend.app_db import env_is_fly
from backend.auth.passwords import is_valid_email, normalize_email
from backend.auth.roles import SessionUser
from backend.auth.store import AuthStore
from backend.config import resolve_secrets_path

DEV_ADMIN_EMAIL = "foothills@faf.local"
DEV_ADMIN_PASSWORD = "Amish"  # local/dev only — never used when Fly env is set
DEV_MANAGER_EMAIL = "manager@example.com"
DEV_MANAGER_PASSWORD = "managerdev1"
DEV_SALES_EMAIL = "sales@example.com"
DEV_SALES_PASSWORD = "salesdev11"


def is_dev_seed(env: Mapping[str, str] | None = None) -> bool:
    src = env if env is not None else os.environ
    if src.get("FLY_APP_NAME") or src.get("FLY_ALLOC_ID"):
        return False
    if str(src.get("NODE_ENV") or "").strip().lower() == "development":
        return True
    flag = str(src.get("FAF_DEV_SEED") or "").strip().lower()
    return flag in {"1", "true", "yes"}


def _read_secrets_auth() -> tuple[str, str] | None:
    path = resolve_secrets_path()
    if not path.is_file():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    auth = data.get("auth") or {}
    if not isinstance(auth, dict):
        return None
    password = str(auth.get("password") or "")
    if not password:
        return None
    email = str(auth.get("email") or "").strip()
    username = str(auth.get("username") or "").strip()
    if email and is_valid_email(email):
        return normalize_email(email), password
    if username and "@" in username and is_valid_email(username):
        return normalize_email(username), password
    if username:
        local = "".join(ch for ch in username.lower() if ch.isalnum() or ch in "._-") or "floor"
        return f"{local}@faf.local", password
    return None


def resolve_bootstrap_credentials() -> tuple[str, str, str]:
    """Return (email, password, source). Password never logged."""
    email = normalize_email(os.environ.get("ADMIN_EMAIL") or "")
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if email and password:
        return email, password, "env"
    secrets = _read_secrets_auth()
    if secrets:
        return secrets[0], secrets[1], "secrets"
    if env_is_fly():
        raise RuntimeError(
            "Users table is empty and ADMIN_EMAIL / ADMIN_PASSWORD are unset. "
            "Set those Fly secrets before starting."
        )
    # Local / development floor: documented default only.
    return DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD, "dev-default"


def bootstrap_users(db_path: Path) -> SessionUser | None:
    store = AuthStore(db_path)
    if store.count() > 0:
        return None
    email, password, _source = resolve_bootstrap_credentials()
    admin = store.insert_user(
        email=email,
        password=password,
        role="admin",
        name=email.split("@", 1)[0],
        allow_short_password=True,
    )
    if is_dev_seed():
        if store.get_by_email(DEV_MANAGER_EMAIL) is None:
            store.insert_user(
                email=DEV_MANAGER_EMAIL,
                password=DEV_MANAGER_PASSWORD,
                role="manager",
                name="Manager",
                created_by=admin.id,
            )
        if store.get_by_email(DEV_SALES_EMAIL) is None:
            store.insert_user(
                email=DEV_SALES_EMAIL,
                password=DEV_SALES_PASSWORD,
                role="sales",
                name="Sales",
                created_by=admin.id,
            )
    return admin
