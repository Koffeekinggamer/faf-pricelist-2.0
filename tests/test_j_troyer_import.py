"""J. Troyer named reader: real Item# and wood groups, never Stain-as-SKU."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from backend.j_troyer_import import import_j_troyer_workbook
from wide_import import import_workbook

LIVE = Path(
    "/Volumes/ExternalSSD/FAF-pricebook/viztech-downloads/all-20260717/J._Troyer_amp_Company"
)
MAIN = LIVE / "Download_2026_J._Troyer_Co._Pricelist_65372.xlsx"
BEDROOM = LIVE / "Download_2026_Bedroom_Pricelist_986904.xlsx"
DINING = LIVE / "Download_2026_Dining_Pricelist_758210.xlsx"


def _xlsx(rows: list[list], sheet="Buffet") -> bytes:
    book = Workbook()
    tab = book.active
    tab.title = sheet
    for row in rows:
        tab.append(row)
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def test_item_number_explodes_across_wood_groups():
    data = _xlsx(
        [
            ["ELENA COLLECTION"],
            [
                "Item#",
                "Description",
                "Dimensions",
                "BR. Maple, Oak, R-Cherry",
                "PREMIUM Cherry, QSWO",
            ],
            ["7430-64", "Buffet - 4 Doors", '32"H x 64"W', 1258.95, 1344],
            ["Stain", "not a sku", "", 99, 99],
        ]
    )
    df = import_j_troyer_workbook(data, filename="jt.xlsx").long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    assert set(items["part_number"]) == {"7430-64"}
    woods = set(items["species"])
    assert "Brown Maple / Oak / Rustic Cherry" in woods
    assert "Premium / Cherry / QSWO" in woods or any("Cherry" in w and "QSWO" in w for w in woods)
    assert "Stain" not in set(items["part_number"])


def test_stain_block_keeps_item_number_not_finish_label():
    data = _xlsx(
        [
            ["AMBIANCE"],
            ['56.25"W x 27.25"H x 18"D'],
            ["", "6105", "Stain", 1167.60],
            ["Wood Door", "", "Two-Tone", 1225.98],
        ],
        sheet="Ambiance",
    )
    df = import_j_troyer_workbook(data, filename="jt.xlsx").long_df
    parts = set(df["part_number"])
    assert "6105" in parts
    assert "Stain" not in parts
    assert "Two-Tone" not in parts
    assert "1225.98" not in parts


def test_import_workbook_routes_j_troyer():
    data = _xlsx(
        [
            ["Item#", "Description", "Dimensions", "Oak, Brown Maple"],
            ["1101", "End Table", '24" H', 301.74],
        ],
        sheet="Canyon",
    )
    result = import_workbook(data, vendor="J. Troyer & Company", filename="J_Troyer_Co.xlsx")
    assert result.detected_importer == "j_troyer_and_company"
    assert result.long_df.iloc[0]["part_number"] == "1101"
    assert "Oak" in str(result.long_df.iloc[0]["species"])


def test_live_books_have_skus_and_woods():
    if not MAIN.is_file():
        return
    main = import_j_troyer_workbook(MAIN.read_bytes(), filename=MAIN.name).long_df
    items = main[main["line_kind"].fillna("item") != "addon"]
    assert "7430-64" in set(items["part_number"])
    assert "Stain" not in set(items["part_number"])
    assert items["species"].fillna("").astype(str).str.strip().ne("").mean() > 0.85
    if BEDROOM.is_file():
        bed = import_j_troyer_workbook(BEDROOM.read_bytes(), filename=BEDROOM.name).long_df
        assert "AR-1000-Q" in set(bed["part_number"])
        assert bed["species"].fillna("").astype(str).str.strip().ne("").all()
    if DINING.is_file():
        dine = import_j_troyer_workbook(DINING.read_bytes(), filename=DINING.name).long_df
        assert any(str(p).startswith("KR-") for p in dine["part_number"])
        assert dine["species"].fillna("").astype(str).str.strip().ne("").mean() > 0.9
