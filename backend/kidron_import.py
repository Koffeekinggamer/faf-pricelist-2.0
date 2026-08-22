"""Locked reader for Kidron Woodcraft's visible Prices sheet.

The left price bands are dealer retail formulas. The right bands are the
factory wholesale finished/unfinished twins used by Search.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

_SKU = re.compile(r"^(#[A-Za-z0-9][A-Za-z0-9./-]*)\s*(.*)$")
# Timberline writes "Deluxe Dresser        #1974" in one cell.
_TRAILING_SKU = re.compile(
    r"^(?P<desc>\S.*?)\s+(?P<sku>#[A-Za-z0-9][A-Za-z0-9./-]*(?:\s+[A-Z&/]{1,4})?)$"
)
# First wholesale column in the two-block books (Solo Galaxy).
_WHOLESALE_COL = 8
# Footer prose sits in the SKU column with no prices; it is not a collection.
_FOOTER_PROSE = re.compile(
    r"(?i)^\*|available\b|compliant\b|^note[s]?\b|^all\s+other\b|^prices?\b"
)


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _money(value: Any) -> Optional[float]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _species(value: Any) -> str:
    parts = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"[\n,]+", str(value or ""))
        if part.strip()
    ]
    combined: list[str] = []
    for part in parts:
        if part.casefold() == "cherry" and combined and combined[-1].casefold() == "rustic":
            combined[-1] = "Rustic Cherry"
        else:
            combined.append(part)
    parts = combined
    return " / ".join(parts)


def _collection_from_filename(filename: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", str(filename or "").strip())
    stem = re.sub(r"[_\-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _pairs_with_finish_twins(
    price_pairs: list[tuple[int, int, str]],
    data_rows: list,
) -> list[tuple[int, int, str]]:
    """Drop bands that price Fin only while other bands carry both twins.

    Solo Galaxy's dealer retail formulas sit under a Fin/Unfin header with the
    Unfin column left blank. The factory wholesale bands always fill both.
    """
    twinned = [
        pair
        for pair in price_pairs
        if any(
            _money(row[pair[1]]) for row in data_rows if pair[1] < len(row)
        )
    ]
    return twinned if twinned and len(twinned) != len(price_pairs) else price_pairs


def _one_block_per_species(
    price_pairs: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """Collapse a repeated species block to the right-hand (wholesale) one.

    Kidron prints two blocks. When both name the same species the left one is
    either a dealer retail formula (Solo Galaxy) or a straight repeat
    (Entertainment Center), so the right block is the factory wholesale. When
    the blocks name different species (Timberline) both are real wood tiers.
    """
    left = [pair for pair in price_pairs if pair[0] < _WHOLESALE_COL]
    right = [pair for pair in price_pairs if pair[0] >= _WHOLESALE_COL]
    if not left or not right:
        return price_pairs
    if {pair[2] for pair in left} == {pair[2] for pair in right}:
        return right
    return price_pairs


def _parse_prices(raw: pd.DataFrame, vendor: str) -> list[dict[str, Any]]:
    rows = raw.values.tolist()
    header_index = None
    price_pairs: list[tuple[int, int, str]] = []
    collection = ""

    for row_index, row in enumerate(rows):
        for col in range(max(0, len(row) - 1)):
            if _text(row[col]).casefold() != "fin":
                continue
            if _text(row[col + 1]).casefold() != "unfin":
                continue
            species = _species(rows[row_index - 1][col] if row_index else "")
            if species:
                price_pairs.append((col, col + 1, species))
        if price_pairs:
            header_index = row_index
            banner = _text(row[0])
            collection = "" if _FOOTER_PROSE.search(banner) else banner
            break

    if header_index is not None:
        price_pairs = _one_block_per_species(
            _pairs_with_finish_twins(price_pairs, rows[header_index + 1 :])
        )

    if header_index is None:
        return []

    out: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        first = _text(row[0] if row else None)
        match = _SKU.match(first)
        trailing = None if match else _TRAILING_SKU.match(first)
        if trailing:
            part_number = trailing.group("sku").strip()
            description = trailing.group("desc").strip() or part_number
            out.extend(
                _price_rows(row, price_pairs, vendor, collection, part_number, description)
            )
            continue
        if not match:
            if (
                first
                and not _FOOTER_PROSE.search(first)
                and not any(_money(row[col]) for col, _, _ in price_pairs)
            ):
                collection = first
            continue
        part_number, description = match.groups()
        description = description.strip() or part_number
        out.extend(
            _price_rows(row, price_pairs, vendor, collection, part_number, description)
        )
    return out


def _parse_finished_configurations(
    raw: pd.DataFrame,
    vendor: str,
    collection: str,
) -> list[dict[str, Any]]:
    """Grand Isle: finished-only sizes priced with and without cowhide."""
    rows = raw.values.tolist()
    header_index: Optional[int] = None
    columns: list[tuple[int, str]] = []
    for row_index, row in enumerate(rows):
        fin_columns = [
            col for col, value in enumerate(row) if _text(value).casefold() == "fin"
        ]
        if len(fin_columns) < 2 or row_index == 0:
            continue
        for col in fin_columns:
            label = _text(rows[row_index - 1][col])
            if label:
                columns.append((col, label))
        if columns:
            header_index = row_index
            break
    if header_index is None:
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()
    for row in rows[header_index + 1 :]:
        size = _text(row[0] if row else None)
        if not re.fullmatch(r"(?i)queen\s*&\s*full|king", size):
            continue
        for col, configuration in columns:
            price = _money(row[col] if col < len(row) else None)
            if price is None:
                continue
            key = (size.casefold(), configuration.casefold(), price)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "vendor": vendor,
                    "collection": collection,
                    "part_number": None,
                    "description": f"{size} — {configuration}",
                    "species": None,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return out


def _price_rows(
    row: list,
    price_pairs: list[tuple[int, int, str]],
    vendor: str,
    collection: str,
    part_number: str,
    description: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finished_col, unfinished_col, species in price_pairs:
        for col, finish_state in (
            (finished_col, "finished"),
            (unfinished_col, "unfinished"),
        ):
            price = _money(row[col] if col < len(row) else None)
            if price is None:
                continue
            out.append(
                {
                    "vendor": vendor,
                    "collection": collection,
                    "part_number": part_number,
                    "description": description,
                    "species": species,
                    "finish_state": finish_state,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return out


def import_kidron_workbook(
    data: bytes,
    *,
    vendor: str = "Kidron Woodcraft",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    views = read_all_sheets(data)
    names = [view.name for view in views]
    tried: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for view in views:
        if sheet_filter and view.name not in sheet_filter:
            continue
        # Kidron ships one collection per file, and the tab is named Prices,
        # Pricing, or Sheet1. The Fin/Unfin header decides, not the tab name.
        parsed: list[dict[str, Any]] = []
        if view.raw is not None and view.role in {"catalog", "cover"}:
            parsed = _parse_prices(view.raw, vendor)
            if not parsed:
                parsed = _parse_finished_configurations(
                    view.raw,
                    vendor,
                    _collection_from_filename(filename),
                )
        tried.append({"sheet": view.name, "rows": len(parsed)})
        records.extend(parsed)

    frame = pd.DataFrame(records)
    # One file is one Kidron collection (Harbor, Flint Ridge, Urban Retreat),
    # so the book name names the group when the sheet has no banner.
    fallback = default_collection or _collection_from_filename(filename)
    if not frame.empty and fallback:
        frame["collection"] = frame["collection"].replace("", fallback)
    result = WorkbookImportResult(
        sheets_tried=tried,
        long_df=frame,
        detected_markup=None,
        sheet_names=names,
        notes="Kidron visible wholesale finished/unfinished bands",
        expected_option_lines=0,
    )
    return tag_import_result(result, "kidron_woodcraft")
