"""LuxHome Seating — AJ's upholstery brand, priced by fabric grade.

The book ships inside AJ's Viztech download folder and prints AJ's template:

* **Seating** — four fabric-grade price columns (``Standard``, ``Premium``,
  ``Ultra Leather``, ``Genuine Leather``) with an OPTIONS band to their right
  (motorized mechanism, battery pack, foam backs, nail heads, wood trim).
* **Pillows** — one ``PRICE`` column with the grade printed down the rows.

Two reference charts sit past the OPTIONS band — fabric yardage and leather
square footage. ``6 yd`` and ``110 sq.ft.`` read like numbers and are not money,
so every price column is named by its header rather than found by scanning.

The grade is an Option, never a species: upholstery is priced by fabric, and the
floor filters Wood by wood. Sections are named by the banner the book prints
above each band, which only sometimes contains the word "Collection".

The OPTIONS header row and the grade header row are printed one above the other.
A band is only complete once the grade row arrives, so option columns seen just
above it belong to that band and are dropped if no grade row follows.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

FABRIC_GRADE_RE = re.compile(
    r"(?i)^(standard|premium|ultra\s*leather|genuine\s*leather|leather|com)$"
)
# SKUs print as 21 HRR, 1114-EL, FRF22, S-CRN, 5101 RM-KA.
_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-/.]*(?: [A-Z0-9\-/.]+)*$")
_PRICE_HEADER_RE = re.compile(r"(?i)^price$")
# Reference lookups that carry a measurement, never money.
_CHART_RE = re.compile(r"(?i)yardage|sq\.?\s*footage|chart|c\.?o\.?m\.?\s*chart")
_OPTION_HEADER_RE = re.compile(r"(?i)\badd\b|nail\s*heads|wood\s*trim")
_CONNECTOR = frozenset({"of", "and", "the", "or", "w/", "&", "with", "in", "on"})
_PAGE_FURNITURE_RE = re.compile(
    r"(?i)wholesale|warranty|topeka|effective|email|fax|phone|heartland|please\s+note"
    r"|unavailable|password|username|log\s+onto|download|catalog|pricelist|terms"
    r"|net\s*30|customers?\s+own\s+material|luxhome|aj'?s"
)

# Nicer floor wording for the charges the book abbreviates.
_OPTION_NAMES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)motorized\s+mechanism"), "Motorized Mechanism"),
    (re.compile(r"(?i)recharg\w*\s+battery"), "Rechargable Battery Pack"),
    (re.compile(r"(?i)optional\s+foam\s+backs?"), "Optional Foam Backs"),
    (re.compile(r"(?i)nail\s*heads"), "Nail Heads"),
    (re.compile(r"(?i)wood\s*trim"), "Wood Trim"),
)


def looks_like_luxhome(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    """The LuxHome book only. AJ's own pricelist has its own reader."""
    name = (filename or "").lower().replace("_", " ")
    if "luxhome" in name or "lux home" in name:
        return True
    return any("luxhome" in str(sheet).lower() for sheet in (sheet_names or []))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _price(value: Any, *, allow_zero: bool = False) -> Optional[float]:
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
    if math.isnan(number) or number < 0 or (number == 0 and not allow_zero):
        return None
    return round(number, 2)


def _grade_label(header: str) -> str:
    text = _text(header)
    low = text.lower()
    if "ultra" in low:
        return "Ultra Leather"
    if "genuine" in low:
        return "Genuine Leather"
    if low == "leather":
        return "Genuine Leather"
    if low == "com":
        return "COM"
    return text.title()


def _option_label(header: str) -> str:
    text = _text(header)
    for pattern, label in _OPTION_NAMES:
        if pattern.search(text):
            return label
    cleaned = re.sub(r"(?i)\badd\b", "", text).strip(" -:")
    return cleaned.title() if cleaned.isupper() else cleaned


def _banner(cells: list[Any]) -> Optional[str]:
    """The section title a band is printed under, or None.

    A banner stands alone in the SKU or the band column — descriptions live in
    the column between them, and sectional names there read exactly like a
    banner. Every word is capitalised, so prose footnotes stay out.
    """
    filled = [(index, _text(cell)) for index, cell in enumerate(cells[:7]) if _text(cell)]
    if len(filled) != 1:
        return None
    index, text = filled[0]
    if index not in (0, 2) or not 3 <= len(text) <= 60:
        return None
    if _PAGE_FURNITURE_RE.search(text) or FABRIC_GRADE_RE.match(text):
        return None
    words = text.split()
    if not any(word[:1].isalpha() for word in words):
        return None
    for word in words:
        if word.lower() in _CONNECTOR:
            continue
        if word.strip("()").isdigit():
            return None
        if not word[:1].isupper():
            return None
    return text if any(c.islower() for c in text) else text.title()


class _Band:
    """Column map for one printed section of the book."""

    def __init__(self) -> None:
        self.grades: dict[int, str] = {}
        self.options: dict[int, str] = {}
        self.accessory_price: Optional[int] = None
        self.collection: Optional[str] = None

    @property
    def live(self) -> bool:
        return bool(self.grades or self.accessory_price is not None)


def _read_options_header(cells: list[Any]) -> Optional[dict[int, str]]:
    """Option columns from the row printed above the grade row."""
    found: dict[int, str] = {}
    for index, cell in enumerate(cells):
        header = _text(cell)
        if not header or index < 3 or _CHART_RE.search(header):
            continue
        if FABRIC_GRADE_RE.match(header):
            return None
        if _OPTION_HEADER_RE.search(header):
            label = _option_label(header)
            if label:
                found[index] = label
    return found or None


