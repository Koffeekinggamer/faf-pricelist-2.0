"""AJ's Furniture — fabric tier, wood price columns, and priced OPTIONS bands.

Only the ``... Wholesale MARKUP`` tab is visible; the plain ``Wholesale`` tab is
hidden and stays that way. The visible tab carries the same prices, so nothing
is lost by reading it.

The book prints four band shapes down one page:

* **Seating** — ``FABRIC`` over the tier column, wood prices across the middle,
  and an OPTIONS band on the right (optional springs, motorized mechanism,
  rechargable battery pack, replacement cushions).
* **Occasional tables** — same wood columns, no fabric tier, ``LIFT TOP ADD``.
* **Custom finish** — ``ID # | Product Name | All Woods``, one upcharge per SKU.
* **Accessories** — pillows and arm pads, one ``PRICE`` column, priced by tier.

Two books ship together and describe the same SKUs: ``Finished`` and
``Unfinished``. That is the finish twin, not two prices for one row, so the tab
name sets ``finish_state``.

Warranty prose sits in the columns beside the accessory prices and the yardage
chart column reads like a number (``4 yd``, ``85 sq.ft.``). Neither is money, so
every price column is named by its header rather than found by scanning.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

FABRIC_TIER_RE = re.compile(r"(?i)^(standard|premium|leather|com)$")
# SKUs print uppercase: 101 CSC, RS-BT16, 10-16, BN-22, SY-E.
_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-/.]*(?: [A-Z0-9\-/.]+)*$")
_WHOLESALE_SHEET_RE = re.compile(r"(?i)^(un)?finished wholesale(\s+markup)?$")
_WOOD_HEADER_RE = re.compile(
    r"(?i)\b(oak|maple|walnut|cherry|hickory|elm|ash|birch|pine|poplar"
    r"|roughsawn|sawn|all\s+woods)\b"
)
_ADDON_HEADER_RE = re.compile(r"(?i)\badd\b|replacement\s+cushions")
# Reference columns that carry text or a chart lookup, never money.
_IGNORE_HEADER_RE = re.compile(r"(?i)yardage|sq\.?\s*footage|chart|category")
_ID_HEADER_RE = re.compile(r"(?i)^id\s*#?$")
_PRICE_HEADER_RE = re.compile(r"(?i)^price$")
_ALL_WOODS_RE = re.compile(r"(?i)^all\s+woods$")

# Nicer floor wording for the charges the book abbreviates.
_ADDON_NAMES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)optional\s+springs"), "Optional Springs"),
    (re.compile(r"(?i)motorized\s+mechanism"), "Motorized Mechanism"),
    (re.compile(r"(?i)recharg\w*\s+battery"), "Rechargable Battery Pack"),
    (re.compile(r"(?i)replacement\s+cushions"), "Replacement Cushions"),
    (re.compile(r"(?i)lift\s+top"), "Lift Top"),
)
CUSTOM_FINISH_OPTION = "Custom Finish"


def looks_like_ajs(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    """AJ's own book only. LuxHome seating ships beside it and is its own reader."""
    names = [str(name).strip().lower() for name in (sheet_names or [])]
    if any("luxhome" in name for name in names):
        return False
    if "luxhome" in (filename or "").lower().replace("_", " "):
        return False
    return any(_WHOLESALE_SHEET_RE.match(name) for name in names)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _price(value: Any) -> Optional[float]:
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            value = float(cleaned)
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number <= 0:
        return None
    return round(number, 2)


def _species_label(header: str) -> str:
    """One printed wood header into the canonical species string."""
    label = re.sub(r"(?i)\b1\s*/\s*4\s+sawn\s+white\b", "QS White Oak", _text(header))
    out: list[str] = []
    for part in (p.strip() for p in re.split(r"\s*[&/]\s*", label)):
        if not part:
            continue
        if part.isupper() and len(part) > 3:
            part = part.title()
        if part not in out:
            out.append(part)
    return " / ".join(out)


def _addon_label(header: str) -> str:
    text = _text(header)
    for pattern, label in _ADDON_NAMES:
        if pattern.search(text):
            return label
    cleaned = re.sub(r"(?i)\badd\b", "", text).strip(" -:")
    return cleaned.title() if cleaned.isupper() else cleaned


class _Band:
    """Column map for one printed section of the book."""

    def __init__(self) -> None:
        self.species: dict[int, str] = {}
        self.addons: dict[int, str] = {}
        self.accessory_price: Optional[int] = None
        self.custom_finish: Optional[int] = None

    @property
    def live(self) -> bool:
        return bool(
            self.species
            or self.addons
            or self.accessory_price is not None
            or self.custom_finish is not None
        )


def _read_band(cells: list[Any]) -> Optional[_Band]:
    """Name the price columns of a section from its printed header row."""
    text = [_text(cell) for cell in cells]
    band = _Band()

    # Custom finish upcharge table: ID # | Product Name | All Woods
    if text and _ID_HEADER_RE.match(text[0]):
        for index, header in enumerate(text):
            if _ALL_WOODS_RE.match(header):
                band.custom_finish = index
                return band
        return None

    # Accessories: one PRICE column, tiers down the rows.
    for index, header in enumerate(text):
        if _PRICE_HEADER_RE.match(header):
            band.accessory_price = index
            return band

    # Seating and occasional tables: wood columns plus ADD columns.
    for index, header in enumerate(text[2:], start=2):
        if not header or _IGNORE_HEADER_RE.search(header):
            continue
        if _ADDON_HEADER_RE.search(header):
            label = _addon_label(header)
            if label:
                band.addons[index] = label
        elif _WOOD_HEADER_RE.search(header):
            species = _species_label(header)
            if species:
                band.species[index] = species
    return band if len(band.species) >= 2 else None


