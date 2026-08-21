"""Drop Load is one PriceBookService operation with per-Builder outcomes."""

from __future__ import annotations

import io

import openpyxl

from backend.drop_parse_session import DropLoadBinding, DropUpload
from backend.service import PriceBookService


def _book(part: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["Part #", "Description", "Species", "Wholesale"])
    ws.append([part, f"{part} item", "Oak", 100])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _service(tmp_path) -> PriceBookService:
    svc = PriceBookService(tmp_path / "master.db")
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    svc._builder_profile_root = tmp_path / "profiles"
    return svc


def test_mixed_batch_blocks_only_the_reader_miss(tmp_path):
    svc = _service(tmp_path)
    alpha = _book("A1")
    beta = _book("B1")
    view = svc.ensure_drop_parse_session(
        [
            DropUpload("Alpha_2026.xlsx", alpha, size=len(alpha)),
            DropUpload("Beta_2026.xlsx", beta, size=len(beta)),
        ],
        vendor_overrides={
            "Alpha_2026.xlsx": "Alpha Furniture",
            "Beta_2026.xlsx": "Beta Furniture",
        },
    )

    store = svc._drop_parse_store()
    payload = store.load(view.session_id)
    assert payload is not None
    payload["files"][1]["readiness"] = {
        "load_ready": True,
        "block_code": "",
        "block_message": "",
    }
    payload["files"][0]["locked_parser"] = "fn_chair"
    payload["files"][0]["detected_importer"] = "generic"
    payload["files"][0]["readiness"] = {
        "load_ready": False,
        "block_code": "settled_reader_miss",
        "block_message": "fn_chair did not read this book",
    }
    store.save(view.session_id, payload)

    result = svc.commit_drop_load(
        view.session_id,
        [
            DropLoadBinding(0, "Alpha Furniture", 2.7),
            DropLoadBinding(1, "Beta Furniture", 2.7),
        ],
    )

    assert [r.status for r in result.results] == ["blocked", "loaded"]
    assert "Alpha Furniture" not in set(svc.repo.list_vendors())
    assert "Beta Furniture" in set(svc.repo.list_vendors())


def test_profile_write_failure_keeps_catalog_and_returns_blocking_warning(
    tmp_path, monkeypatch
):
    svc = _service(tmp_path)
    data = _book("G1")
    view = svc.ensure_drop_parse_session(
        [DropUpload("Gamma_2026.xlsx", data, size=len(data))],
        vendor_overrides={"Gamma_2026.xlsx": "Gamma Furniture"},
    )
    store = svc._drop_parse_store()
    payload = store.load(view.session_id)
    assert payload is not None
    payload["files"][0]["readiness"] = {
        "load_ready": True,
        "block_code": "",
        "block_message": "",
    }
    store.save(view.session_id, payload)

    def fail_lock(*args, **kwargs):
        raise PermissionError("profile read-only")

    monkeypatch.setattr(svc, "lock_builder_parser", fail_lock)
    result = svc.commit_drop_load(
        view.session_id,
        [DropLoadBinding(0, "Gamma Furniture", 2.7)],
    )

    item = result.results[0]
    assert item.status == "loaded"
    assert item.profile_saved is False
    assert "profile read-only" in item.profile_warning
    assert result.blocking_warnings
    assert "Gamma Furniture" in set(svc.repo.list_vendors())


def test_unchanged_wholesale_skips_builder_replacement(tmp_path):
    svc = _service(tmp_path)
    data = _book("S1")

    def drop_and_mark_ready(filename: str):
        view = svc.ensure_drop_parse_session(
            [DropUpload(filename, data, size=len(data))],
            vendor_overrides={filename: "Stable Furniture"},
            force=True,
        )
        store = svc._drop_parse_store()
        payload = store.load(view.session_id)
        assert payload is not None
        payload["files"][0]["readiness"] = {
            "load_ready": True,
            "block_code": "",
            "block_message": "",
        }
        store.save(view.session_id, payload)
        return view

    first = drop_and_mark_ready("Stable_2026.xlsx")
    loaded = svc.commit_drop_load(
        first.session_id,
        [DropLoadBinding(0, "Stable Furniture", 2.7)],
    )
    assert loaded.results[0].status == "loaded"
    count = svc.row_count()

    second = drop_and_mark_ready("Stable_2027.xlsx")
    unchanged = svc.commit_drop_load(
        second.session_id,
        [DropLoadBinding(0, "Stable Furniture", 2.7)],
    )
    assert unchanged.results[0].status == "unchanged"
    assert unchanged.results[0].catalog["deleted"] == 0
    assert svc.row_count() == count


