"""Option upcharge: a flat drawer/door Option raises eligible items' retail (ADR-0008 follow-up)."""

from __future__ import annotations

import pytest

from backend.service import PriceBookService
from backend.standardize import standardize_row


def _svc(tmp_path):
    svc = PriceBookService(db_path=str(tmp_path / "opt.db"))
    svc.init()
    return svc


def _item(vendor, coll, part, desc, retail, finish="finished"):
    return {
        "vendor": vendor,
        "collection": coll,
        "part_number": part,
        "description": desc,
        "species": "Brown Maple",
        "finish_state": finish,
        "base_price": round(retail / 2.7, 2),
        "adjusted_price": retail,
        "line_kind": "item",
    }


def _addon(vendor, label, base, retail):
    return {
        "vendor": vendor,
        "collection": "Addons",
        "part_number": label,  # flat form: part_number == option label
        "description": f"{label} adder",
        "option_key": label,
        "base_price": base,
        "adjusted_price": retail,
        "line_kind": "addon",
    }


def _addon_cat(vendor, label, category, base, retail):
    # Per-category addon: part_number carries the furniture category prefix.
    return {
        "vendor": vendor,
        "collection": "Addons",
        "part_number": f"{category} - {label}",
        "description": f"{label} adder ({category})",
        "option_key": label,
        "base_price": base,
        "adjusted_price": retail,
        "line_kind": "addon",
    }


def test_flat_drawer_option_upcharges_only_eligible_items(tmp_path):
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _item(V, "Bedroom", "B1", "Queen Bed", 2000.0),
        _addon(V, "Undermount Drawer Slides", 20.0, 54.0),
    ])

    res = svc.search("", vendor=V, option_key="Undermount Drawer Slides")
    parts = set(res["part_number"])

    # Drawered item is eligible; bed is not; the standalone addon row is not shown.
    assert "D1" in parts
    assert "B1" not in parts
    assert "Undermount Drawer Slides" not in parts

    dresser = res[res["part_number"] == "D1"].iloc[0]
    # Slides are passed through at wholesale with no markup: 1000 + 20.
    assert dresser["adjusted_price"] == 1020.0
    assert dresser["option_key"] == "Undermount Drawer Slides"
    assert "Undermount Drawer Slides" in str(dresser["notes"])


def test_finish_option_upcharges_every_wood_item_by_category(tmp_path):
    # A finish option (Paint) applies to EVERY physical wood item; the charge
    # comes from the item's matched category. Non-wood accessories are excluded.
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "Q1", "Queen Panel Bed", 2000.0),
        _item(V, "Bedroom", "D9", "9 Drawer Dresser", 1000.0),
        {
            "vendor": V, "collection": "Misc", "part_number": "AC1",
            "description": "Knob Set", "species": None, "finish_state": "finished",
            "base_price": 10.0, "adjusted_price": 27.0, "line_kind": "item",
        },
        _addon_cat(V, "Paint", "Queen Bed", 130.0, 352.0),
        _addon_cat(V, "Paint", "9 Drawer Dresser", 150.0, 406.0),
    ])

    res = svc.search("", vendor=V, option_key="Paint")
    parts = set(res["part_number"])
    assert "Q1" in parts and "D9" in parts   # every wood item eligible
    assert "AC1" not in parts                # non-wood accessory excluded

    q = res[res["part_number"] == "Q1"].iloc[0]
    d = res[res["part_number"] == "D9"].iloc[0]
    assert q["adjusted_price"] == 2352.0     # 2000 + Queen Bed Paint 352
    assert d["adjusted_price"] == 1406.0     # 1000 + 9 Drawer Dresser Paint 406
    assert "Queen Bed" in str(q["notes"])
    assert "9 Drawer Dresser" in str(d["notes"])


