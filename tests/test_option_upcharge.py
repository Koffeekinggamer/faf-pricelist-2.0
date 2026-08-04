"""Option upcharge: a flat drawer/door Option raises eligible items' retail (ADR-0008 follow-up)."""

from __future__ import annotations

from backend.service import PriceBookService


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
    # Retail raised by exactly the flat charge (independent literal: 1000 + 54).
    assert dresser["adjusted_price"] == 1054.0
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
