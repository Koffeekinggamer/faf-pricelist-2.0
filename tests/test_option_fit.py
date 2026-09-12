"""Search Options list follows the piece being looked up (all builders)."""

from __future__ import annotations

from backend.option_fit import (
    filter_options_for_kinds,
    furniture_kinds_from_text,
    order_search_options,
)
from backend.service import PriceBookService


def test_fn_bar_stools_with_arms_only_on_barstool_or_bar_chair():
    opt = "BAR STOOLS WITH ARMS"
    opts = [opt, "Cat. 1", "Paint"]
    for query in ("barstool", "bar stool", "bar chair", "barchair"):
        shown = filter_options_for_kinds(opts, furniture_kinds_from_text(query), text=query)
        assert opt in shown, query
        assert "Paint" in shown
    for query in ("side chair", "chair", "arm chair"):
        shown = filter_options_for_kinds(opts, furniture_kinds_from_text(query), text=query)
        assert opt not in shown, query
    assert opt not in filter_options_for_kinds(opts, set(), text="")


def test_cat_options_list_in_numeric_order_before_the_rest():
    labels = [
        "Unfinished",
        "BAR STOOLS WITH ARMS",
        "Cat. 3",
        "Cat. 1",
        "Memory Swivel Option",
        "Cat. 2",
    ]
    ordered = order_search_options(labels)
    assert ordered[:3] == ["Cat. 1", "Cat. 2", "Cat. 3"]
    assert ordered[3] == "Unfinished"
    assert "BAR STOOLS WITH ARMS" in ordered[4:]
    assert "Memory Swivel Option" in ordered[4:]


def test_bed_query_is_a_bed_kind():
    assert "bed" in furniture_kinds_from_text("queen bed")
    assert "bed" in furniture_kinds_from_text("CWF 505 Meridian Headboard")
    assert "casegood" not in furniture_kinds_from_text("queen bed")


def test_dresser_query_is_casegood():
    assert "casegood" in furniture_kinds_from_text("6 Drawer Dresser")
    assert "bed" not in furniture_kinds_from_text("6 Drawer Dresser")
    assert "nightstand" not in furniture_kinds_from_text("6 Drawer Dresser")


def test_nightstand_query_is_nightstand_and_casegood():
    kinds = furniture_kinds_from_text("3 Drawer Night Stand")
    assert "nightstand" in kinds
    assert "casegood" in kinds
    assert "bed" not in kinds


def test_bed_search_keeps_headboard_and_hides_drawer_slides():
    opts = [
        '20" high low footboard (DEDUCT)',
        "Queen Platform for all beds",
        "Undermount Drawer Slides",
        "Cedar Lined Drawers",
        "Additional Shelves (Each)",
        "VCR Shelf",
        "With Garment Bar",
        "Unfinished",
        "Paint",
    ]
    shown = filter_options_for_kinds(opts, furniture_kinds_from_text("queen bed"))
    assert '20" high low footboard (DEDUCT)' in shown
    assert "Queen Platform for all beds" in shown
    assert "Unfinished" in shown
    assert "Paint" in shown
    assert "Undermount Drawer Slides" not in shown
    assert "Cedar Lined Drawers" not in shown
    assert "Additional Shelves (Each)" not in shown
    assert "VCR Shelf" not in shown
    assert "With Garment Bar" not in shown


def test_casegood_search_keeps_slides_and_hides_footboard():
    opts = [
        '20" high low footboard (DEDUCT)',
        "Undermount Drawer Slides",
        "Slide out Tray for Night Stands",
        "Additional Shelves (Each)",
        "Paint",
    ]
    shown = filter_options_for_kinds(opts, furniture_kinds_from_text("night stand"))
    assert "Undermount Drawer Slides" in shown
    assert "Slide out Tray for Night Stands" in shown
    assert "Additional Shelves (Each)" in shown
    assert "Paint" in shown
    assert '20" high low footboard (DEDUCT)' not in shown
    assert "With Garment Bar" not in filter_options_for_kinds(
        ["With Garment Bar", "Paint"], furniture_kinds_from_text("6 Drawer Dresser")
    )


