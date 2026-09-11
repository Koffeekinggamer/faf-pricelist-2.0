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

import inspect
import io
import json
from pathlib import Path

import openpyxl
import pytest

from backend.ajs_import import looks_like_ajs
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
from backend.catalog_readers import spec_for_vendor
from backend.christina import observe_drop
from backend.fn_chair_import import looks_like_fn_level_one
from backend.jmw_import import looks_like_jmw
from backend.standardize import resolve_builder_vendor
from tests.fixture_corpus import (
    SETTLED_FIXTURES,
    STUB_FIXTURE,
    TIER_B_BLOCKED,
    TIER_B_SHAPE,
)
from wide_import import (
    import_workbook,
    looks_like_amish_aspen,
    looks_like_artisan_chairs,
    looks_like_hillside_chair,
    looks_like_hw_chair_markup,
    looks_like_lamb,
    looks_like_maple_lane,
    looks_like_patio_kraft,
    looks_like_windy_acres,
)

DOWNLOADS = Path.home() / "Downloads"


def _catalog_detector(vendor: str):
    spec = spec_for_vendor(vendor)
    assert spec is not None, f"missing CatalogSpec for {vendor}"
    return spec.matches


def _call_detector(detector, filename, sheets, data=None) -> bool:
    """Call a SETTLED detector the same way the registry does (no extra args)."""
    params = inspect.signature(detector).parameters
    kwargs = {
        "filename": filename,
        "sheet_names": sheets,
        "data": data,
    }
    accepted = {key: value for key, value in kwargs.items() if key in params}
    if accepted:
        return bool(detector(**accepted))
    return bool(detector(filename, sheets))


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
    (
        "AJ's Furniture",
        "ajs_furniture",
        "AJ's Furniture 2028 Pricelist.xlsx",
        ["Cover", "Finished Wholesale MARKUP", "Options"],
        looks_like_ajs,
        DOWNLOADS / "Download_2026_Pricelist_Finished_301390.xls",
    ),
    (
        "Amish Aspen",
        "amish_aspen",
        "Amish Aspen 2028 Pricelist.xlsx",
        ["Cover", "Options", "Pricelist"],
        looks_like_amish_aspen,
        DOWNLOADS / "Download_2026_Pricelist_1501888.xlsx",
    ),
    (
        "Brookside Home Furnishings",
        "brookside_home_furnishings",
        "Brookside Home Furnishings 2028 Pricelist.xlsx",
        ["Cover", "Heritage  Hutches", "Options", "Markup"],
        _catalog_detector("Brookside Home Furnishings"),
        DOWNLOADS / "Download_2026_Pricelist_3164.xlsx",
    ),
    (
        "Fredericksburg Furniture",
        "fredericksburg_furniture",
        "Fredericksburg Furniture 2028 Pricelist.xlsx",
        ["Cover", "Bedroom", "Options"],
        _catalog_detector("Fredericksburg Furniture"),
        DOWNLOADS / "Download_2026_Pricelist_127330.xls",
    ),
    (
        "Frog Pond Furniture",
        "frog_pond_furniture",
        "Frog Pond Furniture 2028 Pricelist.xlsx",
        ["Cover", "1 Weston ", "Options", "Markup", "Index"],
        _catalog_detector("Frog Pond Furniture"),
        DOWNLOADS / "Download_2026_Pricelist_2499.xlsx",
    ),
    (
        "Hillside Chair",
        "hillside_chair",
        "Hillside Chair 2028 Pricelist.xlsx",
        ["Cover", "Options", "Sheet3"],
        looks_like_hillside_chair,
        DOWNLOADS / "Download_2026_Pricelist_2184.xlsx",
    ),
    (
        "Hogback Design And Finishing",
        "hogback_design_and_finishing",
        "Hogback Design And Finishing 2028 Pricelist.xlsx",
        ["Cover", "Pricing", "Options"],
        _catalog_detector("Hogback Design And Finishing"),
        DOWNLOADS / "Download_2026_Pricelist_2196.xlsx",
    ),
    (
        "Hope Wood",
        "hw_chair_markup",
        "Hope Wood HW_Chair 2028 Pricelist.xlsx",
        ["Cover", "Markup Calculator", "Options"],
        looks_like_hw_chair_markup,
        DOWNLOADS / "Download_2026_Pricelist_629159.xlsx",
    ),
    (
        "J. Troyer & Company",
        "j_troyer_and_company",
        "J. Troyer & Company 2028 Pricelist.xlsx",
        ["Cover", "Buffet", "Options"],
        _catalog_detector("J. Troyer & Company"),
        DOWNLOADS / "Download_2026_J._Troyer_Co._Pricelist_65372.xlsx",
    ),
    (
        "Kidron Woodcraft",
        "kidron_woodcraft",
        "Kidron Woodcraft 2028 Pricelist.xlsx",
        ["Cover", "Prices", "Options"],
        _catalog_detector("Kidron Woodcraft"),
        DOWNLOADS / "Solo Galaxy.xlsx",
    ),
    (
        "LAMB",
        "lamb",
        "LAMB 2028 Pricelist.xlsx",
        ["Cover", "Wholesale", "Options"],
        looks_like_lamb,
        DOWNLOADS / "Download_2026_Pricelist_23191.xlsx",
    ),
    (
        "Maple Lane",
        "maple_lane",
        "Maple Lane 2028 Pricelist.xlsx",
        ["Cover", "Wholesale", "Options"],
        looks_like_maple_lane,
        DOWNLOADS / "Download_2026_Pricelist_466191.xlsx",
    ),
    (
        "Patio Kraft",
        "patio_kraft",
        "Patio Kraft 2028 Pricelist.xlsx",
        ["Cover", "Retail", "Wholesale", "Options"],
        looks_like_patio_kraft,
        DOWNLOADS / "Download_2026_Pricelist_305917.xlsx",
    ),
    (
        "Superior Woodcrafts",
        "superior_woodcrafts",
        "Superior Woodcrafts 2028 Pricelist.xlsx",
        ["Cover", "Pricelist", "Options"],
        _catalog_detector("Superior Woodcrafts"),
        DOWNLOADS / "Download_2026_Pricelist_687470.xlsx",
    ),
    (
        "Townline Furniture",
        "townline_furniture",
        "Townline Furniture 2028 Pricelist.xlsx",
        ["Cover", "Finished", "Unfinished", "Options"],
        _catalog_detector("Townline Furniture"),
        DOWNLOADS / "Download_2026_Pricelist_9419.xlsx",
    ),
    (
        "Troyer Ridge Furniture",
        "troyer_ridge_furniture",
        "Troyer Ridge Furniture 2028 Pricelist.xlsx",
        ["Cover", "Bedroom", "Options"],
        _catalog_detector("Troyer Ridge Furniture"),
        DOWNLOADS / "Download_2026_Pricelist_19590.xlsx",
    ),
    (
        "Windy Acres Furniture",
        "windy_acres",
        "Windy Acres Furniture 2028 Pricelist.xlsx",
        ["Cover", "Bedroom Collection", "Instructions", "MarkUp"],
        looks_like_windy_acres,
        DOWNLOADS / "Download_2026_Pricelist_2396.xlsx",
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
    assert _call_detector(detector, next_file, sheets) is True
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
    # Thin KEEP catalogs (ADR-0007) are still extras, not a 100-row floor.
    min_rows = 2 if builder in {"Amish Aspen", "Maple Lane"} else 100
    assert len(result.long_df) > min_rows


SETTLED_FIXTURE_BY_BUILDER = {row[0]: row for row in SETTLED_FIXTURES}


@pytest.mark.parametrize(
    "builder,importer,next_file,sheets,detector,live_book", SETTLED, ids=IDS
)
def test_settled_fixture_parses_under_its_locked_reader(
    builder, importer, next_file, sheets, detector, live_book
):
    """CI proof: SETTLED is fixture-backed. Downloads stay skip-when-absent extras."""
    fixture = SETTLED_FIXTURE_BY_BUILDER[builder]
    _fx_builder, fx_importer, fx_file, path, option_keys = fixture
    assert fx_importer == importer
    data = path.read_bytes()
    result = import_workbook(
        data, filename=fx_file, vendor=builder, preferred_parser=importer
    )
    assert result.detected_importer == importer
    assert result.parser_source == "saved"
    items = result.long_df
    if items is not None and "line_kind" in items.columns:
        kind = items["line_kind"].fillna("item").astype(str).str.lower()
        addons = items[kind == "addon"]
        items = items[kind != "addon"]
    else:
        addons = items.iloc[0:0] if items is not None else items
    assert items is not None and not items.empty
    assert len(items) >= 2
    keys = set()
    if result.long_df is not None and "option_key" in result.long_df.columns:
        keys = {
            str(k).strip()
            for k in result.long_df["option_key"].dropna()
            if str(k).strip()
        }
    missing = [key for key in option_keys if key not in keys]
    assert not missing, f"{builder} fixture missed Options {missing}; got {sorted(keys)}"
    assert addons is not None and not addons.empty, (
        f"{builder} fixture parsed items but no addon Options — capture miss"
    )


def test_settled_covers_tier_b_builders_with_fixture_bytes():
    settled = {row[0]: row[1] for row in SETTLED}
    fixtures = {row[0]: row[1] for row in SETTLED_FIXTURES}
    assert STUB_FIXTURE[0] not in settled
    assert STUB_FIXTURE[0] not in {row[0] for row in TIER_B_SHAPE}
    for builder, importer in TIER_B_SHAPE:
        assert builder in fixtures, f"{builder} is Tier B but has no fixture bytes"
        assert builder in settled, f"{builder} has fixture bytes but is not SETTLED"
        assert settled[builder] == importer
        assert fixtures[builder] == importer
        assert importer not in GENERIC_PARSER_IDS
    for builder, reason in TIER_B_BLOCKED.items():
        assert builder not in fixtures, f"{builder} blocked ({reason}) must not have SETTLED fixture bytes"
        assert builder not in settled, f"{builder} blocked ({reason}) must stay out of SETTLED"


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
