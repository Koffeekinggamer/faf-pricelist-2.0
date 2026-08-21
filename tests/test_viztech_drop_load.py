"""Viztech monthly import must use Drop Load, not add_rows."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl

from backend.service import PriceBookService
from scripts.viztech_sync import drop_load_ranked_files, import_folder, vendor_from_folder


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
