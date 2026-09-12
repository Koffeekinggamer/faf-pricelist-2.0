"""Identity maps must not collide before factory 49+ expansion.

``identify_reader`` stays the Drop runtime seam. ``builder_identity`` inventories
VENDOR_CANON, profile hints, CATALOG_SPECS tokens, and registry detect so a
duplicate short token or detector path fails pytest instead of silently
first-winning.
"""

from __future__ import annotations

from backend.builder_identity import (
    WATCHED_SHORT_TOKENS,
    IdentityClaim,
    ReaderHit,
    catalog_spec_tokens,
    detector_path_collisions,
    identity_claims,
    is_short_token,
    is_viztech_download_stem,
    known_builders,
    matching_filename_hint_vendors,
    matching_readers,
    next_year_probe_filenames,
    short_token_claims,
    token_collisions,
)
from backend.builder_parsers import guess_named_parser, identify_reader
from backend.catalog_readers import CatalogSpec
from backend.standardize import resolve_builder_vendor
from tests.fixture_corpus import OPTIONS_FIXTURE, SETTLED_FIXTURES, STUB_FIXTURE, WIDE_FIXTURE
from tests.test_builder_parser_contract import SETTLED


def test_token_collisions_reports_two_vendors_sharing_a_short_token():
    claims = (
        IdentityClaim("Artisan Chairs", "ac", "vendor_canon"),
        IdentityClaim("Acme Chairs", "ac", "catalog_token", "acme_chairs"),
    )
    found = token_collisions(claims)
    assert "ac" in found
    assert {claim.vendor for claim in found["ac"]} == {"Artisan Chairs", "Acme Chairs"}


def test_same_vendor_may_repeat_a_token_across_maps():
    claims = (
        IdentityClaim("J & M Woodworking", "jmw", "vendor_canon"),
        IdentityClaim("J & M Woodworking", "jmw", "profile_hint", "jmw"),
    )
    assert token_collisions(claims) == {}


def test_live_identity_maps_have_no_token_collisions():
    collisions = token_collisions()
    assert collisions == {}, _format_token_collisions(collisions)


def test_space_separated_factory_names_are_not_short_tokens():
    assert is_short_token("ac")
    assert is_short_token("ao_pricelist")
    assert is_short_token("fnc")
    assert not is_short_token("hope wood")
    assert not is_short_token("fn chair")
    assert not is_short_token("artisan chairs")


def test_catalog_inventory_keeps_short_extra_tokens():
    spec = CatalogSpec("acme_chairs", "Acme Chairs", extra_tokens=("ac",))
    assert "ac" in catalog_spec_tokens(spec)
    assert "ac" not in spec.tokens()


def test_watched_short_tokens_map_to_exactly_one_vendor():
    by_token: dict[str, set[str]] = {}
    for claim in short_token_claims():
        if claim.token in WATCHED_SHORT_TOKENS:
            by_token.setdefault(claim.token, set()).add(claim.vendor)
    missing = [token for token in WATCHED_SHORT_TOKENS if token not in by_token]
    assert missing == [], f"watched short tokens missing from inventory: {missing}"
    ambiguous = {token: vendors for token, vendors in by_token.items() if len(vendors) != 1}
    assert ambiguous == {}, f"ambiguous short tokens: {ambiguous}"


def test_detector_path_collisions_reports_two_readers_on_one_filename(monkeypatch):
    def fake_matching(filename, *, sheet_names=None, data=None):
        return (
            ReaderHit("Artisan Chairs", "artisan_chairs"),
            ReaderHit("Acme Chairs", "acme_chairs"),
        )

    monkeypatch.setattr("backend.builder_identity.matching_readers", fake_matching)
    found = detector_path_collisions(["AC_2028_Pricelist.xlsx"])
    assert "AC_2028_Pricelist.xlsx" in found
    assert {hit.vendor for hit in found["AC_2028_Pricelist.xlsx"]} == {
        "Artisan Chairs",
        "Acme Chairs",
    }


