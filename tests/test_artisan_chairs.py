"""Artisan Chairs (AC_ pricelist) named reader."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl

from backend import PriceBookService
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.drop_parse_session import evaluate_readiness
from backend.import_service import ImportService
from backend.standardize import resolve_builder_vendor
from wide_import import import_workbook, looks_like_artisan_chairs

DOWNLOADS = Path.home() / "Downloads"
LIVE = DOWNLOADS / "AC_2026_Pricelist_0226.xlsx"


def test_ac_filename_is_artisan_chairs():
    assert resolve_builder_vendor("", filename="AC_2026_Pricelist_0226.xlsx") == "Artisan Chairs"
    assert resolve_builder_vendor("", filename="AC_2027_Pricelist_0301.xlsx") == "Artisan Chairs"
    assert looks_like_artisan_chairs("AC_2027_Pricelist_0301.xlsx", ["Retail with MARKUP", "Wholesale"])
    vendor, parser_id = DEFAULT_READER_REGISTRY.detect(
        "AC_2027_Pricelist_0301.xlsx",
        sheet_names=["Retail with MARKUP", "Wholesale"],
    )
    assert vendor == "Artisan Chairs"
    assert parser_id == "artisan_chairs"


def test_lamb_wholesale_retail_book_is_not_artisan_chairs():
    sheets = ["Retail with MARKUP", "Wholesale"]
    assert not looks_like_artisan_chairs(
        "LAMB 2025 Wholesale Price List.xlsx", sheets
    )
    vendor, parser_id = DEFAULT_READER_REGISTRY.detect(
        "LAMB 2025 Wholesale Price List.xlsx",
        sheet_names=sheets,
    )
    assert parser_id == "lamb"
    assert vendor == "LAMB"


def test_lamb_viztech_download_filename_still_detects():
    vendor, parser_id = DEFAULT_READER_REGISTRY.detect(
        "LAMB_Woodworking/Download_2026_Pricelist_23191.xlsx",
        sheet_names=["Retail with MARKUP", "Wholesale"],
    )
    assert parser_id == "lamb"
    assert vendor == "LAMB"


def test_live_ac_book_parses_wholesale_only():
    if not LIVE.is_file():
        return
    data = LIVE.read_bytes()
    result = DEFAULT_READER_REGISTRY.run(
        "artisan_chairs",
        data,
        vendor="Artisan Chairs",
        filename=LIVE.name,
    )
    assert result is not None
    assert not result.long_df.empty
    layouts = {str(t.get("layout") or "") for t in (result.sheets_tried or [])}
    assert "viewed_retail" in layouts
    assert len(result.long_df) >= 1000
    addons = result.long_df[
        result.long_df["line_kind"].fillna("item").astype(str).str.lower() == "addon"
    ]
    assert len(addons) == 30
    assert set(addons["option_key"]) >= {
        "Fabric Seat",
        "Premium Seat + Revolutionary + Crypton",
        "Faux or Ultra Leather Seat",
        "Leather Seat",
        "Nail Heads",
        "Memory Swivel",
        "Kick Plates Powder Coated",
        "Benton Scoop (see page 8 of catalog)",
        "Deep Scoop (see page 8 of catalog)",
    }
    special = addons[
        (addons["option_key"] == "Premium Seat + Revolutionary + Crypton")
        & (addons["part_number"] == "Asher - Premium Seat + Revolutionary + Crypton")
    ]
    assert special.iloc[0]["base_price"] == 18.0
    items = result.long_df[
        result.long_df["line_kind"].fillna("item").astype(str).str.lower() != "addon"
    ]
    aberdeen = items[items["collection"] == "Aberdeen"]
    assert not aberdeen.empty
    assert set(aberdeen["finish_state"].dropna().astype(str).str.lower()) >= {
        "finished",
        "unfinished",
    }
    assert "Desk Arm Chair w/ Gas Lift" in set(aberdeen["description"].astype(str))
    oak_side = aberdeen[
        (aberdeen["description"] == "Side Chair")
        & (aberdeen["species"].astype(str).str.contains("Oak", case=False))
        & (~aberdeen["species"].astype(str).str.contains("White|QSWO", case=False))
    ]
    finished = oak_side[oak_side["finish_state"] == "finished"]["base_price"].min()
    unfinished = oak_side[oak_side["finish_state"] == "unfinished"]["base_price"].min()
    assert finished == 150.0
    assert unfinished == 108.0


def test_artisan_chair_search_prices_collection_specific_seat_option(tmp_path):
    if not LIVE.is_file():
        return
    preview = ImportService().preview_excel(
        LIVE.read_bytes(),
        filename=LIVE.name,
        vendor="Artisan Chairs",
        multiplier=2.7,
    )
    svc = PriceBookService(db_path=str(tmp_path / "artisan.db"))
    svc.init()
    svc.repo.insert_rows(preview.rows)

    asher = svc.search(
        "Arm Chair",
        collection="Asher",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        option_key="Premium Seat + Revolutionary + Crypton",
        limit=10,
    )
    advance = svc.search(
        "Arm Chair",
        collection="Advance",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        option_key="Premium Seat + Revolutionary + Crypton",
        limit=10,
    )

    assert asher.iloc[0]["base_price"] == 284.0  # 266 finished oak + 18 Heartland seat
    assert asher.iloc[0]["adjusted_price"] == 770.0
    assert advance.iloc[0]["base_price"] != asher.iloc[0]["base_price"]


def test_artisan_kick_plates_price_per_selected_plate(tmp_path):
    if not LIVE.is_file():
        return
    preview = ImportService().preview_excel(
        LIVE.read_bytes(),
        filename=LIVE.name,
        vendor="Artisan Chairs",
        multiplier=2.7,
    )
    svc = PriceBookService(db_path=str(tmp_path / "plates.db"))
    svc.init()
    svc.repo.insert_rows(preview.rows)

    base = svc.search(
        "Stationary Bar Stool",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        limit=1,
    ).iloc[0]
    with_plates = svc.search(
        "Stationary Bar Stool",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        option_key="Kick Plates Powder Coated",
        option_qty={"Kick Plates Powder Coated": 3},
        limit=1,
    ).iloc[0]

    assert with_plates["base_price"] == base["base_price"] + 45.0


def test_artisan_unfinished_is_an_option_that_switches_the_finished_price(tmp_path):
    if not LIVE.is_file():
        return
    preview = ImportService().preview_excel(
        LIVE.read_bytes(),
        filename=LIVE.name,
        vendor="Artisan Chairs",
        multiplier=2.7,
    )
    svc = PriceBookService(db_path=str(tmp_path / "finish.db"))
    svc.init()
    svc.repo.insert_rows(preview.rows)

    assert "Unfinished" in svc.list_option_keys("Artisan Chairs")

    finished = svc.search(
        "Side Chair",
        collection="Aberdeen",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        limit=5,
    )
    unfinished = svc.search(
        "Side Chair",
        collection="Aberdeen",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        option_key="Unfinished",
        limit=5,
    )

    assert not finished.empty
    assert finished.iloc[0]["base_price"] == 150.0
    assert finished.iloc[0]["finish_state"] == "finished"
    assert unfinished.iloc[0]["base_price"] == 108.0
    assert unfinished.iloc[0]["finish_state"] == "unfinished"
    # Unfinished replaces the base; it is not a stacked adder on finished.
    assert unfinished.iloc[0]["base_price"] < finished.iloc[0]["base_price"]


def test_aberdeen_desk_arm_chair_is_in_the_catalog(tmp_path):
    if not LIVE.is_file():
        return
    preview = ImportService().preview_excel(
        LIVE.read_bytes(),
        filename=LIVE.name,
        vendor="Artisan Chairs",
        multiplier=2.7,
    )
    svc = PriceBookService(db_path=str(tmp_path / "desk.db"))
    svc.init()
    svc.repo.insert_rows(preview.rows)

    desk = svc.search(
        "Desk Arm Chair",
        collection="Aberdeen",
        vendor="Artisan Chairs",
        species="Oak / Rustic / Oak",
        limit=5,
    )
    assert not desk.empty
    assert (
        desk.iloc[0]["description"]
        == "Desk Arm Chair w/ Gas Lift — Aberdeen"
    )
    assert desk.iloc[0]["base_price"] == 317.0  # finished oak from the book


def test_expected_option_lines_survive_a_dead_addon_scanner(monkeypatch):
    """The gate counts source option lines, not the rows the reader emitted."""
    if not LIVE.is_file():
        return
    import wide_import

    monkeypatch.setattr(
        wide_import, "artisan_chairs_option_addons", lambda data, *, vendor: []
    )
    preview = ImportService().preview_excel(
        LIVE.read_bytes(),
        filename=LIVE.name,
        vendor="Artisan Chairs",
        multiplier=2.7,
    )

    assert preview.priced_option_count > 0
    readiness = evaluate_readiness(
        {
            "rows": preview.rows,
            "priced_option_count": preview.priced_option_count,
        }
    )
    assert readiness.load_ready is False
    assert readiness.block_code == "options_missing"


def test_option_line_count_belongs_to_the_reader_not_the_caller():
    """A builder with no option block reports zero without AC's scanner."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Price List"
    sheet.append(["Item", "Oak"])
    sheet.append(["Side Chair", 100])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = import_workbook(buffer.getvalue(), vendor="North River", filename="NR.xlsx")

    assert result.expected_option_lines == 0
    preview = ImportService().preview_excel(
        buffer.getvalue(), filename="NR.xlsx", vendor="North River"
    )
    assert preview.priced_option_count == 0
