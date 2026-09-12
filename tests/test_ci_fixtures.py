"""CI must parse committed fixtures. Mac Downloads may stay skipped."""

from __future__ import annotations

import openpyxl
import pytest

from backend.book_options import extract_book_options
from backend.builder_parsers import guess_named_parser, preferred_parser_for
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.workbook_sheets import hidden_sheet_names, read_all_sheets
from tests.fixture_corpus import (
    OPTIONS_FIXTURE,
    SETTLED_FIXTURES,
    WIDE_FIXTURE,
    all_fixture_paths,
)
from tests.test_builder_parser_contract import SETTLED, _call_detector
from wide_import import import_workbook, list_excel_sheets

SETTLED_BY_BUILDER = {row[0]: row for row in SETTLED}
SETTLED_IDS = [row[0] for row in SETTLED_FIXTURES]


def _items(df):
    if df is None or getattr(df, "empty", True):
        return df
    if "line_kind" not in df.columns:
        return df
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    return df[kind != "addon"]


def _addons(df):
    if df is None or getattr(df, "empty", True) or "line_kind" not in df.columns:
        return df.iloc[0:0] if df is not None else df
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    return df[kind == "addon"]


def _option_keys(df) -> set[str]:
    if df is None or getattr(df, "empty", True) or "option_key" not in df.columns:
        return set()
    keys = df["option_key"].dropna().astype(str)
    return {key.strip() for key in keys if key.strip()}


@pytest.mark.parametrize("path", all_fixture_paths(), ids=lambda p: p.name)
def test_fixture_file_is_visible_xlsx(path):
    assert path.is_file(), f"missing committed fixture {path}"
    data = path.read_bytes()
    assert data[:2] == b"PK"
    assert hidden_sheet_names(data) == set()
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        names = list(wb.sheetnames)
        assert names
        for name in names:
            assert wb[name].sheet_state == "visible"
    finally:
        wb.close()
    views = read_all_sheets(data)
    assert {v.name for v in views} == set(names)
    assert set(list_excel_sheets(data)) == set(names)
    assert all(v.role != "error" for v in views)


@pytest.mark.parametrize(
    "builder,importer,next_file,path,option_keys", SETTLED_FIXTURES, ids=SETTLED_IDS
)
def test_settled_fixture_keeps_the_locked_reader(
    builder, importer, next_file, path, option_keys
):
    contract = SETTLED_BY_BUILDER[builder]
    detector = contract[4]
    data = path.read_bytes()
    sheets = list_excel_sheets(data)
    assert _call_detector(detector, next_file, sheets, data=data) is True
    assert guess_named_parser(next_file, sheet_names=sheets, data=data)[1] == importer
    assert preferred_parser_for(builder, filename=next_file) == importer

    result = import_workbook(
        data, filename=next_file, vendor=builder, preferred_parser=importer
    )
    assert result.detected_importer == importer
    assert result.parser_source == "saved"
    items = _items(result.long_df)
    assert items is not None and not items.empty
    assert len(items) >= 2
    keys = _option_keys(result.long_df)
    missing = [key for key in option_keys if key not in keys]
    assert not missing, f"{builder} fixture missed Options {missing}; got {sorted(keys)}"
    addons = _addons(result.long_df)
    assert addons is not None and not addons.empty, (
        f"{builder} fixture parsed items but no addon Options — capture miss"
    )


def test_fn_chair_fixture_keeps_style_parts_and_fabric_addon():
    builder, importer, next_file, path, _opts = SETTLED_FIXTURES[0]
    result = import_workbook(
        path.read_bytes(),
        filename=next_file,
        vendor=builder,
        preferred_parser=importer,
    )
    items = _items(result.long_df)
    parts = set(items["part_number"].astype(str))
    assert "Abe Side Chair" in parts
    assert "Abe Arm Chair" in parts
    cat1 = items[items["option_key"].astype(str) == "Cat. 1"]
    assert not cat1.empty
    addons = _addons(result.long_df)
    assert set(addons["option_key"].astype(str)) >= {"Solid Fabrics / COM"}
    assert 23.0 in set(float(v) for v in addons["base_price"])


def test_ashery_oak_fixture_expands_woods_and_options():
    builder, importer, next_file, path, _opts = SETTLED_FIXTURES[1]
    result = import_workbook(
        path.read_bytes(),
        filename=next_file,
        vendor=builder,
        preferred_parser=importer,
    )
    items = _items(result.long_df)
    woods = set(items["species"].dropna().astype(str))
    assert {"Oak", "Brown Maple", "Hickory", "QSWO", "Rustic Walnut"} <= woods
    sofa = items[items["part_number"].astype(str) == "BF-1648-DS"]
    oak = float(sofa[sofa["species"] == "Oak"].iloc[0]["base_price"])
    hick = float(sofa[sofa["species"] == "Hickory"].iloc[0]["base_price"])
    assert oak == 350
    assert hick == 385.0
    assert "BF-1648-END" in set(items["part_number"].astype(str))
    tried = {s["sheet"]: s for s in (result.sheets_tried or [])}
    assert tried["Master"]["layout"] == "ashery_oak_master_wood_expand"
    assert tried["Products"]["layout"] == "ashery_oak_products_fill"
    addons = _addons(result.long_df)
    paint = addons[addons["option_key"].astype(str) == "Paint"].iloc[0]
    assert paint["addon_pct"] == 35.0