def test_cedar_on_drawer_pieces_never_on_beds():
    opts = [
        "Cedar Lined Drawers",
        "Cedar Bottom Drawers (add per drawer)",
        "Paint",
        "Queen Platform for all beds",
    ]
    for piece in (
        "6 Drawer Dresser",
        "night stand",
        "armoire",
        "Drawer Unit",
        "desk",
    ):
        shown = filter_options_for_kinds(opts, furniture_kinds_from_text(piece))
        assert "Cedar Lined Drawers" in shown, piece
        assert "Cedar Bottom Drawers (add per drawer)" in shown, piece
        assert "Queen Platform for all beds" not in shown
    bed = filter_options_for_kinds(opts, furniture_kinds_from_text("queen bed"))
    assert "Cedar Lined Drawers" not in bed
    mixed = filter_options_for_kinds(opts, {"bed", "casegood"})
    assert "Cedar Lined Drawers" not in mixed
    assert "Paint" in mixed


def test_phone_charger_and_nightstand_doors_only_on_nightstands():
    opts = [
        "Night Stand with Doors",
        "Phone Charger",
        "Undermount Drawer Slides",
        "Paint",
    ]
    on_stand = filter_options_for_kinds(opts, furniture_kinds_from_text("night stand"))
    on_dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    assert "Phone Charger" in on_stand
    assert "Night Stand with Doors" in on_stand
    assert "Undermount Drawer Slides" in on_stand
    assert "Phone Charger" not in on_dresser
    assert "Night Stand with Doors" not in on_dresser
    assert "Undermount Drawer Slides" in on_dresser
    assert "Paint" in on_dresser


def test_square_corners_on_buffet_top_only_on_buffets():
    opt = "Square corners on buffet top"
    opts = [opt, "Soft Close hinges", "Paint"]
    buffet = filter_options_for_kinds(opts, furniture_kinds_from_text("buffet"))
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    hutch = filter_options_for_kinds(opts, furniture_kinds_from_text("2 Door Hutch"))
    assert "buffet" in furniture_kinds_from_text("buffet")
    assert opt in buffet
    assert "Soft Close hinges" in buffet
    assert opt not in chair
    assert opt not in table
    assert opt not in dresser
    assert opt not in hutch
    assert "Paint" in chair


def test_brookside_extenda_bench_only_on_benches():
    opt = "Extenda bench - Shaker bench"
    opts = [opt, "Fabric Cushions", "Paint"]
    bench = filter_options_for_kinds(opts, furniture_kinds_from_text("shaker bench"))
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    assert "bench" in furniture_kinds_from_text("shaker bench")
    assert opt in bench
    assert opt not in chair
    assert opt not in table
    assert "Fabric Cushions" in chair
    assert "Paint" in chair


def test_brookside_usb_outlet_only_on_nightstands():
    opts = ["USB outlet", "Gear Slides", "Paint"]
    stand = filter_options_for_kinds(opts, furniture_kinds_from_text("night stand"))
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    assert "USB outlet" in stand
    assert "USB outlet" not in chair
    assert "USB outlet" not in table
    assert "USB outlet" not in dresser
    assert "Paint" in chair


def test_wardrobe_and_door_chest_keep_garment_bar():
    opts = ["With Garment Bar", "Undermount Drawer Slides", "Queen Platform for all beds"]
    for piece in ("armoire", "wardrobe", "Gentleman's Chest", "chest with doors"):
        shown = filter_options_for_kinds(opts, furniture_kinds_from_text(piece))
        assert "With Garment Bar" in shown, piece
        assert "Queen Platform for all beds" not in shown


def test_empty_kinds_keep_every_option():
    opts = ["Undermount Drawer Slides", "Queen Platform for all beds"]
    assert filter_options_for_kinds(opts, set()) == opts


