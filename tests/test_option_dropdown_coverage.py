"""Feedback loop: Option dropdown = addon charges + finish codes (ADR-0008)."""

from __future__ import annotations

from backend.db import init_db
from backend.repository import PriceBookRepository
from backend.service import PriceBookService


def _row(
    vendor: str,
    *,
    species: str | None = "Oak",
    option_key: str | None = None,
    part: str = "P1",
    line_kind: str = "item",
    base_price: float = 100,
):
    return {
        "vendor": vendor,
        "collection": "Casegoods" if line_kind == "item" else "Addons",
        "part_number": part,
        "description": part,
        "option_key": option_key,
        "species": species,
        "finish_state": "finished",
        "base_price": base_price,
        "multiplier": 2.7,
        "adjusted_price": round(base_price * 2.7, 2),
        "price_basis": "wholesale",
        "source_file": "t.xlsx",
        "line_kind": line_kind,
    }


def test_wood_only_builder_without_addons_has_empty_option(tmp_path):
    """Wood-only catalogs correctly show empty Option until addons exist."""
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Wood Only Co", species="Oak"),
            _row("Wood Only Co", species="Cherry", part="P2"),
        ]
    )
    assert repo.list_species(vendor="Wood Only Co")
    assert repo.list_option_keys("Wood Only Co") == []


def test_addon_charge_appears_in_option_dropdown(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Wood Only Co", species="Oak"),
            _row(
                "Wood Only Co",
                species=None,
                option_key="Solid Fabrics / COM",
                part="Solid Fabrics / COM",
                line_kind="addon",
                base_price=23,
            ),
            _row(
                "Wood Only Co",
                species=None,
                option_key="Rustic +15%",
                part="Rustic +15%",
                line_kind="addon",
                base_price=1,
            ),
        ]
    )
    opts = repo.list_option_keys("Wood Only Co")
    assert "Solid Fabrics / COM" in opts
    assert "Rustic +15%" in opts


def test_service_add_addon_charge_lists_in_options(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.add_addon_charge(
        vendor="Addon Co",
        label="Nailhead trim",
        flat_wholesale=45,
    )
    # Need a sellable row so vendor exists in book; add_addon alone is enough
    assert "Nailhead trim" in svc.list_option_keys("Addon Co")


def test_search_hides_addons_unless_option_filtered(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("FN Chair", species="Oak", option_key="Cat. 1", part="Abe Side Chair"),
            _row(
                "FN Chair",
                species=None,
                option_key="Solid Fabrics / COM",
                part="Abe Side Chair — Solid Fabrics / COM",
                line_kind="addon",
                base_price=23,
            ),
        ]
    )
    default = repo.search("Abe", vendor="FN Chair", finish_state="finished")
    assert len(default) == 1
    assert float(default.iloc[0]["base_price"]) == 100

    addons = repo.search(
        "",
        vendor="FN Chair",
        option_key="Solid Fabrics / COM",
        finish_state="finished",
    )
    assert len(addons) == 1
    assert float(addons.iloc[0]["base_price"]) == 23
    assert addons.iloc[0]["line_kind"] == "addon"


def test_fn_chair_still_lists_cats(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("FN Chair", species="Oak", option_key="Cat. 1"),
            _row("FN Chair", species="Oak", option_key="Cat. 2", part="P2"),
        ]
    )
    assert repo.list_option_keys("FN Chair") == ["Cat. 1", "Cat. 2"]