def test_jmw_fixture_expands_percentage_woods_and_finish_options():
    builder, importer, next_file, path, _opts = SETTLED_FIXTURES[2]
    result = import_workbook(
        path.read_bytes(),
        filename=next_file,
        vendor=builder,
        preferred_parser=importer,
    )
    items = _items(result.long_df)
    woods = set(items["species"].dropna().astype(str))
    assert {"Brown Maple", "Cherry", "Walnut"} <= woods
    mule = items[
        (items["part_number"].astype(str) == "40")
        & (items["option_key"].isna() | (items["option_key"].astype(str) == ""))
    ]
    bm = float(mule[mule["species"] == "Brown Maple"].iloc[0]["base_price"])
    ch = float(mule[mule["species"] == "Cherry"].iloc[0]["base_price"])
    assert bm == 400
    assert ch == 440.0
    keys = _option_keys(result.long_df)
    assert {"Fabric", "Crypton", "Leather", "Paint", "2-tone Stain"} <= keys
    addons = _addons(result.long_df)
    assert {"Paint", "2-tone Stain"} <= set(addons["option_key"].astype(str))


def test_artisan_chairs_fixture_keeps_unfinished_and_options_block():
    builder, importer, next_file, path, _opts = SETTLED_FIXTURES[3]
    result = import_workbook(
        path.read_bytes(),
        filename=next_file,
        vendor=builder,
        preferred_parser=importer,
    )
    items = _items(result.long_df)
    aberdeen = items[items["collection"].astype(str) == "Aberdeen"]
    oak_side = aberdeen[
        (aberdeen["description"].astype(str) == "Side Chair")
        & (aberdeen["species"].astype(str).str.contains("Oak", case=False))
    ]
    finished = oak_side[oak_side["finish_state"] == "finished"]["base_price"].min()
    unfinished = oak_side[oak_side["finish_state"] == "unfinished"]["base_price"].min()
    assert finished == 150.0
    assert unfinished == 108.0
    addons = _addons(result.long_df)
    assert {"Fabric Seat", "Leather Seat", "Nail Heads"} <= set(
        addons["option_key"].astype(str)
    )
    assert result.expected_option_lines >= 3
    layouts = {str(t.get("layout") or "") for t in (result.sheets_tried or [])}
    assert "viewed_retail" in layouts


def test_criswell_fixture_keeps_left_wholesale_and_options_tab():
    builder, importer, next_file, path, _opts = SETTLED_FIXTURES[4]
    result = import_workbook(
        path.read_bytes(),
        filename=next_file,
        vendor=builder,
        preferred_parser=importer,
    )
    items = _items(result.long_df)
    oak = items[
        items["part_number"].astype(str).str.startswith("CWF8111")
        & items["species"].fillna("").astype(str).str.contains("Oak", case=False)
    ]
    assert not oak.empty
    assert float(oak.iloc[0]["base_price"]) == 1099.0
    addons = _addons(result.long_df)
    assert "Phone Charger" in set(addons["option_key"].astype(str))
    assert result.expected_option_lines >= 1


def test_wide_species_token_fixture_unpivots_woods():
    vendor, importer, filename, path = WIDE_FIXTURE
    data = path.read_bytes()
    sheets = list_excel_sheets(data)
    detected_vendor, detected = DEFAULT_READER_REGISTRY.detect(
        filename, sheet_names=sheets, data=data
    )
    assert detected_vendor == vendor
    assert detected == importer
    result = import_workbook(
        data, filename=filename, vendor=vendor, preferred_parser=importer
    )
    assert result.detected_importer == importer
    items = _items(result.long_df)
    assert items is not None and not items.empty
    species = {str(s).lower() for s in items["species"].dropna()}
    assert any("oak" in s for s in species)
    assert any("cherry" in s for s in species)
    assert any("walnut" in s for s in species)
    prices = {float(p) for p in items["base_price"].dropna()}
    assert 500.0 in prices
    assert 140.0 in prices
    layouts = {str(t.get("layout") or "") for t in (result.sheets_tried or [])}
    assert any("wide_species" in layout for layout in layouts)
    views = read_all_sheets(data)
    assert any(v.role == "options" for v in views)
    addons = _addons(result.long_df)
    assert addons is not None and not addons.empty, (
        "wide_species fixture must still encode Options — empty is a capture miss"
    )


def test_options_tab_fixture_proves_options_are_present():
    vendor, importer, filename, path, option_keys = OPTIONS_FIXTURE
    data = path.read_bytes()
    views = read_all_sheets(data)
    assert any(v.role == "options" and v.name == "Options" for v in views)
    extracted = extract_book_options(data, vendor=vendor)
    extracted_keys = {str(r.get("option_key") or "") for r in extracted}
    missing_extract = [key for key in option_keys if key not in extracted_keys]
    assert not missing_extract, extracted_keys

    detected_vendor, detected = DEFAULT_READER_REGISTRY.detect(
        filename, sheet_names=list_excel_sheets(data), data=data
    )
    assert detected_vendor == vendor
    assert detected == importer
    result = import_workbook(
        data, filename=filename, vendor=vendor, preferred_parser=importer
    )
    assert result.detected_importer == importer
    items = _items(result.long_df)
    assert items is not None and not items.empty
    assert "MAG22NS" in set(items["part_number"].astype(str))
    addons = _addons(result.long_df)
    assert addons is not None and not addons.empty
    keys = _option_keys(result.long_df)
    missing = [key for key in option_keys if key not in keys]
    assert not missing, keys
