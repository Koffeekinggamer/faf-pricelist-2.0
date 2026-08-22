"""Drop parse session — ensure / clear / wholesale_from (PriceBookService seam)."""

from __future__ import annotations

import io
import pickle
import time

import openpyxl
import pytest

from backend.drop_parse_session import (
    DiskDropParseStore,
    DropSessionGone,
    DropUpload,
    SESSION_SCHEMA_VERSION,
    drop_upload_from_path,
    evaluate_readiness,
    is_drop_filename,
)
from backend.service import PriceBookService


def test_is_drop_filename_accepts_excel_and_pdf():
    assert is_drop_filename("JMW_2026_Pricelist.xlsx")
    assert is_drop_filename("list.XLSM")
    assert is_drop_filename("book.pdf")
    assert not is_drop_filename("notes.docx")
    assert not is_drop_filename("sheet.csv")


def test_drop_upload_from_path(tmp_path):
    xlsx = tmp_path / "NorthRiver_2026.xlsx"
    xlsx.write_bytes(_simple_book())
    got = drop_upload_from_path(xlsx)
    assert got is not None
    assert got.filename == "NorthRiver_2026.xlsx"
    assert got.size >= 2
    assert drop_upload_from_path(tmp_path / "missing.xlsx") is None
    assert drop_upload_from_path(tmp_path / "notes.txt") is None


def _xlsx_bytes(rows: list[list], sheet: str = "Price List") -> bytes:
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
        ],
        sheet="Catalog",
    )


@pytest.fixture
def svc(tmp_path):
    db = tmp_path / "t.db"
    s = PriceBookService(db_path=db)
    s.init()
    s._drop_parse_root = tmp_path / "drop_sessions"
    return s


def test_ensure_returns_session_with_file_preview_not_full_rows(svc):
    data = _simple_book()
    view = svc.ensure_drop_parse_session(
        [DropUpload("FlatBuilder.xlsx", data, size=len(data))],
        prefer_workbook_markup=False,
    )
    assert view.session_id
    assert len(view.files) == 1
    f = view.files[0]
    assert f.filename == "FlatBuilder.xlsx"
    assert f.row_count >= 2
    assert f.error == ""
    assert f.suggested_builder
    assert f.suggested_mult > 0
    assert f.variants
    assert f.variants.get("item_count", 0) >= 2
    assert f.detected_importer
    assert f.parser_source in {"guessed", "saved"}
    assert f.lock_fields.importer == f.detected_importer
    assert isinstance(f.readiness.load_ready, bool)
    # UI-safe: sample only, not the full catalog
    assert len(f.sample) <= 8
    assert not hasattr(f, "rows") or not getattr(f, "rows", None)


def test_ensure_reuses_session_same_batch(svc):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    v1 = svc.ensure_drop_parse_session(uploads, prefer_workbook_markup=False)
    v2 = svc.ensure_drop_parse_session(
        uploads,
        session_id=v1.session_id,
        prefer_workbook_markup=False,
    )
    assert v2.session_id == v1.session_id
    assert v2.files[0].row_count == v1.files[0].row_count


def test_force_reparse_new_parse(svc):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    v1 = svc.ensure_drop_parse_session(uploads)
    v2 = svc.ensure_drop_parse_session(uploads, session_id=v1.session_id, force=True)
    assert v2.session_id  # still valid
    assert v2.files[0].row_count >= 2


def test_clear_then_wholesale_raises(svc):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    view = svc.ensure_drop_parse_session(uploads)
    svc.clear_drop_parse_session(view.session_id)
    with pytest.raises(DropSessionGone):
        svc.wholesale_from_drop_parse_session(view.session_id)


def test_wholesale_rows_unbound_by_widget_mult(svc):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    view = svc.ensure_drop_parse_session(uploads)
    files = svc.wholesale_from_drop_parse_session(view.session_id)
    assert len(files) == 1
    assert files[0].row_count >= 2
    assert len(files[0].rows) == files[0].row_count
    # Stored as wholesale — base_price present; commit binds mult later
    assert any(r.get("base_price") is not None for r in files[0].rows)


