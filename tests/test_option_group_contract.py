"""Shipped Option groups must bind to option keys the builder's reader emits.

ADR-0011 makes single-select groups the only thing stopping two alternative
prices from stacking on one chair. The binding is a regex in profile JSON
pointed at strings a parser produces, and nothing in the parser knows the
regex exists: a relabelled book ("Leather Seats") silently unbinds the group
and the floor can check two seat prices at once. The contract here is that
every shipped single-select group still catches at least two real option keys
for its builder, so an unbound group fails a test instead of overcharging.

Option keys come from the loaded catalog when it is on the machine, and from
the builder's own reader on their live book otherwise. When neither is
available for a builder, that builder is skipped rather than asserted green.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.builder_profiles import (
    PROFILES_DIR,
    exclusive_option_conflicts,
    load_builder_profile,
    single_select_group,
)
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "master_pricebook.db"
DOWNLOADS = Path.home() / "Downloads"


def _grouped_profiles() -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        vendor = str(raw.get("vendor") or "").strip()
        if vendor and raw.get("option_groups"):
            found.append((vendor, raw))
    return found


GROUPED = _grouped_profiles()
IDS = [vendor for vendor, _ in GROUPED]


def _keys_from_catalog(vendor: str) -> list[str]:
    if not CATALOG.is_file():
        return []
    con = sqlite3.connect(str(CATALOG))
    try:
        rows = con.execute(
            "SELECT DISTINCT option_key FROM pricebook "
            "WHERE vendor = ? AND option_key IS NOT NULL AND TRIM(option_key) <> ''",
            (vendor,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [str(row[0]) for row in rows]


def _keys_from_live_book(raw: dict, vendor: str) -> list[str]:
    parser = raw.get("parser") or {}
    importer = str(parser.get("importer") or "").strip()
    source = str(parser.get("source_file") or "").strip()
    book = DOWNLOADS / source
    if not importer or not source or not book.is_file():
        return []
    result = DEFAULT_READER_REGISTRY.run(
        importer, book.read_bytes(), vendor=vendor, filename=book.name
    )
    if result is None or result.long_df.empty:
        return []
    if "option_key" not in result.long_df.columns:
        return []
    keys = result.long_df["option_key"].dropna().astype(str)
    return sorted({key.strip() for key in keys if key.strip()})


def _real_option_keys(vendor: str, raw: dict) -> list[str]:
    return _keys_from_catalog(vendor) or _keys_from_live_book(raw, vendor)


@pytest.mark.parametrize("vendor,raw", GROUPED, ids=IDS)
def test_every_single_select_group_binds_to_real_option_keys(vendor, raw):
    keys = _real_option_keys(vendor, raw)
    if not keys:
        pytest.skip(f"no catalog rows or live book for {vendor}")

    profile = load_builder_profile(vendor)
    for group in raw.get("option_groups") or []:
        if str(group.get("selection") or "single").strip().lower() != "single":
            continue
        name = str(group.get("name") or group.get("match") or "?")
        members = [
            key
            for key in keys
            if (single_select_group(profile, key) or {}).get("match")
            == group.get("match")
        ]
        assert len(members) >= 2, (
            f"{vendor} group {name!r} binds {len(members)} of this builder's "
            f"{len(keys)} option keys — a single-select group with fewer than "
            "two members drops nothing, so the alternatives can stack"
        )
        # The whole point of the group: picking one member drops the siblings.
        assert exclusive_option_conflicts(profile, members[0], members)


@pytest.mark.parametrize("vendor,raw", GROUPED, ids=IDS)
def test_group_members_never_span_two_groups(vendor, raw):
    """One option key belongs to at most one family, else last-pick-wins lies."""
    keys = _real_option_keys(vendor, raw)
    if not keys:
        pytest.skip(f"no catalog rows or live book for {vendor}")

    for key in keys:
        matched = [
            str(group.get("name") or group.get("match"))
            for group in raw.get("option_groups") or []
            if str(group.get("selection") or "single").strip().lower() == "single"
            and (single_select_group(load_builder_profile(vendor), key) or {}).get(
                "match"
            )
            == group.get("match")
        ]
        assert len(matched) <= 1, f"{vendor} option {key!r} is in groups {matched}"
