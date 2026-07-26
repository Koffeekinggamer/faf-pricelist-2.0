"""Atomic builder replace — prior catalog must survive failed inserts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.db import init_db
from backend.pricing import retail_from_wholesale
from backend.repository import PriceBookRepository
from backend.service import PriceBookService


def _row(vendor: str, part: str, base: float, mult: float = 2.7, source: str = "t.xlsx") -> dict:
    return {
        "vendor": vendor,
        "collection": "Test",
        "part_number": part,
        "description": f"Item {part}",
        "dimensions": None,
        "option_key": None,
        "species": "Oak",
        "species_tier": None,
        "finish_state": "finished",
        "base_price": base,
        "price_basis": "wholesale",
        "multiplier": mult,
        "adjusted_price": retail_from_wholesale(base, mult),
        "unit": None,
        "notes": None,
        "source_file": source,
        "imported_at": "2026-07-26T00:00:00",
    }


def test_replace_vendor_rows_swaps_catalog(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.replace_vendor_rows(
        "Builder A",
        [_row("Builder A", "A1", 100), _row("Builder A", "A2", 200)],
        multiplier=2.7,
    )
    assert repo.row_count() == 2

    result = repo.replace_vendor_rows(
        "Builder A",
        [_row("Builder A", "B1", 150, 1.7)],
        multiplier=1.7,
    )
    assert result["deleted"] == 2
    assert result["inserted"] == 1
    assert repo.row_count() == 1
    assert repo.get_vendor_multiplier("Builder A") == 1.7
    parts = [
        r["part_number"]
        for r in repo.search(query="", vendor="Builder A", limit=50).to_dict("records")
    ]
    assert parts == ["B1"]


def test_replace_vendor_atomic_rolls_back_on_insert_failure(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.replace_vendor_rows(
        "Builder A",
        [_row("Builder A", "KEEP", 100)],
        multiplier=2.7,
    )
    assert repo.row_count() == 1

    # Force INSERT to fail after DELETE inside the same transaction
    with repo._conn() as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_insert BEFORE INSERT ON pricebook
            BEGIN
              SELECT RAISE(ABORT, 'simulated insert failure');
            END;
            """
        )
        conn.commit()

    with pytest.raises(sqlite3.Error, match="simulated insert failure"):
        repo.replace_vendor_rows(
            "Builder A",
            [_row("Builder A", "NEW", 999)],
            multiplier=1.7,
        )

    # Prior catalog must still be present
    assert repo.row_count() == 1
    frame = repo.search(query="KEEP", vendor="Builder A", limit=10)
    assert len(frame) == 1
    assert float(frame.iloc[0]["base_price"]) == 100.0
    assert repo.get_vendor_multiplier("Builder A") == 2.7


def test_service_add_rows_replace_vendor_atomic(tmp_path: Path):
    db = tmp_path / "t.db"
    svc = PriceBookService(db)
    svc.init()
    svc.add_rows(
        [_row("Hope Wood", "H1", 80), _row("Hope Wood", "H2", 90)],
        mode="replace_vendor",
    )
    assert svc.stats()["rows"] == 2

    out = svc.add_rows([_row("Hope Wood", "H9", 110)], mode="replace_vendor")
    assert out["deleted"] == 2
    assert out["inserted"] == 1
    assert svc.stats()["rows"] == 1
