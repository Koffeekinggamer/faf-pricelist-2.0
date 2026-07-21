"""Paths and defaults for FAF Pricelist 2.0."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FAF2_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("FAF2_DB_PATH", DATA_DIR / "master_pricebook.db"))
BACKUP_DIR = Path(
    os.environ.get(
        "FAF2_BACKUP_DIR",
        Path.home() / "Documents" / "FAF-pricelist-2.0-backups",
    )
)

# Optional: use v1 Excel unpivot engine when present
V1_ROOT = Path(os.environ.get("FAF_V1_ROOT", Path.home() / "FAF-pricebook"))

DEFAULT_MULTIPLIER = 2.7
APP_USERNAME = (os.environ.get("APP_USERNAME") or "Foothills").strip()
APP_PASSWORD = (os.environ.get("APP_PASSWORD") or "Amish").strip()

DATA_DIR.mkdir(parents=True, exist_ok=True)
