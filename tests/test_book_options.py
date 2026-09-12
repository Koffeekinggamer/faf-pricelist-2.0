"""Size-option pricing and finishes are Search Options for every builder."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd

from backend.book_options import extract_book_options, merge_book_options
from backend.standardize import canonical_option_label
from wide_import import WorkbookImportResult, import_workbook


def _xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pricelist"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _millcraft_front_matter() -> bytes:
    return _xlsx(
        [
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
            ["", "Description", "Item Number", "Standard Wood", "Premium Wood"],
            ["", "1 Drw Nightstand", "MAG22NS", 410.5, 492.5],
        ]
    )


def test_extracts_size_pct_finishes_and_flat_add_ons():
    rows = extract_book_options(_millcraft_front_matter(), vendor="Millcraft")
    by = {r["option_key"]: r for r in rows}
    assert by['Size change (up to 10")']["addon_pct"] == 10
    assert by['Size change (over 10")']["addon_pct"] == 20
    assert by["Two-tone"]["addon_pct"] == 10
    assert by["Distressing"]["addon_pct"] == 20
    assert by["Hand-rubbed oil"]["addon_pct"] == 20
    assert by["Hidden Jewelry Tray"]["base_price"] == 30
    assert by["Lock"]["base_price"] == 25
    assert all(r["line_kind"] == "addon" for r in rows)
    assert "Oak" not in by
    assert "Standard Wood" not in by


def test_wood_percent_adders_are_not_options():
    data = _xlsx(
        [
            ["Options"],
            ["Rec. Barnwood Oak add", "30% on 1st Column Price"],
            ["Clear black Walnut add", "50% on 1st Column Price"],
            ["Walnut, add 75% to the oak price."],
            ["Painting add 10%"],
        ]
    )
    keys = {r["option_key"] for r in extract_book_options(data, vendor="Frog Pond Furniture")}
    assert "Painting" in keys or "Paint" in keys
    assert not any("barnwood" in k.lower() for k in keys)
    assert not any("walnut" in k.lower() for k in keys)


def test_book_listed_woods_become_species_for_any_builder():
    existing = pd.DataFrame(
        [
            {
                "vendor": "Any Factory",
                "part_number": "NS1",
                "description": "Nightstand",
                "species": "Oak",
                "finish_state": "finished",
                "base_price": 200,
                "multiplier": 2.7,
                "adjusted_price": 540,
                "line_kind": "item",
                "option_key": None,
            }
        ]
    )
    result = WorkbookImportResult(
        sheets_tried=[],
        long_df=existing,
        detected_markup=None,
        sheet_names=["Pricelist"],
    )
    data = _xlsx(
        [
            ["Options"],
            ["Painting add 10%"],
            ["Walnut, ADD 50% to Oak pricing."],
        ]
    )
    merged = merge_book_options(result, data, vendor="Any Factory")
    items = merged.long_df[merged.long_df["line_kind"].fillna("item") != "addon"]
    woods = set(items["species"].astype(str))
    assert "Oak" in woods
    assert "Walnut" in woods
    walnut = items[items["species"] == "Walnut"]
    assert float(walnut["base_price"].iloc[0]) == 300
    assert float(walnut["adjusted_price"].iloc[0]) == 810
    keys = {str(k) for k in merged.long_df.get("option_key", []).fillna("") if str(k).strip()}
    assert any("paint" in k.lower() for k in keys)
    assert "Walnut" not in keys


def test_wood_named_collection_fills_blank_species():
    from backend.book_options import convert_option_woods_to_species

    df = pd.DataFrame(
        [
            {
                "vendor": "Brookside Home Furnishings",
                "part_number": "BA2341",
                "description": "Arm Chair",
                "species": None,
                "collection": "Barnwood",
                "finish_state": "finished",
                "base_price": 200,
                "line_kind": "item",
            }
        ]
    )
    out = convert_option_woods_to_species(df)
    assert str(out.iloc[0]["species"]) == "Barnwood"


def test_steel_and_metal_bases_fill_blank_species():
    from backend.book_options import convert_option_woods_to_species

    df = pd.DataFrame(
        [
            {
                "vendor": "Troyer Design Company",
                "part_number": "MHP-16",
                "description": 'COFFEE — 16" H',
                "species": None,
                "collection": "Steel Bases Wholesale prices",
                "finish_state": "finished",
                "base_price": 170,
                "line_kind": "item",
            },
            {
                "vendor": "Stone River Furniture",
                "part_number": "1100-10",
                "description": "Single Pedestal End Table",
                "species": None,
                "collection": "Metal Bases",
                "finish_state": "finished",
                "base_price": 152,
                "line_kind": "item",
            },
        ]
    )
    out = convert_option_woods_to_species(df)
    steel = out[out["part_number"] == "MHP-16"].iloc[0]
    metal = out[out["part_number"] == "1100-10"].iloc[0]
    assert steel["species"] == "Steel"
    assert metal["species"] == "Metal"


def test_cushions_fill_blank_species():
    from backend.book_options import convert_option_woods_to_species

    df = pd.DataFrame(
        [
            {
                "vendor": "Patio Kraft",
                "part_number": "BRCS",
                "description": "Replacement Cushion Sets (1 seat & 1 back)",
                "species": None,
                "collection": "Brooklyn Collection",
                "finish_state": "finished",
                "base_price": 209,
                "line_kind": "item",
            },
            {
                "vendor": "Patio Kraft",
                "part_number": "BRAC",
                "description": "Brooklyn Armrest Cushion (Set of 2)",
                "species": None,
                "collection": "Accessories",
                "finish_state": "finished",
                "base_price": 79,
                "line_kind": "item",
            },
        ]
    )
    out = convert_option_woods_to_species(df)
    assert (out["species"] == "Cushion").all()


def test_named_parser_wood_addon_converts_to_species():
    from backend.book_options import convert_option_woods_to_species

    df = pd.DataFrame(
        [
            {
                "vendor": "LAMB",
                "part_number": "T1",
                "description": "Table",
                "species": "Oak",
                "finish_state": "finished",
                "base_price": 400,
                "line_kind": "item",
                "option_key": None,
            },
            {
                "vendor": "LAMB",
                "part_number": "Walnut",
                "description": "Walnut",
                "species": None,
                "finish_state": "finished",
                "base_price": None,
                "line_kind": "addon",
                "option_key": "Walnut",
                "addon_pct": 50,
            },
            {
                "vendor": "LAMB",
                "part_number": "Paint",
                "description": "Paint",
                "species": None,
                "finish_state": "finished",
                "base_price": None,
                "line_kind": "addon",
                "option_key": "Paint",
                "addon_pct": 10,
            },
        ]
    )
    out = convert_option_woods_to_species(df)
    items = out[out["line_kind"].fillna("item") != "addon"]
    assert "Walnut" in set(items["species"].astype(str))
    assert float(items[items["species"] == "Walnut"]["base_price"].iloc[0]) == 600
    keys = {str(k) for k in out.get("option_key", []).fillna("") if str(k).strip()}
    assert "Paint" in keys
    assert "Walnut" not in keys


def test_import_workbook_puts_size_and_finish_on_search_options():
    data = _millcraft_front_matter()
    result = import_workbook(data, vendor="Millcraft", filename="Millcraft.xlsx")
    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    keys = set(addons["option_key"].astype(str))
    assert 'Size change (up to 10")' in keys
    assert "Two-tone" in keys
    assert "Lock" in keys


def test_skips_fn_ordering_select_consistent_color_instruction():
    data = _xlsx(
        [
            ["*IF ORDERING SELECT (CONSISTANT COLOR) ADD 30% PER CHAIR"],
            ["IF ORDERING SELECT (CONSISTANT COLOR OF WOOD AND STAIN) ADD 30%"],
            ["BARSTOOLS WITH ARMS: $30"],
        ]
    )
    keys = {r["option_key"] for r in extract_book_options(data, vendor="FN Chair")}
    assert not any("ordering select" in k.lower() for k in keys)
    assert not any("consist" in k.lower() for k in keys)
    assert "BARSTOOLS WITH ARMS" in keys


def test_skips_fn_elm_seat_upgrade_wood_note():
    book = (
        "*ANY SEAT CAN BE CHANGED TO A DIFFERENT WOOD SPECIES IF DESIRED. "
        "(ELM ALSO AVAILABLE) IF SEAT IS A UPGRADED (HIGHER PRICE BRACKET) "
        "WOOD SPECIE ADD $30. IF SEAT IS IN SAME PRICE BRACKET (OR LOWER) "
        "STANDARD PRICE IS USED. ALSO SEE  FINISHING OPTIONS."
    )
    live = "D. (ELM ALSO AVAILABLE) IF SEAT IS A UPGRADED…"
    data = _xlsx(
        [
            [book],
            [live, 30],
            ["INTERCHANGE ANY STYLE SEAT: $10"],
        ]
    )
    keys = {r["option_key"] for r in extract_book_options(data, vendor="FN Chair")}
    assert not any("elm also available" in k.lower() for k in keys)
    assert not any("seat is a upgraded" in k.lower() for k in keys)
    assert "INTERCHANGE ANY STYLE SEAT" in keys
    assert canonical_option_label(live) is None
    assert canonical_option_label(book) is None


def test_skips_cover_sheet_and_catalog_fragments():
    data = _xlsx(
        [
            ["4. Password for Price List"],
            ["Password: $4"],
            ["Suggested Markup for Online Sales: $2"],
            ["Tri-View: $21"],
            ["Lingerie: $34"],
            ["Straight Mirror: $27"],
            ["Twin/Full/Queen: $48"],
            ["King/California King Bed: $48"],
            ["6 Drawer Chest: $34"],
            ["2 Drawer Armoire: $41"],
            ["3 Drawer Night Stand: $27"],
            ["Pull Out Swivel: $12"],
            ["With leather: $175"],
            ["With TV Pullout Swivel (Add): $135"],
            ["Tall Dresser & Triple Dresser: $48"],
            ["Prices for the year: $2026"],
            ['36" Deep x 37" High OPTION: Hidden Chair: $120'],
            ["ieces 15% larger like the Premier Series, add 15%"],
            ["ADD 10%"],
            ["Size Changes"],
            ["Two Toning"],
            ["Distressing"],
            ["Premium Finish Choices:"],
            ["Hand Rubbed Oil"],
        ]
    )
    rows = extract_book_options(data, vendor="X")
    keys = {r["option_key"] for r in rows}
    assert "Password" not in keys
    assert not any("password" in k.lower() for k in keys)
    assert not any("markup" in k.lower() or "online sales" in k.lower() for k in keys)
    assert not any("tri" in k.lower() and "view" in k.lower() for k in keys)
    assert "Lingerie" not in keys
    assert "Straight Mirror" not in keys
    assert "Twin/Full/Queen" not in keys
    assert "King/California King Bed" not in keys
    assert "6 Drawer Chest" not in keys
    assert "2 Drawer Armoire" not in keys
    assert "3 Drawer Night Stand" not in keys
    assert "Pull Out Swivel" not in keys
    assert "With leather" not in keys
    assert not any("swivel" in k.lower() for k in keys)
    assert "Tall Dresser & Triple Dresser" not in keys
    assert "Prices for the year" not in keys
    assert not any("Hidden Chair" in k or "OPTION:" in k for k in keys)
    assert not any(k[:1].islower() for k in keys)
    assert 'Size change (up to 10")' in keys
    assert "Two-tone" in keys


def test_for_prefix_dollar_adders_and_cost_is_percent():
    data = _xlsx(
        [
            ["Options"],
            ["For hidden jewelry drawer add 100.00"],
            ["For hidden hand gun storage (With sliding top) add 150.00"],
            ["For platform bed add 200.00"],
            ["Headboard only cost is 50% of bed"],
        ]
    )
    by = {
        row["option_key"]: row for row in extract_book_options(data, vendor="Windy Acres Furniture")
    }
    assert by["Hidden jewelry drawer"]["base_price"] == 100
    assert by["Hidden hand gun storage (With sliding top)"]["base_price"] == 150
    assert by["Platform bed"]["base_price"] == 200
    assert by["Headboard only"]["addon_pct"] == 50
    assert not any(k[:1].islower() for k in by)


def test_merge_does_not_duplicate_existing_option_keys():
    existing = pd.DataFrame(
        [
            {
                "vendor": "Millcraft",
                "option_key": "Lock",
                "line_kind": "addon",
                "base_price": 25,
            }
        ]
    )
    result = WorkbookImportResult(
        sheets_tried=[],
        long_df=existing,
        detected_markup=None,
        sheet_names=["Pricelist"],
    )
    merged = merge_book_options(result, _millcraft_front_matter(), vendor="Millcraft")
    locks = merged.long_df[merged.long_df["option_key"] == "Lock"]
    assert len(locks) == 1


def test_extracts_visible_options_rows_with_percent_dollar_and_deduct_shapes():
    data = _xlsx(
        [
            ["Options"],
            ["Paint & Glaze", 0.15],
            ["Without Drawers", "$45 Less"],
            ["Plank Rough Sawn Tops", "No Upcharge"],
            ["Option: Slatted or Grooved Doors, ADD", 65, 65, 65, 65],
        ]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Paint & Glaze"]["addon_pct"] == 15
    assert by["Without Drawers"]["base_price"] == -45
    assert by["Plank Rough Sawn Tops"]["base_price"] == 0
    assert by["Slatted or Grooved Doors"]["base_price"] == 65


def test_extracts_formatted_finish_percent_rows_after_finish_banner():
    data = _xlsx(
        [
            ["FINISHING OPTIONS FOR ALL PRODUCTS"],
            ["ADD ALL THAT APPLY"],
            [None, None, None, None, None, "Category 2 Colors", None, None, 0.8],
            [None, None, None, None, None, "Two-Tone", None, None, 0.4],
        ]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Category 2 Colors"]["addon_pct"] == 80
    assert by["Two-tone"]["addon_pct"] == 40


def test_extracts_per_drawer_hardware_charges_from_visible_note():
    data = _xlsx(
        [["*Add $10/drawer for side mount soft close, $20/drawer for undermount soft close"]]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Side Mount Soft Close Slides"]["base_price"] == 10
    assert by["Undermount Soft Close Slides"]["base_price"] == 20


def test_options_banner_does_not_turn_following_product_skus_into_options():
    data = _xlsx(
        [
            ["Options"],
            ["10-16", "Chair", 250, 250, 250],
            ["101 CSC", "Corner Sofa", 1200, 1200],
            ["Option: Slatted Door, ADD", 65, 65],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert "10-16" not in labels
    assert "101 CSC" not in labels
    assert "Slatted Door" in labels


def test_brookside_island_top_sentence_shortens_to_the_floor_label():
    data = _xlsx(
        [
            ["Options"],
            [
                'Island top is 1 1/4" plank with sawmarks *Call for pricing',
                "Call for pricing",
            ],
        ]
    )

    labels = {
        row["option_key"] for row in extract_book_options(data, vendor="Brookside Home Furnishings")
    }

    assert labels == {'1 1/4" plank island top with sawmarks'}
    assert (
        canonical_option_label('Island top is 1 1/4" plank with sawmarks *Cal…')
        == '1 1/4" plank island top with sawmarks'
    )


def test_fn_chair_nail_heads_sentence_shortens_to_the_floor_label():
    data = _xlsx(
        [
            ["Options"],
            [
                "TO ADD NAIL HEADS AROUND ANY UPHOLSTERED SEAT AND/OR BACK",
                30,
            ],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="FN Chair")}

    assert labels == {"Nail Heads Around Upholstered Seat"}
    assert (
        canonical_option_label("TO ADD NAIL HEADS AROUND ANY UPHOLSTERED SEAT…")
        == "Nail Heads Around Upholstered Seat"
    )


def test_five_star_additional_leaves_sentence_shortens_to_the_floor_label():
    data = _xlsx(
        [
            ["Options"],
            [
                "Additional leaves add $75 per leaf plus $75 for drop legs (Up to 12 Leaves)",
                75,
            ],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="Five Star Tables")}

    assert labels == {"Additional leaves ($75 per leaf)"}
    assert (
        canonical_option_label(
            "Additional leaves add $75 per leaf plus $75 for drop legs (Up to 12 Leaves)"
        )
        == "Additional leaves ($75 per leaf)"
    )
    assert (
        canonical_option_label("Additional leaves add $75 per leaf plus $75 f…")
        == "Additional leaves ($75 per leaf)"
    )
    assert (
        canonical_option_label(
            "Additional leaves add $75 each plus $75 for drop legs (Up to 6 Leaves in select sizes)"
        )
        == "Additional leaves ($75 per leaf)"
    )


def test_quote_only_lines_surface_as_non_priced_options():
    """Call-for-quote and TBD choices exist. The floor must see them, not guess."""
    data = _xlsx(
        [
            ["Options"],
            ["Leather", "Call for pricing"],
            ["Marble Top", "TBD"],
            ["Paint", "add 20%"],
        ]
    )

    rows = extract_book_options(data, vendor="X")
    by_label = {row["option_key"]: row for row in rows}

    assert set(by_label) == {"Leather", "Marble Top", "Paint"}
    leather = by_label["Leather"]
    assert leather["base_price"] is None
    assert leather["addon_pct"] is None
    assert "quote" in leather["notes"].lower()
    assert by_label["Paint"]["addon_pct"] == 20.0


def test_builder_names_never_become_option_labels():
    """Ashery Oak is a builder. A builder name in an Options tab is not an Option."""
    data = _xlsx(
        [
            ["Options"],
            ["Ashery Oak", "Add 10%"],
            ["Quality Fabrications Leather", "Add 15%"],
            ["Paint", "Add 20%"],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert "Ashery Oak" not in labels
    assert "Quality Fabrications Leather" not in labels
    assert "Paint" in labels


def test_per_sku_finish_markup_rows_are_not_global_options():
    data = _xlsx(
        [
            [
                "110 CSF",
                '36" Cubic Slat Footstool',
                54.6,
                "Standard Wiping Stains",
                "List Price",
                "add 10%",
            ],
            [
                "10-36",
                'AJ #1 36" Square End Table',
                110.25,
                "Standard Wiping Stains",
                "List Price",
                "add 10%",
            ],
            [
                "PD-36",
                'Pioneer 36" Coffee Table',
                99.75,
                "Standard Wiping Stains",
                "List Price",
                "add 10%",
            ],
            ["Paint", "add 20%"],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert labels == {"Paint"}
