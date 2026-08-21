"""Unfinished is an Option; Search defaults to finished when the catalog lists it."""

from __future__ import annotations

from backend.builder_profiles import effective_finish_as_option
from backend.service import PriceBookService


def _svc(tmp_path) -> PriceBookService:
    svc = PriceBookService(tmp_path / "finish.db")
    svc.init()
    return svc


def _item(vendor: str, finish: str, price: float, part: str = "T-1") -> dict:
    return {
        "vendor": vendor,
        "collection": "Tables",
        "part_number": part,
        "description": "Side Table",
        "species": "Oak",
        "finish_state": finish,
        "base_price": price,
        "multiplier": 2.7,
        "price_basis": "wholesale",
        "line_kind": "item",
        "source_file": "test.xlsx",
    }


def test_catalog_unfinished_is_an_option_and_search_defaults_finished(tmp_path):
    svc = _svc(tmp_path)
    svc.repo.insert_rows(
        [
            _item("Elite Designs", "finished", 200),
            _item("Elite Designs", "unfinished", 140),
        ]
    )

    assert "Unfinished" in svc.list_option_keys("Elite Designs")
    spec = effective_finish_as_option(
        {},
        finish_states=svc.repo.list_finish_states("Elite Designs"),
    )
    assert spec["default"] == "finished"
    assert spec["selects"] == "unfinished"

    finished = svc.search("Side Table", vendor="Elite Designs", limit=5)
    unfinished = svc.search(
        "Side Table",
        vendor="Elite Designs",
        option_key="Unfinished",
        limit=5,
    )
    assert not finished.empty
    assert finished.iloc[0]["finish_state"] == "finished"
    assert finished.iloc[0]["base_price"] == 200
    assert unfinished.iloc[0]["finish_state"] == "unfinished"
    assert unfinished.iloc[0]["base_price"] == 140
    assert unfinished.iloc[0]["base_price"] < finished.iloc[0]["base_price"]


def test_finished_only_builder_has_no_unfinished_option(tmp_path):
    svc = _svc(tmp_path)
    svc.repo.insert_rows([_item("Finished Only Co", "finished", 90)])
    assert "Unfinished" not in svc.list_option_keys("Finished Only Co")
    hit = svc.search("Side Table", vendor="Finished Only Co", limit=5)
    assert hit.iloc[0]["finish_state"] == "finished"


def test_unfinished_only_builder_still_surfaces_the_option(tmp_path):
    svc = _svc(tmp_path)
    svc.repo.insert_rows([_item("Unf Only Co", "unfinished", 80)])
    assert "Unfinished" in svc.list_option_keys("Unf Only Co")
    hit = svc.search("Side Table", vendor="Unf Only Co", finish_state="finished", limit=5)
    assert not hit.empty
    assert hit.iloc[0]["finish_state"] == "unfinished"