def test_percent_addon_raises_eligible_items_by_pct(tmp_path):
    """addon_pct Option: retail += item_retail × pct/100 (ADR-0008 / ADR-0011)."""
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _item(V, "Bedroom", "B1", "Queen Bed", 2000.0),
        {
            "vendor": V,
            "collection": "Addons",
            "part_number": "Premium Drawer Slides",
            "description": "Premium Drawer Slides pct",
            "option_key": "Premium Drawer Slides",
            "base_price": None,
            "adjusted_price": None,
            "addon_pct": 10.0,
            "line_kind": "addon",
        },
    ])

    res = svc.search("", vendor=V, option_key="Premium Drawer Slides")
    parts = set(res["part_number"])
    assert "D1" in parts
    assert "B1" not in parts
    dresser = res[res["part_number"] == "D1"].iloc[0]
    # 1000 + 10% = 1100
    assert dresser["adjusted_price"] == 1100.0
    assert "+10%" in str(dresser["notes"])


def test_multi_options_stack_upcharges(tmp_path):
    """Selecting Paint + Undermount Drawer Slides stacks both on a dresser."""
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D9", "9 Drawer Dresser", 1000.0),
        _item(V, "Bedroom", "Q1", "Queen Panel Bed", 2000.0),
        _addon(V, "Undermount Drawer Slides", 20.0, 54.0),
        _addon_cat(V, "Paint", "9 Drawer Dresser", 150.0, 406.0),
        _addon_cat(V, "Paint", "Queen Bed", 130.0, 352.0),
    ])

    res = svc.search(
        "",
        vendor=V,
        option_key=["Paint", "Undermount Drawer Slides"],
    )
    parts = set(res["part_number"])
    assert "D9" in parts
    assert "Q1" in parts  # bed gets Paint only

    dresser = res[res["part_number"] == "D9"].iloc[0]
    bed = res[res["part_number"] == "Q1"].iloc[0]
    # Dresser: 1000 + Paint 406 + Slides wholesale 20
    assert dresser["adjusted_price"] == 1426.0
    assert "Paint" in str(dresser["notes"]) and "Undermount Drawer Slides" in str(dresser["notes"])
    # Bed: 2000 + Paint 352 (not eligible for drawer slides)
    assert bed["adjusted_price"] == 2352.0
    assert "Paint" in str(bed["notes"])
    assert "Undermount Drawer Slides" not in str(bed["notes"])


def test_fn_chair_cat_filters_before_fabric_upcharge(tmp_path):
    """Cat.N is a priced item variant; fabric adds to that selected variant."""
    svc = _svc(tmp_path)
    vendor = "FN Chair"
    svc.repo.insert_rows(
        [
            {
                **_item(vendor, "Seating", "Abe Side Chair", "Abe Side Chair", 304.0),
                "base_price": 112.0,
                "option_key": None,
            },
            {
                **_item(
                    vendor,
                    "Seating",
                    "Abe Side Chair",
                    "Abe Side Chair - Cat. 1",
                    428.0,
                ),
                "base_price": 158.0,
                "option_key": "Cat. 1",
            },
            _addon_cat(
                vendor,
                "Solid Fabrics / COM / Faux Leathers",
                "Abe Side Chair",
                25.0,
                68.0,
            ),
        ]
    )

    result = svc.search(
        "Abe Side Chair",
        vendor=vendor,
        option_key=["Cat. 1", "Solid Fabrics / COM / Faux Leathers"],
    )

    assert len(result) == 1
    assert result.iloc[0]["base_price"] == 183.0
    assert result.iloc[0]["adjusted_price"] == 496.0


