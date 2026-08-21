"""Builder Profiles loader (ADR-0011) — durable rules only; charges stay in DB."""

from __future__ import annotations

import json
from pathlib import Path

from backend.builder_profiles import (
    DEFAULT_PROFILE,
    clear_profile_cache,
    list_locked_parsers,
    load_builder_profile,
    match_profile_vendor,
    save_parser_lock,
    vendor_slug,
)


def test_vendor_slug_j_and_m():
    assert vendor_slug("J & M Woodworking") == "j-and-m-woodworking"
    assert vendor_slug("j and m woodworking") == "j-and-m-woodworking"


def test_load_j_and_m_profile_from_repo():
    clear_profile_cache()
    p = load_builder_profile("J & M Woodworking")
    assert p["vendor"] == "J & M Woodworking"
    assert "drawer" in p["item_upcharge_option_keywords"]
    assert "dresser" in p["drawer_door_item_keywords"]
    assert any(
        "manschest" in (r.get("match_category_any") or [])
        for r in p["category_synonym_overrides"]
    )
    assert (p.get("parser") or {}).get("importer") == "jmw"


def test_unknown_vendor_gets_default_vocab():
    clear_profile_cache()
    p = load_builder_profile("Test Builder")
    assert p["item_upcharge_option_keywords"] == DEFAULT_PROFILE["item_upcharge_option_keywords"]
    assert p["drawer_door_item_keywords"] == DEFAULT_PROFILE["drawer_door_item_keywords"]


def test_custom_profile_root(tmp_path: Path):
    clear_profile_cache()
    data = {
        "version": 1,
        "vendor": "Acme Furniture",
        "item_upcharge_option_keywords": ["soft-close"],
        "drawer_door_item_keywords": ["drawer"],
        "compound_item_markers": [],
        "category_synonym_overrides": [],
    }
    path = tmp_path / "acme-furniture.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    p = load_builder_profile("Acme Furniture", root=tmp_path)
    assert p["item_upcharge_option_keywords"] == ["soft-close"]
    assert p["drawer_door_item_keywords"] == ["drawer"]


def test_profile_module_owns_parser_lock_lifecycle(tmp_path: Path):
    path = save_parser_lock(
        "Acme Furniture",
        importer="jmw",
        source_file="Acme_2026_Pricelist.xlsx",
        layouts=["jmw_br_maple_expand"],
        root=tmp_path,
    )
    assert path is not None
    assert match_profile_vendor("Acme_2027_Pricelist.xlsx", root=tmp_path) == (
        "Acme Furniture"
    )
    assert list_locked_parsers(root=tmp_path) == [
        {
            "vendor": "Acme Furniture",
            "importer": "jmw",
            "source_file": "Acme_2026_Pricelist.xlsx",
        }
    ]

    # A generic fallthrough can add safe filename metadata but cannot weaken
    # the settled reader.
    save_parser_lock(
        "Acme Furniture",
        importer="generic",
        source_file="Acme_2027_Pricelist.xlsx",
        layouts=["long_flat"],
        root=tmp_path,
    )
    assert (load_builder_profile("Acme Furniture", root=tmp_path)["parser"])[
        "importer"
    ] == "jmw"
    assert not path.with_suffix(".json.tmp").exists()
