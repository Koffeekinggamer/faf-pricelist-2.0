"""Smart Drop parse inventories each builder's variants from the file."""

from __future__ import annotations

from backend.smart_parse import summarize_parse_variants, variants_caption


def test_summarize_separates_woods_stains_and_upcharges():
    rows = [
        {
            "line_kind": "item",
            "part_number": "46",
            "description": "Nightstand",
            "collection": "Bedroom",
            "species": "Brown Maple",
            "finish_state": "finished",
            "option_key": None,
        },
        {
            "line_kind": "item",
            "part_number": "46",
            "description": "Nightstand",
            "collection": "Bedroom",
            "species": "Cherry",
            "finish_state": "finished",
            "option_key": None,
        },
        {
            "line_kind": "item",
            "part_number": "80",
            "description": "King Panel Bed",
            "collection": "Beds",
            "species": "Oak",
            "finish_state": "finished",
            "option_key": "Flat Panel",
        },
        {
            "line_kind": "addon",
            "part_number": "Paint",
            "description": "Paint",
            "option_key": "Paint",
            "species": None,
        },
        {
            "line_kind": "addon",
            "part_number": "Extra Drawers or Doors",
            "description": "Extra Drawers or Doors",
            "option_key": "Extra Drawers or Doors",
        },
    ]
    summary = summarize_parse_variants(
        rows,
        vendor="Test Builder",
        sheets_tried=[{"layout": "wide_species"}, {"layout": "skip"}],
    )
    assert summary["layouts"] == ["wide_species"]
    assert summary["item_count"] == 2
    assert "Brown Maple" in summary["woods"]
    assert "Cherry" in summary["woods"]
    assert "Oak" in summary["woods"]
    assert "Paint" in summary["stains"]
    assert "Paint" in summary["addons"]
    assert "Extra Drawers or Doors" in summary["addons"]
    assert "Flat Panel" in summary["customizations"]
    assert "Bedroom" in summary["collections"]
    cap = variants_caption(summary)
    assert "woods" in cap and "upcharges" in cap


def test_unknown_builder_still_gets_a_variant_inventory():
    rows = [
        {
            "line_kind": "item",
            "part_number": "X1",
            "description": "Chair",
            "collection": "Seating",
            "species": "Walnut",
            "finish_state": "unfinished",
            "option_key": "Cat. 1",
        }
    ]
    summary = summarize_parse_variants(rows, vendor="Brand New Factory")
    assert summary["woods"] == ["Walnut"]
    assert summary["finishes"] == ["unfinished"]
    assert summary["customizations"] == ["Cat. 1"]
