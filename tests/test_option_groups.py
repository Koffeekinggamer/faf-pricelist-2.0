"""Single-select Option groups: alternatives replace each other (ADR-0011)."""

from __future__ import annotations

from backend.builder_profiles import (
    exclusive_option_conflicts,
    load_builder_profile,
    resolve_option_groups,
)


def test_fn_chair_categories_are_a_single_select_group():
    profile = load_builder_profile("FN Chair")
    selected = ["Cat. 1", "Cat. 2", "Cat. 3"]
    assert exclusive_option_conflicts(profile, "Cat. 3", selected) == [
        "Cat. 1",
        "Cat. 2",
    ]


def test_fn_chair_fabric_and_category_do_not_conflict():
    profile = load_builder_profile("FN Chair")
    selected = ["Cat. 1", "Solid Fabrics / COM / Faux Leathers"]
    assert exclusive_option_conflicts(profile, "Cat. 1", selected) == []
    assert (
        exclusive_option_conflicts(
            profile, "Solid Fabrics / COM / Faux Leathers", selected
        )
        == []
    )


def test_fn_chair_fabric_tiers_are_a_single_select_group():
    profile = load_builder_profile("FN Chair")
    selected = [
        "Cat. 1",
        "Solid Fabrics / COM / Faux Leathers",
        "Revolution, Easy Living & Premium Fabrics",
        "Non-Heartland Leather or Ultra Fabrics",
        "Leather & Ultra Fabric",
    ]
    conflicts = exclusive_option_conflicts(profile, "Leather & Ultra Fabric", selected)
    assert "Cat. 1" not in conflicts
    assert conflicts == [
        "Solid Fabrics / COM / Faux Leathers",
        "Revolution, Easy Living & Premium Fabrics",
        "Non-Heartland Leather or Ultra Fabrics",
    ]


def test_fn_chair_keeps_one_category_and_one_fabric():
    profile = load_builder_profile("FN Chair")
    assert resolve_option_groups(
        profile,
        [
            "Cat. 1",
            "Cat. 3",
            "Solid Fabrics / COM / Faux Leathers",
            "Non-Heartland Fabric",
        ],
    ) == ["Cat. 3", "Non-Heartland Fabric"]


def test_artisan_chairs_keeps_one_upholstered_and_one_wood_seat():
    profile = load_builder_profile("Artisan Chairs")
    assert resolve_option_groups(
        profile,
        [
            "Fabric Seat",
            "Leather Seat",
            "Walnut Seat on Brown Maple",
            "Elm Seats on Brown Maple",
            "Nail Heads",
        ],
    ) == ["Leather Seat", "Elm Seats on Brown Maple", "Nail Heads"]


def test_builders_without_groups_keep_stackable_options():
    profile = load_builder_profile("J & M Woodworking")
    selected = ["Paint", "Undermount Drawer Slides"]
    assert exclusive_option_conflicts(profile, "Paint", selected) == []
