"""Paths and defaults for FAF Pricelist 2.0."""

from __future__ import annotations

import hashlib
import hmac
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

DEFAULT_MULTIPLIER = 2.7
APP_USERNAME = (os.environ.get("APP_USERNAME") or "Foothills").strip()
APP_PASSWORD = (os.environ.get("APP_PASSWORD") or "Amish").strip()
# Optional: sha256:<hex> — preferred over plaintext APP_PASSWORD when set
APP_PASSWORD_HASH = (os.environ.get("APP_PASSWORD_HASH") or "").strip()

DATA_DIR.mkdir(parents=True, exist_ok=True)


def password_matches(provided: str, expected_plain: str = "", expected_hash: str = "") -> bool:
    """Constant-time password check. Supports sha256:<hex> hashes."""
    provided = provided or ""
    expected_hash = (expected_hash or APP_PASSWORD_HASH or "").strip()
    if expected_hash:
        digest = expected_hash
        if digest.lower().startswith("sha256:"):
            digest = digest.split(":", 1)[1]
        got = hashlib.sha256(provided.encode("utf-8")).hexdigest()
        return hmac.compare_digest(got.lower(), digest.lower())
    expected = expected_plain if expected_plain != "" else APP_PASSWORD
    return hmac.compare_digest(provided, expected)
