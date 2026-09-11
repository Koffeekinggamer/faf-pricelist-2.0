"""Write the committed CI Excel fixtures from known-good synthetic layouts."""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixture_corpus import (  # noqa: E402
    OPTIONS_FIXTURE,
    SETTLED_FIXTURES,
    WIDE_FIXTURE,
)


def _book(sheets: dict[str, list[list]]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        for row in rows:
            ws.append(row)
        assert ws.sheet_state == "visible"
    return wb


def _save(path: Path, sheets: dict[str, list[list]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = _book(sheets)
    wb.save(path)


def build_fn_chair(path: Path) -> None:
    pl_print = [
        [
            "Abe",
            None,
            "Red Oak / Sap Cherry / Wormy Maple / Rustic Red Oak",
            "Brown Soft Maple / Rustic Brown Maple / Rustic Cherry",
            "Walnut / Rustic Walnut",
            None,
            None,
            None,
            None,
            None,
            "Solid Fabrics / COM",
        ],
        ["Side Chair", "Unf", 105, 113, 216, None, None, None, None, None, 23],
        [None, "Cat. 1", 147, 155, 258, None, None, None, None, None, None],
        [None, "Cat. 2", 181, 189, 292, None, None, None, None, None, None],
        ["Arm Chair", "Unf", 144, 155, 280, None, None, None, None, None, 23],
        [None, "Cat. 1", 199, 210, 335, None, None, None, None, None, None],
        [
            "Alana",
            None,
            "Red Oak / Sap Cherry / Wormy Maple / Rustic Red Oak",
            "Brown Soft Maple / Rustic Brown Maple / Rustic Cherry",
            "Walnut / Rustic Walnut",
            None,
            None,
            None,
            None,
            None,
            "Solid Fabrics / COM",
        ],
        ["Side Chair", "Unf", 110, 118, 220, None, None, None, None, None, 23],
        [None, "Cat. 1", 160, 168, 270, None, None, None, None, None, None],
    ]
    _save(
        path,
        {
            "Cover Page": [["FN Chair Level One — synthetic CI fixture"]],
            "PCL Color List": [["STAIN COLORS"], ["Cat. 1", "Natural"]],
            "PL Print": pl_print,
            "PL With Markup": [["Markup"], [2.7]],
            "PL To Export": [["Abe Side Chair", 92]],
        },
    )


def build_ashery_oak(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Ashery Oak — synthetic CI fixture"]],
            "Markup": [["Enter Markup"], [2.7]],
            "Options&Portal": [
                ["Wood Species Pricing", None, None, "ADD"],
                [
                    "Regular prices listed are in Oak, Rustic Cherry, Sap Cherry, and Brown Maple"
                ],
                ["Hickory …", None, None, 0.10],
                ["Rustic Walnut …", None, None, 0.10],
                ["QSWO …", None, None, 0.30],
                ["Prime Walnut …", None, None, 0.55],
                ["Options"],
                ["For painting , Add:", None, None, 0.35],
                ["For Locks on Drawers , Add:", None, None, 13],
            ],
            "Products": [
                [None, None, None, "Oak / Rustic Cherry", "Hickory", "QSWO / Cherry"],
                ["Model #", "Description", "Overall Size", "Regular", "10% More", "35% More"],
                ["BARN FLOOR OCCASIONAL TABLES", None, None, None, None, None],
                ["BF-1648-DS", "Sofa Table", '48"W x 16"D x 30"H', 350, 366, 450],
                ["BF-1648-END", "End Table", '24"W x 16"D x 24"H', 220, 230, 280],
            ],
        },
    )


def build_jmw(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["J & M Woodworking — synthetic CI fixture"]],
            "Markup": [["Enter Markup"], [2.7]],
            " Percentage": [
                [None, "Wood Specie", "Percentage"],
                [None, "Br. Maple", 0],
                [None, "Cherry", 0.1],
                [None, "Walnut", 0.6],
                [None, "QSWO", 0.3],
            ],
            "Hampton": [
                ["Hampton Collection"],
                ["Item #", "Description", "Br. Maple"],
                ["40", "Mule Chest", 400],
                ["41", "Nightstand with Fabric Panel", 220],
            ],
            "Specialty Finish Options": [
                ["Specialty Finish Options", None, None],
                ["Item", "2-tone Stain", "Paint"],
                ["King Bed", 75, 135],
                ["Queen Bed", 75, 130],
            ],
        },
    )


