"""Verified county-level destination tax rates for NC, SC, and GA."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from backend.config import APP_DIR

TAX_DATA_PATH = APP_DIR / "data" / "county_sales_tax.json"
STATE_NAMES = {
    "GA": "Georgia",
    "NC": "North Carolina",
    "SC": "South Carolina",
}


def _format_rate(rate_pct: float) -> str:
    return f"{float(rate_pct):g}%"


def _normalize_county(value: str) -> str:
    county = " ".join(str(value or "").strip().split())
    if county.casefold().endswith(" county"):
        county = county[:-7].rstrip()
    return county.casefold()


@dataclass(frozen=True)
class CountyTaxRate:
    state: str
    county: str
    rate_pct: float

    @property
    def state_name(self) -> str:
        return STATE_NAMES[self.state]

    @property
    def key(self) -> str:
        return f"{self.state}:{self.county}"

    @property
    def display_label(self) -> str:
        return (
            f"{self.state_name} · {self.county} County, {self.state} — "
            f"{_format_rate(self.rate_pct)}"
        )


@lru_cache(maxsize=4)
def load_county_sales_tax(
    path: Optional[Union[str, Path]] = None,
) -> tuple[CountyTaxRate, ...]:
    """Load verified picker rates, excluding any source rows marked TBD."""
    source = Path(path) if path else TAX_DATA_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows: list[CountyTaxRate] = []
    seen: set[tuple[str, str]] = set()
    for raw in payload.get("rates", []):
        if raw.get("rate_pct") in (None, "", "TBD"):
            continue
        state = str(raw.get("state") or "").strip().upper()
        county = str(raw.get("county") or "").strip()
        if state not in STATE_NAMES or not county:
            continue
        identity = (state, _normalize_county(county))
        if identity in seen:
            raise ValueError(f"Duplicate county tax rate: {state} {county}")
        seen.add(identity)
        rows.append(
            CountyTaxRate(
                state=state,
                county=county,
                rate_pct=float(raw["rate_pct"]),
            )
        )
    return tuple(rows)


def county_tax_options() -> tuple[CountyTaxRate, ...]:
    """Return picker options grouped by state name, then county."""
    return tuple(
        sorted(
            load_county_sales_tax(),
            key=lambda row: (row.state_name, row.county.casefold()),
        )
    )


def find_county_tax(county: str, state: str) -> CountyTaxRate:
    """Find one county rate by state abbreviation and county name."""
    state_key = str(state or "").strip().upper()
    county_key = _normalize_county(county)
    for row in load_county_sales_tax():
        if row.state == state_key and _normalize_county(row.county) == county_key:
            return row
    raise LookupError(f"No verified county tax rate for {county}, {state_key}")
