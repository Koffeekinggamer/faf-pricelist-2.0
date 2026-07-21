"""SQLite persistence for catalog rows + vendor multipliers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .config import DB_PATH, DEFAULT_MULTIPLIER

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT NOT NULL,
    collection TEXT,
    part_number TEXT,
    description TEXT,
    species TEXT,
    finish_state TEXT,
    base_price REAL,
    multiplier REAL,
    adjusted_price REAL,
    source_file TEXT,
    imported_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_vendor ON items(vendor);

CREATE TABLE IF NOT EXISTS vendors (
    name TEXT PRIMARY KEY,
    multiplier REAL NOT NULL DEFAULT 2.7,
    phone TEXT,
    notes TEXT,
    updated_at TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path or DB_PATH)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
    return path


def stats(db_path: Optional[Path] = None) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
        vendors = conn.execute(
            "SELECT COUNT(DISTINCT vendor) AS c FROM items"
        ).fetchone()["c"]
    return {"rows": rows, "vendors": vendors, "db_path": str(db_path or DB_PATH)}


def list_vendors(db_path: Optional[Path] = None) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT vendor FROM items WHERE vendor IS NOT NULL AND vendor != '' ORDER BY vendor"
        ).fetchall()
    return [r["vendor"] for r in rows]


def delete_vendor(vendor: str, db_path: Optional[Path] = None) -> int:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM items WHERE vendor = ?", (vendor,))
        n = cur.rowcount
        conn.execute("DELETE FROM vendors WHERE name = ?", (vendor,))
        return n


def insert_rows(rows: list[dict], db_path: Optional[Path] = None) -> int:
    if not rows:
        return 0
    now = _now()
    with connect(db_path) as conn:
        n = 0
        for r in rows:
            conn.execute(
                """
                INSERT INTO items (
                    vendor, collection, part_number, description, species,
                    finish_state, base_price, multiplier, adjusted_price,
                    source_file, imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r.get("vendor"),
                    r.get("collection"),
                    r.get("part_number"),
                    r.get("description"),
                    r.get("species"),
                    r.get("finish_state"),
                    r.get("base_price"),
                    r.get("multiplier"),
                    r.get("adjusted_price"),
                    r.get("source_file"),
                    now,
                ),
            )
            n += 1
        return n


def replace_vendor_rows(
    vendor: str, rows: list[dict], db_path: Optional[Path] = None
) -> dict:
    deleted = delete_vendor(vendor, db_path=db_path)
    for r in rows:
        r["vendor"] = vendor
    inserted = insert_rows(rows, db_path=db_path)
    return {"deleted": deleted, "inserted": inserted}


def get_multiplier(
    vendor: str, default: float = DEFAULT_MULTIPLIER, db_path: Optional[Path] = None
) -> float:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT multiplier FROM vendors WHERE name = ?", (vendor,)
        ).fetchone()
        if row and row["multiplier"] is not None:
            return float(row["multiplier"])
        # fallback: common mult on items
        row2 = conn.execute(
            "SELECT multiplier FROM items WHERE vendor = ? AND multiplier IS NOT NULL LIMIT 1",
            (vendor,),
        ).fetchone()
        if row2 and row2["multiplier"] is not None:
            return float(row2["multiplier"])
    return float(default)


def set_multiplier(
    vendor: str,
    multiplier: float,
    notes: str = "",
    db_path: Optional[Path] = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO vendors (name, multiplier, notes, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                multiplier = excluded.multiplier,
                notes = COALESCE(excluded.notes, vendors.notes),
                updated_at = excluded.updated_at
            """,
            (vendor, float(multiplier), notes or None, _now()),
        )


def set_phone(vendor: str, phone: str = "", db_path: Optional[Path] = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO vendors (name, multiplier, phone, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                phone = excluded.phone,
                updated_at = excluded.updated_at
            """,
            (vendor, DEFAULT_MULTIPLIER, phone or None, _now()),
        )


def get_phone(vendor: str, db_path: Optional[Path] = None) -> str:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT phone FROM vendors WHERE name = ?", (vendor,)
        ).fetchone()
        return (row["phone"] or "") if row else ""


def reapply_multiplier(
    vendor: str, multiplier: float, db_path: Optional[Path] = None
) -> int:
    """Recompute adjusted_price for all items of vendor."""
    from .pricing import retail_from_wholesale

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, base_price FROM items WHERE vendor = ?", (vendor,)
        ).fetchall()
        n = 0
        for r in rows:
            retail = retail_from_wholesale(r["base_price"], multiplier)
            conn.execute(
                "UPDATE items SET multiplier = ?, adjusted_price = ? WHERE id = ?",
                (float(multiplier), retail, r["id"]),
            )
            n += 1
        set_multiplier(vendor, multiplier, db_path=db_path)
        return n


def vendor_table(db_path: Optional[Path] = None) -> list[dict]:
    with connect(db_path) as conn:
        vendors = list_vendors(db_path)
        out = []
        for v in vendors:
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM items WHERE vendor = ?", (v,)
            ).fetchone()["c"]
            out.append(
                {
                    "Builder": v,
                    "Phone": get_phone(v, db_path),
                    "Items": cnt,
                    "Multiplier": get_multiplier(v, db_path=db_path),
                }
            )
        return out
