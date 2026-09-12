"""Feedback loop: Option dropdown = addon charges + finish codes (ADR-0008)."""

from __future__ import annotations

from backend.db import init_db
from backend.repository import PriceBookRepository
from backend.service import PriceBookService


def _row(
    vendor: str,
    *,
    species: str | None = "Oak",
    option_key: str | None = None,
    part: str = "P1",
    line_kind: str = "item",
    base_price: float = 100,
):
    return {
        "vendor": vendor,
        "collection": "Casegoods" if line_kind == "item" else "Addons",
        "part_number": part,
        "description": part,
        "option_key": option_key,
        "species": species,
        "finish_state": "finished",
        "base_price": base_price,
        "multiplier": 2.7,
        "adjusted_price": round(base_price * 2.7, 2),
        "price_basis": "wholesale",
        "source_file": "t.xlsx",
        "line_kind": line_kind,
    }


def test_wood_only_builder_without_addons_has_empty_option(tmp_path):
    """Wood-only catalogs correctly show empty Option until addons exist."""
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Wood Only Co", species="Oak"),
            _row("Wood Only Co", species="Cherry", part="P2"),
        ]
    )
    assert repo.list_species(vendor="Wood Only Co")
    assert repo.list_option_keys("Wood Only Co") == []


def test_addon_charge_appears_in_option_dropdown(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Wood Only Co", species="Oak"),
            _row(
                "Wood Only Co",
                species=None,
                option_key="Solid Fabrics / COM",
                part="Solid Fabrics / COM",
                line_kind="addon",
                base_price=23,
            ),
            _row(
                "Wood Only Co",
                species=None,
                option_key="Rustic +15%",
                part="Rustic +15%",
                line_kind="addon",
                base_price=1,
            ),
        ]
    )
    opts = repo.list_option_keys("Wood Only Co")
    assert "Solid Fabrics / COM" in opts
    assert "Rustic +15%" in opts


