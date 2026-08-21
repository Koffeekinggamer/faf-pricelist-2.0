"""Locked Townline reader preserving visible Finished/Unfinished twins."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result


def _read_sheet(
    data: bytes,
    *,
    sheet_name: str,
    vendor: str,
    filename: str,
) -> WorkbookImportResult:
    from wide_import import import_workbook

    return import_workbook(
        data,
        vendor=vendor,
        filename=filename,
        sheet_filter=[sheet_name],
        force_layout_guess=True,
    )


def import_townline_workbook(
    data: bytes,
    *,
    vendor: str = "Townline Furniture",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    views = read_all_sheets(data)
    names = [view.name for view in views]
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    for view in views:
        name = str(view.name)
        if sheet_filter and name not in sheet_filter:
            continue
        if name.strip().casefold() not in {"finished", "unfinished"}:
            continue
        parsed = _read_sheet(
            data,
            sheet_name=name,
            vendor=vendor,
            filename=filename,
        )
        frame = parsed.long_df.copy()
        if frame.empty:
            tried.append({"sheet": name, "rows": 0})
            continue
        frame["finish_state"] = (
            "unfinished" if name.strip().casefold() == "unfinished" else "finished"
        )
        if default_collection:
            frame["collection"] = frame["collection"].replace("", default_collection)
        frames.append(frame)
        tried.extend(parsed.sheets_tried)

    long_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result = WorkbookImportResult(
        sheets_tried=tried,
        long_df=long_df,
        detected_markup=None,
        sheet_names=names,
        notes="Townline visible Finished/Unfinished sheets",
        expected_option_lines=0,
    )
    return tag_import_result(result, "townline_furniture")
