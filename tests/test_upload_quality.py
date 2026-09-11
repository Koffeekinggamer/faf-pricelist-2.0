"""0–100% quality rating for every builder upload."""

from __future__ import annotations

from backend.db import init_db
from backend.repository import PriceBookRepository
from backend.service import PriceBookService
from backend.upload_quality import rate_drop_parse, rate_upload


def test_perfect_upload_rates_100():
    rating = rate_upload(
        item_rows=10,
        blank_species=0,
        blank_descriptions=0,
        missing_part_numbers=0,
        missing_prices=0,
        search_options=["Two-tone"],
        retail_mismatches=0,
        parser_locked=True,
    )
    assert rating.percent == 100
    assert rating.deductions == []


def test_empty_search_options_is_a_30_point_miss():
    rating = rate_upload(
        item_rows=10,
        blank_species=0,
        blank_descriptions=0,
        missing_part_numbers=0,
        missing_prices=0,
        search_options=[],
        retail_mismatches=0,
        parser_locked=True,
    )
    assert rating.percent == 70
    assert "Search Options empty" in rating.deductions


def test_half_blank_species_earns_half_the_wood_points():
    rating = rate_upload(
        item_rows=10,
        blank_species=5,
        blank_descriptions=0,
        missing_part_numbers=0,
        missing_prices=0,
        search_options=["Paint"],
        retail_mismatches=0,
        parser_locked=True,
    )
    assert rating.percent == 88
    assert any("species" in d.lower() for d in rating.deductions)


def test_any_species_miss_caps_perfect_at_99():
    rating = rate_upload(
        item_rows=6239,
        blank_species=85,
        blank_descriptions=0,
        missing_part_numbers=0,
        missing_prices=0,
        search_options=["Two-tone"],
        retail_mismatches=0,
        parser_locked=True,
    )
    assert rating.percent == 99
    assert rating.deductions


def test_zero_items_rates_0():
    rating = rate_upload(
        item_rows=0,
        blank_species=0,
        blank_descriptions=0,
        missing_part_numbers=0,
        missing_prices=0,
        search_options=[],
        retail_mismatches=0,
        parser_locked=False,
    )
    assert rating.percent == 0


def test_drop_parse_with_addons_and_woods_scores_the_upload():
    rating = rate_drop_parse(
        {
            "rows": [
                {
                    "line_kind": "item",
                    "part_number": "T1",
                    "description": "Table",
                    "species": "Oak",
                    "base_price": 100,
                },
                {
                    "line_kind": "addon",
                    "option_key": "Two-tone",
                    "description": "Two-tone",
                    "part_number": "Two-tone",
                    "base_price": 35,
                },
            ],
            "detected_importer": "brookside_home_furnishings",
            "locked_parser": "brookside_home_furnishings",
        }
    )
    assert rating.percent == 100


def _row(vendor: str, part: str, **extra) -> dict:
    rec = {
        "vendor": vendor,
        "collection": "Tables",
        "part_number": part,
        "description": f"{part} Table",
        "option_key": None,
        "species": "Oak",
        "finish_state": "finished",
        "base_price": 100,
        "multiplier": 2.7,
        "adjusted_price": 270,
        "price_basis": "wholesale",
        "source_file": "book.xlsx",
        "line_kind": "item",
    }
    rec.update(extra)
    return rec


def test_service_rates_every_builder_upload(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Good Co", "G1"),
            _row(
                "Good Co",
                "Two-tone",
                line_kind="addon",
                option_key="Two-tone",
                species=None,
                description="Two-tone",
                base_price=20,
                adjusted_price=54,
            ),
            _row("Miss Co", "M1", species=None, description=""),
        ]
    )
    svc = PriceBookService(db)
    ratings = {r["vendor"]: r for r in svc.list_upload_quality()}
    assert set(ratings) == {"Good Co", "Miss Co"}
    assert ratings["Good Co"]["percent"] < 100  # no named parser lock
    assert ratings["Miss Co"]["percent"] < ratings["Good Co"]["percent"]
    assert ratings["Miss Co"]["percent"] >= 0
