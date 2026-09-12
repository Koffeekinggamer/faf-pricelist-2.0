"""Paths and defaults."""

from __future__ import annotations

import os
from pathlib import Path

# Project root: parent of backend/
APP_DIR = Path(__file__).resolve().parent.parent


def _env_path(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def resolve_data_dir() -> Path:
    """Catalog, images, lessons, and secrets live here when traveling.

    Set FAF_DATA_DIR from ./run.sh after ExternalSSD is plugged in.
    Fly keeps using /data via FAF_DB_PATH. Tests leave this unset so they
    stay on the checkout, not the live drive.
    """
    env = _env_path("FAF_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return APP_DIR


def resolve_db_path() -> Path:
    env_db = _env_path("FAF_DB_PATH", "PRICEBOOK_DB_PATH")
    if env_db:
        return Path(env_db).expanduser()
    return resolve_data_dir() / "master_pricebook.db"


def resolve_app_db_path(*, catalog_path: Path | None = None) -> Path:
    """Users / quotes / activity — sibling of the catalog, never mixed into a dump."""
    env = _env_path("PRICEBOOK_APP_DB")
    if not env:
        raw = _env_path("DATABASE_URL")
        if raw.startswith("sqlite:///"):
            env = raw[len("sqlite:///") :]
        elif raw and "://" not in raw:
            env = raw
    if env:
        return Path(env).expanduser()
    catalog = Path(catalog_path) if catalog_path is not None else resolve_db_path()
    return catalog.parent / "pricebook_app.db"


def resolve_session_secret() -> str:
    return _env_path("SESSION_SECRET", "NEXTAUTH_SECRET", "FAF_LOGIN_SECRET")


def resolve_secrets_path() -> Path:
    env = _env_path("FAF_SECRETS_PATH")
    if env:
        return Path(env).expanduser()
    data = resolve_data_dir()
    portable = data / "secrets.toml"
    if portable.is_file():
        return portable
    return APP_DIR / ".streamlit" / "secrets.toml"


DATA_DIR = resolve_data_dir()
DB_PATH = resolve_db_path()
SECRETS_PATH = resolve_secrets_path()

DEFAULT_MULTIPLIER = 2.7
DEFAULT_PRICE_BASIS = "wholesale"
DEFAULT_SEARCH_LIMIT = 150
# ADR-0007: builders below this sellable-row count are thin catalogs
THIN_CATALOG_MAX_ROWS = 150

# Shown on customer quote PDFs (edit to match the store)
STORE = {
    "name": "Foothills Amish Furniture",
    "tagline": "Customer Price Quote",
    "phone": "",
    "email": "",
    "address": "",
    "footer": "Prices subject to change. Thank you for your business.",
}

# Unique identity for a sellable configuration (dedupe / upsert)
IDENTITY_FIELDS = (
    "vendor",
    "collection",
    "part_number",
    "species",
    "finish_state",
    "option_key",
    "dimensions",
)
