"""Viztech monthly import must use Drop Load, not add_rows."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl

from backend.service import PriceBookService
from scripts.viztech_sync import (
    drop_load_ranked_files,
    import_folder,
    ranked_excel_plan,
    vendor_from_folder,
)


def _catalog_xlsx(part: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["Part #", "Description", "Species", "Wholesale"])
    for i in range(40):
        ws.append([f"{part}{i}", f"{part} item {i}", "Oak", 100 + i])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _service(tmp_path: Path) -> PriceBookService:
    svc = PriceBookService(tmp_path / "master.db")
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    svc._builder_profile_root = tmp_path / "profiles"
    return svc


def test_ranked_excel_plan_keeps_every_pricesheet_in_a_builder_folder(tmp_path):
    """Kidron ships Harbor, Solo Galaxy, and the rest as separate books. Load all of them."""
    cache = tmp_path / "viztech-cache"
    unzipped = cache / "Kidron_Woodcraft" / "Download_unzipped"
    unzipped.mkdir(parents=True)
    for name in (
        "Harbor.xlsx",
        "Solo Galaxy.xlsx",
        "Cover Page.xlsx",
        "Quotes Calculator.xlsx",
    ):
        (unzipped / name).write_bytes(_catalog_xlsx(name[:2]))

    plan = ranked_excel_plan(cache)
    names = {path.name for vendor, files in plan for path in files if vendor == "Kidron Woodcraft"}

    assert names == {"Harbor.xlsx", "Solo Galaxy.xlsx"}


def test_ajs_luxhome_book_is_not_claimed_as_an_ajs_pricesheet(tmp_path):
    cache = tmp_path / "viztech-cache"
    folder = cache / "AJ_039_s_Furniture"
    folder.mkdir(parents=True)
    (folder / "Download_2026_Pricelist_Finished.xls").write_bytes(_catalog_xlsx("F"))
    (folder / "Download_2026_LuxHome_Pricelist.xls").write_bytes(_catalog_xlsx("L"))

    plan = ranked_excel_plan(cache)
    names = {path.name for vendor, files in plan for path in files if "AJ" in vendor}

    assert any("Finished" in name for name in names)
    assert not any("LuxHome" in name for name in names)


def test_import_folder_binds_every_pricesheet_to_the_same_builder(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    cache = tmp_path / "viztech-cache"
    folder = cache / "Kidron_Woodcraft"
    folder.mkdir(parents=True)
    harbor = folder / "Harbor.xlsx"
    solo = folder / "Solo Galaxy.xlsx"
    harbor.write_bytes(_catalog_xlsx("H"))
    solo.write_bytes(_catalog_xlsx("S"))

    captured = {"bindings": []}
    real_commit = svc.commit_drop_load

    def counting_commit(session_id, bindings, **kwargs):
        captured["bindings"] = list(bindings)
        return real_commit(session_id, bindings, **kwargs)

    monkeypatch.setattr(svc, "commit_drop_load", counting_commit)
    monkeypatch.setattr(
        svc,
        "add_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("blocked Drop must not call add_rows")
        ),
    )

    summary = import_folder(cache, svc=svc)

    assert [binding.builder for binding in captured["bindings"]] == [
        "Kidron Woodcraft",
        "Kidron Woodcraft",
    ]
    assert summary["blocked"] == 1
    assert "extras unused" not in str(summary)


def test_drop_load_ranked_files_commits_through_the_gate(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    folder = tmp_path / "Alpha-Furniture"
    folder.mkdir()
    path = folder / "2025 Pricelists.xlsx"
    path.write_bytes(_catalog_xlsx("A"))

    add_rows_calls = {"n": 0}
    real_add = svc.add_rows

    def counting_add(*args, **kwargs):
        add_rows_calls["n"] += 1
        return real_add(*args, **kwargs)

    monkeypatch.setattr(svc, "add_rows", counting_add)

    summary = drop_load_ranked_files(svc, [("Alpha Furniture", path, 2.7)])
    # Thin fixture is blocked by species_quality — that is the gate working.
    assert summary["blocked"] == 1
    assert summary["ok"] == 0
    assert add_rows_calls["n"] == 0
    assert "Alpha Furniture" not in set(svc.repo.list_vendors())


def test_import_folder_uses_drop_load_not_direct_add_rows(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    cache = tmp_path / "viztech-cache"
    builder_dir = cache / "Black-Horse-Furniture"
    builder_dir.mkdir(parents=True)
    xlsx = builder_dir / "2025 Pricelists.xlsx"
    xlsx.write_bytes(_catalog_xlsx("BH"))
    assert xlsx.stat().st_size > 2000
    assert vendor_from_folder(builder_dir.name)

    commit_calls = {"n": 0}
    real_commit = svc.commit_drop_load

    def counting_commit(*args, **kwargs):
        commit_calls["n"] += 1
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(svc, "commit_drop_load", counting_commit)

    def boom(*args, **kwargs):
        raise AssertionError("blocked Drop must not call add_rows")

    monkeypatch.setattr(svc, "add_rows", boom)

    summary = import_folder(cache, svc=svc)
    assert commit_calls["n"] == 1
    assert summary["blocked"] == 1
    assert summary["ok"] == 0
