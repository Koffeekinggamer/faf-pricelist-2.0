"""HTML drop zone must not change smart-parse or named-parser quality."""

from __future__ import annotations

import base64
import io

import openpyxl

from backend.drop_parse_session import DropUpload
from backend.dropzone_widget import drop_upload_from_payload
from backend.service import PriceBookService
from wide_import import import_workbook


def _xlsx_bytes(rows: list[list], sheet: str = "Catalog") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _simple_book() -> bytes:
    return _xlsx_bytes(
        [
            ["Part #", "Description", "Wood", "Wholesale"],
            ["P1", "Bench", "Maple", 220],
            ["P2", "Stool", "Oak", 90],
        ]
    )


def _html_drop_upload(filename: str, data: bytes) -> DropUpload:
    """Same JSON the HTML5 zone posts: name + base64 bytes."""
    payload = {
        "name": filename,
        "size": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
        "ts": 1,
    }
    got = drop_upload_from_payload(payload)
    assert got is not None
    return got


def test_html_drop_bytes_match_original_xlsx():
    raw = _simple_book()
    got = _html_drop_upload("NorthRiver_2026.xlsx", raw)
    assert got.data == raw
    assert got.filename == "NorthRiver_2026.xlsx"
    assert got.size == len(raw)


def test_html_drop_workbook_parse_matches_direct_bytes():
    raw = _simple_book()
    got = _html_drop_upload("NorthRiver_2026.xlsx", raw)
    direct = import_workbook(raw, filename="NorthRiver_2026.xlsx", vendor="North River")
    via_html = import_workbook(
        got.data, filename=got.filename, vendor="North River"
    )
    assert via_html.detected_importer == direct.detected_importer
    assert via_html.parser_source == direct.parser_source
    assert len(via_html.long_df) == len(direct.long_df)
    assert not via_html.long_df.empty


def test_html_drop_session_keeps_smart_parse_and_named_parser(tmp_path):
    raw = _simple_book()
    html_up = _html_drop_upload("NorthRiver_2026.xlsx", raw)
    svc = PriceBookService(db_path=tmp_path / "t.db")
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"

    raw_view = svc.ensure_drop_parse_session(
        [DropUpload("NorthRiver_2026.xlsx", raw, size=len(raw))]
    )
    html_view = svc.ensure_drop_parse_session(
        [html_up],
        force=True,
    )
    raw_f = raw_view.files[0]
    html_f = html_view.files[0]
    assert html_f.error == ""
    assert html_f.row_count == raw_f.row_count
    assert html_f.detected_importer == raw_f.detected_importer
    assert html_f.parser_source == raw_f.parser_source
    assert html_f.variants.get("item_count") == raw_f.variants.get("item_count")
    assert html_f.variants.get("woods") == raw_f.variants.get("woods")
    assert html_f.variants.get("layouts") == raw_f.variants.get("layouts")
    assert html_f.suggested_builder == raw_f.suggested_builder

    locked = svc.lock_builder_parser(
        "North River Furniture",
        importer=html_f.detected_importer,
        source_file=html_f.filename,
        layouts=(html_f.variants or {}).get("layouts"),
        root=tmp_path / "profiles",
    )
    assert locked is not None
    assert locked.name == "north-river-furniture.json"


def test_html_drop_ao_filename_selects_ashery_oak_parser():
    raw = _simple_book()
    html_up = _html_drop_upload("AO_Pricelist_070625.xlsx", raw)
    from backend.builder_parsers import guess_named_parser, preferred_parser_for
    from backend.standardize import resolve_builder_vendor

    vend = resolve_builder_vendor(html_up.filename, filename=html_up.filename)
    assert vend == "Ashery Oak"
    assert preferred_parser_for(vend, filename=html_up.filename) == "ashery_oak"
    assert guess_named_parser(html_up.filename, sheet_names=["Master", "Options&Portal"]) == (
        "Ashery Oak",
        "ashery_oak",
    )


def test_html_drop_jmw_filename_still_selects_jmw_parser():
    raw = _simple_book()
    html_up = _html_drop_upload("JMW_2026_Pricelist.xlsx", raw)
    from backend.builder_parsers import preferred_parser_for
    from backend.standardize import resolve_builder_vendor

    vend = resolve_builder_vendor(html_up.filename, filename=html_up.filename)
    assert vend == "J & M Woodworking"
    assert preferred_parser_for(vend, filename=html_up.filename) == "jmw"