def test_markup_preference_change_invalidates(svc):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    v1 = svc.ensure_drop_parse_session(uploads, prefer_workbook_markup=False)
    v2 = svc.ensure_drop_parse_session(
        uploads,
        session_id=v1.session_id,
        prefer_workbook_markup=True,
    )
    # New batch identity → new session
    assert v2.session_id != v1.session_id
    assert v2.files[0].row_count >= 2


def test_ttl_expiry_forces_reparse(svc, monkeypatch):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    view = svc.ensure_drop_parse_session(uploads)
    # Age the session past TTL
    from backend import drop_parse_session as dps

    store = dps.DiskDropParseStore(svc._drop_parse_root)
    payload = store.load(view.session_id)
    assert payload is not None
    payload["saved_at"] = time.time() - (dps.DEFAULT_TTL_SECONDS + 10)
    store.save(view.session_id, payload)
    # ensure with same id should rebuild (not raise)
    v2 = svc.ensure_drop_parse_session(
        uploads, session_id=view.session_id, prefer_workbook_markup=False
    )
    assert v2.files[0].row_count >= 2


def test_excel_parsed_once_per_ensure(svc, monkeypatch):
    data = _simple_book()
    uploads = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    calls = {"n": 0}
    orig = svc.imports.preview_excel

    def counting(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(svc.imports, "preview_excel", counting)
    svc.ensure_drop_parse_session(uploads)
    assert calls["n"] == 1


def test_reuse_allows_empty_bytes_when_session_fresh(svc):
    data = _simple_book()
    full = [DropUpload("FlatBuilder.xlsx", data, size=len(data))]
    view = svc.ensure_drop_parse_session(full)
    light = [DropUpload("FlatBuilder.xlsx", b"", size=len(data))]
    reused = svc.ensure_drop_parse_session(
        light, session_id=view.session_id, prefer_workbook_markup=False
    )
    assert reused.session_id == view.session_id


def test_parse_requires_bytes_when_no_session(svc):
    light = [DropUpload("FlatBuilder.xlsx", b"", size=100)]
    with pytest.raises(ValueError, match="upload data required"):
        svc.ensure_drop_parse_session(light)


def test_priced_options_without_addons_block_load():
    readiness = evaluate_readiness(
        {
            "rows": [
                {
                    "vendor": "Builder",
                    "part_number": "C1",
                    "species": "Oak",
                    "base_price": 100.0,
                    "line_kind": "item",
                }
            ],
            "priced_option_count": 4,
        }
    )

    assert readiness.load_ready is False
    assert readiness.block_code == "options_missing"
    assert "4 priced option" in readiness.block_message


def test_unfinished_source_without_unfinished_rows_or_option_blocks_load():
    readiness = evaluate_readiness(
        {
            "rows": [
                {
                    "vendor": "Builder",
                    "part_number": "C1",
                    "species": "Oak",
                    "finish_state": "finished",
                    "base_price": 100.0,
                    "line_kind": "item",
                }
            ],
            "expected_finish_states": ["finished", "unfinished"],
        }
    )

    assert readiness.load_ready is False
    assert readiness.block_code == "finish_state_missing"
    assert "unfinished" in readiness.block_message.lower()


def test_unfinished_source_with_unfinished_rows_passes_finish_gate():
    rows = [
        {
            "vendor": "Builder",
            "part_number": f"C{i}",
            "species": "Oak",
            "finish_state": state,
            "base_price": 100.0,
            "line_kind": "item",
        }
        for i, state in enumerate(("finished", "unfinished"), start=1)
    ]

    readiness = evaluate_readiness(
        {"rows": rows, "expected_finish_states": ["finished", "unfinished"]}
    )

    assert readiness.load_ready is True


def test_old_unversioned_session_is_invalidated(tmp_path):
    store = DiskDropParseStore(tmp_path)
    path = store.path_for("dps_old")
    path.write_bytes(
        pickle.dumps(
            {
                "batch_key": "old",
                "saved_at": time.time(),
                "files": [],
            }
        )
    )
    assert store.load("dps_old") is None

    store.save(
        "dps_new",
        {"batch_key": "new", "saved_at": time.time(), "files": []},
    )
    loaded = store.load("dps_new")
    assert loaded is not None
    assert loaded["schema_version"] == SESSION_SCHEMA_VERSION
