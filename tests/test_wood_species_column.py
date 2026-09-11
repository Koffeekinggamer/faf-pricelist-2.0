"""The Wood column carries wood species only — never footnotes or unit text."""

from backend.standardize import (
    dimension_axis,
    is_wood_column_label,
    mixed_wood_label,
    standardize_row,
    standardize_species,
)


def test_footnote_text_is_stripped_from_a_wood_list():
    raw = (
        "Rustic QSWO / Rustic Cherry / Brown Maple / Sap Cherry / Height: / 8 / 1 / "
        '2" / from / floor / to / bottom / of / sideboard.'
    )

    assert standardize_species(raw) == "Rustic QSWO / Rustic Cherry / Brown Maple / Sap Cherry"


def test_drawer_unit_callouts_are_not_wood():
    raw = "Oak / Standard / Footboard / Drawer / Unit / #002 / Drawer / Unit / 004 / 0"

    assert standardize_species(raw) == "Oak / Standard"


def test_dotted_qswo_is_recognized_as_one_species():
    raw = "Rustic Hickory / Q.S.W.O / Cherry / Elm / Hickory / Hard Maple"

    assert standardize_species(raw) == "Rustic Hickory / QSWO / Cherry / Elm / Hickory / Hard Maple"


def test_split_wood_names_the_catalog_already_uses_are_left_alone():
    assert standardize_species("Oak / Rustic / Oak") == "Oak / Rustic / Oak"
    assert (
        standardize_species("Red Oak / Wormy Maple / Premium") == "Red Oak / Wormy Maple / Premium"
    )


def test_roughsawn_brown_maple_is_one_wood_not_three():
    """AJ's prints it as one word. It is a real species column, not Rough + Sawn."""
    assert standardize_species("Roughsawn Brown Maple") == "Rough Sawn Brown Maple"
    assert standardize_species("Rough Sawn Brown Maple") == "Rough Sawn Brown Maple"


def test_price_header_is_not_a_wood():
    assert standardize_species("Fin.Retail") is None
    assert standardize_species("Unfin.Retail") is None


def test_hwd_headers_are_dimensions_never_wood():
    for raw in ('H"', 'W"', 'D"', "H", "W", "D", "HB H", "FB H", "Height", "Width", "Depth"):
        assert standardize_species(raw) is None, raw
    assert dimension_axis('H"') == "H"
    assert dimension_axis('W"') == "W"
    assert dimension_axis('D"') == "D"
    assert dimension_axis('HB H"') == "HB H"
    assert dimension_axis('FB H"') == "FB H"
    kept = standardize_row(
        {
            "vendor": "Frog Pond Furniture",
            "part_number": "100K",
            "description": "King Bed",
            "species": 'H"',
            "base_price": 966,
        }
    )
    assert kept is None


def test_option_tab_woods_stay_woods_not_features():
    assert is_wood_column_label("Rec. Barnwood Oak")
    assert is_wood_column_label("Clear black Walnut")
    assert is_wood_column_label("Prime Walnut")
    assert is_wood_column_label("Walnut")
    assert standardize_species("Rec. Barnwood Oak") == "Rec. Barnwood Oak"
    assert standardize_species("Clear black Walnut") == "Clear Black Walnut"
    assert not is_wood_column_label("Walnut Seat")
    assert not is_wood_column_label("Walnut Tops")
    assert not is_wood_column_label("Paint")
    assert not is_wood_column_label("Two-tone")
    assert not is_wood_column_label("Rustic +15%")
    assert not is_wood_column_label("Cedar Drawer Bottoms")
    assert is_wood_column_label("Prices are for Sap Cherry, Oak, Rustic Cherry")


def test_non_wood_pricing_tiers_still_survive():
    assert standardize_species("Wood Tier 2") == "Wood Tier 2"
    assert standardize_species("Standard Wood") == "Standard Wood"
    assert standardize_species("All Woods") == "All / Woods"
    assert standardize_species("Standard Colors") == "Standard Colors"


def test_standardize_row_keeps_only_wood_in_the_species_field():
    row = standardize_row(
        {
            "vendor": "Criswell Bedroom",
            "part_number": "CWF1192 Twin",
            "description": "CWF #1192 Arch Spindle Bed - Twin",
            "collection": "Arch Spindle Bed",
            "species": 'Oak / Height: / 8 / 1 / 2" / from / floor / to / bottom',
            "base_price": 1656.0,
        }
    )

    assert row["species"] == "Oak"


def test_steel_and_metal_are_row_materials_not_blank():
    assert standardize_species("Steel") == "Steel"
    assert standardize_species("Metal") == "Metal"
    assert standardize_species("Steel Bases") == "Steel"
    assert standardize_species("Metal Base Series") == "Metal"
    assert standardize_species("Cushion") == "Cushion"
    assert standardize_species("Replacement Cushion Sets") == "Cushion"


def test_mixed_wood_pair_is_shown_as_wood_slash_wood():
    assert mixed_wood_label("Cherry / Hickory") == "Cherry/Hickory"
    assert mixed_wood_label("Oak / Brown Maple") == "Oak/Brown Maple"
    assert mixed_wood_label("Wormy Maple / Walnut / Combo") == "Wormy Maple/Walnut"
    assert mixed_wood_label("Wormy Maple / Walnut Combo") == "Wormy Maple/Walnut"
    assert mixed_wood_label("Premium / Cherry / QSWO") is None
    assert mixed_wood_label("Brown Maple / Oak / Rustic Cherry") is None
    assert mixed_wood_label("Oak") is None