def _read_grade_header(cells: list[Any]) -> Optional[dict[int, str]]:
    found: dict[int, str] = {}
    for index, cell in enumerate(cells):
        header = _text(cell)
        if not header or index < 2 or _CHART_RE.search(header):
            continue
        if FABRIC_GRADE_RE.match(header):
            found[index] = _grade_label(header)
    return found if len(found) >= 2 else None


def _accessory_price_column(cells: list[Any]) -> Optional[int]:
    for index, cell in enumerate(cells):
        if _PRICE_HEADER_RE.match(_text(cell)):
            return index
    return None


def _sku(value: Any) -> str:
    text = _text(value)
    if not text or len(text) > 22 or re.search(r"[a-z]", text):
        return ""
    return text if _SKU_RE.match(text) else ""


def _row(
    *,
    vendor: str,
    collection: Optional[str],
    part: str,
    description: str,
    option_key: Optional[str],
    price: Optional[float],
    line_kind: str,
) -> dict:
    return {
        "vendor": vendor,
        "collection": collection,
        "part_number": part,
        "description": description or part,
        "dimensions": None,
        "option_key": option_key,
        "species": None,
        "species_tier": None,
        "finish_state": "finished",
        "base_price": price,
        "price_basis": "wholesale",
        "unit": None,
        "notes": None,
        "line_kind": line_kind,
    }


def _parse_sheet(raw: pd.DataFrame, *, vendor: str) -> list[dict]:
    rows: list[dict] = []
    band = _Band()
    collection: Optional[str] = None
    pending_options: dict[int, str] = {}
    seen_options: set[str] = set()

    for position in range(len(raw)):
        cells = raw.iloc[position].tolist()

        banner = _banner(cells)
        if banner is not None:
            collection = banner
            band = _Band()
            pending_options = {}
            continue

        grades = _read_grade_header(cells)
        if grades is not None:
            band = _Band()
            band.grades = grades
            band.options = pending_options
            band.collection = collection
            pending_options = {}
            continue

        options = _read_options_header(cells)
        if options is not None:
            pending_options = options
            continue

        price_col = _accessory_price_column(cells)
        if price_col is not None:
            band = _Band()
            band.accessory_price = price_col
            band.collection = collection
            pending_options = {}
            continue

        if not band.live:
            continue

        part = _sku(cells[0] if cells else None)
        if not part:
            continue
        description = _text(cells[1]) if len(cells) > 1 else ""
        if len(description) < 2:
            continue

        def amount(index: Optional[int], *, allow_zero: bool = False) -> Optional[float]:
            if index is None or index >= len(cells):
                return None
            return _price(cells[index], allow_zero=allow_zero)

        if band.accessory_price is not None:
            grade = _text(cells[2]) if len(cells) > 2 else ""
            charge = amount(band.accessory_price)
            if charge is not None:
                rows.append(
                    _row(
                        vendor=vendor,
                        collection=band.collection,
                        part=part,
                        description=description,
                        option_key=_grade_label(grade) if FABRIC_GRADE_RE.match(grade) else None,
                        price=charge,
                        line_kind="item",
                    )
                )
            continue

        for index, grade in band.grades.items():
            charge = amount(index)
            if charge is None:
                continue
            rows.append(
                _row(
                    vendor=vendor,
                    collection=band.collection,
                    part=part,
                    description=description,
                    option_key=grade,
                    price=charge,
                    line_kind="item",
                )
            )

        # Option charges are per SKU, not per fabric grade.
        for index, label in band.options.items():
            charge = amount(index, allow_zero=True)
            if charge is None:
                continue
            key = f"{part}|{label}"
            if key in seen_options:
                continue
            seen_options.add(key)
            rows.append(
                _row(
                    vendor=vendor,
                    collection=band.collection,
                    part=part,
                    description=description,
                    option_key=label,
                    price=charge,
                    line_kind="addon",
                )
            )

    return rows


def import_luxhome_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    vendor_name = (vendor or "").strip() or "AJ's Furniture"
    rows: list[dict] = []
    tried: list[dict] = []
    views = read_all_sheets(data)
    names = [str(view.name) for view in views]

    for view in views:
        if sheet_filter and view.name not in sheet_filter:
            continue
        if view.raw is None or view.raw.empty:
            continue
        parsed = _parse_sheet(view.raw, vendor=vendor_name)
        tried.append(
            {
                "sheet": view.name,
                "layout": "luxhome_fabric_grades",
                "rows": len(parsed),
                "note": "Standard / Premium / Ultra Leather / Genuine Leather + OPTIONS",
            }
        )
        rows.extend(parsed)

    long_df = pd.DataFrame(rows)
    option_lines = 0
    if not long_df.empty:
        if default_collection:
            long_df["collection"] = long_df["collection"].fillna(default_collection)
        option_lines = int((long_df["line_kind"] == "addon").sum())

    result = WorkbookImportResult(
        sheets_tried=tried,
        long_df=long_df,
        detected_markup=None,
        sheet_names=names,
        notes="LuxHome fabric grades + OPTIONS band",
        expected_option_lines=option_lines,
    )
    return tag_import_result(result, "luxhome")
