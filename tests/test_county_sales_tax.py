"""County sales-tax table: NC / SC / GA rates and fuzzy search."""

from __future__ import annotations

from backend.county_sales_tax import (
    COUNTY_RATES,
    format_county_selection,
    get_county,
    search_counties,
    verify_ga_counties,
)


def test_spartanburg_sc_is_seven_percent() -> None:
    row = get_county("Spartanburg", "SC")
    assert row is not None
    assert row.rate == 0.07
    assert format_county_selection(row) == "Spartanburg County, SC — 7%"


def test_mecklenburg_nc_is_8_25_percent() -> None:
    row = get_county("Mecklenburg", "NC")
    assert row is not None
    assert row.rate == 0.0825
    assert format_county_selection(row) == "Mecklenburg County, NC — 8.25%"


def test_fulton_ga_is_8_9_percent() -> None:
    row = get_county("Fulton", "GA")
    assert row is not None
    assert row.rate == 0.089
    assert format_county_selection(row) == "Fulton County, GA — 8.9%"


def test_horry_myrtle_beach_is_separate_nine_percent() -> None:
    horry = get_county("Horry", "SC")
    myrtle = get_county("Horry-Myrtle Beach", "SC")
    assert horry is not None and horry.rate == 0.08
    assert myrtle is not None and myrtle.rate == 0.09


def test_fuzzy_spart_meck_fulton() -> None:
    spart = search_counties("spart")
    assert spart
    assert spart[0].county == "Spartanburg"
    assert spart[0].state == "SC"

    meck = search_counties("meck")
    assert meck
    assert meck[0].county == "Mecklenburg"
    assert meck[0].state == "NC"

    fulton = search_counties("fulton")
    assert fulton
    assert fulton[0].county == "Fulton"
    assert fulton[0].state == "GA"


def test_search_matches_state_name_and_abbr() -> None:
    sc = search_counties("south carolina")
    assert sc
    assert all(r.state == "SC" for r in sc)
    nc = search_counties("NC")
    assert nc
    assert all(r.state == "NC" for r in nc)


def test_all_counties_present_no_omissions() -> None:
    by_state = {"SC": 0, "NC": 0, "GA": 0}
    for row in COUNTY_RATES:
        by_state[row.state] += 1
    assert by_state["SC"] == 47  # 46 counties + Horry-Myrtle Beach
    assert by_state["NC"] == 100
    assert by_state["GA"] == 159
    assert len(COUNTY_RATES) == 306


def test_ga_uncertain_counties_are_verify_at_8_percent() -> None:
    verify = verify_ga_counties()
    assert len(verify) == 159 - 14
    for row in verify:
        assert row.rate == 0.08
        assert "VERIFY" in (row.notes or "")
