"""Kickoff #6: extracted factory readers register once; aliases stay real."""

import wide_import
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.patio_kraft_import import looks_like_patio_kraft

MOVED = (
    ("patio_kraft", "backend.patio_kraft_import"),
    ("lamb", "backend.lamb_import"),
    ("windy_acres", "backend.windy_acres_import"),
    ("amish_aspen", "backend.amish_aspen_import"),
    ("hillside_chair", "backend.hillside_chair_import"),
    ("maple_lane", "backend.maple_lane_import"),
    ("hw_chair_markup", "backend.hw_chair_import"),
    ("artisan_chairs", "backend.artisan_chairs_import"),
    ("luxhome", "backend.luxhome_import"),
)


def test_extracted_readers_register_once_outside_wide_import():
    for parser_id, module in MOVED:
        entry = DEFAULT_READER_REGISTRY.get(parser_id)
        assert entry is not None, parser_id
        assert entry.detector.startswith(f"{module}:"), entry.detector
        assert entry.reader.startswith(f"{module}:"), entry.reader


def test_wide_import_aliases_are_the_home_functions():
    assert wide_import.looks_like_patio_kraft is looks_like_patio_kraft