def test_hidden_compartment_never_lists_in_search_options():
    opts = [
        "Hidden Compartment",
        "Hidden Gun Storage (In Bed)",
        "Phone Charger",
        "Paint",
    ]
    assert "Hidden Compartment" not in filter_options_for_kinds(opts, set())
    assert "Hidden Gun Storage (In Bed)" not in filter_options_for_kinds(opts, set())
    assert "Hidden Gun Storage (In Bed)" not in filter_options_for_kinds(
        opts, furniture_kinds_from_text("queen bed"), text="queen bed"
    )
    assert "Phone Charger" in filter_options_for_kinds(
        opts, furniture_kinds_from_text("night stand"), text="night stand"
    )


def test_fn_ordering_select_consistent_color_never_lists_in_search_options():
    """FN Chair Price List Notes: instruction prose, not a Search Option."""
    live = "IF ORDERING SELECT (CONSISTANT COLOR)"
    book = "*IF ORDERING SELECT (CONSISTANT COLOR) ADD 30% PER CHAIR"
    truncated = "IF ORDERING SELECT (CONSISTANT COLOR OF"
    opts = [live, book, truncated, "Cat. 1", "Paint"]
    shown = filter_options_for_kinds(opts, set())
    assert live not in shown
    assert book not in shown
    assert truncated not in shown
    assert "Cat. 1" in shown
    assert "Paint" in shown
    chair = filter_options_for_kinds(
        opts, furniture_kinds_from_text("Abe Side Chair"), text="Abe Side Chair"
    )
    assert live not in chair
    assert "Cat. 1" in chair


def test_fn_elm_seat_upgrade_note_never_lists_in_search_options():
    """FN Chair Price List Notes: Elm-available-if-upgraded is a wood note."""
    live = "D. (ELM ALSO AVAILABLE) IF SEAT IS A UPGRADED…"
    book = (
        "*ANY SEAT CAN BE CHANGED TO A DIFFERENT WOOD SPECIES IF DESIRED. "
        "(ELM ALSO AVAILABLE) IF SEAT IS A UPGRADED (HIGHER PRICE BRACKET) "
        "WOOD SPECIE ADD $30. IF SEAT IS IN SAME PRICE BRACKET (OR LOWER) "
        "STANDARD PRICE IS USED. ALSO SEE  FINISHING OPTIONS."
    )
    opts = [live, book, "Cat. 1", "INTERCHANGE ANY STYLE SEAT"]
    shown = filter_options_for_kinds(opts, set())
    assert live not in shown
    assert book not in shown
    assert "Cat. 1" in shown
    assert "INTERCHANGE ANY STYLE SEAT" in shown
    chair = filter_options_for_kinds(
        opts, furniture_kinds_from_text("Abe Side Chair"), text="Abe Side Chair"
    )
    assert live not in chair
    assert "Cat. 1" in chair


def test_gear_slides_are_table_only_for_every_builder():
    opts = ["Gear Slides", "Plywood Back", "Paint"]
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    island = filter_options_for_kinds(opts, furniture_kinds_from_text("kitchen island"))
    assert "Gear Slides" in table
    assert "Paint" in table
    assert "Gear Slides" not in chair
    assert "Gear Slides" not in dresser
    assert "Gear Slides" not in island


def test_plywood_back_is_not_for_chairs():
    opts = ["Plywood Back", "Fabric Cushions", "Paint"]
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    assert "Plywood Back" not in chair
    assert "Fabric Cushions" in chair
    assert "Plywood Back" in dresser
    assert "Plywood Back" not in table
    assert "Paint" in chair


def test_soft_close_hinges_only_on_pieces_with_doors():
    opts = ["Soft Close hinges", "Plywood Back", "Paint"]
    for piece in ("2 Door Hutch", "china cabinet", "armoire", "buffet"):
        shown = filter_options_for_kinds(opts, furniture_kinds_from_text(piece))
        assert "Soft Close hinges" in shown, piece
        assert "Paint" in shown
    dresser = filter_options_for_kinds(opts, furniture_kinds_from_text("6 Drawer Dresser"))
    chair = filter_options_for_kinds(opts, furniture_kinds_from_text("side chair"))
    table = filter_options_for_kinds(opts, furniture_kinds_from_text("dining table"))
    assert "Soft Close hinges" not in dresser
    assert "Plywood Back" in dresser
    assert "Soft Close hinges" not in chair
    assert "Soft Close hinges" not in table