def test_service_options_are_scoped_to_the_matching_builder_item(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    harmony = {
        **_row("LuxHome", species=None, option_key="Standard", part="21 HRR"),
        "collection": "Harmony Collection",
    }
    serene = {
        **_row("LuxHome", species=None, option_key="Premium", part="10 SC-FA"),
        "collection": "Serene Collection",
    }
    lookalike = {
        **_row("LuxHome", species=None, option_key="Ultra", part="21 HRR"),
        "collection": "Other Collection",
    }
    prefix_collision = {
        **_row("LuxHome", species=None, option_key="Bleed", part="21 HRR-ALT"),
        "collection": "Harmony Collection",
    }
    svc.repo.insert_rows(
        [
            harmony,
            serene,
            lookalike,
            prefix_collision,
            {
                **_row(
                    "LuxHome",
                    species=None,
                    option_key="Motorized Mechanism",
                    part="21 HRR",
                    line_kind="addon",
                    base_price=80,
                ),
                "collection": "Harmony Collection",
            },
            {
                **_row(
                    "LuxHome",
                    species=None,
                    option_key="Battery Pack",
                    part="10 SC-FA",
                    line_kind="addon",
                    base_price=100,
                ),
                "collection": "Serene Collection",
            },
            {
                **_row(
                    "LuxHome",
                    species=None,
                    option_key="Battery Pack",
                    part="21 HRR",
                    line_kind="addon",
                    base_price=100,
                ),
                "collection": "Other Collection",
            },
            _row("Other Builder", option_key="Other Option", part="21 HRR"),
        ]
    )

    assert svc.list_option_keys(
        "LuxHome",
        query="21 HRR",
        collection="Harmony Collection",
        part_number="21 HRR",
    ) == [
        "Motorized Mechanism",
        "Standard",
    ]
    exact = svc.search(
        "21 HRR",
        vendor="LuxHome",
        collection="Harmony Collection",
        part_number="21 HRR",
    )
    assert set(exact["part_number"]) == {"21 HRR"}


def test_primary_search_never_returns_addons_or_lists_plain_items_as_options(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.repo.insert_rows(
        [
            _row("Builder", part="CHAIR-1"),
            _row("Builder", part="Battery Pack"),
            _row(
                "Builder",
                species=None,
                option_key="Motorized Mechanism",
                part="CHAIR-1",
                line_kind="addon",
                base_price=80,
            ),
        ]
    )

    assert set(svc.search("", vendor="Builder")["part_number"]) == {
        "CHAIR-1",
        "Battery Pack",
    }
    assert svc.search("Motorized Mechanism", vendor="Builder").empty
    assert "Battery Pack" not in svc.list_option_keys("Builder")


def test_primary_search_hides_known_legacy_option_titles_mislabeled_as_items(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.repo.insert_rows(
        [
            _row("Crystal Valley Hardwoods", part="CV-100"),
            _row("Crystal Valley Hardwoods", part="OPTION P-1"),
            _row("Crystal Valley Hardwoods", part="option: Storage Bed"),
            _row("INTEG Wood Products", part="I-100"),
            _row("INTEG Wood Products", part="Options"),
            {
                **_row("INTEG Wood Products", part="Soft Close Slides"),
                "collection": "Options",
            },
            {
                **_row("INTEG Wood Products", part="Custom Hardware"),
                "collection": "Upgrades / Options",
            },
            {
                **_row("Genuine Oak", part="GO-100"),
                "description": "Corner Curio OPTIONS: Extra Glass Shelves Add $30",
            },
            _row("Genuine Oak", part="OPTIONS: Hardware"),
            _row("Elite Designs", part="ED-100"),
            _row("Elite Designs", part="$36904 Standard hardware"),
            {
                **_row("Nisley Cabinet LLC", part="NS100"),
                "description": "Nightstand OPTIONS: Cedar Drawer Bottoms Add $80",
            },
            _row("Nisley Cabinet LLC", part="OPTIONS: Soft Close Slides"),
            _row("Nisley Cabinet LLC", part="OPTION P-1"),
            _row("Nisley Cabinet LLC", part="Add $25 for leaf storage"),
            {
                **_row("Five Star Tables", part="T-100"),
                "description": "Mission Stool Fabric Seats Add $20; Leather $40",
            },
            _row("Five Star Tables", part="add $25 for leaf storage"),
        ]
    )

    assert set(svc.search("", vendor="Crystal Valley Hardwoods")["part_number"]) == {"CV-100"}
    assert set(svc.search("", vendor="INTEG Wood Products")["part_number"]) == {"I-100"}
    assert set(svc.search("", vendor="Genuine Oak")["part_number"]) == {"GO-100"}
    assert set(svc.search("", vendor="Elite Designs")["part_number"]) == {"ED-100"}
    assert set(svc.search("", vendor="Nisley Cabinet LLC")["part_number"]) == {"NS100"}
    assert set(svc.search("", vendor="Five Star Tables")["part_number"]) == {"T-100"}
    assert [
        item.part_number
        for item in svc.list_search_item_identities("", vendor="INTEG Wood Products")
    ] == ["I-100"]
    assert [
        item.part_number
        for item in svc.list_search_item_identities("", vendor="Elite Designs")
    ] == ["ED-100"]
    assert [
        item.part_number
        for item in svc.list_search_item_identities("", vendor="Nisley Cabinet LLC")
    ] == ["NS100"]


def test_crystal_valley_end_table_does_not_get_vendor_wide_options(tmp_path):
    svc = PriceBookService(tmp_path / "t.db")
    svc.init()
    vendor = "Crystal Valley Hardwoods"
    svc.repo.insert_rows(
        [
            _row(vendor, part="AN1624E"),
            {
                **_row(vendor, part="BED-1"),
                "finish_state": "unfinished",
            },
            *[
                _row(
                    vendor,
                    species=None,
                    option_key=label,
                    part=label,
                    line_kind="addon",
                )
                for label in (
                    "Springhill and McCoy",
                    "Tz movement from Hermle of Germany",
                    "Also available without through tenons",
                    "Storage Bed option",
                )
            ],
        ]
    )

    assert svc.list_option_keys(
        vendor,
        query="AN1624E",
        collection="Casegoods",
        part_number="AN1624E",
    ) == []


def test_genuine_oak_curio_keeps_only_options_printed_on_that_item(tmp_path):
    svc = PriceBookService(tmp_path / "t.db")
    svc.init()
    vendor = "Genuine Oak"
    item = _row(vendor, part="G06-46")
    item["description"] = "Bunker Hill Corner Curio OPTIONS: Extra Glass Shelves Add $30"
    svc.repo.insert_rows(
        [
            item,
            *[
                _row(
                    vendor,
                    species=None,
                    option_key=label,
                    part=label,
                    line_kind="addon",
                )
                for label in (
                    "Extra Glass Shelves Add $30",
                    "2 Drawer Storage",
                    "Paint / Glaze",
                    "Shiplap Back",
                    "Reverse Layout",
                )
            ],
        ]
    )

    assert svc.list_option_keys(
        vendor,
        query="G06-46",
        collection="Casegoods",
        part_number="G06-46",
    ) == ["Extra Glass Shelves Add $30"]


def test_five_star_stool_keeps_only_seat_options_printed_in_title(tmp_path):
    svc = PriceBookService(tmp_path / "t.db")
    svc.init()
    vendor = "Five Star Tables"
    item = _row(vendor, part="145S")
    item["description"] = "Plain Mission Stool — Fabric Seats Add $20; Leather $40"
    svc.repo.insert_rows(
        [
            item,
            *[
                _row(
                    vendor,
                    species=None,
                    option_key=label,
                    part=label,
                    line_kind="addon",
                )
                for label in (
                    "Fabric Seat",
                    "Leather Seat",
                    "Butterfly Leaves",
                    "Horseshoe Base",
                    "Pub Height",
                    "Custom Height",
                )
            ],
        ]
    )

    assert svc.list_option_keys(
        vendor,
        query="145S",
        collection="Casegoods",
        part_number="145S",
    ) == ["Fabric Seat", "Leather Seat"]


def test_five_star_non_seat_goods_reject_bare_leather_or_fabric_price(tmp_path):
    """Bare Leather $40 / Fabric $20 evidence requires seating-goods context."""
    svc = PriceBookService(tmp_path / "t.db")
    svc.init()
    vendor = "Five Star Tables"
    table = _row(vendor, part="T-200")
    table["description"] = "Mission Dining Table — Leather $40; Fabric $20 available"
    svc.repo.insert_rows(
        [
            table,
            *[
                _row(
                    vendor,
                    species=None,
                    option_key=label,
                    part=label,
                    line_kind="addon",
                )
                for label in ("Fabric Seat", "Leather Seat", "Butterfly Leaves")
            ],
        ]
    )

    assert svc.list_option_keys(
        vendor,
        query="T-200",
        collection="Casegoods",
        part_number="T-200",
    ) == []


def test_artisan_bar_stool_keeps_profile_declared_seat_options(tmp_path):
    svc = PriceBookService(tmp_path / "t.db")
    svc.init()
    vendor = "Artisan Chairs"
    item = _row(vendor, part='24" Stationary Bar Stool')
    item["description"] = '24" Stationary Bar Stool'
    svc.repo.insert_rows(
        [
            item,
            *[
                _row(
                    vendor,
                    species=None,
                    option_key=label,
                    part=label,
                    line_kind="addon",
                )
                for label in (
                    "Fabric Seat",
                    "Leather Seat",
                    "Butterfly Leaves",
                )
            ],
        ]
    )

    assert svc.list_option_keys(
        vendor,
        query='24" Stationary Bar Stool',
        collection="Casegoods",
        part_number='24" Stationary Bar Stool',
    ) == ["Fabric Seat", "Leather Seat"]


def test_service_add_addon_charge_lists_in_options(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    svc = PriceBookService(db)
    svc.add_addon_charge(
        vendor="Addon Co",
        label="Nailhead trim",
        flat_wholesale=45,
    )
    # Need a sellable row so vendor exists in book; add_addon alone is enough
    assert "Nailhead trim" in svc.list_option_keys("Addon Co")


def test_repository_search_never_returns_addons_as_primary_items(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("FN Chair", species="Oak", option_key="Cat. 1", part="Abe Side Chair"),
            _row(
                "FN Chair",
                species=None,
                option_key="Solid Fabrics / COM",
                part="Abe Side Chair — Solid Fabrics / COM",
                line_kind="addon",
                base_price=23,
            ),
        ]
    )
    default = repo.search("Abe", vendor="FN Chair", finish_state="finished")
    assert len(default) == 1
    assert float(default.iloc[0]["base_price"]) == 100

    addons = repo.search(
        "",
        vendor="FN Chair",
        option_key="Solid Fabrics / COM",
        finish_state="finished",
    )
    assert addons.empty


def test_fn_chair_still_lists_cats(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("FN Chair", species="Oak", option_key="Cat. 1"),
            _row("FN Chair", species="Oak", option_key="Cat. 2", part="P2"),
        ]
    )
    assert repo.list_option_keys("FN Chair") == ["Cat. 1", "Cat. 2"]


def test_standard_premium_wood_columns_are_wood_not_options(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Millcraft Co", species="Standard Wood", part="NS1"),
            _row("Millcraft Co", species="Premium Wood", part="NS2"),
            _row(
                "Millcraft Co",
                species=None,
                option_key="Two-tone",
                part="Two-tone",
                line_kind="addon",
            ),
        ]
    )
    opts = repo.list_option_keys("Millcraft Co")
    woods = repo.list_species(vendor="Millcraft Co")
    assert "Two-tone" in opts
    assert "Standard Wood" not in opts
    assert "Premium Wood" not in opts
    assert "Standard Wood" in woods
    assert "Premium Wood" in woods


def test_premium_wood_group_is_wood_not_option(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row(
                "J. Troyer & Company",
                species="Premium / Cherry / QSWO",
                part="7430-64",
            ),
            _row(
                "J. Troyer & Company",
                species="Brown Maple / Oak / Rustic Cherry",
                part="7430-64b",
            ),
            _row(
                "J. Troyer & Company",
                species=None,
                option_key="Two-Tone",
                part="Two-Tone",
                line_kind="addon",
            ),
        ]
    )
    opts = repo.list_option_keys("J. Troyer & Company")
    woods = repo.list_species(vendor="J. Troyer & Company")
    assert "Two-Tone" in opts
    assert "Premium / Cherry / QSWO" not in opts
    assert "Cherry" in woods
    assert "QSWO" in woods
    assert "Brown Maple" in woods


