"""Destination county sales tax for NC, SC, and GA (September 2026 charts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StateCode = Literal["SC", "NC", "GA"]

STATE_NAMES: dict[StateCode, str] = {
    "GA": "Georgia",
    "NC": "North Carolina",
    "SC": "South Carolina",
}

SC_SOURCE = "SCDOR ST-500 effective May 1, 2026 (includes 6% state)"
NC_SOURCE = (
    "NCDOR combined general merchandise rates, September 2026 (state 4.75% plus local/transit)"
)
GA_SOURCE = "GA DOR combined general merchandise (state 4% plus local), September 2026"
GA_VERIFY = "VERIFY on GA DOR general rate chart before production"

# Known GA combined rates Judson specified; all other GA counties are 0.08 + VERIFY.
_GA_KNOWN: dict[str, float] = {
    "Fulton": 0.089,
    "DeKalb": 0.089,
    "Cobb": 0.0775,
    "Gwinnett": 0.08,
    "Chatham": 0.08,
    "Cherokee": 0.07,
    "Clayton": 0.09,
    "Hall": 0.09,
    "Forsyth": 0.08,
    "Richmond": 0.08,
    "Houston": 0.09,
    "Columbia": 0.09,
    "Bibb": 0.08,
    "Muscogee": 0.09,
}

_SC_RATES: tuple[tuple[str, float], ...] = (
    ("Abbeville", 0.07),
    ("Aiken", 0.08),
    ("Allendale", 0.08),
    ("Anderson", 0.07),
    ("Bamberg", 0.08),
    ("Barnwell", 0.08),
    ("Beaufort", 0.06),
    ("Berkeley", 0.09),
    ("Calhoun", 0.08),
    ("Charleston", 0.09),
    ("Cherokee", 0.08),
    ("Chester", 0.08),
    ("Chesterfield", 0.08),
    ("Clarendon", 0.07),
    ("Colleton", 0.08),
    ("Darlington", 0.08),
    ("Dillon", 0.08),
    ("Dorchester", 0.07),
    ("Edgefield", 0.08),
    ("Fairfield", 0.07),
    ("Florence", 0.08),
    ("Georgetown", 0.07),
    ("Greenville", 0.06),
    ("Greenwood", 0.07),
    ("Hampton", 0.07),
    ("Horry", 0.08),
    ("Horry-Myrtle Beach", 0.09),
    ("Jasper", 0.09),
    ("Kershaw", 0.08),
    ("Lancaster", 0.08),
    ("Laurens", 0.08),
    ("Lee", 0.08),
    ("Lexington", 0.07),
    ("McCormick", 0.08),
    ("Marion", 0.08),
    ("Marlboro", 0.08),
    ("Newberry", 0.07),
    ("Oconee", 0.06),
    ("Orangeburg", 0.07),
    ("Pickens", 0.07),
    ("Richland", 0.08),
    ("Saluda", 0.08),
    ("Spartanburg", 0.07),
    ("Sumter", 0.08),
    ("Union", 0.07),
    ("Williamsburg", 0.08),
    ("York", 0.07),
)

_NC_RATES: tuple[tuple[str, float], ...] = (
    ("Alamance", 0.0675),
    ("Alexander", 0.07),
    ("Alleghany", 0.07),
    ("Anson", 0.07),
    ("Ashe", 0.07),
    ("Avery", 0.0675),
    ("Beaufort", 0.0675),
    ("Bertie", 0.07),
    ("Bladen", 0.0675),
    ("Brunswick", 0.0675),
    ("Buncombe", 0.07),
    ("Burke", 0.0675),
    ("Cabarrus", 0.07),
    ("Caldwell", 0.0675),
    ("Camden", 0.0675),
    ("Carteret", 0.0675),
    ("Caswell", 0.0675),
    ("Catawba", 0.07),
    ("Chatham", 0.07),
    ("Cherokee", 0.07),
    ("Chowan", 0.0675),
    ("Clay", 0.07),
    ("Cleveland", 0.0675),
    ("Columbus", 0.0675),
    ("Craven", 0.0675),
    ("Cumberland", 0.07),
    ("Currituck", 0.0675),
    ("Dare", 0.0675),
    ("Davidson", 0.07),
    ("Davie", 0.0675),
    ("Duplin", 0.07),
    ("Durham", 0.075),
    ("Edgecombe", 0.07),
    ("Forsyth", 0.07),
    ("Franklin", 0.0675),
    ("Gaston", 0.07),
    ("Gates", 0.0675),
    ("Graham", 0.07),
    ("Granville", 0.0675),
    ("Greene", 0.07),
    ("Guilford", 0.0675),
    ("Halifax", 0.07),
    ("Harnett", 0.07),
    ("Haywood", 0.07),
    ("Henderson", 0.0675),
    ("Hertford", 0.07),
    ("Hoke", 0.0675),
    ("Hyde", 0.0675),
    ("Iredell", 0.0675),
    ("Jackson", 0.07),
    ("Johnston", 0.0675),
    ("Jones", 0.07),
    ("Lee", 0.07),
    ("Lenoir", 0.0675),
    ("Lincoln", 0.07),
    ("Macon", 0.0675),
    ("Madison", 0.07),
    ("Martin", 0.07),
    ("McDowell", 0.0675),
    ("Mecklenburg", 0.0825),
    ("Mitchell", 0.0675),
    ("Montgomery", 0.07),
    ("Moore", 0.07),
    ("Nash", 0.0675),
    ("New Hanover", 0.07),
    ("Northampton", 0.0675),
    ("Onslow", 0.07),
    ("Orange", 0.075),
    ("Pamlico", 0.0675),
    ("Pasquotank", 0.07),
    ("Pender", 0.0675),
    ("Perquimans", 0.0675),
    ("Person", 0.0675),
    ("Pitt", 0.07),
    ("Polk", 0.0675),
    ("Randolph", 0.07),
    ("Richmond", 0.0675),
    ("Robeson", 0.07),
    ("Rockingham", 0.07),
    ("Rowan", 0.07),
    ("Rutherford", 0.07),
    ("Sampson", 0.07),
    ("Scotland", 0.0675),
    ("Stanly", 0.07),
    ("Stokes", 0.0675),
    ("Surry", 0.07),
    ("Swain", 0.07),
    ("Transylvania", 0.0675),
    ("Tyrrell", 0.0675),
    ("Union", 0.0675),
    ("Vance", 0.0675),
    ("Wake", 0.0725),
    ("Warren", 0.0675),
    ("Washington", 0.07),
    ("Watauga", 0.0675),
    ("Wayne", 0.0675),
    ("Wilkes", 0.07),
    ("Wilson", 0.0675),
    ("Yadkin", 0.0675),
    ("Yancey", 0.0675),
)

_GA_COUNTIES: tuple[str, ...] = (
    "Appling",
    "Atkinson",
    "Bacon",
    "Baker",
    "Baldwin",
    "Banks",
    "Barrow",
    "Bartow",
    "Ben Hill",
    "Berrien",
    "Bibb",
    "Bleckley",
    "Brantley",
    "Brooks",
    "Bryan",
    "Bulloch",
    "Burke",
    "Butts",
    "Calhoun",
    "Camden",
    "Candler",
    "Carroll",
    "Catoosa",
    "Charlton",
    "Chatham",
    "Chattahoochee",
    "Chattooga",
    "Cherokee",
    "Clarke",
    "Clay",
    "Clayton",
    "Clinch",
    "Cobb",
    "Coffee",
    "Colquitt",
    "Columbia",
    "Cook",
    "Coweta",
    "Crawford",
    "Crisp",
    "Dade",
    "Dawson",
    "Decatur",
    "DeKalb",
    "Dodge",
    "Dooly",
    "Dougherty",
    "Douglas",
    "Early",
    "Echols",
    "Effingham",
    "Elbert",
    "Emanuel",
    "Evans",
    "Fannin",
    "Fayette",
    "Floyd",
    "Forsyth",
    "Franklin",
    "Fulton",
    "Gilmer",
    "Glascock",
    "Glynn",
    "Gordon",
    "Grady",
    "Greene",
    "Gwinnett",
    "Habersham",
    "Hall",
    "Hancock",
    "Haralson",
    "Harris",
    "Hart",
    "Heard",
    "Henry",
    "Houston",
    "Irwin",
    "Jackson",
    "Jasper",
    "Jeff Davis",
    "Jefferson",
    "Jenkins",
    "Johnson",
    "Jones",
    "Lamar",
    "Lanier",
    "Laurens",
    "Lee",
    "Liberty",
    "Lincoln",
    "Long",
    "Lowndes",
    "Lumpkin",
    "Macon",
    "Madison",
    "Marion",
    "McDuffie",
    "McIntosh",
    "Meriwether",
    "Miller",
    "Mitchell",
    "Monroe",
    "Montgomery",
    "Morgan",
    "Murray",
    "Muscogee",
    "Newton",
    "Oconee",
    "Oglethorpe",
    "Paulding",
    "Peach",
    "Pickens",
    "Pierce",
    "Pike",
    "Polk",
    "Pulaski",
    "Putnam",
    "Quitman",
    "Rabun",
    "Randolph",
    "Richmond",
    "Rockdale",
    "Schley",
    "Screven",
    "Seminole",
    "Spalding",
    "Stephens",
    "Stewart",
    "Sumter",
    "Talbot",
    "Taliaferro",
    "Tattnall",
    "Taylor",
    "Telfair",
    "Terrell",
    "Thomas",
    "Tift",
    "Toombs",
    "Towns",
    "Treutlen",
    "Troup",
    "Turner",
    "Twiggs",
    "Union",
    "Upson",
    "Walker",
    "Walton",
    "Ware",
    "Warren",
    "Washington",
    "Wayne",
    "Webster",
    "Wheeler",
    "White",
    "Whitfield",
    "Wilcox",
    "Wilkes",
    "Wilkinson",
    "Worth",
)


@dataclass(frozen=True)
class CountyRate:
    state: StateCode
    county: str
    label: str
    rate: float
    source: str
    notes: str = ""


def _label(county: str, state: StateCode) -> str:
    if county == "Horry-Myrtle Beach":
        return "Horry-Myrtle Beach, SC"
    return f"{county} County, {state}"


def _build() -> tuple[CountyRate, ...]:
    rows: list[CountyRate] = []
    for county, rate in _SC_RATES:
        notes = ""
        if county == "Horry-Myrtle Beach":
            notes = "Separate jurisdiction under Horry; SCDOR ST-500 May 1 2026"
        rows.append(
            CountyRate(
                state="SC",
                county=county,
                label=_label(county, "SC"),
                rate=rate,
                source=SC_SOURCE,
                notes=notes,
            )
        )
    for county, rate in _NC_RATES:
        rows.append(
            CountyRate(
                state="NC",
                county=county,
                label=_label(county, "NC"),
                rate=rate,
                source=NC_SOURCE,
            )
        )
    for county in _GA_COUNTIES:
        known = _GA_KNOWN.get(county)
        if known is not None:
            rows.append(
                CountyRate(
                    state="GA",
                    county=county,
                    label=_label(county, "GA"),
                    rate=known,
                    source=GA_SOURCE,
                )
            )
        else:
            rows.append(
                CountyRate(
                    state="GA",
                    county=county,
                    label=_label(county, "GA"),
                    rate=0.08,
                    source=GA_SOURCE,
                    notes=GA_VERIFY,
                )
            )
    return tuple(rows)


COUNTY_RATES: tuple[CountyRate, ...] = _build()


def format_rate_pct(rate: float) -> str:
    pct = rate * 100.0
    if abs(pct - round(pct)) < 1e-9:
        return f"{int(round(pct))}%"
    text = f"{pct:.4f}".rstrip("0").rstrip(".")
    return f"{text}%"


def format_county_selection(row: CountyRate) -> str:
    return f"{row.label} — {format_rate_pct(row.rate)}"


def get_county(county: str, state: str) -> CountyRate | None:
    want_c = county.strip().casefold()
    want_s = state.strip().upper()
    for row in COUNTY_RATES:
        if row.state == want_s and row.county.casefold() == want_c:
            return row
    return None


def verify_ga_counties() -> tuple[CountyRate, ...]:
    return tuple(r for r in COUNTY_RATES if r.state == "GA" and GA_VERIFY in (r.notes or ""))


def _score(row: CountyRate, query: str) -> int:
    q = query.strip().casefold()
    if not q:
        return 1
    county = row.county.casefold()
    label = row.label.casefold()
    state_name = STATE_NAMES[row.state].casefold()
    abbr = row.state.casefold()
    if county == q or label == q:
        return 100
    if county.startswith(q):
        return 90
    if q in county:
        return 80
    if q in label:
        return 70
    if q == abbr or q == state_name:
        return 40
    if abbr.startswith(q) or state_name.startswith(q) or q in state_name:
        return 30
    return 0


def search_counties(query: str) -> list[CountyRate]:
    """Fuzzy type-ahead on county, state abbr, and full state name."""
    q = query.strip()
    abbr = q.upper()
    if abbr in STATE_NAMES:
        return [row for row in COUNTY_RATES if row.state == abbr]
    scored = [(score, row) for row in COUNTY_RATES if (score := _score(row, q)) > 0]
    order = {"GA": 0, "NC": 1, "SC": 2}
    scored.sort(key=lambda item: (-item[0], order.get(item[1].state, 9), item[1].county))
    return [row for _, row in scored]


def grouped_counties() -> dict[str, list[CountyRate]]:
    groups: dict[str, list[CountyRate]] = {
        "Georgia": [],
        "North Carolina": [],
        "South Carolina": [],
    }
    names = {"GA": "Georgia", "NC": "North Carolina", "SC": "South Carolina"}
    for row in COUNTY_RATES:
        groups[names[row.state]].append(row)
    return groups
