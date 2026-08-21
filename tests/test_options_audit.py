"""Whole-book Options audit through the same service the floor uses."""

from __future__ import annotations

from backend.db import init_db
from backend.options_audit import audit_catalog_options
from backend.service import PriceBookService


def _row(
    vendor: str,
    part: str,
    *,
    option: str | None = None,
    line_kind: str = "item",
    base: float = 100.0,
    retail: float = 270.0,
    pct: float | None = None,
    finish: str = "finished",
) -> dict:
    return {
        "vendor": vendor,
        "collection": "Catalog" if line_kind == "item" else "Addons",
        "part_number": part,
        "description": part,
        "option_key": option,
        "species": "Oak" if line_kind == "item" else None,
        "finish_state": finish,
        "base_price": base,
        "adjusted_price": retail,
        "addon_pct": pct,
        "multiplier": 2.7,
        "price_basis": "wholesale",
        "source_file": "book.xlsx",
        "line_kind": line_kind,
    }


def _service(tmp_path) -> PriceBookService:
    path = tmp_path / "book.db"
    init_db(path)
    return PriceBookService(path)


def test_audit_flags_a_builder_whose_search_options_are_empty(tmp_path):
    svc = _service(tmp_path)
    svc.repo.insert_rows([_row("Empty Builder", "T1")])

    report = audit_catalog_options(svc)
    builder = report["builders"][0]

    assert report["builder_count"] == 1
    assert builder["vendor"] == "Empty Builder"
    assert builder["search_options"] == []
    assert "Search Options empty" in builder["issues"]


def test_audit_proves_charge_shapes_retail_and_quantity_labels(tmp_path):
    svc = _service(tmp_path)
    svc.repo.insert_rows(
        [
            _row("Good Builder", "D1", finish="finished"),
            _row("Good Builder", "D1-U", finish="unfinished"),
            _row(
                "Good Builder",
                "Per Knob",
                option="Per Knob",
                line_kind="addon",
                base=5.0,
                retail=14.0,
            ),
            _row(
                "Good Builder",
                "Two-tone",
                option="Two-tone",
                line_kind="addon",
                base=0.0,
                retail=0.0,
                pct=10.0,
            ),
        ]
    )

    report = audit_catalog_options(svc)
    builder = report["builders"][0]

    assert builder["charge_shapes"] == {"dollar": 1, "percent": 1, "zero": 0}
    assert builder["retail_mismatches"] == []
    assert builder["quantity_options"] == ["Per Knob"]
    assert "Unfinished" in builder["search_options"]
    assert builder["issues"] == []


def test_audit_reports_wrong_stored_retail_without_rewriting_it(tmp_path):
    svc = _service(tmp_path)
    svc.repo.insert_rows(
        [
            _row("Bad Builder", "T1"),
            _row(
                "Bad Builder",
                "Per Shelf",
                option="Per Shelf",
                line_kind="addon",
                base=10.0,
                retail=99.0,
            ),
        ]
    )

    report = audit_catalog_options(svc)
    builder = report["builders"][0]

    assert builder["retail_mismatches"] == [
        {
            "option": "Per Shelf",
            "stored_retail": 99.0,
            "expected_retail": 28.0,
        }
    ]
    assert "1 add-on retail calculation mismatch" in builder["issues"]


def test_audit_rejects_a_deduct_label_stored_as_a_positive_charge(tmp_path):
    svc = _service(tmp_path)
    svc.repo.insert_rows(
        [
            _row("Wrong Sign Builder", "B1"),
            _row(
                "Wrong Sign Builder",
                "Low Footboard (DEDUCT)",
                option="Low Footboard (DEDUCT)",
                line_kind="addon",
                base=20.0,
                retail=54.0,
            ),
        ]
    )

    builder = audit_catalog_options(svc)["builders"][0]

    assert builder["deduction_sign_mismatches"] == ["Low Footboard (DEDUCT)"]
    assert "1 deduction stored as a positive charge" in builder["issues"]
