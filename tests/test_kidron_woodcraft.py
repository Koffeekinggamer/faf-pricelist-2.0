"""Kidron's visible Prices tab has retail formulas left and wholesale twins right."""

import io

import openpyxl

from backend.kidron_import import import_kidron_workbook


def _book() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prices"
    ws.append(
        [
            None,
            "Brown Maple\nOak",
            None,
            "Cherry\nWhite Oak\nHickory\nQSWO",
            None,
            None,
            None,
            None,
            None,
            "Brown Maple\nOak",
            None,
            "QSWO\nClear Maple\nHickory, Cherry",
            None,
            "Rustic\nCherry\nRustic QSWO",
            None,
            "Walnut",
        ]
    )
    ws.append(
        [
            "Solo Bookcases",
            "Fin",
            "Unfin",
            "Fin",
            "Unfin",
            None,
            None,
            None,
            None,
            "Fin",
            "Unfin",
            "Fin",
            "Unfin",
            "Fin",
            "Unfin",
            "Fin",
            "Unfin",
        ]
    )
    ws.append(
        [
            "#S8080 Solo Bookcase",
            2180,
            None,
            2610,
            None,
            None,
            None,
            None,
            None,
            716,
            628,
            943,
            831,
            830,
            729,
            1145,
            1007,
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reader_uses_wholesale_finish_twins_not_left_retail_formulas():
    result = import_kidron_workbook(
        _book(),
        vendor="Kidron Woodcraft",
        filename="Solo Galaxy.xlsx",
    )
    rows = result.long_df

    assert len(rows) == 8
    assert set(rows["finish_state"]) == {"finished", "unfinished"}
    brown = rows[rows["species"] == "Brown Maple / Oak"]
    assert dict(zip(brown["finish_state"], brown["base_price"])) == {
        "finished": 716.0,
        "unfinished": 628.0,
    }
    assert 2180.0 not in set(rows["base_price"])
    assert set(rows["part_number"]) == {"#S8080"}
    assert set(rows["description"]) == {"Solo Bookcase"}
    assert "Rustic Cherry / Rustic QSWO" in set(rows["species"])
