#!/usr/bin/env python3
"""Reparse existing builders through locked readers and Drop Load.

Only builders already present in the master book are eligible.  Exact source
filenames come from their Builder Profiles; missing or blocked files never
replace a catalog.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import PriceBookService
from backend.builder_profiles import load_builder_profile
from backend.drop_parse_session import DropLoadBinding, DropUpload
from scripts.finalreview_inspect import index_excels, resolve
from scripts.viztech_sync import backup_db


def reimport_locked_builders(
    *,
    apply: bool,
    only: set[str] | None = None,
    min_ratio: float = 0.2,
) -> dict:
    svc = PriceBookService()
    svc.init()
    summary = svc.vendor_summary()
    existing_rows = {
        str(row["vendor"]): int(row["rows"])
        for _, row in summary.iterrows()
    }
    vendors = sorted(existing_rows)
    if only:
        vendors = [vendor for vendor in vendors if vendor in only]
    excel_index = index_excels()

    if apply:
        backup_db()

    results = []
    for position, vendor in enumerate(vendors, start=1):
        profile = load_builder_profile(vendor)
        parser = profile.get("parser") or {}
        source_file = str(parser.get("source_file") or "")
        importer = str(parser.get("importer") or "")
        paths = resolve(source_file, excel_index)
        expected_files = [
            part.strip()
            for part in source_file.split(" + ")
            if part.strip()
        ]
        item = {
            "vendor": vendor,
            "position": position,
            "builders": len(vendors),
            "importer": importer,
            "source_file": source_file,
            "paths": [str(path) for path in paths],
            "old_rows": existing_rows[vendor],
        }
        print(
            f"[{position}/{len(vendors)}] {vendor} "
            f"parser={importer or '?'} files={len(paths)}/{len(expected_files)}",
            flush=True,
        )
        if not importer or not source_file:
            item.update(status="blocked", reason="profile parser/source missing")
            results.append(item)
            continue
        if len(paths) != len(expected_files):
            item.update(status="blocked", reason="locked source file missing")
            results.append(item)
            continue

        uploads = []
        bindings = []
        vendor_overrides = {}
        for file_index, path in enumerate(paths):
            data = path.read_bytes()
            drop_name = f"{path.parent.name}/{path.name}"
            uploads.append(DropUpload(drop_name, data, size=len(data)))
            bindings.append(
                DropLoadBinding(
                    file_index=file_index,
                    builder=vendor,
                    multiplier=svc.get_vendor_multiplier(vendor),
                )
            )
            vendor_overrides[drop_name] = vendor
        view = svc.ensure_drop_parse_session(
            uploads,
            vendor_overrides=vendor_overrides,
            force=True,
        )
        item["parsed_rows"] = view.total_rows
        item["files"] = [
            {
                "filename": file.filename,
                "rows": file.row_count,
                "load_ready": file.readiness.load_ready,
                "block": file.readiness.block_message,
                "parser": file.detected_importer,
            }
            for file in view.files
        ]
        blocked = [file for file in view.files if not file.readiness.load_ready]
        minimum = max(1, int(existing_rows[vendor] * min_ratio))
        if blocked:
            item.update(status="blocked", reason="one or more source files not ready")
            results.append(item)
            continue
        if view.total_rows < minimum:
            item.update(
                status="blocked",
                reason=f"parsed row count {view.total_rows} below safety floor {minimum}",
            )
            results.append(item)
            continue
        if not apply:
            item["status"] = "ready"
            results.append(item)
            continue

        batch = svc.commit_drop_load(
            view.session_id,
            bindings,
            mode="replace_vendor",
        )
        loaded = next(
            (result for result in batch.results if result.builder == vendor),
            None,
        )
        if loaded is None:
            item.update(status="error", reason="missing Drop Load result")
        else:
            item.update(
                status=loaded.status,
                catalog=loaded.catalog,
                parser=loaded.parser_id,
                warning=loaded.profile_warning,
            )
        results.append(item)

    return {
        "apply": apply,
        "started": datetime.now().isoformat(timespec="seconds"),
        "builders": len(vendors),
        "status_counts": {
            status: sum(1 for result in results if result.get("status") == status)
            for status in sorted({str(result.get("status")) for result in results})
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--min-ratio", type=float, default=0.2)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/tmp/reimport_locked_descriptions.json"),
    )
    args = parser.parse_args()
    report = reimport_locked_builders(
        apply=args.apply,
        only=set(args.only) or None,
        min_ratio=args.min_ratio,
    )
    args.report.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["status_counts"], indent=2), flush=True)
    print(f"WROTE {args.report}", flush=True)
    return 0 if not report["status_counts"].get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
