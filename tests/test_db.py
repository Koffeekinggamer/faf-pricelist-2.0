"""Atomic vendor replace + phone/multiplier hygiene."""

from pathlib import Path

from backend import db
from backend.pricing import retail_from_wholesale


def _row(vendor: str, part: str, base: float, mult: float = 2.7) -> dict:
    return {
        "vendor": vendor,
        "collection": "Test",
        "part_number": part,
        "description": f"Item {part}",
        "species": "Oak",
        "finish_state": "finished",
        "base_price": base,
        "multiplier": mult,
        "adjusted_price": retail_from_wholesale(base, mult),
        "source_file": "test.xlsx",
    }


def test_replace_vendor_rows_atomic(tmp_path: Path):
    path = tmp_path / "t.db"
    db.init_db(path)
    db.replace_vendor_rows(
        "Builder A",
        [_row("Builder A", "A1", 100), _row("Builder A", "A2", 200)],
        db_path=path,
        multiplier=2.7,
        notes="seed",
    )
    assert db.stats(path)["rows"] == 2

    db.replace_vendor_rows(
        "Builder A",
        [_row("Builder A", "B1", 150, 1.7)],
        db_path=path,
        multiplier=1.7,
        notes="replace",
    )
    stats = db.stats(path)
    assert stats["rows"] == 1
    assert db.get_multiplier("Builder A", db_path=path) == 1.7

    with db.connect(path) as conn:
        parts = [
            r["part_number"]
            for r in conn.execute(
                "SELECT part_number FROM items WHERE vendor = ?", ("Builder A",)
            )
        ]
    assert parts == ["B1"]


def test_set_phone_preserves_multiplier(tmp_path: Path):
    path = tmp_path / "t.db"
    db.init_db(path)
    db.replace_vendor_rows(
        "Oak Co",
        [_row("Oak Co", "X1", 50, 1.7)],
        db_path=path,
        multiplier=1.7,
    )
    db.set_phone("Oak Co", "555-0100", db_path=path)
    assert db.get_multiplier("Oak Co", db_path=path) == 1.7
    assert db.get_phone("Oak Co", db_path=path) == "555-0100"


def test_reapply_multiplier(tmp_path: Path):
    path = tmp_path / "t.db"
    db.init_db(path)
    db.replace_vendor_rows(
        "Mult Co",
        [_row("Mult Co", "M1", 100, 2.7)],
        db_path=path,
        multiplier=2.7,
    )
    n = db.reapply_multiplier("Mult Co", 2.0, db_path=path)
    assert n == 1
    with db.connect(path) as conn:
        retail = conn.execute(
            "SELECT adjusted_price FROM items WHERE vendor = ?", ("Mult Co",)
        ).fetchone()["adjusted_price"]
    assert retail == 200.0
