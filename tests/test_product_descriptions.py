"""Human-facing product descriptions preserve visible source context."""

import pandas as pd

from backend.product_descriptions import human_description
from backend.standardize import standardize_row
from wide_import import (
    SheetLayout,
    classify_column,
    unpivot_wide_finish,
    unpivot_wide_species,
)


def test_sku_only_description_uses_collection_and_dimensions():
    row = {
        "part_number": "HTS1100-4260",
        "description": "HTS1100-4260",
        "collection": "Standard Pedestal - 652 Mission",
        "dimensions": '42" x 60"',
        "line_kind": "item",
    }

    assert (
        human_description(row)
        == 'Standard Pedestal - 652 Mission — 42" x 60"'
    )


def test_rich_source_description_keeps_nonduplicated_context():
    row = {
        "part_number": "SH-2262",
        "description": "Double Pedestal Desk",
        "collection": "Shaker Office Furniture",
        "dimensions": '22" x 62"',
        "line_kind": "item",
    }

    assert (
        human_description(row)
        == 'Double Pedestal Desk — Shaker Office Furniture — 22" x 62"'
    )


def test_context_already_in_description_is_not_repeated():
    row = {
        "part_number": "BED-Q",
        "description": 'Charleston Queen Bed — 66" x 86"',
        "collection": "Charleston Beds",
        "dimensions": '66" x 86"',
        "line_kind": "item",
    }

    assert human_description(row) == 'Charleston Queen Bed — 66" x 86"'


def test_human_name_used_as_part_number_remains_the_description():
    row = {
        "part_number": "Desk Arm Chair w/ Gas Lift",
        "description": "Desk Arm Chair w/ Gas Lift",
        "collection": "Aberdeen",
        "notes": "Wholesale matrix",
        "line_kind": "item",
    }

    assert (
        human_description(row)
        == "Desk Arm Chair w/ Gas Lift — Aberdeen"
    )


def test_parser_metadata_and_finish_placeholders_are_not_product_context():
    row = {
        "part_number": "INT-45",
        "description": "unfinished",
        "collection": "Charleston TV Console",
        "dimensions": '45" TV opening',
        "notes": "finish_est=334.0",
        "finish_state": "unfinished",
        "line_kind": "item",
    }

    assert human_description(row) == 'Charleston TV Console — 45" TV opening'


def test_unlabeled_visible_row_gets_honest_builder_context():
    row = {
        "vendor": "Brookside Home Furnishings",
        "part_number": "NaT",
        "description": "NaT",
        "collection": "NaT",
        "line_kind": "item",
    }

    assert human_description(row) == "Brookside Home Furnishings catalog item"


def test_human_feature_note_is_kept_but_structured_filters_are_not_added():
    row = {
        "part_number": "A-100",
        "description": "Mission Side Chair",
        "collection": "Seating",
        "dimensions": "",
        "notes": "Includes steam-bent lumbar back",
        "species": "Oak",
        "finish_state": "finished",
        "option_key": "Cat. 1",
        "line_kind": "item",
    }

    assert (
        human_description(row)
        == "Mission Side Chair — Includes steam-bent lumbar back"
    )


def test_addon_description_is_not_rewritten():
    row = {
        "part_number": "two-tone",
        "description": "Two-tone finish adder",
        "collection": "Addons",
        "dimensions": '48"',
        "line_kind": "addon",
    }

    assert human_description(row) == "Two-tone finish adder"


def test_import_scaffolding_is_not_added_as_human_context():
    row = {
        "part_number": "B364320",
        "description": "B364320",
        "collection": "2026 Wholesale",
        "dimensions": '18-1/2" × 36" × 68"',
        "notes": "Wholesale matrix",
        "line_kind": "item",
    }

    assert human_description(row) == '18-1/2" × 36" × 68"'


def test_standardize_row_applies_human_description_to_every_item_path():
    row = standardize_row(
        {
            "vendor": "Hermies Table Shop",
            "part_number": "HTS1100-4260",
            "description": "HTS1100-4260",
            "collection": "Standard Pedestal - 652 Mission",
            "dimensions": '42" x 60"',
            "base_price": 900,
        }
    )

    assert row is not None
    assert (
        row["description"]
        == 'Standard Pedestal - 652 Mission — 42" x 60"'
    )
    assert row["part_number"] == "HTS1100-4260"


def test_standardize_row_does_not_store_pandas_nat_as_description():
    row = standardize_row(
        {
            "vendor": "Brookside Home Furnishings",
            "part_number": "TM-4272",
            "description": "NaT",
            "collection": "Charleston Leg Table",
            "dimensions": '42" x 72"',
            "base_price": 500,
        }
    )

    assert row is not None
    assert row["description"] == 'Charleston Leg Table — 42" x 72"'


def test_wide_finish_keeps_identifier_as_description_fallback():
    frame = pd.DataFrame(
        [{"Part #": "B364320", "Finished": 500, "Unfinished": 400}]
    )
    layout = SheetLayout(
        sheet_name="Price List",
        layout="wide_finish",
        id_col="Part #",
        finish_cols=["Finished", "Unfinished"],
    )

    parsed = unpivot_wide_finish(frame, layout, vendor="Hoosier Crafts")

    assert set(parsed["description"]) == {"B364320"}


def test_wide_species_preserves_section_name_and_ditto_sku():
    frame = pd.DataFrame(
        [
            {
                "Item #": "#5200 Wall Unit",
                "Size": None,
                "State": None,
                "Oak": None,
                "Cherry": None,
            },
            {
                "Item #": "Item #",
                "Size": "Size",
                "State": None,
                "Oak": "Oak",
                "Cherry": "Cherry",
            },
            {
                "Item #": None,
                "Size": None,
                "State": None,
                "Oak": "B. Maple",
                "Cherry": "Hickory",
            },
            {
                "Item #": "5200",
                "Size": '45" TV Opening',
                "State": "unfinished",
                "Oak": 2466,
                "Cherry": 2959,
            },
            {
                "Item #": '""',
                "Size": '51" TV Opening',
                "State": "unfinished",
                "Oak": 2516,
                "Cherry": 3019,
            },
        ]
    )
    layout = SheetLayout(
        sheet_name="Wall Units 1",
        layout="wide_species",
        id_col="Item #",
        dim_cols=["Size"],
        species_cols=["Oak", "Cherry"],
    )

    parsed = unpivot_wide_species(
        frame, layout, vendor="INTEG Wood Products"
    )

    assert set(parsed["part_number"]) == {"5200"}
    assert set(parsed["description"]) == {"5200"}
    assert set(parsed["collection"]) == {"#5200 Wall Unit"}


def test_item_description_header_is_description_not_identifier():
    assert classify_column("Item Description") == "desc"