def build_artisan_chairs(path: Path) -> None:
    wholesale = [
        ["Artisan Chairs Wholesale — synthetic CI fixture"],
        ["", "Unfinished", "", "", "", "Finished", "", "", ""],
        [
            "Aberdeen",
            "Oak",
            "Cherry",
            "Walnut",
            "Brown Maple",
            "Oak",
            "Cherry",
            "Walnut",
            "Brown Maple",
        ],
        ["Side Chair", 108, 118, 140, 112, 150, 165, 195, 155],
        ["Arm Chair", 140, 152, 180, 145, 199, 220, 260, 205],
        ["Desk Arm Chair w/ Gas Lift", 220, 240, 280, 228, 317, 349, 410, 328],
        ["Asher"],
        [
            "Asher",
            "Oak",
            "Cherry",
            "Walnut",
            "Brown Maple",
            "Oak",
            "Cherry",
            "Walnut",
            "Brown Maple",
        ],
        ["Side Chair", 120, 132, 160, 125, 170, 187, 225, 176],
        ["Arm Chair", 188, 206, 248, 195, 266, 292, 350, 275],
        ["Options"],
        ["", "Fabric Seat", "", "", "ADD $12"],
        ["", "Premium Seat + Revolutionary + Crypton", "", "", "ADD $18"],
        ["", "Leather Seat", "", "", "ADD $45"],
        ["", "Nail Heads", "", "", "ADD $20"],
        ["Internet policy"],
    ]
    _save(
        path,
        {
            "Retail with MARKUP": [
                ["Artisan Chairs retail twin — viewed, not imported"],
                ["Side Chair", 405],
            ],
            "Wholesale": wholesale,
        },
    )


def build_criswell(path: Path) -> None:
    _save(
        path,
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE — synthetic CI fixture"]],
            "Bloomfield Collection": [
                [
                    "CWF8100 Series Bloomfield Set",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "CWF8100 Series Bloomfield Set",
                ],
                [None, None, "Oak", None, "Cherry", None, "QSWO", None, None, None, "Oak"],
                [
                    "CWF8111",
                    "Tall Dresser",
                    1099,
                    None,
                    1170,
                    None,
                    1359,
                    None,
                    "CWF8111",
                    "Tall Dresser",
                    1099,
                    None,
                    1170,
                    None,
                    1359,
                ],
                [
                    "CWF8112",
                    "Chest",
                    899,
                    None,
                    960,
                    None,
                    1110,
                    None,
                    "CWF8112",
                    "Chest",
                    899,
                    None,
                    960,
                    None,
                    1110,
                ],
            ],
            "Options ": [
                ["Options", None, "Oak", None, "Cherry"],
                ["Phone Charger", 55, None, 55, None],
                ['20" high low footboard (DEDUCT)', 203],
            ],
        },
    )


def build_genuine_oak_wide(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Genuine Oak Designs — synthetic CI wide_species fixture"]],
            "Pricelist": [
                ["Item #", "Description", "Oak", "Cherry", "Walnut"],
                ["T-100", "Trestle Table", 500, 550, 600],
                ["C-10", "Side Chair", 120, 130, 140],
                ["B-20", "Bench", 180, 198, 220],
            ],
        },
    )


def build_millcraft_options(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Millcraft — synthetic CI Options-tab fixture"]],
            "Options": [
                ["", "PREFERRED DEALER Wholesale Price List"],
                ["", "", "Standard Options *No Upcharge*"],
                ["", "Oak", "Brown Maple"],
                ["", "ADD 10%"],
                ["", "Size Changes", "", "", "ADD ON OPTIONS"],
                [
                    "",
                    "Any casegood or bed can be customized up to 10''.",
                    "",
                    "",
                    "Hidden Jewelry Tray: $30",
                ],
                ["", "Two Toning", "", "", "Lock: $25"],
                ["", "ADD 20%"],
                ["", "Size changes on any casegood or bed over 10''."],
                ["", "Premium Finish Choices:"],
                ["", "Distressing"],
                ["", "Hand Rubbed Oil"],
            ],
            "Pricelist": [
                ["Description", "Item Number", "Oak", "Brown Maple"],
                ["1 Drw Nightstand", "MAG22NS", 410.5, 492.5],
                ["6 Drw Chest", "MAG66CH", 880, 1056],
            ],
        },
    )


def main() -> None:
    builders = {
        "FN Chair": build_fn_chair,
        "Ashery Oak": build_ashery_oak,
        "J & M Woodworking": build_jmw,
        "Artisan Chairs": build_artisan_chairs,
        "Criswell Bedroom": build_criswell,
    }
    for builder, _importer, _next_file, path, _opts in SETTLED_FIXTURES:
        builders[builder](path)
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    build_genuine_oak_wide(WIDE_FIXTURE[3])
    print(f"wrote {WIDE_FIXTURE[3].relative_to(ROOT)} ({WIDE_FIXTURE[3].stat().st_size} bytes)")
    build_millcraft_options(OPTIONS_FIXTURE[3])
    print(
        f"wrote {OPTIONS_FIXTURE[3].relative_to(ROOT)} ({OPTIONS_FIXTURE[3].stat().st_size} bytes)"
    )


if __name__ == "__main__":
    main()
