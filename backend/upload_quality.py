"""0–100% quality rating for a builder upload.

Rubric (100 points):
  Options 30 · Species 25 · Descriptions 15 · SKUs 10 · Prices 10 · Parser 10

Empty Search Options is a capture miss, not “this builder has no Options.”
Thin KEEP catalogs are not penalized for size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.standardize import is_wood_column_label

_PLACEHOLDER_DESC = re.compile(
    r"(?i)^(?:nan|nat|none|null|options?|finished|unfinished|finish|"
    r"price|wholesale|retail)$"
)
_GENERIC_PARSERS = {"", "generic", "pdf"}

MAX_POINTS = {
    "options": 30,
    "species": 25,
    "descriptions": 15,
    "skus": 10,
    "prices": 10,
    "parser": 10,
}


@dataclass(frozen=True)
class UploadQuality:
    percent: int
    points: dict[str, float] = field(default_factory=dict)
    deductions: list[str] = field(default_factory=list)


def rate_upload(
    *,
    item_rows: int,
    blank_species: int,
    blank_descriptions: int,
    missing_part_numbers: int,
    missing_prices: int,
    search_options: list[str],
    retail_mismatches: int,
    parser_locked: bool,
) -> UploadQuality:
    if item_rows <= 0:
        return UploadQuality(0, {key: 0 for key in MAX_POINTS}, ["Zero sellable rows"])

    deductions: list[str] = []
    points: dict[str, float] = {}

    options = [str(o).strip() for o in search_options if str(o).strip()]
    if options:
        points["options"] = float(MAX_POINTS["options"])
    else:
        points["options"] = 0.0
        deductions.append("Search Options empty")

    filled_species = max(item_rows - blank_species, 0)
    points["species"] = MAX_POINTS["species"] * filled_species / item_rows
    if blank_species:
        deductions.append(f"{blank_species}/{item_rows} sellable rows missing species")

    filled_desc = max(item_rows - blank_descriptions, 0)
    points["descriptions"] = MAX_POINTS["descriptions"] * filled_desc / item_rows
    if blank_descriptions:
        deductions.append(f"{blank_descriptions}/{item_rows} item descriptions blank")

    filled_sku = max(item_rows - missing_part_numbers, 0)
    points["skus"] = MAX_POINTS["skus"] * filled_sku / item_rows
    if missing_part_numbers:
        deductions.append(f"{missing_part_numbers}/{item_rows} items missing a part number")

    priced = max(item_rows - missing_prices, 0)
    price_pts = MAX_POINTS["prices"] * priced / item_rows
    if retail_mismatches:
        price_pts = 0.0
        deductions.append(f"{retail_mismatches} add-on retail mismatch(es)")
    elif missing_prices:
        deductions.append(f"{missing_prices}/{item_rows} items missing wholesale")
    points["prices"] = price_pts

    if parser_locked:
        points["parser"] = float(MAX_POINTS["parser"])
    else:
        points["parser"] = 0.0
        deductions.append("Named parser not locked")

    percent = int(round(sum(points.values())))
    if deductions:
        percent = min(percent, 99)
    return UploadQuality(max(0, min(100, percent)), points, deductions)


def rate_drop_parse(payload: dict[str, Any]) -> UploadQuality:
    """Score one Drop file from its parse rows (before or after Load)."""
    rows = list(payload.get("rows") or [])
    items = [row for row in rows if str(row.get("line_kind") or "item").strip().lower() != "addon"]
    addons = [row for row in rows if str(row.get("line_kind") or "item").strip().lower() == "addon"]
    options: list[str] = []
    for row in addons:
        label = str(
            row.get("option_key") or row.get("description") or row.get("part_number") or ""
        ).strip()
        if label and not is_wood_column_label(label):
            options.append(label)
    for row in items:
        species = str(row.get("species") or "").strip()
        key = str(row.get("option_key") or "").strip()
        if key and not is_wood_column_label(key):
            options.append(key)
        # Color/fabric tiers live in species and still count as Options captured
        if species and not is_wood_column_label(species):
            if re.search(r"(?i)color|fabric|leather|poly|woodgrain", species):
                options.append(species)

    locked = _importer_is_locked(
        str(payload.get("locked_parser") or payload.get("detected_importer") or "")
    )
    return rate_upload(
        item_rows=len(items),
        blank_species=sum(1 for row in items if not str(row.get("species") or "").strip()),
        blank_descriptions=sum(1 for row in items if _blank_description(row)),
        missing_part_numbers=sum(
            1 for row in items if not str(row.get("part_number") or "").strip()
        ),
        missing_prices=sum(1 for row in items if not _has_price(row.get("base_price"))),
        search_options=options,
        retail_mismatches=0,
        parser_locked=locked,
    )


def _importer_is_locked(importer: str) -> bool:
    return str(importer or "").strip().lower() not in _GENERIC_PARSERS


def _blank_description(row: dict[str, Any]) -> bool:
    desc = str(row.get("description") or "").strip()
    return not desc or bool(_PLACEHOLDER_DESC.fullmatch(desc))


def _has_price(value: Any) -> bool:
    try:
        return value is not None and str(value).strip() != "" and float(value) == float(value)
    except (TypeError, ValueError):
        return False


def _parser_locked_for_builder(vendor: str, *, profile_root: Optional[Any] = None) -> bool:
    from backend.builder_profiles import load_builder_profile

    profile = (
        load_builder_profile(vendor, root=profile_root)
        if profile_root
        else load_builder_profile(vendor)
    )
    parser = (profile or {}).get("parser") or {}
    importer = str(parser.get("importer") or "").strip()
    return bool(parser.get("locked")) and _importer_is_locked(importer)


def _catalog_facts(service: Any, vendor: str) -> dict[str, Any]:
    import sqlite3

    from backend.pricing import catalog_retail

    conn = sqlite3.connect(service.path)
    conn.row_factory = sqlite3.Row
    try:
        items = conn.execute(
            """
            SELECT part_number, description, species, base_price
            FROM pricebook
            WHERE vendor=? AND lower(COALESCE(line_kind, 'item')) != 'addon'
            """,
            (vendor,),
        ).fetchall()
        addons = conn.execute(
            """
            SELECT option_key, description, part_number, base_price,
                   adjusted_price, multiplier
            FROM pricebook
            WHERE vendor=? AND lower(COALESCE(line_kind, 'item')) = 'addon'
            """,
            (vendor,),
        ).fetchall()
    finally:
        conn.close()

    search_options = list(service.list_option_keys(vendor) or [])
    mismatches = 0
    for row in addons:
        label = str(row["option_key"] or row["description"] or row["part_number"] or "")
        try:
            wholesale = float(row["base_price"] or 0)
        except (TypeError, ValueError):
            wholesale = 0.0
        if wholesale <= 0:
            continue
        expected = catalog_retail(
            row["base_price"],
            row["multiplier"],
            line_kind="addon",
            option_key=label,
        )
        try:
            stored = float(row["adjusted_price"] or 0)
        except (TypeError, ValueError):
            stored = 0.0
        if expected is not None and abs(float(expected) - stored) > 0.01:
            mismatches += 1

    root = getattr(service, "_builder_profile_root", None)
    return {
        "item_rows": len(items),
        "blank_species": sum(1 for row in items if not str(row["species"] or "").strip()),
        "blank_descriptions": sum(
            1 for row in items if _blank_description({"description": row["description"]})
        ),
        "missing_part_numbers": sum(
            1 for row in items if not str(row["part_number"] or "").strip()
        ),
        "missing_prices": sum(1 for row in items if not _has_price(row["base_price"])),
        "search_options": search_options,
        "retail_mismatches": mismatches,
        "parser_locked": _parser_locked_for_builder(vendor, profile_root=root),
    }


def rate_builder(service: Any, vendor: str) -> UploadQuality:
    return rate_upload(**_catalog_facts(service, vendor))


def list_upload_quality(service: Any) -> list[dict[str, Any]]:
    vendors = list(service.list_vendors() or [])
    out: list[dict[str, Any]] = []
    for vendor in vendors:
        rating = rate_builder(service, vendor)
        out.append(
            {
                "vendor": vendor,
                "percent": rating.percent,
                "deductions": list(rating.deductions),
            }
        )
    return out