def test_filename_hints_do_not_split_a_next_year_file():
    split = {}
    for path in next_year_probe_filenames():
        vendors = matching_filename_hint_vendors(path)
        if len(set(vendors)) > 1:
            split[path] = vendors
    for builder, _importer, next_file, *_rest in SETTLED:
        vendors = matching_filename_hint_vendors(next_file)
        if len(set(vendors)) > 1:
            split[next_file] = vendors
        elif vendors:
            assert set(vendors) == {builder}
    assert split == {}, f"filename hints split files: {split}"


def test_no_two_detectors_claim_the_same_next_year_filename():
    paths = list(next_year_probe_filenames())
    paths.extend(row[2] for row in SETTLED)
    paths.extend(row[2] for row in SETTLED_FIXTURES)
    paths.append(WIDE_FIXTURE[2])
    paths.append(OPTIONS_FIXTURE[2])
    paths.append(STUB_FIXTURE[2])
    collisions = detector_path_collisions(paths)
    assert collisions == {}, _format_detector_collisions(collisions)


def test_settled_next_year_files_still_have_one_reader():
    for builder, importer, next_file, sheets, _detector, _live in SETTLED:
        hits = matching_readers(next_file, sheet_names=sheets)
        ids = {hit.parser_id for hit in hits}
        assert importer in ids, f"{builder}: {next_file} missed {importer}; hits={hits}"
        others = [hit for hit in hits if hit.parser_id != importer]
        assert others == [], f"{builder}: extra readers claimed {next_file}: {others}"


def test_settled_identify_reader_still_locks_the_named_parser():
    for builder, importer, next_file, sheets, _detector, _live in SETTLED:
        vendor, parser_id, source = identify_reader(next_file, sheet_names=sheets)
        assert vendor == builder
        assert parser_id == importer
        assert source == "saved"
        assert resolve_builder_vendor(next_file, filename=next_file) == builder


def test_download_stem_never_wins_as_vendor():
    name = "Download_2027_Pricelist_111.xlsx"
    assert is_viztech_download_stem(name)
    assert resolve_builder_vendor(name, filename=name) is None
    assert resolve_builder_vendor(name) is None
    vendor, parser_id, source = identify_reader(name)
    assert vendor == ""
    assert parser_id == ""
    assert source == ""
    assert vendor not in known_builders()
    assert guess_named_parser(name) == ("", "")


def test_download_stem_with_factory_folder_still_resolves():
    vendor, parser_id = guess_named_parser(
        "Black Horse Furniture/Download_2027_Pricelist.xlsx"
    )
    assert vendor == "Black Horse Furniture"
    assert parser_id == "black_horse_furniture"


def test_identity_inventory_covers_all_four_maps():
    sources = {claim.source for claim in identity_claims()}
    assert {
        "vendor_canon",
        "catalog_token",
        "profile_hint",
        "parser_id",
    } <= sources
    builders = known_builders()
    assert "Artisan Chairs" in builders
    assert "Ashery Oak" in builders
    assert "FN Chair" in builders
    assert "Download" not in builders


def _format_token_collisions(collisions: dict[str, tuple[IdentityClaim, ...]]) -> str:
    lines = []
    for token, group in sorted(collisions.items()):
        owners = ", ".join(f"{claim.vendor} ({claim.source})" for claim in group)
        lines.append(f"{token}: {owners}")
    return "token collisions:\n" + "\n".join(lines)


def _format_detector_collisions(collisions: dict[str, tuple[ReaderHit, ...]]) -> str:
    lines = []
    for path, hits in sorted(collisions.items()):
        owners = ", ".join(f"{hit.parser_id}/{hit.vendor}" for hit in hits)
        lines.append(f"{path}: {owners}")
    return "detector path collisions:\n" + "\n".join(lines)
