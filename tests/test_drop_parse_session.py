"""Drop parse session — ensure / clear / wholesale_from (PriceBookService seam)."""

from __future__ import annotations

import io
import time

import openpyxl
import pytest

from backend.drop_parse_session import DropSessionGone, DropUpload
from backend.service import PriceBookService


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
