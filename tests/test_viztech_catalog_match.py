"""Viztech catalog photos match pricebook SKUs; extras stay unmatched."""

from PIL import Image

from backend.viztech_catalog_match import (
    is_catalog_download_label,
    looks_like_negative,
    match_filename_to_part,
    match_vendor_to_slug,
    photo_clarity_score,
    restore_negative,
)


def test_vendor_slug_maps_book_names():
    slugs = [
        "ashery-oak",
        "criswell-furniture",
        "fn-chairs-llc",
        "jm-woodworking",
        "lamb-woodworking",
        "nisley-cabinets-llc",
        "windy-acres",
        "stoney-acres-furniture-2",
        "genuine-oak-designs",
        "weaver-woodcraft",
    ]
    assert match_vendor_to_slug("Five Star Tables", slugs) == "weaver-woodcraft"
    assert match_vendor_to_slug("Ashery Oak", slugs) == "ashery-oak"
    assert match_vendor_to_slug("Criswell Bedroom", slugs) == "criswell-furniture"
    assert match_vendor_to_slug("FN Chair", slugs) == "fn-chairs-llc"
    assert match_vendor_to_slug("J & M Woodworking", slugs) == "jm-woodworking"
    assert match_vendor_to_slug("LAMB", slugs) == "lamb-woodworking"
    assert match_vendor_to_slug("Nisley Cabinet LLC", slugs) == "nisley-cabinets-llc"
    assert match_vendor_to_slug("Windy Acres Furniture", slugs) == "windy-acres"
    assert match_vendor_to_slug("Genuine Oak", slugs) == "genuine-oak-designs"


def test_filename_matches_known_sku_only():
    known = {"BF-1648-DS", "1010", "9SE"}
    assert match_filename_to_part("BF-1648-DS.jpg", known) == "BF-1648-DS"
    assert match_filename_to_part("bf_1648_ds.png", known) == "BF-1648-DS"
    assert match_filename_to_part("1010.jpg", known) == "1010"
    assert match_filename_to_part("ZZZ99.jpg", known) is None
    assert match_filename_to_part("table.jpg", known) is None
    assert match_filename_to_part("BF-1648-DS-Front.jpg", known) == "BF-1648-DS"
    assert match_filename_to_part("bf1648ds_side.webp", known) == "BF-1648-DS"


def test_clear_studio_shot_scores_above_inverted_pdf_extract():
    clear = Image.new("RGB", (80, 80), (245, 245, 245))
    for x in range(25, 55):
        for y in range(25, 55):
            clear.putpixel((x, y), (160, 110, 70))
    negative = Image.new("RGB", (80, 80), (5, 5, 5))
    for x in range(25, 55):
        for y in range(25, 55):
            negative.putpixel((x, y), (80, 140, 190))
    assert looks_like_negative(negative) is True
    assert looks_like_negative(clear) is False
    assert photo_clarity_score(clear, "BF-1648-DS.jpg") > photo_clarity_score(
        negative, "1010.jpg"
    )
    flipped = restore_negative(negative)
    assert looks_like_negative(flipped) is False


def test_catalog_label_skips_pricelists():
    assert is_catalog_download_label("2026 Catalog") is True
    assert is_catalog_download_label("Product Catalog") is True
    assert is_catalog_download_label("2026 Pricelist") is False
    assert is_catalog_download_label("Branding Files") is False
