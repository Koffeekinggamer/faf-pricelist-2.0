"""Named per-builder parsers — lock on Drop Load, reuse on the next book."""

from __future__ import annotations

import io
import json
from pathlib import Path

import openpyxl

from backend.builder_parsers import (
    filename_hints_for,
    guess_named_parser,
    infer_importer,
    match_vendor_from_saved_parsers,
    preferred_parser_for,
    profile_writes_allowed,
    save_named_parser,
)
from backend.builder_profiles import clear_profile_cache, load_builder_profile
from backend.drop_parse_session import DropUpload
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


def test_j_and_m_profile_has_named_parser():
    clear_profile_cache()
    p = load_builder_profile("J & M Woodworking")
    assert (p.get("parser") or {}).get("importer") == "jmw"
    assert preferred_parser_for("J & M Woodworking") == "jmw"


def test_save_and_reload_named_parser(tmp_path: Path):
    clear_profile_cache()
    path = save_named_parser(
        "Acme Furniture",
        importer="generic",
        source_file="Acme_2026_Pricelist.xlsx",
        layouts=["long_flat"],
        root=tmp_path,
    )
    assert path is not None and path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["vendor"] == "Acme Furniture"
    assert raw["parser"]["importer"] == "generic"
    assert raw["parser"]["locked"] is True
    assert "acme" in " ".join(raw["parser"]["filename_hints"])
    assert preferred_parser_for("Acme Furniture", root=tmp_path) == "generic"
    assert match_vendor_from_saved_parsers("Acme_2027_Wholesale.xlsx", root=tmp_path) == (
        "Acme Furniture"
    )


def test_fly_skips_write_to_default_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FLY_APP_NAME", "faf-pricebook")
    assert profile_writes_allowed() is False
    # Explicit root still writes (tests / local override).
    path = save_named_parser(
        "Fly Test",
        importer="generic",
        source_file="fly.xlsx",
        root=tmp_path,
    )
    assert path is not None


def test_infer_importer_from_layouts():
    assert infer_importer("", ["jmw_br_maple_expand"]) == "jmw"
    assert infer_importer("fn_chair", []) == "fn_chair"
    assert infer_importer("", ["ashery_oak_master_wood_expand"]) == "ashery_oak"
    assert infer_importer("", ["wide_species"]) == "generic"


def test_guess_named_parser_ashery_oak():
    vend, pid = guess_named_parser(
        "AO_Pricelist_070625.xlsx",
        sheet_names=["Markup", "Master", "Options&Portal", "Products"],
    )
    assert vend == "Ashery Oak"
    assert pid == "ashery_oak"
    assert guess_named_parser("other.xlsx", sheet_names=["Sheet1"]) == ("", "")


def test_filename_hints_strip_year_noise():
    hints = filename_hints_for("Hope Wood", "HopeWood_2027_Pricelist.xlsx")
    assert "hope wood" in hints
    assert any("hopewood" in h.replace(" ", "") for h in hints)


def test_import_workbook_tags_generic_parser():
    result = import_workbook(_simple_book(), filename="FlatBuilder.xlsx", vendor="Flat")
    assert result.detected_importer == "generic"
    assert result.parser_source == "guessed"
    assert not result.long_df.empty


def test_import_workbook_uses_preferred_parser_first(monkeypatch):
    called = {"id": ""}

    def fake_run(parser_id, data, **kwargs):
        called["id"] = parser_id
        return None

    monkeypatch.setattr("backend.builder_parsers.run_named_parser", fake_run)
    result = import_workbook(
        _simple_book(),
        filename="whatever.xlsx",
        vendor="Mystery",
        preferred_parser="jmw",
    )
    assert called["id"] == "jmw"
    # jmw returned nothing → fall through to generic
    assert result.detected_importer == "generic"
    assert result.parser_source == "guessed"


