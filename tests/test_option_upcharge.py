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


def test_finish_option_does_not_upcharge_items(tmp_path):
    # "Paint" is a per-category finish upcharge, not a drawer/door option: items
    # must keep their own price (prior behaviour), so D1 is never returned upcharged.
    svc = _svc(tmp_path)
    V = "Test Builder"
    svc.repo.insert_rows([
        _item(V, "Bedroom", "D1", "6 Drawer Dresser", 1000.0),
        _addon(V, "Paint", 50.0, 135.0),
    ])

    res = svc.search("", vendor=V, option_key="Paint")
    if (res["part_number"] == "D1").any():
        assert res[res["part_number"] == "D1"].iloc[0]["adjusted_price"] == 1000.0
