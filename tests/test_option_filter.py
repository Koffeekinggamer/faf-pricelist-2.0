"""Search Option dropdown is scoped per vendor."""

from __future__ import annotations

from backend.repository import PriceBookRepository


def test_list_option_keys_empty_for_all(tmp_path):
    db = tmp_path / "t.db"
    repo = PriceBookRepository(db)
    # init schema via insert path
    from backend.db import init_db

    init_db(db)
    assert repo.list_option_keys(None) == []
    assert repo.list_option_keys("All") == []


def test_list_option_keys_and_search_filter(tmp_path):
    db = tmp_path / "t.db"
    from backend.db import init_db

    init_db(db)
    repo = PriceBookRepository(db)
    rows = [
        {
            "vendor": "FN Chair",
            "collection": "Seating",
            "part_number": "Abe Side Chair",
            "description": "Abe Side Chair — Cat. 1",
            "option_key": "Cat. 1",
            "species": "Walnut / Rustic Walnut",
            "finish_state": "finished",
            "base_price": 258,
            "multiplier": 2.7,
            "adjusted_price": 698,
            "price_basis": "wholesale",
            "source_file": "test.xlsx",
        },
        {
            "vendor": "FN Chair",
            "collection": "Seating",
            "part_number": "Abe Side Chair",
            "description": "Abe Side Chair — Cat. 2",
            "option_key": "Cat. 2",
            "species": "Walnut / Rustic Walnut",
            "finish_state": "finished",
            "base_price": 292,
            "multiplier": 2.7,
            "adjusted_price": 790,
            "price_basis": "wholesale",
            "source_file": "test.xlsx",
        },
        {
            "vendor": "Other Builder",
            "collection": "Casegoods",
            "part_number": "X1",
            "description": "X1",
            "option_key": "Special",
            "species": "Oak",
            "finish_state": "finished",
            "base_price": 100,
            "multiplier": 2.7,
            "adjusted_price": 270,
            "price_basis": "wholesale",
            "source_file": "other.xlsx",
        },
    ]
    repo.insert_rows(rows)
    assert repo.list_option_keys("FN Chair") == ["Cat. 1", "Cat. 2"]
    assert repo.list_option_keys("Other Builder") == ["Special"]
    hit = repo.search(
        "Abe",
        vendor="FN Chair",
        option_key="Cat. 1",
        finish_state="finished",
        limit=20,
    )
    assert len(hit) == 1
    assert hit.iloc[0]["option_key"] == "Cat. 1"