def test_island_top_option_only_on_islands():
    opt = '1 1/4" plank island top with sawmarks'
    opts = [opt, "Fabric Cushions", "Paint"]
    on_island = filter_options_for_kinds(
        opts, furniture_kinds_from_text("kitchen island"), text="kitchen island"
    )
    on_chair = filter_options_for_kinds(
        opts, furniture_kinds_from_text("side chair"), text="side chair"
    )
    on_table = filter_options_for_kinds(
        opts, furniture_kinds_from_text("dining table"), text="dining table"
    )
    assert "island" in furniture_kinds_from_text("kitchen island")
    assert opt in on_island
    assert opt not in on_chair
    assert opt not in on_table
    assert "Fabric Cushions" in on_chair
    assert "Paint" in on_chair
    assert "Paint" in on_island


def test_drawer_unit_on_all_bed_sizes_only_on_beds():
    opt = "drawer unit on all bed sizes"
    opts = [opt, "Undermount Drawer Slides", "Paint"]
    on_bed = filter_options_for_kinds(
        opts, furniture_kinds_from_text("queen bed"), text="queen bed"
    )
    on_dresser = filter_options_for_kinds(
        opts, furniture_kinds_from_text("6 Drawer Dresser"), text="6 Drawer Dresser"
    )
    assert opt in on_bed
    assert "Undermount Drawer Slides" not in on_bed
    assert opt not in on_dresser
    assert "Undermount Drawer Slides" in on_dresser


def test_cwf505_wood_panels_only_when_meridian_bed_searched():
    opt = "CWF 505 Meridian Bed w/ Wood Panels ("
    opts = [opt, "Phone Charger", "Queen Platform for all beds"]
    assert opt not in filter_options_for_kinds(opts, set(), text="")
    assert opt not in filter_options_for_kinds(
        opts, furniture_kinds_from_text("queen bed"), text="queen bed"
    )
    assert opt not in filter_options_for_kinds(
        opts, furniture_kinds_from_text("meridian dresser"), text="meridian dresser"
    )
    shown = filter_options_for_kinds(
        opts, furniture_kinds_from_text("meridian bed"), text="meridian bed"
    )
    assert opt in shown
    assert "Queen Platform for all beds" in shown
    assert opt in filter_options_for_kinds(opts, furniture_kinds_from_text("CWF505"), text="CWF505")


def test_service_filters_options_from_sku_hits(tmp_path):
    svc = PriceBookService(db_path=str(tmp_path / "fit.db"))
    svc.init()
    vendor = "Fit Factory"
    svc.repo.insert_rows(
        [
            {
                "vendor": vendor,
                "collection": "Bedroom",
                "part_number": "CWF8110",
                "description": "Queen Bed",
                "species": "Oak",
                "finish_state": "finished",
                "base_price": 1000,
                "adjusted_price": 2700,
                "line_kind": "item",
            },
            {
                "vendor": vendor,
                "collection": "Addons",
                "part_number": "Undermount Drawer Slides",
                "description": "Undermount Drawer Slides",
                "option_key": "Undermount Drawer Slides",
                "base_price": 20,
                "adjusted_price": 20,
                "line_kind": "addon",
            },
            {
                "vendor": vendor,
                "collection": "Addons",
                "part_number": "Queen Platform for all beds",
                "description": "Queen Platform for all beds",
                "option_key": "Queen Platform for all beds",
                "base_price": 80,
                "adjusted_price": 216,
                "line_kind": "addon",
            },
        ]
    )
    all_opts = svc.list_option_keys(vendor)
    shown = svc.options_for_search(vendor, "CWF8110", all_opts)
    assert "Queen Platform for all beds" in shown
    assert "Undermount Drawer Slides" not in shown
    assert svc.options_for_search(vendor, "", all_opts) == all_opts
