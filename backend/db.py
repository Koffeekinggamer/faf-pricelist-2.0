"""SQLite connection and migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from backend.config import DB_PATH
from backend.models import NEW_COLUMNS, QUOTE_NEW_COLUMNS, SCHEMA_SQL, VENDOR_NEW_COLUMNS


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Union[str, Path]] = None) -> Path:
    """Create tables and apply column migrations. Returns DB path."""
    path = Path(db_path) if db_path else DB_PATH
    with get_connection(path) as conn:
        conn.executescript(SCHEMA_SQL)
        existing = {
            r[1] for r in conn.execute("PRAGMA table_info(pricebook)").fetchall()
        }
        for col, typ in NEW_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE pricebook ADD COLUMN {col} {typ}")
        vendor_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(vendors)").fetchall()
        }
        for col, typ in VENDOR_NEW_COLUMNS.items():
            if col not in vendor_cols:
                conn.execute(f"ALTER TABLE vendors ADD COLUMN {col} {typ}")
        quote_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(quotes)").fetchall()
        }
        for col, typ in QUOTE_NEW_COLUMNS.items():
            if col not in quote_cols:
                conn.execute(f"ALTER TABLE quotes ADD COLUMN {col} {typ}")
        conn.commit()
    return path
