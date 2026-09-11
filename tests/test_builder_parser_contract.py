"""Settled builders MUST keep their own reader on every future upload.

Each builder here has been perfected and locked. The contract:
  1. the shipped profile names that builder's own importer, never `generic`;
  2. the builder's own detector claims their workbook shape;
  3. next year's filename still resolves to the builder and the same importer;
  4. a fallthrough Load can never downgrade the lock to a layout guess;
  5. if the builder's reader cannot read a book, Christina blocks the Load
     instead of letting the lock degrade quietly.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import openpyxl
import pytest

from backend.ashery_oak_import import looks_like_ashery_oak
from backend.criswell_import import looks_like_criswell
from backend.builder_parsers import (
    GENERIC_PARSER_IDS,
    guess_named_parser,
    match_vendor_from_saved_parsers,
    preferred_parser_for,
    save_named_parser,
)
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.builder_profiles import PROFILES_DIR, clear_profile_cache
from backend.christina import observe_drop
from backend.fn_chair_import import looks_like_fn_level_one
from backend.jmw_import import looks_like_jmw
from backend.standardize import resolve_builder_vendor
from wide_import import import_workbook, looks_like_artisan_chairs

DOWNLOADS = Path.home() / "Downloads"

# builder, locked importer, next year's filename, sheet names, detector, live book
SETTLED = [
    (
        "FN Chair",
        "fn_chair",
        "FNC_2028_Pricelist_0915.xlsm",
        ["Cover Page", "PCL Color List", "PL Print", "PL With Markup", "PL To Export"],
        looks_like_fn_level_one,
        DOWNLOADS / "FNC_2027_Pricelist_0826.xlsm",
    ),
    (
        "Ashery Oak",
        "ashery_oak",
        "AO_Pricelist_080126.xlsx",
        ["Markup", "Options&Portal bk", "Master", "Cover", "Options&Portal", "Products"],
        looks_like_ashery_oak,
        DOWNLOADS / "AO_Pricelist_070625.xlsx",
    ),
    (
        "J & M Woodworking",
        "jmw",
        "JMW_2027_Pricelist_0101.xlsx",
        ["Markup", "Cover", " Percentage", "Hampton", "Specialty Finish Options"],
        looks_like_jmw,
        DOWNLOADS / "JMW_2026_Pricelist_0426.xlsx",
    ),
    (
        "Artisan Chairs",
        "artisan_chairs",
        "AC_2027_Pricelist_0301.xlsx",
        ["Retail with MARKUP", "Wholesale"],
        looks_like_artisan_chairs,
        DOWNLOADS / "AC_2026_Pricelist_0226.xlsx",
    ),
    (
        "Criswell Bedroom",
        "criswell",
        "CWF_Pricelists_2026_0101/Living Rooms Price List.xlsx",
        ["Markup", "Cover", "Bloomfield Collection", "Options "],
        looks_like_criswell,
        DOWNLOADS / "CWF_Pricelists_2025_1224" / "Wholesale Price List.xlsx",
    ),
]

IDS = [row[0] for row in SETTLED]


def _flat_book() -> bytes:
    """A book none of the named readers can read — forces a generic fallthrough."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["Part #", "Description", "Wood", "Wholesale"])
    ws.append(["P1", "Bench", "Maple", 220])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _fresh_profile_cache():
    clear_profile_cache()
    yield
    clear_profile_cache()


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_settled_builder_ships_its_own_parser(
    builder, importer, next_file, sheets, detector, live_book
):
    raw = json.loads((PROFILES_DIR / f"{_slug(builder)}.json").read_text(encoding="utf-8"))
    locked = str((raw.get("parser") or {}).get("importer") or "")
    assert locked == importer
    assert locked not in GENERIC_PARSER_IDS
    assert preferred_parser_for(builder) == importer


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_next_upload_resolves_to_the_same_reader(
    builder, importer, next_file, sheets, detector, live_book
):
    assert detector(next_file, sheets) is True
    assert guess_named_parser(next_file, sheet_names=sheets)[1] == importer
    assert resolve_builder_vendor(next_file, filename=next_file) == builder
    assert match_vendor_from_saved_parsers(next_file) == builder
    assert preferred_parser_for(builder, filename=next_file) == importer
    assert preferred_parser_for("", filename=next_file) == importer


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_fallthrough_load_cannot_downgrade_the_lock(
    builder, importer, next_file, sheets, detector, live_book, tmp_path: Path
):
    save_named_parser(
        builder, importer=importer, source_file=next_file, root=tmp_path
    )
    save_named_parser(
        builder, importer="generic", source_file="mystery.xlsx", layouts=["long_flat"], root=tmp_path
    )
    assert preferred_parser_for(builder, root=tmp_path) == importer


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_christina_blocks_a_load_when_the_reader_misses(
    builder, importer, next_file, sheets, detector, live_book, tmp_path: Path
):
    lesson = observe_drop(
        {
            "filename": next_file,
            "suggested_builder": builder,
            "detected_importer": "generic",
            "parser_source": "saved",
            "locked_parser": importer,
            "row_count": 1,
            "rows": [{"species": "Oak", "line_kind": "item"}],
        },
        path=tmp_path / "christina_lessons.jsonl",
    )
    assert lesson["needs_fix"] is True
    assert importer in " ".join(lesson["issues"])
    assert lesson["next_step"].startswith("Do not Load")


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_live_book_parses_under_its_locked_reader(
    builder, importer, next_file, sheets, detector, live_book
):
    # Extra: the real Mac book when present. CI proof is tests/test_ci_fixtures.py.
    if not live_book.is_file():
        pytest.skip(f"{live_book.name} not on this machine")
    data = live_book.read_bytes()
    # Renamed to next year's file: the lock must still carry the parse.
    result = import_workbook(
        data, filename=next_file, vendor=builder, preferred_parser=importer
    )
    assert result.detected_importer == importer
    assert result.parser_source == "saved"
    assert len(result.long_df) > 100


def test_a_generic_first_lock_is_still_allowed(tmp_path: Path):
    """New builders start on the guesser; only downgrades of a settled lock are blocked."""
    save_named_parser(
        "Brand New Builder", importer="generic", source_file="BNB_2026.xlsx", root=tmp_path
    )
    assert preferred_parser_for("Brand New Builder", root=tmp_path) == "generic"


def test_every_specific_reader_is_registered_once():
    from backend.catalog_readers import CATALOG_SPECS

    ids = [entry.parser_id for entry in DEFAULT_READER_REGISTRY.entries]
    assert len(ids) == len(set(ids))
    required = {
        "fn_chair",
        "artisan_chairs",
        "criswell",
        "jmw",
        "ashery_oak",
        "patio_kraft",
        "amish_aspen",
        "hillside_chair",
        "maple_lane",
        "hw_chair_markup",
        "lamb",
        "luxhome",
        "windy_acres",
        "generic",
        "pdf",
    }
    required.update(spec.parser_id for spec in CATALOG_SPECS)
    assert set(ids) == required
    assert DEFAULT_READER_REGISTRY.generic_ids == frozenset({"generic", "pdf"})
    for builder, importer, *_ in SETTLED:
        assert DEFAULT_READER_REGISTRY.get(importer).specific is True


def _slug(vendor: str) -> str:
    from backend.builder_profiles import vendor_slug

    return vendor_slug(vendor)