def test_fn_chair_keeps_one_category_when_two_are_passed(tmp_path):
    """Cat. 1/2/3 are alternatives — the newest pick replaces the earlier one."""
    svc = _svc(tmp_path)
    vendor = "FN Chair"
    svc.repo.insert_rows(
        [
            {
                **_item(
                    vendor,
                    "Seating",
                    "Abe Side Chair",
                    "Abe Side Chair - Cat. 1",
                    428.0,
                ),
                "base_price": 158.0,
                "option_key": "Cat. 1",
            },
            {
                **_item(
                    vendor,
                    "Seating",
                    "Abe Side Chair",
                    "Abe Side Chair - Cat. 2",
                    528.0,
                ),
                "base_price": 195.0,
                "option_key": "Cat. 2",
            },
            _addon_cat(
                vendor,
                "Solid Fabrics / COM / Faux Leathers",
                "Abe Side Chair",
                25.0,
                68.0,
            ),
        ]
    )

    result = svc.search(
        "Abe Side Chair",
        vendor=vendor,
        option_key=["Cat. 1", "Cat. 2", "Solid Fabrics / COM / Faux Leathers"],
    )

    assert len(result) == 1
    # Cat. 2 wholesale 195 + fabric 25, retail to the next even dollar.
    assert result.iloc[0]["base_price"] == 220.0
    assert result.iloc[0]["adjusted_price"] == 596.0


def test_mirrors_exempt_from_drawer_door_options(tmp_path):
    """Mirrors never get drawer/door upcharges (even console / vanity mirrors)."""
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _item(V, "Bedroom", "M1", "Tri-View Mirror", 500.0),
        _item(V, "Bedroom", "M2", "Console Mirror", 400.0),
        _addon(V, "Undermount Drawer Slides", 20.0, 54.0),
        _addon(V, "Extra Drawers or Doors", 30.0, 81.0),
    ])

    slides = svc.search("", vendor=V, option_key="Undermount Drawer Slides")
    assert "D1" in set(slides["part_number"])
    assert "M1" not in set(slides["part_number"])
    assert "M2" not in set(slides["part_number"])

    doors = svc.search("", vendor=V, option_key="Extra Drawers or Doors")
    assert "D1" in set(doors["part_number"])
    assert "M1" not in set(doors["part_number"])
    assert "M2" not in set(doors["part_number"])


def test_any_drawer_option_gets_a_qty_control():
    allowed = PriceBookService._option_qty_allowed
    assert allowed("Cedar Drawer Bottoms")
    assert allowed("Cedar Lined Drawers")
    assert allowed("Hidden Drawers")
    assert allowed("Extra Drawers or Doors")
    assert allowed("Undermount Drawer Slides")
    assert allowed("Soft Close Slides")
    assert allowed("Beveled Glass Per Door")
    assert allowed("Additional Shelves (Each)")
    assert allowed("Add Adj Shelves")
    assert allowed("Per Knob")
    assert allowed("Additional leaves")
    assert not allowed("Two-tone")
    assert not allowed("Lock")
    assert not allowed("Distressing")
    assert not allowed("Set of 4 LED Lights w/ 1 Touch Switch")
    assert not allowed("2 Drawer Armoire")
    assert not allowed("Without Drawers")
    assert not allowed("Docking Drawer In Drawer")
    assert not allowed("USB port in nightstand drawer")


def test_per_knob_qty_multiplies_the_selected_piece_charge(tmp_path):
    svc = _svc(tmp_path)
    vendor = "J. Troyer & Company"
    svc.repo.insert_rows(
        [
            _item(vendor, "Dining", "SB1", "Charleston Sideboard", 1000.0),
            _addon(vendor, "Per Knob", 5.0, 14.0),
        ]
    )

    three = svc.search(
        "SB1",
        vendor=vendor,
        option_key="Per Knob",
        option_qty={"Per Knob": 3},
    )

    assert len(three) == 1
    assert float(three.iloc[0]["adjusted_price"]) == 1000.0 + 14.0 * 3
    assert three.iloc[0]["option_key"] == "Per Knob ×3"
    assert "×3" in str(three.iloc[0]["notes"])


