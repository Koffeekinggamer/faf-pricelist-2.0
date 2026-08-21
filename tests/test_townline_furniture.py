from types import SimpleNamespace

import pandas as pd

import backend.townline_import as townline_import
from wide_import import WorkbookImportResult


def test_visible_unfinished_and_finished_tabs_keep_distinct_finish_states(monkeypatch):
    views = [
        SimpleNamespace(name="Unfinished", raw=pd.DataFrame([[1]])),
        SimpleNamespace(name="Finished", raw=pd.DataFrame([[1]])),
    ]
    monkeypatch.setattr(townline_import, "read_all_sheets", lambda data: views)

    def fake_sheet(data, *, sheet_name, vendor, filename):
        return WorkbookImportResult(
            sheets_tried=[{"sheet": sheet_name, "rows": 1}],
            long_df=pd.DataFrame(
                [
                    {
                        "vendor": vendor,
                        "part_number": "TL-25",
                        "description": "Acadia Hutch",
                        "finish_state": "finished",
                        "base_price": 100,
                        "line_kind": "item",
                    }
                ]
            ),
            detected_markup=None,
            sheet_names=[sheet_name],
            notes="test",
        )

    monkeypatch.setattr(townline_import, "_read_sheet", fake_sheet)

    result = townline_import.import_townline_workbook(
        b"x", vendor="Townline Furniture", filename="Townline.xlsx"
    )

    assert list(result.long_df["finish_state"]) == ["unfinished", "finished"]
