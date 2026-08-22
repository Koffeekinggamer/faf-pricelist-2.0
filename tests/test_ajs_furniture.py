"""AJ's Furniture sells a fabric tier, a finish, and four add-on charges.

The book prints one row per fabric grade, wood prices across the page, and an
OPTIONS band on the right (springs, motorized mechanism, battery pack,
replacement cushions). The generic wide-species layout kept only the wood
prices, so the floor saw three identical rows at three prices and no Options.
"""

import io

import pandas as pd

from backend.ajs_import import import_ajs_workbook, looks_like_ajs


def _book(sheet: str, rows: list[list]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False, header=False)
    return buffer.getvalue()


HEADER = [
    None,
    None,
    "FABRIC",
    "RED OAK & BROWN MAPLE",
    "CHERRY &\n1/4 SAWN\n WHITE",
    "WALNUT",
    "Roughsawn Brown Maple",
    "OPTIONAL SPRINGS\nADD",
    "MOTORIZED MECHANISM ADD",
    "RECHARGABLE BATTERY PACK ADD",
    "FABRIC & LEATHER \nYARDAGE\nCHART",
    "\nREPLACEMENT\nCUSHIONS",
]


def _finished_book() -> bytes:
    return _book(
        "Finished Wholesale",
        [
            [None, None, None, "FINISHED PRICES", None, None, None, "OPTIONS"],
            HEADER,
            ["101 CSC", "Cubic Slat Chair", "Standard", 887.45, 1008.58, 1109.69, None, 77.7, 94.5, 105.0, "4 yd", 393.75],
            ["101 CSC", "Cubic Slat Chair", "Premium", 916.85, 1037.98, 1139.09, None, 77.7, 94.5, 105.0, None, 423.15],
            ["101 CSC", "Cubic Slat Chair", "Leather", 1132.1, 1253.23, 1354.34, None, 77.7, 94.5, 105.0, "85 sq.ft.", 638.4],
        ],
    )


def test_detects_ajs_from_the_visible_markup_tab():
    """The plain Wholesale tab is hidden; only the MARKUP tab is visible."""
    assert looks_like_ajs(
        filename="Download_2026_Pricelist_Finished_301390.xls",
        sheet_names=["Finished Wholesale MARKUP"],
    )
    assert looks_like_ajs(
        filename="Download_2026_Pricelist_Unfinished_301389.xls",
        sheet_names=["Unfinished Wholesale MARKUP"],
    )


def test_luxhome_seating_is_not_claimed_by_the_ajs_reader():
    assert not looks_like_ajs(
        filename="Download_2026_LuxHome_Pricelist_648810.xls",
        sheet_names=["Wholesale MARKUP"],
    )


