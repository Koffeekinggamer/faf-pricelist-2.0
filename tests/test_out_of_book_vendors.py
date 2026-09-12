"""VENDOR_CANON orphans stay named; only Millers gets a locked reader."""

from pathlib import Path

from backend.builder_profiles import PROFILES_DIR, vendor_slug
from backend.catalog_readers import spec_for_vendor
from backend.standardize import resolve_builder_vendor
from tests.test_builder_parser_contract import SETTLED

DOCS = Path(__file__).resolve().parents[1] / "docs" / "OUT_OF_BOOK_VENDORS.md"

OUT_OF_BOOK_NO_READER = (
    "Rainbow Bedding",
    "Charleston Forge",
    "Beaverdam",
    "GVWI",
)


def test_out_of_book_doc_names_each_orphan():
    text = DOCS.read_text(encoding="utf-8")
    for vendor in ("Millers Woodshop", *OUT_OF_BOOK_NO_READER):
        assert vendor in text, f"{vendor} missing from {DOCS.name}"
    assert "Do not invent a catalog" in text


def test_orphans_without_a_reader_have_no_profile_or_spec():
    settled = {row[0] for row in SETTLED}
    for vendor in OUT_OF_BOOK_NO_READER:
        assert spec_for_vendor(vendor) is None
        assert not (PROFILES_DIR / f"{vendor_slug(vendor)}.json").is_file()
        assert vendor not in settled


def test_canon_aliases_still_resolve():
    assert resolve_builder_vendor("MWS 2023") == "Millers Woodshop"
    assert resolve_builder_vendor("", filename="Jan 2026 wholesale.xlsx") == "Rainbow Bedding"
    assert resolve_builder_vendor("Charleston Forge") == "Charleston Forge"
    assert resolve_builder_vendor("Beaverdam") == "Beaverdam"
    assert resolve_builder_vendor("Gable Valley") == "GVWI"


def test_millers_is_the_only_orphan_with_a_locked_reader():
    assert spec_for_vendor("Millers Woodshop") is not None
    assert spec_for_vendor("Millers Woodshop").parser_id == "millers_woodshop"
    assert (PROFILES_DIR / f"{vendor_slug('Millers Woodshop')}.json").is_file()
    assert spec_for_vendor("Rainbow Bedding") is None
