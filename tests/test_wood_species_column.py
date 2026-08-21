"""The Wood column carries wood species only — never footnotes or unit text."""

from backend.standardize import standardize_row, standardize_species


def test_footnote_text_is_stripped_from_a_wood_list():
    raw = (
        'Rustic QSWO / Rustic Cherry / Brown Maple / Sap Cherry / Height: / 8 / 1 / '
        '2" / from / floor / to / bottom / of / sideboard.'
    )

    assert (
        standardize_species(raw)
        == "Rustic QSWO / Rustic Cherry / Brown Maple / Sap Cherry"
    )


def test_drawer_unit_callouts_are_not_wood():
    raw = "Oak / Standard / Footboard / Drawer / Unit / #002 / Drawer / Unit / 004 / 0"

    assert standardize_species(raw) == "Oak / Standard"


def test_dotted_qswo_is_recognized_as_one_species():
    raw = "Rustic Hickory / Q.S.W.O / Cherry / Elm / Hickory / Hard Maple"

    assert (
        standardize_species(raw)
        == "Rustic Hickory / QSWO / Cherry / Elm / Hickory / Hard Maple"
    )


def test_split_wood_names_the_catalog_already_uses_are_left_alone():
    assert standardize_species("Oak / Rustic / Oak") == "Oak / Rustic / Oak"
    assert (
        standardize_species("Red Oak / Wormy Maple / Premium")
        == "Red Oak / Wormy Maple / Premium"
    )


def test_price_header_is_not_a_wood():
    assert standardize_species("Fin.Retail") is None
    assert standardize_species("Unfin.Retail") is None


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
