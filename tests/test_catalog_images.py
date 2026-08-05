"""Catalog image matcher + search image_path attachment."""

from __future__ import annotations

import pandas as pd

from backend.catalog_images import (
    CaptionHit,
    ImageHit,
    MatchedImage,
    captions_from_words,
    is_sku_token,
    match_captions_to_images,
    plan_upserts,
    relative_image_path,
)
from backend.db import init_db
from backend.service import PriceBookService


def test_is_sku_token_requires_digit():
    assert is_sku_token("1010")
    assert is_sku_token("9SE")
    assert is_sku_token("1047-SLT")
    assert not is_sku_token("Maple")
    assert not is_sku_token("OCS")
    assert not is_sku_token("")


def test_captions_from_words_finds_sku_pipe():
    words = [
        {"text": "1010", "x0": 10, "x1": 40, "top": 200, "bottom": 210, "height": 10},
        {"text": "|", "x0": 42, "x1": 48, "top": 199, "bottom": 209, "height": 10},
        {"text": "Queen", "x0": 50, "x1": 90, "top": 200, "bottom": 210, "height": 10},
        {"text": "Maple", "x0": 10, "x1": 50, "top": 220, "bottom": 228, "height": 8},
        {"text": "|", "x0": 52, "x1": 58, "top": 220, "bottom": 228, "height": 8},
        {"text": "Cocoa", "x0": 60, "x1": 100, "top": 220, "bottom": 228, "height": 8},
        {"text": "9SE", "x0": 200, "x1": 230, "top": 200, "bottom": 210, "height": 10},
        {"text": "|", "x0": 232, "x1": 238, "top": 199, "bottom": 209, "height": 10},
    ]
    caps = captions_from_words(words)
    skus = {c.sku for c in caps}
    assert skus == {"1010", "9SE"}


def test_match_captions_to_images_nearest_above():
    caps = [
        CaptionHit(sku="1010", x0=70, top=200, x1=100, bottom=210),
        CaptionHit(sku="9SE", x0=330, top=200, x1=360, bottom=210),
    ]
    images = [
        ImageHit(
            name="Im0",
            x0=60,
            top=20,
            x1=280,
            bottom=190,
            width=220,
            height=170,
            page=3,
        ),
        ImageHit(
            name="Im1",
            x0=320,
            top=40,
            x1=540,
            bottom=190,
            width=220,
            height=150,
            page=3,
        ),
    ]
    matched = match_captions_to_images(caps, images)
    by_sku = {m.sku: m.image.name for m in matched}
    assert by_sku == {"1010": "Im0", "9SE": "Im1"}


def test_primary_captions_drops_inline_accessory_sku():
    from backend.catalog_images import primary_captions

    caps = [
        CaptionHit(sku="1010", x0=64, top=209, x1=90, bottom=219),
        CaptionHit(sku="2013", x0=188, top=209, x1=220, bottom=219),
        CaptionHit(sku="1006", x0=331, top=209, x1=360, bottom=219),
    ]
    skus = [c.sku for c in primary_captions(caps)]
    assert skus == ["1010", "1006"]


def test_plan_upserts_skips_unknown_and_maps_known():
    matched = [
        MatchedImage(
            sku="1010",
            image=ImageHit("Im0", 0, 0, 100, 100, 100, 100, 1),
            page=1,
        ),
        MatchedImage(
            sku="ZZZ99",
            image=ImageHit("Im1", 0, 0, 100, 100, 100, 100, 1),
            page=1,
        ),
        MatchedImage(
            sku="9se",  # case-insensitive match to DB
            image=ImageHit("Im2", 0, 0, 100, 100, 100, 100, 2),
            page=2,
        ),
    ]
    plan = plan_upserts(
        matched,
        known_part_numbers={"1010", "9SE", "6700"},
        vendor="J & M Woodworking",
        source_file="catalog.pdf",
    )
    assert plan["matched_count"] == 2
    parts = {u["part_number"] for u in plan["upserts"]}
    assert parts == {"1010", "9SE"}
    assert plan["skipped_unknown"] == ["ZZZ99"]
    assert "6700" in plan["missing_photo_skus"]
    assert plan["upserts"][0]["image_path"] == relative_image_path("1010")


def test_search_includes_image_path(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.init()
    # Seed one item + catalog image
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
    img_rel = relative_image_path("1010")
    # Create a tiny file so UI resolution would succeed; search only needs path in DB.
    dest = tmp_path / img_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"not-a-real-jpeg")
    svc.repo.upsert_catalog_image(
        vendor="J & M Woodworking",
        part_number="1010",
        image_path=img_rel,
        source_file="catalog.pdf",
        page=3,
        match_method="nearest_caption",
        updated_at="2026-01-01T00:00:00Z",
    )
    df = svc.search("1010", vendor="J & M Woodworking")
    assert not df.empty
    assert "image_path" in df.columns
    assert df.iloc[0]["image_path"] == img_rel


def test_search_image_path_none_without_catalog_row(tmp_path):
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
    df = svc.search("1010", vendor="J & M Woodworking")
    assert not df.empty
    assert df.iloc[0]["image_path"] is None or pd.isna(df.iloc[0]["image_path"])


def test_vendors_with_catalog_images_lists_photographed_builders(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.init()
    assert svc.vendors_with_catalog_images() == set()
    svc.repo.upsert_catalog_image(
        vendor="J & M Woodworking",
        part_number="1010",
        image_path=relative_image_path("1010"),
        source_file="catalog.pdf",
        page=3,
        match_method="nearest_caption",
        updated_at="2026-01-01T00:00:00Z",
    )
    # Search may land on SKUs without photos; the builder still counts, which is
    # what keeps the Image column from vanishing mid-search.
    assert svc.vendors_with_catalog_images() == {"J & M Woodworking"}
