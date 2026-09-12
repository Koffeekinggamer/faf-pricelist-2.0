"""King + Queen size Options collapse to one checkbox plus a size prompt."""

from __future__ import annotations

from backend.option_prompts import (
    DRAWER_UNIT_DISPLAY,
    PLATFORM_DISPLAY,
    collapse_platform_options,
    collapse_size_prompt_options,
    platform_size_choices,
    resolve_platform_choice,
    resolve_size_choice,
    size_prompt_choices,
)


def test_king_and_queen_platform_collapse_to_one_option():
    opts = [
        "Phone Charger",
        "King Platform for all beds",
        "Queen Platform for all beds",
        "Paint",
    ]
    shown = collapse_platform_options(opts)
    assert shown == ["Phone Charger", PLATFORM_DISPLAY, "Paint"]
    assert "King Platform for all beds" not in shown
    assert "Queen Platform for all beds" not in shown


def test_single_platform_stays_its_own_checkbox():
    opts = ["Queen Platform for all beds", "Paint"]
    assert collapse_platform_options(opts) == opts


def test_size_prompt_resolves_to_the_catalog_option():
    catalog = ["King Platform for all beds", "Queen Platform for all beds"]
    assert resolve_platform_choice(catalog, selected=False, size="King") is None
    assert resolve_platform_choice(catalog, selected=True, size="Select size") is None
    assert (
        resolve_platform_choice(catalog, selected=True, size="Queen")
        == "Queen Platform for all beds"
    )
    assert (
        resolve_platform_choice(catalog, selected=True, size="King") == "King Platform for all beds"
    )


def test_size_choices_include_placeholder_then_queen_and_king():
    catalog = ["King Platform for all beds", "Queen Platform for all beds"]
    assert platform_size_choices(catalog) == ["Select size", "Queen", "King"]


def test_drawer_unit_size_pair_collapses_to_one_checkbox():
    opts = [
        "Phone Charger",
        "Queen drawer unit on all bed sizes",
        "King drawer unit on all bed sizes",
    ]
    shown = collapse_size_prompt_options(opts)
    assert shown == ["Phone Charger", DRAWER_UNIT_DISPLAY]
    assert (
        resolve_size_choice(opts, DRAWER_UNIT_DISPLAY, selected=True, size="Queen")
        == "Queen drawer unit on all bed sizes"
    )
    assert (
        resolve_size_choice(opts, DRAWER_UNIT_DISPLAY, selected=True, size="King")
        == "King drawer unit on all bed sizes"
    )
    assert size_prompt_choices(opts, DRAWER_UNIT_DISPLAY) == [
        "Select size",
        "Queen",
        "King",
    ]
