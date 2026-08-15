"""Verify before cleanup: SKU × wood / Queen vs Full are not duplicates."""

from __future__ import annotations

from backend.db import init_db
from backend.duplicate_verify import verify_duplicate_group
from backend.repository import PriceBookRepository


def _row(
    *,
    part: str = "81",
    desc: str,
    species: str = "Brown Maple",
    base: float,
    collection: str = "Shaker Beds",
) -> dict:
    return {
        "vendor": "J & M Woodworking",
        "collection": collection,
        "part_number": part,
        "description": desc,
        "dimensions": None,
        "option_key": None,
        "species": species,
        "finish_state": "finished",
        "base_price": base,
        "price_basis": "wholesale",
        "multiplier": 2.7,
        "adjusted_price": 1742.0,
        "source_file": "t.xlsx",
        "line_kind": "item",
    }


def test_queen_vs_full_same_part_and_wood_is_not_a_duplicate():
    queen = _row(desc='Queen Panel Bed 64"W x 87.25" L', base=645.0)
    full = _row(desc='Full Panel Bed 58"W x 82.25"L', base=605.0)
    ok, reason = verify_duplicate_group([queen, full])
    assert ok is False
    assert "differs" in reason


def test_same_species_is_not_enough_to_call_duplicate():
    oak = _row(desc="Nightstand", species="Oak", base=200.0)
    cherry = _row(desc="Nightstand", species="Cherry", base=220.0)
    ok, _reason = verify_duplicate_group([oak, cherry])
    assert ok is False


def test_true_copies_verify():
    a = _row(desc="Nightstand", base=200.0)
    b = dict(a)
    ok, reason = verify_duplicate_group([a, b])
    assert ok is True
    assert reason == ""


def test_cleanup_skips_queen_full_and_deletes_only_true_copies(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row(desc='Queen Panel Bed 64"W x 87.25" L', base=645.0),
            _row(desc='Full Panel Bed 58"W x 82.25"L', base=605.0),
            _row(desc="Nightstand", part="46", base=200.0),
            _row(desc="Nightstand", part="46", base=200.0),
        ]
    )
    assert repo.find_duplicate_groups(50).empty is False
    dups = repo.find_duplicate_groups(50)
    assert list(dups["part_number"]) == ["46"]
    dry = repo.cleanup_duplicates(dry_run=True)
    assert dry["would_delete"] == 1
    assert dry["skipped_distinct"] >= 1
    live = repo.cleanup_duplicates(dry_run=False)
    assert live["deleted"] == 1
    assert repo.row_count() == 3