def test_mixed_wood_pair_appears_in_wood_dropdown_as_wood_slash_wood(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Meadow Lane Furniture", species="Cherry / Hickory", part="T1"),
            _row("Meadow Lane Furniture", species="Oak / Brown Maple", part="T2"),
            _row(
                "Meadow Lane Furniture",
                species="Wormy Maple / Walnut / Combo",
                part="T3",
            ),
            _row("Meadow Lane Furniture", species="Cherry", part="T4"),
            _row(
                "Meadow Lane Furniture",
                species="Elm / Cherry / Hickory / Maple",
                part="T5",
            ),
        ]
    )
    woods = repo.list_species(vendor="Meadow Lane Furniture")
    assert "Cherry/Hickory" in woods
    assert "Oak/Brown Maple" in woods
    assert "Wormy Maple/Walnut" in woods
    assert "Cherry / Hickory" not in woods
    assert "Cherry" in woods
    assert "Hickory" in woods
    assert "Elm/Cherry/Hickory/Maple" not in woods
    hit = repo.search(
        "",
        vendor="Meadow Lane Furniture",
        species="Cherry/Hickory",
        finish_state="finished",
        limit=20,
    )
    assert list(hit["part_number"]) == ["T1"]
    combo = repo.search(
        "",
        vendor="Meadow Lane Furniture",
        species="Wormy Maple/Walnut",
        finish_state="finished",
        limit=20,
    )
    assert list(combo["part_number"]) == ["T3"]


def test_wood_named_addon_is_wood_not_option(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Frog Pond Furniture", species="Oak", part="100K"),
            _row(
                "Frog Pond Furniture",
                species="Rec. Barnwood Oak",
                part="100K",
            ),
            _row(
                "Frog Pond Furniture",
                species=None,
                option_key="Rec. Barnwood Oak",
                part="Rec. Barnwood Oak",
                line_kind="addon",
            ),
            _row(
                "Frog Pond Furniture",
                species=None,
                option_key="Painting",
                part="Painting",
                line_kind="addon",
            ),
        ]
    )
    opts = repo.list_option_keys("Frog Pond Furniture")
    woods = repo.list_species(vendor="Frog Pond Furniture")
    assert "Painting" in opts
    assert "Rec. Barnwood Oak" not in opts
    assert "Rec. Barnwood Oak" in woods
    assert "Oak" in woods
