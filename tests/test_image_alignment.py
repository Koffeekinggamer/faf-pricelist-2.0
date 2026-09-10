from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image

from backend.christina import review_image_alignment
from backend.db import init_db
from backend.image_alignment import (
    extract_sku_keys_from_text,
    keys_match,
    normalize_catalog_key,
    page_is_skipped_figure,
    viztech_image_policy,
)
from backend.service import PriceBookService


def _tiny_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (20, 40, 80)).save(buf, format="JPEG")
    return buf.getvalue()


def test_normalize_and_exact_key_match():
    assert normalize_catalog_key("1010") == "1010"
    assert normalize_catalog_key(" 10-10 ") == "1010"
    assert keys_match(part_number="1010", item_number="", extracted=["1010"])
    assert keys_match(part_number="1010", item_number="A1", extracted=["1010", "A1"])
    assert not keys_match(part_number="1010", item_number="A1", extracted=["1010"])
    assert not keys_match(part_number="1010", item_number="", extracted=["1024"])


def test_skip_covers_contents_charts():
    assert page_is_skipped_figure("Table of Contents")
    assert page_is_skipped_figure("Cover Price List 2026")
    assert page_is_skipped_figure("Wood species chart")
    assert not page_is_skipped_figure("1010 | Queen Slat Bed")


def test_extract_sku_keys_from_nearby_text():
    keys = extract_sku_keys_from_text("Shown: 1010 | Queen Slat Bed  also 9SE")
    assert "1010" in keys
    assert "9SE" in keys


def test_viztech_skip_when_builder_missing():
    policy = viztech_image_policy("Unknown Factory", slugs=["jmwoodworking"])
    assert policy["use_viztech"] is False
    assert policy["log"] == "viztech_images_skipped: builder_not_on_viztech"


def test_christina_never_fakes_a_vision_pass():
    review = review_image_alignment(
        builder="J & M Woodworking",
        part_number="1010",
        item_number="",
        extracted_keys=["1010"],
        descriptor="Queen slat bed",
        source="single",
        asset_key="assets/catalog_images/j-and-m-woodworking/1010.jpg",
        prior_hero=None,
        vision_available=False,
    )
    assert review["verdict"] == "pending_vision"
    assert review["verdict"] != "pass"


def test_christina_flags_key_or_builder_mismatch():
    review = review_image_alignment(
        builder="J & M Woodworking",
        part_number="1010",
        item_number="",
        extracted_keys=["1024"],
        descriptor="Wrong bed",
        source="single",
        asset_key="x.jpg",
        prior_hero=None,
        vision_available=False,
    )
    assert review["verdict"] == "flag"
    assert any("key" in f.lower() for f in review["findings"])


def test_search_hides_draft_heroes_until_override(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.init()
    svc.repo.insert_rows(
        [
            {
                "vendor": "J & M Woodworking",
                "collection": "Beds",
                "part_number": "1010",
                "description": "Queen Slat Bed",
                "species": "Br. Maple",
                "finish_state": "finished",
                "base_price": 100.0,
                "multiplier": 2.7,
                "adjusted_price": 270.0,
                "line_kind": "item",
                "source_file": "test",
                "imported_at": "2026-01-01",
            }
        ]
    )
    result = svc.ingest_single_catalog_image(
        vendor="J & M Woodworking",
        items=["1010"],
        image_bytes=_tiny_jpeg(),
        filename="1010.jpg",
        descriptor="Queen slat bed",
        notes="",
        image_root=tmp_path,
    )
    assert result["ok"]
    assert result["status"] == "draft"
    df = svc.search("1010", vendor="J & M Woodworking")
    assert df.iloc[0]["image_path"] is None or pd.isna(df.iloc[0]["image_path"])
    svc.override_catalog_image(
        vendor="J & M Woodworking",
        part_number="1010",
        reason="floor photo confirmed",
    )
    df2 = svc.search("1010", vendor="J & M Woodworking")
    assert str(df2.iloc[0]["image_path"]).endswith("1010.jpg")
