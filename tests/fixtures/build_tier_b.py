"""Synthetic visible-tab workbooks for Tier B SETTLED fixtures.

Layouts are cloned from the dedicated tests / readers already in the repo.
Nothing is hidden. Empty Options is a capture miss — every book encodes adders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import openpyxl

OPTIONS_TAB = [
    ["Options"],
    ["For painting , Add 10%"],
    ["Two Toning", "", "ADD 20%"],
    ["Lock: $25"],
]


def _save(path: Path, sheets: dict[str, list[list]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    wb.save(path)


def build_ajs(path: Path) -> None:
    header = [
        None,
        None,
        "FABRIC",
        "RED OAK & BROWN MAPLE",
        "CHERRY &\n1/4 SAWN\n WHITE",
        "WALNUT",
        "Roughsawn Brown Maple",
        "OPTIONAL SPRINGS\nADD",
        "MOTORIZED MECHANISM ADD",
        "RECHARGABLE BATTERY PACK ADD",
        "FABRIC & LEATHER \nYARDAGE\nCHART",
        "\nREPLACEMENT\nCUSHIONS",
    ]
    _save(
        path,
        {
            "Cover": [["AJ's Furniture — synthetic CI fixture"]],
            "Finished Wholesale MARKUP": [
                [None, None, None, "FINISHED PRICES", None, None, None, "OPTIONS"],
                header,
                [
                    "101 CSC",
                    "Cubic Slat Chair",
                    "Standard",
                    887.45,
                    1008.58,
                    1109.69,
                    None,
                    77.7,
                    94.5,
                    105.0,
                    "4 yd",
                    393.75,
                ],
                [
                    "101 CSC",
                    "Cubic Slat Chair",
                    "Premium",
                    916.85,
                    1037.98,
                    1139.09,
                    None,
                    77.7,
                    94.5,
                    105.0,
                    None,
                    423.15,
                ],
                [
                    "102 CSC",
                    "Cubic Slat Sofa",
                    "Standard",
                    1280.0,
                    1400.0,
                    1520.0,
                    None,
                    88.0,
                    110.0,
                    120.0,
                    "8 yd",
                    510.0,
                ],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_amish_aspen(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Amish Aspen — synthetic CI fixture"]],
            "Options": OPTIONS_TAB,
            "Pricelist": [
                ["Bedroom"],
                ["Coffee Table", None, None, 250, "24 x 48"],
                ["Night Stand", None, None, 180, "18 x 18"],
                ["Chest", None, None, 420, "36 x 20"],
            ],
        },
    )


def build_brookside(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Brookside Home Furnishings — synthetic CI fixture"]],
            "Heritage  Hutches": [
                ["Heritage Collection", "", "", "", "", "", "", "", "", "", "Heritage Collection"],
                ["Hutches"],
                [
                    "Unit #",
                    "Description",
                    "Oak ",
                    0,
                    "S Chy Brown Maple Rus Hick",
                    0,
                    "Cherry Elm Hickory",
                    0,
                    "QSWO",
                    0,
                    "Unit #",
                    "Description",
                    "Oak ",
                ],
                ["", "", "Finished prices - For Unfinished Deduct end column % ", "", "", "", "", "", "", "Unf"],
                ["#16", "2 Door Top", 658.75, "", 724.63, "", 823.44, "", 955.19, 0.08, "#16", "2 Door Top", 658.75],
                ["#13", "2 Door Base", 809.53, "", 890.48, "", 1011.91, "", 1173.82, 0.08],
            ],
            "Options": OPTIONS_TAB,
            "Markup": [["Standard Markup", 1.0]],
        },
    )


def build_five_star(path: Path) -> None:
    """Oak-priced dining sizes plus wood % and real Options. Visible tabs only."""
    _save(
        path,
        {
            "Cover": [["Five Star Tables — synthetic CI fixture"]],
            "Tables": [
                ["Dining Tables"],
                ["42x66", 900],
                ["48x72", 1100],
                ["Side Chair", 200],
            ],
            "Options": [
                ["Options"],
                ["Regular prices listed are in Oak"],
                ["For Walnut, ADD 80%"],
                ["For Cherry / Maple / Elm, ADD 35%"],
                ["Two Toning", "", "ADD 20%"],
                ["Lock: $25"],
                ["Terms"],
                ["Net 30"],
            ],
        },
    )


def build_fredericksburg(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Fredericksburg Furniture — synthetic CI fixture"]],
            "Bedroom": [
                [None, None, "Oak", "Cherry", "QSWO"],
                [None, None, "Finished", "Finished", "Finished"],
                ["#16", "2 Door Top", 658, 724, 823],
                ["#13", "2 Door Base", 809, 890, 1011],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_frog_pond(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Frog Pond Furniture — synthetic CI fixture"]],
            "1 Weston ": [
                ["", "", "", "", "", "10% Less for unfinished"],
                [
                    "Weston Collection",
                    "",
                    "",
                    "",
                    "",
                    "Sap Cherry, Oak, Brown Maple, Rustic Cherry",
                    "Elm, Cherry, Hickory, QSWO, Hard Maple",
                ],
                ["", "", "", "", "", "Finished", "Finished"],
                ["Item #", "Description", 'H"', 'W"', 'D"'],
                ["100K", "King Bed w/ Regular Footboard", 53, 80, 87, 966, 1256],
                ["105", "3 Drawer Night Stand", 26, 24, 17.5, 478, 621],
            ],
            "Options": [
                ["Options"],
                ["Painting add 10%"],
                ["2-Toned Stains add 5%"],
            ],
            "Markup": [["Standard Markup", 1.0]],
            "Index": [["Bedroom Collection Index"]],
        },
    )


def build_hillside(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Hillside Chair — synthetic CI fixture"]],
            "Options": OPTIONS_TAB,
            "Sheet3": [
                ["Small Avon: AC364 Side Chair", None, "Oak", None, "Cherry", None, "Walnut"],
                [None, None, "Unf", "Fin", "Unf", "Fin", "Unf", "Fin"],
                [None, "Side Chair", 100, 140, 110, 154, 130, 182],
                [None, "Arm Chair", 120, 168, 132, 185, 156, 218],
            ],
        },
    )


def build_hogback(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Hogback Design And Finishing — synthetic CI fixture"]],
            "Pricing": [
                ["HB10", "Nightstand", "24x18", 400, 520],
                ["HB11", "Chest", "36x20", 600, 780],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_hope_wood(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Hope Wood / HW Chair — synthetic CI fixture"]],
            "Markup Calculator": [
                ["HW Chair markup calculator"],
                [None, "Oak", "Cherry", "Walnut"],
                [None, "C", "D", "E"],
                ["Side Chair", 200, 220, 260],
                ["Arm Chair", 240, 264, 312],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_j_troyer(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["J. Troyer & Company — synthetic CI fixture"]],
            "Buffet": [
                ["ELENA COLLECTION"],
                [
                    "Item#",
                    "Description",
                    "Dimensions",
                    "BR. Maple, Oak, R-Cherry",
                    "PREMIUM Cherry, QSWO",
                ],
                ["7430-64", "Buffet - 4 Doors", '32"H x 64"W', 1258.95, 1344],
                ["1101", "End Table", '24" H', 301.74, 340],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_kidron(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Kidron Woodcraft — synthetic CI fixture"]],
            "Prices": [
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
                ],
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
                ],
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
                ],
                [
                    "#S8081 Solo Bookcase Tall",
                    2400,
                    None,
                    2800,
                    None,
                    None,
                    None,
                    None,
                    None,
                    800,
                    700,
                    1040,
                    910,
                    920,
                    810,
                    1260,
                    1100,
                ],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_lamb(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["LAMB — synthetic CI fixture"]],
            "Wholesale": [
                ["FURNITURE OPTIONS"],
                ["LED Lights", None, None, None, None, None, 45],
                ["Lock", None, None, None, None, None, 25],
                ["ASHTON"],
                [
                    "Item No.",
                    "Size",
                    "Description",
                    "Oak, Brown Maple",
                    "Cherry, Hickory",
                    "Finishing Cost",
                    "Oak, Brown Maple",
                    "Cherry, Hickory",
                ],
                [
                    "LA-ASH-3067-EX",
                    "30x67",
                    "Ashton Table",
                    500,
                    550,
                    80,
                    580,
                    630,
                ],
                [
                    "LA-ASH-1848-NS",
                    "18x48",
                    "Ashton Nightstand",
                    220,
                    240,
                    40,
                    260,
                    280,
                ],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_maple_lane(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Maple Lane — synthetic CI fixture"]],
            "Wholesale": [
                ["Pet Diner"],
                ["CODE", "Description", None, "Red Oak", "Br. Maple"],
                ["ML10", "Pet Diner"],
                [None, "24 x 18", None, 220, 240],
                ["ML20", "Toy Box"],
                [None, "36 x 20", None, 310, 340],
                ["Maui Quartz = MQ"],
                ["Crypton fabric pads come in three colors"],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_patio_kraft(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Patio Kraft — synthetic CI fixture"]],
            "Retail": [["Retail twin — viewed, not the wholesale source"], ["VECG", 567]],
            "Wholesale": [
                ["Vienna Collection"],
                [None, None, "Standard Colors", "Bright Colors", "Woodgrain Colors"],
                ["Item #", "Description", "Price", "Price", "Price"],
                ["VECG", "Chair Glider", 210, 230, 250],
                ["Item #", "Description", "Price", "Price", "Price"],
                ["VELC", "Lounge Chair", 280, 300, 330],
                ["Item #", "Description", "Price", "Price", "Price"],
                ["VEBN", "Bench", 190, 210, 230],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_superior(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Superior Woodcrafts — synthetic CI fixture"]],
            "Pricelist": [
                [
                    "ITEM #",
                    "DESCRIPTION",
                    "WOOD SPECIES",
                    "UNFINISHED",
                    "FINISHED",
                    "UNFIN.RETAIL",
                    "FIN.RETAIL",
                ],
                ["A1", "Desk", "Oak", 100, 130, 270, 351],
                ["A1C", "Desk", "Cherry", 120, 150, 324, 405],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_townline(path: Path) -> None:
    catalog = [
        ["Item #", "Description", "Oak", "Cherry"],
        ["TL-25", "Acadia Hutch", 400, 440],
        ["TL-30", "Acadia Base", 320, 352],
    ]
    _save(
        path,
        {
            "Cover": [["Townline Furniture — synthetic CI fixture"]],
            "Finished": catalog,
            "Unfinished": [
                ["Item #", "Description", "Oak", "Cherry"],
                ["TL-25", "Acadia Hutch", 360, 396],
                ["TL-30", "Acadia Base", 288, 317],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_troyer_ridge(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Troyer Ridge Furniture — synthetic CI fixture"]],
            "Bedroom": [
                [
                    "Oak / Brown Maple / Rustic Hickory / Rustic Cherry",
                    None,
                    None,
                    None,
                    "Hard Maple / Cherry / QSWO",
                ],
                ["TR100 Dresser"],
                [
                    "Queen",
                    '54" W',
                    800,
                    None,
                    900,
                    None,
                    None,
                    None,
                    700,
                    800,
                    800,
                    900,
                ],
                [
                    "King",
                    '76" W',
                    880,
                    None,
                    990,
                    None,
                    None,
                    None,
                    770,
                    880,
                    880,
                    990,
                ],
            ],
            "Options": OPTIONS_TAB,
        },
    )


def build_windy_acres(path: Path) -> None:
    _save(
        path,
        {
            "Cover": [["Windy Acres Furniture — synthetic CI fixture"]],
            "Bedroom Collection": [
                ["", "Options"],
                ["", "For two tone add 35.00 per piece"],
                ["", "Painting add 15%"],
                ["", "For hidden jewelry drawer add 100.00"],
                ["", "Addie Collection - Value Groups"],
                [
                    "",
                    "Addie",
                    "",
                    "",
                    "",
                    "",
                    "Br. Maple\nWormy Maple\nR. Cherry",
                    "",
                    "Elm\nHickory\nCherry",
                    "",
                    "R. Walnut\nQSWO",
                ],
                [
                    "",
                    "ITEM #",
                    "Description",
                    'D"',
                    'W"',
                    'H"',
                    "Finished",
                    "Unfinished",
                    "Finished",
                    "Unfinished",
                    "Finished",
                    "Unfinished",
                ],
                [
                    "1702-NS-AC-F",
                    "1702",
                    "Night stand 3-Drawer",
                    16.25,
                    22,
                    27.75,
                    429,
                    377,
                    455,
                    407,
                    526,
                    475,
                ],
                [
                    "1715-CK-AC-WSR-AW",
                    "1715-CK",
                    "California King-W/Storage Rails",
                    "",
                    53,
                    25,
                    1629,
                    1438,
                    1782,
                    1591,
                    2013,
                    1822,
                ],
            ],
            "Instructions": [["INSTRUCTIONS - PLEASE READ CAREFULLY!"]],
            "MarkUp": [["Markup", 1.0]],
        },
    )


TIER_B_BUILDERS: dict[str, Callable[[Path], None]] = {
    "AJ's Furniture": build_ajs,
    "Amish Aspen": build_amish_aspen,
    "Brookside Home Furnishings": build_brookside,
    "Fredericksburg Furniture": build_fredericksburg,
    "Five Star Tables": build_five_star,
    "Frog Pond Furniture": build_frog_pond,
    "Hillside Chair": build_hillside,
    "Hogback Design And Finishing": build_hogback,
    "Hope Wood": build_hope_wood,
    "J. Troyer & Company": build_j_troyer,
    "Kidron Woodcraft": build_kidron,
    "LAMB": build_lamb,
    "Maple Lane": build_maple_lane,
    "Patio Kraft": build_patio_kraft,
    "Superior Woodcrafts": build_superior,
    "Townline Furniture": build_townline,
    "Troyer Ridge Furniture": build_troyer_ridge,
    "Windy Acres Furniture": build_windy_acres,
}