def test_drop_load_locks_parser_for_next_file(tmp_path: Path):
    db = tmp_path / "t.db"
    svc = PriceBookService(db_path=db)
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    profiles = tmp_path / "profiles"
    profiles.mkdir()

    data = _simple_book()
    view = svc.ensure_drop_parse_session(
        [DropUpload("Acme_2026.xlsx", data, size=len(data))],
    )
    f = view.files[0]
    assert f.detected_importer
    assert f.parser_source == "guessed"

    path = svc.lock_builder_parser(
        "Acme Furniture",
        importer=f.detected_importer,
        source_file="Acme_2026.xlsx",
        layouts=(f.variants or {}).get("layouts"),
        root=profiles,
    )
    assert path is not None
    assert preferred_parser_for("Acme Furniture", root=profiles) == "generic"

    # Next year's file resolves by hint and uses the locked parser id.
    assert match_vendor_from_saved_parsers("Acme_2027.xlsx", root=profiles) == (
        "Acme Furniture"
    )
    assert preferred_parser_for(
        "Acme Furniture", filename="Acme_2027.xlsx", root=profiles
    ) == "generic"


def test_next_year_filename_drop_uses_locked_parser(tmp_path: Path, monkeypatch):
    """After Load locks a parser, next year's file name reuses it without a typed vendor."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    save_named_parser(
        "Acme Furniture",
        importer="generic",
        source_file="Acme_2026.xlsx",
        layouts=["long_flat"],
        root=profiles,
    )
    monkeypatch.setattr("backend.builder_profiles.PROFILES_DIR", profiles)
    clear_profile_cache()

    db = tmp_path / "t.db"
    svc = PriceBookService(db_path=db)
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    data = _simple_book()
    view = svc.ensure_drop_parse_session(
        [DropUpload("Acme_2027.xlsx", data, size=len(data))],
    )
    f = view.files[0]
    assert f.suggested_builder == "Acme Furniture"
    assert f.parser_source == "saved"
    assert f.detected_importer == "generic"
    assert f.row_count >= 1


def test_named_parser_zero_rows_falls_through_then_lock_refreshes(tmp_path: Path):
    """If the locked importer cannot read this book, Drop guesses again and Load can retag."""
    result = import_workbook(
        _simple_book(),
        filename="flat_catalog.xlsx",
        vendor="FN Chair",
        preferred_parser="fn_chair",
    )
    assert result.long_df is not None and not result.long_df.empty
    assert result.detected_importer == "generic"
    assert result.parser_source == "guessed"
    path = save_named_parser(
        "FN Chair",
        importer=result.detected_importer,
        source_file="flat_catalog.xlsx",
        layouts=["long_flat"],
        root=tmp_path,
    )
    assert path is not None
    assert preferred_parser_for("FN Chair", root=tmp_path) == "generic"


def test_reparse_honors_vendor_override_saved_parser(tmp_path: Path, monkeypatch):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    save_named_parser(
        "Acme Furniture",
        importer="generic",
        source_file="Acme_2026.xlsx",
        root=profiles,
    )
    monkeypatch.setattr("backend.builder_profiles.PROFILES_DIR", profiles)
    clear_profile_cache()

    db = tmp_path / "t.db"
    svc = PriceBookService(db_path=db)
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    data = _simple_book()
    view = svc.ensure_drop_parse_session(
        [DropUpload("mystery_book.xlsx", data, size=len(data))],
        vendor_overrides={"mystery_book.xlsx": "Acme Furniture"},
    )
    assert view.files[0].suggested_builder == "Acme Furniture"
    assert view.files[0].parser_source == "saved"
    assert view.files[0].detected_importer == "generic"


def test_lock_parser_uses_typed_name_not_filename(tmp_path: Path):
    path = PriceBookService(tmp_path / "t.db").lock_builder_parser(
        "North River Furniture",
        importer="generic",
        source_file="JMW_lookalike.xlsx",
        layouts=["long_flat"],
        root=tmp_path / "profiles",
    )
    assert path is not None
    assert path.name == "north-river-furniture.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["vendor"] == "North River Furniture"
    assert raw["parser"]["importer"] == "generic"
    assert not (tmp_path / "profiles" / "j-and-m-woodworking.json").exists()