def _sku(value: Any) -> str:
    text = _text(value)
    if not text or len(text) > 22 or re.search(r"[a-z]", text):
        return ""
    return text if _SKU_RE.match(text) else ""


def _row(
    *,
    vendor: str,
    part: str,
    description: str,
    option_key: Optional[str],
    species: Optional[str],
    finish_state: str,
    price: float,
    line_kind: str,
) -> dict:
    return {
        "vendor": vendor,
        "part_number": part,
        "description": description or part,
        "option_key": option_key,
        "species": species,
        "finish_state": finish_state,
        "base_price": price,
        "price_basis": "wholesale",
        "line_kind": line_kind,
    }


def _parse_sheet(raw: pd.DataFrame, *, vendor: str, finish_state: str) -> list[dict]:
    rows: list[dict] = []
    band = _Band()
    seen_addons: set[str] = set()

    for position in range(len(raw)):
        cells = raw.iloc[position].tolist()
        found = _read_band(cells)
        if found is not None:
            band = found
            continue
        if not band.live:
            continue

        part = _sku(cells[0] if cells else None)
        if not part:
            continue
        description = _text(cells[1]) if len(cells) > 1 else ""
        tier_text = _text(cells[2]) if len(cells) > 2 else ""
        tier: Optional[str] = None
        if FABRIC_TIER_RE.match(tier_text):
            tier = "COM" if tier_text.lower() == "com" else tier_text.title()

        def amount(index: Optional[int]) -> Optional[float]:
            if index is None or index >= len(cells):
                return None
            return _price(cells[index])

        if band.custom_finish is not None:
            charge = amount(band.custom_finish)
            if charge is not None:
                rows.append(
                    _row(
                        vendor=vendor,
                        part=part,
                        description=description,
                        option_key=CUSTOM_FINISH_OPTION,
                        species=None,
                        finish_state=finish_state,
                        price=charge,
                        line_kind="addon",
                    )
                )
            continue

        if band.accessory_price is not None:
            charge = amount(band.accessory_price)
            if charge is not None:
                rows.append(
                    _row(
                        vendor=vendor,
                        part=part,
                        description=description,
                        option_key=tier,
                        species=None,
                        finish_state=finish_state,
                        price=charge,
                        line_kind="addon",
                    )
                )
            continue

        for index, species in band.species.items():
            charge = amount(index)
            if charge is None:
                continue
            rows.append(
                _row(
                    vendor=vendor,
                    part=part,
                    description=description,
                    option_key=tier,
                    species=species,
                    finish_state=finish_state,
                    price=charge,
                    line_kind="item",
                )
            )

        # Option charges are per SKU, not per fabric grade. The book repeats them
        # down all three tier rows, so only the first sighting is kept.
        for index, label in band.addons.items():
            charge = amount(index)
            if charge is None:
                continue
            key = f"{part}|{label}"
            if key in seen_addons:
                continue
            seen_addons.add(key)
            rows.append(
                _row(
                    vendor=vendor,
                    part=part,
                    description=description,
                    option_key=label,
                    species=None,
                    finish_state=finish_state,
                    price=charge,
                    line_kind="addon",
                )
            )
    return rows


def import_ajs_workbook(
    data: bytes,
    *,
    vendor: str = "AJ's Furniture",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    views = read_all_sheets(data)
    names = [view.name for view in views]
    tried: list[dict] = []
    frames: list[dict] = []

    for view in views:
        name = str(view.name)
        if sheet_filter and name not in sheet_filter:
            continue
        if view.raw is None or view.raw.empty:
            tried.append({"sheet": name, "rows": 0, "note": "empty"})
            continue
        finish_state = "unfinished" if "unfinished" in name.lower() else "finished"
        parsed = _parse_sheet(view.raw, vendor=vendor, finish_state=finish_state)
        tried.append({"sheet": name, "rows": len(parsed), "note": finish_state})
        frames.extend(parsed)

    if not frames:
        # Something else shipped in AJ's folder (LuxHome seating, a one-off
        # sheet). Detection still named the builder, so let the generic unpivot
        # read it rather than dropping the file.
        from backend.catalog_readers import import_catalog_workbook, spec_for_vendor

        spec = spec_for_vendor(vendor or "AJ's Furniture")
        if spec is not None:
            return import_catalog_workbook(
                spec,
                data,
                vendor=vendor,
                default_collection=default_collection,
                sheet_filter=sheet_filter,
                filename=filename,
            )

    long_df = pd.DataFrame(frames)
    option_lines = 0
    if not long_df.empty:
        if default_collection:
            long_df["collection"] = default_collection
        option_lines = int((long_df["line_kind"] == "addon").sum())

    result = WorkbookImportResult(
        sheets_tried=tried,
        long_df=long_df,
        detected_markup=None,
        sheet_names=names,
        notes="AJ's fabric tier + wood columns + OPTIONS bands",
        expected_option_lines=option_lines,
    )
    return tag_import_result(result, "ajs_furniture")
