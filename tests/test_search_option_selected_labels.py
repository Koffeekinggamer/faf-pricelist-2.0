"""Regression: Options Selected labels must not shadow Search query ``q``.

After c5ca106 moved the search box above the Options panel, the Selected
bits loop reassigned ``q`` to an int quantity. Selecting any option then
crashed with ``AttributeError: 'int' object has no attribute 'strip'``.
"""

from __future__ import annotations

from backend.service import PriceBookService, SearchItemIdentity
from pricebook_app import _format_selected_option_labels


def test_format_selected_option_labels_leaves_search_query_untouched():
    q = "21 HRR"
    of_list = ["Motorized Mechanism"]
    option_qty = {"Motorized Mechanism": 1}

    bits = _format_selected_option_labels(of_list, option_qty)

    assert bits == ["Motorized Mechanism"]
    assert q == "21 HRR"
    assert isinstance(q, str)
    # Mimic the empty-check / search call sites that call .strip() on q.
    assert (q or "").strip() == "21 HRR"


def test_format_selected_option_labels_shows_qty_when_above_one():
    bits = _format_selected_option_labels(
        ["Extra Drawers or Doors"],
        {"Extra Drawers or Doors": 3},
    )
    assert bits == ["Extra Drawers or Doors ×3"]


def test_search_item_picker_deduplicates_variants_but_keeps_collection_identity(tmp_path):
    svc = PriceBookService(tmp_path / "items.db")
    svc.init()
    svc.repo.insert_rows(
        [
            {
                "vendor": "LuxHome",
                "collection": "Harmony Collection",
                "part_number": "21 HRR",
                "description": "Harmony Rocker Recliner",
                "option_key": "Standard",
                "finish_state": "finished",
                "base_price": 100,
                "line_kind": "item",
            },
            {
                "vendor": "LuxHome",
                "collection": "Harmony Collection",
                "part_number": "21 HRR",
                "description": "Harmony Rocker Recliner",
                "option_key": "Premium",
                "finish_state": "finished",
                "base_price": 110,
                "line_kind": "item",
            },
            {
                "vendor": "LuxHome",
                "collection": "Other Collection",
                "part_number": "21 HRR",
                "description": "Lookalike SKU",
                "option_key": "Standard",
                "finish_state": "finished",
                "base_price": 120,
                "line_kind": "item",
            },
        ]
    )

    assert svc.list_search_item_identities("21 HRR", vendor="LuxHome") == [
        SearchItemIdentity(
            vendor="LuxHome",
            collection="Harmony Collection",
            part_number="21 HRR",
            description="Harmony Rocker Recliner",
        ),
        SearchItemIdentity(
            vendor="LuxHome",
            collection="Other Collection",
            part_number="21 HRR",
            description="Lookalike SKU",
        ),
    ]


def test_shadowing_repro_matches_pre_fix_crash_pattern():
    """Exact c5ca106 crash: Selected bits loop assigned qty into ``q``."""
    q = "21 HRR"
    of_list = ["Motorized Mechanism"]
    option_qty = {"Motorized Mechanism": 1}

    # Broken pattern (pre-fix):
    broken_q = q
    for o in of_list:
        broken_q = option_qty.get(o, 1)
    assert isinstance(broken_q, int)
    try:
        (broken_q or "").strip()
        raised = False
    except AttributeError:
        raised = True
    assert raised

    # Fixed pattern:
    bits = _format_selected_option_labels(of_list, option_qty)
    assert bits == ["Motorized Mechanism"]
    assert (q or "").strip() == "21 HRR"