def test_new_option_rows_prevent_unchanged_skip(tmp_path):
    svc = _service(tmp_path)
    data = _book("O1")

    first = svc.ensure_drop_parse_session(
        [DropUpload("Options_2026.xlsx", data, size=len(data))],
        vendor_overrides={"Options_2026.xlsx": "Options Furniture"},
        force=True,
    )
    store = svc._drop_parse_store()
    first_payload = store.load(first.session_id)
    assert first_payload is not None
    first_payload["files"][0]["readiness"] = {
        "load_ready": True,
        "block_code": "",
        "block_message": "",
    }
    store.save(first.session_id, first_payload)
    loaded = svc.commit_drop_load(
        first.session_id,
        [DropLoadBinding(0, "Options Furniture", 2.7)],
    )
    assert loaded.results[0].status == "loaded"

    second = svc.ensure_drop_parse_session(
        [DropUpload("Options_2027.xlsx", data, size=len(data))],
        vendor_overrides={"Options_2027.xlsx": "Options Furniture"},
        force=True,
    )
    payload = store.load(second.session_id)
    assert payload is not None
    payload["files"][0]["rows"].append(
        {
            "vendor": "Options Furniture",
            "collection": "Addons",
            "part_number": "Fabric Seat",
            "description": "Fabric Seat",
            "option_key": "Fabric Seat",
            "species": None,
            "finish_state": "finished",
            "base_price": 28.0,
            "line_kind": "addon",
        }
    )
    payload["files"][0]["readiness"] = {
        "load_ready": True,
        "block_code": "",
        "block_message": "",
    }
    store.save(second.session_id, payload)

    changed = svc.commit_drop_load(
        second.session_id,
        [DropLoadBinding(0, "Options Furniture", 2.7)],
    )
    assert changed.results[0].status == "loaded"
    assert "Fabric Seat" in svc.list_option_keys(vendor="Options Furniture")


def test_same_builder_multi_file_drop_concatenates_into_one_catalog(tmp_path):
    """One factory, four books → one vendor catalog, not last-file-wins."""
    svc = _service(tmp_path)
    beds_af = _book("CWF1100")
    beds_hw = _book("CWF1154")
    cases = _book("CWF8111")
    living = _book("CWF3044")
    view = svc.ensure_drop_parse_session(
        [
            DropUpload("Beds A-F.xlsx", beds_af, size=len(beds_af)),
            DropUpload("Beds H-W.xlsx", beds_hw, size=len(beds_hw)),
            DropUpload("Wholesale Price List.xlsx", cases, size=len(cases)),
            DropUpload("Living Rooms Price List.xlsx", living, size=len(living)),
        ],
        vendor_overrides={
            "Beds A-F.xlsx": "Criswell Bedroom",
            "Beds H-W.xlsx": "Criswell Bedroom",
            "Wholesale Price List.xlsx": "Criswell Bedroom",
            "Living Rooms Price List.xlsx": "Criswell Bedroom",
        },
    )
    store = svc._drop_parse_store()
    payload = store.load(view.session_id)
    assert payload is not None
    for file_payload in payload["files"]:
        file_payload["readiness"] = {
            "load_ready": True,
            "block_code": "",
            "block_message": "",
        }
    store.save(view.session_id, payload)

    result = svc.commit_drop_load(
        view.session_id,
        [
            DropLoadBinding(0, "Criswell Bedroom", 2.7),
            DropLoadBinding(1, "Criswell Bedroom", 2.7),
            DropLoadBinding(2, "Criswell Bedroom", 2.7),
            DropLoadBinding(3, "Criswell Bedroom", 2.7),
        ],
    )

    assert len(result.results) == 1
    assert result.results[0].status == "loaded"
    assert result.results[0].builder == "Criswell Bedroom"
    parts = set(
        svc.repo.search("", vendor="Criswell Bedroom", limit=50)["part_number"].astype(str)
    )
    assert {"CWF1100", "CWF1154", "CWF8111", "CWF3044"} <= parts