def test_deduct_option_stays_negative_and_lowers_retail(tmp_path):
    row = standardize_row(
        {
            "vendor": "Criswell Bedroom",
            "collection": "Addons",
            "part_number": '20" high low footboard (DEDUCT)',
            "description": '20" high low footboard (DEDUCT)',
            "option_key": '20" high low footboard (DEDUCT)',
            "line_kind": "addon",
            "base_price": -203.0,
            "multiplier": 2.7,
        }
    )
    assert row is not None
    assert row["base_price"] == -203.0
    assert row["adjusted_price"] == -550.0

    svc = _svc(tmp_path)
    vendor = "Criswell Bedroom"
    svc.repo.insert_rows(
        [
            _item(vendor, "Bedroom", "B1", "Charleston Bed", 2000.0),
            row,
        ]
    )
    result = svc.search(
        "B1",
        vendor=vendor,
        option_key='20" high low footboard (DEDUCT)',
    )
    assert float(result.iloc[0]["adjusted_price"]) == 1450.0


def test_visible_less_row_keeps_negative_charge_when_label_says_without():
    row = standardize_row(
        {
            "vendor": "Black Horse Furniture",
            "line_kind": "addon",
            "option_key": "Without Drawers",
            "description": "Without Drawers",
            "base_price": -45,
            "price_basis": "wholesale",
            "notes": "deduction from visible row",
            "multiplier": 2,
        }
    )

    assert row is not None
    assert row["base_price"] == -45
    assert row["adjusted_price"] == -90


def test_quote_required_option_survives_standardization_with_no_price():
    """A call-for-quote choice is a real Option. Dropping it hides it from the floor."""
    row = standardize_row(
        {
            "vendor": "Premier Woodcraft",
            "line_kind": "addon",
            "option_key": "Leather",
            "description": "Leather",
            "base_price": None,
            "price_basis": "wholesale",
            "notes": "quote required — factory does not publish a price",
            "multiplier": 2.7,
        }
    )

    assert row is not None
    assert row["base_price"] is None
    assert row["adjusted_price"] is None
    assert row["option_key"] == "Leather"


def test_cedar_drawer_bottoms_qty_multiplies_flat_charge(tmp_path):
    svc = _svc(tmp_path)
    V = "Millcraft"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "NS1", "3 Drawer Nightstand", 1000.0),
        _addon(V, "Cedar Drawer Bottoms", 80.0, 216.0),
    ])

    three = svc.search(
        "",
        vendor=V,
        option_key="Cedar Drawer Bottoms",
        option_qty={"Cedar Drawer Bottoms": 3},
    )
    row = three.iloc[0]
    assert float(row["adjusted_price"]) == 1000.0 + 216.0 * 3
    assert "×3" in str(row["notes"])
    """Qty N stacks the Extra Drawers or Doors flat charge N times."""
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _addon(V, "Extra Drawers or Doors", 30.0, 81.0),
    ])

    one = svc.search("", vendor=V, option_key="Extra Drawers or Doors")
    assert float(one.iloc[0]["adjusted_price"]) == 1081.0

    three = svc.search(
        "",
        vendor=V,
        option_key="Extra Drawers or Doors",
        option_qty={"Extra Drawers or Doors": 3},
    )
    dresser = three.iloc[0]
    assert float(dresser["adjusted_price"]) == 1000.0 + 81.0 * 3
    assert "×3" in str(dresser["notes"])


def test_undermount_slides_qty_multiplies_flat_charge(tmp_path):
    """Qty N stacks Undermount Drawer Slides flat charge N times."""
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _addon(V, "Undermount Drawer Slides", 20.0, 54.0),
    ])

    three = svc.search(
        "",
        vendor=V,
        option_key="Undermount Drawer Slides",
        option_qty={"Undermount Drawer Slides": 3},
    )
    dresser = three.iloc[0]
    assert float(dresser["adjusted_price"]) == 1000.0 + 20.0 * 3
    assert "×3" in str(dresser["notes"])


def test_future_imports_store_undermount_slides_without_markup():
    row = standardize_row(
        {
            "vendor": "Any Future Builder",
            "collection": "Addons",
            "part_number": "Undermount Drawer Slides",
            "description": "Undermount Drawer Slides",
            "option_key": "Undermount Drawer Slides",
            "line_kind": "addon",
            "base_price": 17.5,
            "multiplier": 2.7,
        }
    )
    assert row is not None
    assert row["multiplier"] == 1.0
    assert row["adjusted_price"] == 17.5
