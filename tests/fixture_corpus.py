"""Checked-in Excel fixtures so CI can prove parsers without Mac Downloads.

Paths and expected parse facts live here. Bytes are written by
``tests/fixtures/build_fixtures.py`` and committed under ``tests/fixtures/``.
Live Mac Downloads tests stay as extra coverage and may skip.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# builder, locked importer, next-year Drop filename, fixture path, option keys
# that the reader must emit (empty Options is a capture miss).
SETTLED_FIXTURES = [
    (
        "FN Chair",
        "fn_chair",
        "FNC_2028_Pricelist_0915.xlsm",
        FIXTURES_DIR / "settled" / "fn-chair.xlsx",
        ("Cat. 1", "Solid Fabrics / COM"),
    ),
    (
        "Ashery Oak",
        "ashery_oak",
        "AO_Pricelist_080126.xlsx",
        FIXTURES_DIR / "settled" / "ashery-oak.xlsx",
        ("Paint", "Drawer lock"),
    ),
    (
        "J & M Woodworking",
        "jmw",
        "JMW_2027_Pricelist_0101.xlsx",
        FIXTURES_DIR / "settled" / "j-and-m-woodworking.xlsx",
        ("2-tone Stain", "Paint", "Fabric", "Crypton", "Leather"),
    ),
    (
        "Artisan Chairs",
        "artisan_chairs",
        "AC_2027_Pricelist_0301.xlsx",
        FIXTURES_DIR / "settled" / "artisan-chairs.xlsx",
        ("Fabric Seat", "Leather Seat", "Nail Heads"),
    ),
    (
        "Criswell Bedroom",
        "criswell",
        "CWF_Pricelists_2026_0101/Living Rooms Price List.xlsx",
        FIXTURES_DIR / "settled" / "criswell-bedroom.xlsx",
        ("Phone Charger",),
    ),
]

WIDE_FIXTURE = (
    "Genuine Oak",
    "genuine_oak",
    "Genuine_Oak_2027_Pricelist.xlsx",
    FIXTURES_DIR / "wide" / "genuine-oak-wide-species.xlsx",
)

OPTIONS_FIXTURE = (
    "Millcraft",
    "millcraft",
    "Millcraft_2027_Pricelist.xlsx",
    FIXTURES_DIR / "options" / "millcraft-options.xlsx",
    ('Size change (up to 10")', "Two-tone", "Lock"),
)

# Template builder from scripts/add_builder.py — not a selling factory and
# not in SETTLED. Later SETTLED-expansion jobs clone this row.
STUB_FIXTURE = (
    "Stub Workshop",
    "stub_workshop",
    "Stub_Workshop_2028_Pricelist.xlsx",
    FIXTURES_DIR / "stubs" / "stub-workshop.xlsx",
    ('Size change (up to 10")', "Two-tone", "Lock"),
)


def all_fixture_paths() -> list[Path]:
    paths = [row[3] for row in SETTLED_FIXTURES]
    paths.append(WIDE_FIXTURE[3])
    paths.append(OPTIONS_FIXTURE[3])
    paths.append(STUB_FIXTURE[3])
    return paths
