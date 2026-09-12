"""Official September 2026 county sales-tax lookup behavior."""

from backend.county_sales_tax import (
    county_tax_options,
    find_county_tax,
    load_county_sales_tax,
)


def test_all_nc_sc_ga_counties_are_available():
    rows = load_county_sales_tax()
    by_state = {
        state: [row for row in rows if row.state == state] for state in ("NC", "SC", "GA")
    }

    assert len(by_state["NC"]) == 100
    assert len(by_state["SC"]) == 46
    assert len(by_state["GA"]) == 159
    assert len(rows) == 305


def test_verified_county_rate_lookups():
    assert find_county_tax("Spartanburg", "SC").rate_pct == 7.0
    assert find_county_tax("Mecklenburg County", "NC").rate_pct == 8.25
    assert find_county_tax("Fulton", "GA").rate_pct == 7.75
    assert find_county_tax("Richmond", "GA").rate_pct == 8.5


def test_picker_has_state_grouping_labels_and_no_city_overlays():
    labels = [row.display_label for row in county_tax_options()]

    assert labels[0].startswith("Georgia ·")
    assert any(label == "South Carolina · Spartanburg County, SC — 7%" for label in labels)
    assert not any("Myrtle Beach" in label or "Atlanta" in label for label in labels)