def test_fabric_tier_is_the_option_not_a_dropped_column():
    result = import_ajs_workbook(
        _finished_book(), vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    items = result.long_df[result.long_df["line_kind"] == "item"]
    assert set(items["option_key"]) == {"Standard", "Premium", "Leather"}
    chair = items[items["species"] == "Red Oak / Brown Maple"]
    prices = dict(zip(chair["option_key"], chair["base_price"]))
    assert prices == {"Standard": 887.45, "Premium": 916.85, "Leather": 1132.1}


def test_every_wood_column_becomes_its_own_species_price():
    result = import_ajs_workbook(
        _finished_book(), vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    items = result.long_df[result.long_df["line_kind"] == "item"]
    standard = items[items["option_key"] == "Standard"]
    assert dict(zip(standard["species"], standard["base_price"])) == {
        "Red Oak / Brown Maple": 887.45,
        "Cherry / QS White Oak": 1008.58,
        "Walnut": 1109.69,
    }


def test_the_options_band_lands_as_addon_charges_once_per_sku():
    result = import_ajs_workbook(
        _finished_book(), vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    charges = dict(zip(addons["option_key"], addons["base_price"]))
    assert charges == {
        "Optional Springs": 77.7,
        "Motorized Mechanism": 94.5,
        "Rechargable Battery Pack": 105.0,
        "Replacement Cushions": 393.75,
    }
    assert set(addons["part_number"]) == {"101 CSC"}


def test_yardage_chart_is_never_read_as_a_price():
    result = import_ajs_workbook(
        _finished_book(), vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    blob = " ".join(str(v) for v in result.long_df["option_key"].fillna("")).lower()
    assert "yardage" not in blob
    assert "sq.ft" not in blob


def test_the_unfinished_twin_is_an_unfinished_row_not_a_second_finished_price():
    unfinished = _book(
        "Unfinished Wholesale",
        [
            [None, None, None, "UNFINISHED PRICES", None, None, None, "OPTIONS"],
            HEADER,
            ["101 CSC", "Cubic Slat Chair", "Standard", 787.7, 908.83, 1009.94, None, 77.7, None, None, "4 yd", None],
        ],
    )

    result = import_ajs_workbook(
        unfinished, vendor="AJ's Furniture", filename="Pricelist_Unfinished.xls"
    )

    items = result.long_df[result.long_df["line_kind"] == "item"]
    assert set(items["finish_state"]) == {"unfinished"}
    assert items[items["species"] == "Red Oak / Brown Maple"]["base_price"].iloc[0] == 787.7


def test_accessory_band_prices_by_tier_and_ignores_the_warranty_prose():
    accessories = _book(
        "Finished Wholesale",
        [
            ["Pillows", None, None, None, None],
            [None, "*Price per pillow", None, "PRICE", "AJ'S FURNITURE LLC WARRANTY"],
            ["213 SP", "13x13 Small Pillow", "Standard", 32.55, "Hardwood frames and springs"],
            ["213 SP", "13x13 Small Pillow", "Premium", 36.75, "Seat foam cores"],
            ["220 GAP", "Glider Arm Pads", "Standard", 74.55, None],
        ],
    )

    result = import_ajs_workbook(
        accessories, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    rows = result.long_df
    pillow = rows[rows["part_number"] == "213 SP"]
    assert set(pillow["option_key"]) == {"Standard", "Premium"}
    assert set(pillow["line_kind"]) == {"addon"}
    assert pillow["description"].iloc[0] == "13x13 Small Pillow"
    assert dict(zip(pillow["option_key"], pillow["base_price"])) == {
        "Standard": 32.55,
        "Premium": 36.75,
    }


def test_occasional_tables_have_no_fabric_tier_but_still_price_by_wood():
    tables = _book(
        "Finished Wholesale",
        [
            [None, None, None, "FINISHED PRICES", None, None, None, "OPTIONS"],
            [None, None, None, "RED OAK & BROWN MAPLE", "CHERRY &\n1/4 SAWN\n WHITE", "WALNUT", "Roughsawn Brown Maple", "LIFT TOP ADD"],
            ["BN-25", "Barrington Coffee Table", None, 506.41, 646.73, 788.86, None, 120.75],
            ["RS-BT16", 'Beaumont 16" End Table', None, None, None, None, 346.08, None],
        ],
    )

    result = import_ajs_workbook(
        tables, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    items = result.long_df[result.long_df["line_kind"] == "item"]
    coffee = items[items["part_number"] == "BN-25"]
    assert set(coffee["option_key"].fillna("")) == {""}
    assert dict(zip(coffee["species"], coffee["base_price"])) == {
        "Red Oak / Brown Maple": 506.41,
        "Cherry / QS White Oak": 646.73,
        "Walnut": 788.86,
    }
    roughsawn = items[items["part_number"] == "RS-BT16"]
    assert list(roughsawn["species"]) == ["Roughsawn Brown Maple"]

    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    assert dict(zip(addons["part_number"], addons["option_key"])) == {"BN-25": "Lift Top"}


def test_custom_finish_upcharge_is_an_option_not_a_ninety_dollar_sofa():
    custom = _book(
        "Finished Wholesale",
        [
            ["CUSTOM FINISH PRICING CALCULATOR", None, None, None],
            ["ID #", "Product Name", None, "All Woods"],
            ["101 CSC", "Cubic Slat Chair", None, 99.75],
            ["143 CPS", "Cubic Panel Sofa", None, 220.5],
        ],
    )

    result = import_ajs_workbook(
        custom, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    rows = result.long_df
    assert set(rows["line_kind"]) == {"addon"}
    assert set(rows["option_key"]) == {"Custom Finish"}
    assert dict(zip(rows["part_number"], rows["base_price"])) == {
        "101 CSC": 99.75,
        "143 CPS": 220.5,
    }


def test_each_band_shape_names_its_own_collection():
    """AJ's prints no collection banners, so the band shape is the section.

    Every row landed with an empty collection before this, which left the floor
    with one flat list of 211 SKUs and no way to tell a sofa from an end table.
    """
    result = import_ajs_workbook(
        _finished_book(), vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )
    assert set(result.long_df["collection"]) == {"Seating"}

    tables = _book(
        "Finished Wholesale",
        [
            ["OCCASIONAL PIECES", None, None, None, None, None, None, None],
            [None, None, None, "RED OAK & BROWN MAPLE", "CHERRY &\n1/4 SAWN\n WHITE", "WALNUT", "Roughsawn Brown Maple", "LIFT TOP ADD"],
            ["BN-25", "Barrington Coffee Table", None, 506.41, 646.73, 788.86, None, 120.75],
        ],
    )
    occasional = import_ajs_workbook(
        tables, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )
    assert set(occasional.long_df["collection"]) == {"Occasional Pieces"}

    pillows = _book(
        "Finished Wholesale",
        [
            ["Pillows", None, None, None, None],
            [None, "*Price per pillow", None, "PRICE", "AJ'S FURNITURE LLC WARRANTY"],
            ["213 SP", "13x13 Small Pillow", "Standard", 32.55, "Hardwood frames"],
        ],
    )
    accessories = import_ajs_workbook(
        pillows, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )
    assert set(accessories.long_df["collection"]) == {"Accessories"}

    custom = _book(
        "Finished Wholesale",
        [
            ["ID #", "Product Name", None, "All Woods"],
            ["101 CSC", "Cubic Slat Chair", None, 99.75],
        ],
    )
    finish = import_ajs_workbook(
        custom, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )
    assert set(finish.long_df["collection"]) == {"Custom Finish"}


def test_quote_only_cushion_is_an_option_the_floor_can_see():
    """The Roughsawn sofas print ``Quote`` where a cushion price would go.

    A dropped cell reads as "no such option" on the floor. The factory does
    sell it, it just won't publish the number, so it ships as a priceless
    Option rather than a free one.
    """
    roughsawn = _book(
        "Finished Wholesale",
        [
            [None, None, None, "FINISHED PRICES", None, None, None, "OPTIONS"],
            HEADER,
            ["RS32 HDS", "Houston Deluxe Sofa", "Standard", None, None, None, 1738.48, None, None, None, "12 1/2 yd", "Quote"],
        ],
    )

    result = import_ajs_workbook(
        roughsawn, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    cushions = result.long_df[result.long_df["option_key"] == "Replacement Cushions"]
    assert len(cushions) == 1
    assert cushions["line_kind"].iloc[0] == "addon"
    assert pd.isna(cushions["base_price"].iloc[0])
    assert "quote required" in str(cushions["notes"].iloc[0]).lower()


def test_page_furniture_and_footnotes_never_become_products():
    noisy = _book(
        "Finished Wholesale",
        [
            [None, None, None, "FINISHED PRICES", None, None, None, "OPTIONS"],
            HEADER,
            ["101 CSC", "Cubic Slat Chair", "Standard", 887.45, None, None, None, None, None, None, None, None],
            [None, None, None, "use Cherry & 1/4 Sawn White pricing for /Hard Maple/Hickory"],
            ["When selecting options, list them clearly", None, None, None],
            ["FINISHED WHOLESALE\nAJ's Furniture\n5355W 400S", None, "**All pricing based on Heartland"],
            [None, None, None, None],
        ],
    )

    result = import_ajs_workbook(
        noisy, vendor="AJ's Furniture", filename="Pricelist_Finished.xls"
    )

    assert set(result.long_df["part_number"]) == {"101 CSC"}
