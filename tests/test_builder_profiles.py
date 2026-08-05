"""Builder Profiles loader (ADR-0011) — durable rules only; charges stay in DB."""

from __future__ import annotations

import json
from pathlib import Path

from backend.builder_profiles import (
    DEFAULT_PROFILE,
    clear_profile_cache,
    load_builder_profile,
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
