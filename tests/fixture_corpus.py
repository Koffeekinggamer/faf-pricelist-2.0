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
# not in SETTLED. Kickoff job 5 clones the fixture pattern, not this stub lock.
STUB_FIXTURE = (
    "Stub Workshop",
    "stub_workshop",
    "Stub_Workshop_2028_Pricelist.xlsx",
    FIXTURES_DIR / "stubs" / "stub-workshop.xlsx",
    ('Size change (up to 10")', "Two-tone", "Lock"),
)

# Audit §2.3 — shape-specific / dedicated module. Promote to SETTLED only
# when fixture bytes + a shape test exist.
TIER_B_SHAPE = (
    ("AJ's Furniture", "ajs_furniture"),
    ("Amish Aspen", "amish_aspen"),
    ("Brookside Home Furnishings", "brookside_home_furnishings"),
    ("Fredericksburg Furniture", "fredericksburg_furniture"),
    ("Five Star Tables", "five_star_tables"),
    ("Frog Pond Furniture", "frog_pond_furniture"),
    ("Hillside Chair", "hillside_chair"),
    ("Hogback Design And Finishing", "hogback_design_and_finishing"),
    ("Hope Wood", "hw_chair_markup"),
    ("J. Troyer & Company", "j_troyer_and_company"),
    ("Kidron Woodcraft", "kidron_woodcraft"),
    ("LAMB", "lamb"),
    ("Maple Lane", "maple_lane"),
    ("Patio Kraft", "patio_kraft"),
    ("Superior Woodcrafts", "superior_woodcrafts"),
    ("Townline Furniture", "townline_furniture"),
    ("Troyer Ridge Furniture", "troyer_ridge_furniture"),
    ("Windy Acres Furniture", "windy_acres"),
)

# No Tier B factory remains blocked. Token-only locks stay in Tier C.
TIER_B_BLOCKED: dict[str, str] = {}

# Shared Options-tab keys for Tier B books that do not print their own adders.
TIER_B_OPTIONS = ("Two-tone", "Lock")


def _tier_b_fixture(builder: str, importer: str, filename: str, slug: str, option_keys: tuple[str, ...]):
    return (
        builder,
        importer,
        filename,
        FIXTURES_DIR / "settled" / f"{slug}.xlsx",
        option_keys,
    )


SETTLED_FIXTURES.extend(
    [
        _tier_b_fixture(
            "AJ's Furniture",
            "ajs_furniture",
            "AJ's Furniture 2028 Pricelist.xlsx",
            "aj-s-furniture",
            ("Standard", "Optional Springs", "Motorized Mechanism"),
        ),
        _tier_b_fixture(
            "Amish Aspen",
            "amish_aspen",
            "Amish Aspen 2028 Pricelist.xlsx",
            "amish-aspen",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Brookside Home Furnishings",
            "brookside_home_furnishings",
            "Brookside Home Furnishings 2028 Pricelist.xlsx",
            "brookside-home-furnishings",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Fredericksburg Furniture",
            "fredericksburg_furniture",
            "Fredericksburg Furniture 2028 Pricelist.xlsx",
            "fredericksburg-furniture",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Five Star Tables",
            "five_star_tables",
            "Five Star Tables 2028 Pricelist.xlsx",
            "five-star-tables",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Frog Pond Furniture",
            "frog_pond_furniture",
            "Frog Pond Furniture 2028 Pricelist.xlsx",
            "frog-pond-furniture",
            ("Paint", "2-Toned Stains"),
        ),
        _tier_b_fixture(
            "Hillside Chair",
            "hillside_chair",
            "Hillside Chair 2028 Pricelist.xlsx",
            "hillside-chair",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Hogback Design And Finishing",
            "hogback_design_and_finishing",
            "Hogback Design And Finishing 2028 Pricelist.xlsx",
            "hogback-design-and-finishing",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Hope Wood",
            "hw_chair_markup",
            "Hope Wood HW_Chair 2028 Pricelist.xlsx",
            "hope-wood",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "J. Troyer & Company",
            "j_troyer_and_company",
            "J. Troyer & Company 2028 Pricelist.xlsx",
            "j-troyer-and-company",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Kidron Woodcraft",
            "kidron_woodcraft",
            "Kidron Woodcraft 2028 Pricelist.xlsx",
            "kidron-woodcraft",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "LAMB",
            "lamb",
            "LAMB 2028 Pricelist.xlsx",
            "lamb",
            ("LED Lights", "Lock"),
        ),
        _tier_b_fixture(
            "Maple Lane",
            "maple_lane",
            "Maple Lane 2028 Pricelist.xlsx",
            "maple-lane",
            ("Corian top — Maui Quartz", "Crypton fabric pad — Breeze"),
        ),
        _tier_b_fixture(
            "Patio Kraft",
            "patio_kraft",
            "Patio Kraft 2028 Pricelist.xlsx",
            "patio-kraft",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Superior Woodcrafts",
            "superior_woodcrafts",
            "Superior Woodcrafts 2028 Pricelist.xlsx",
            "superior-woodcrafts",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Townline Furniture",
            "townline_furniture",
            "Townline Furniture 2028 Pricelist.xlsx",
            "townline-furniture",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Troyer Ridge Furniture",
            "troyer_ridge_furniture",
            "Troyer Ridge Furniture 2028 Pricelist.xlsx",
            "troyer-ridge-furniture",
            TIER_B_OPTIONS,
        ),
        _tier_b_fixture(
            "Windy Acres Furniture",
            "windy_acres",
            "Windy Acres Furniture 2028 Pricelist.xlsx",
            "windy-acres-furniture",
            ("Two-tone", "Paint", "Hidden jewelry drawer"),
        ),
    ]
)


def all_fixture_paths() -> list[Path]:
    paths = [row[3] for row in SETTLED_FIXTURES]
    paths.append(WIDE_FIXTURE[3])
    paths.append(OPTIONS_FIXTURE[3])
    paths.append(STUB_FIXTURE[3])
    return paths

