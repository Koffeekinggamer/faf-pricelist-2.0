"""Artisan Chairs (AC_ pricelist) — Wholesale unfinished/finished matrix + Options."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from wide_import import WorkbookImportResult, _to_float, looks_like_species_header


def looks_like_artisan_chairs(
    filename: str = "", sheet_names: Optional[list[str]] = None, data: Optional[bytes] = None
) -> bool:
    """AC_<year>_Pricelist books: Wholesale + Retail with MARKUP.

    Sheet names alone are not enough — LAMB and other factories also ship
    Wholesale + Retail with MARKUP tabs. Filename (or empty filename in
    tests that already know the factory) must look like Artisan Chairs.
    """
    fn = (filename or "").lower()
    if re.search(r"artisan\s*chairs?|(?:^|[^a-z])ac[_\s-](?:20\d{2}|pricelist)", fn):
        return True
    if fn.strip():
        return False
    names = {str(n).strip().lower() for n in (sheet_names or [])}
    return "wholesale" in names and "retail with markup" in names


def artisan_chairs_option_addons(data: bytes, *, vendor: str) -> list[dict]:
    """Read every priced line in Artisan Chairs' Wholesale Options block."""
    try:
        from backend.workbook_sheets import read_sheet

        raw = read_sheet(data, "Wholesale", header=None)
    except (ValueError, OSError):
        return []

    rows: list[dict] = []
    in_options = False
    special_collections: list[str] = []
    for _, series in raw.iterrows():
        cells = ["" if pd.isna(value) else str(value).strip() for value in series.tolist()]
        text = " ".join(value for value in cells if value)
        if not in_options:
            if re.fullmatch(r"(?i)options", text):
                in_options = True
            continue
        if re.fullmatch(r"(?i)miscellaneous", text):
            continue
        if re.search(r"(?i)internet policy", text):
            break

        # AC's labels sit in B; two collection-specific prices are indented in D.
        label = cells[1] if len(cells) > 1 and cells[1] else ""
        indented = cells[3] if len(cells) > 3 and cells[3] else ""
        if label and re.search(r"(?i)priced with heartland standard fabric", label):
            special_collections = [
                part.strip() for part in label.split("-", 1)[0].split(",") if part.strip()
            ]
            continue
        if label:
            special_collections = []
        option = label or indented
        if not option:
            continue

        add_cell = next(
            (value for value in cells if re.search(r"(?i)\bADD\b", value)),
            "",
        )
        no_upcharge = any(re.search(r"(?i)^no upcharge$", value) for value in cells)
        if not add_cell and not no_upcharge:
            continue
        amount = 0.0 if no_upcharge else None
        if not no_upcharge:
            for value in reversed(cells):
                match = re.search(r"\$?\s*(\d+(?:\.\d+)?)", value.replace(",", ""))
                if match and value != option:
                    amount = float(match.group(1))
                    break
        if amount is None:
            continue

        canonical = option
        if special_collections:
            if re.fullmatch(r"(?i)leather", canonical):
                canonical = "Leather Seat"
            for collection in special_collections:
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": "Addons",
                        "part_number": f"{collection} - {canonical}",
                        "description": f"{canonical} adder ({collection})",
                        "option_key": canonical,
                        "species": None,
                        "finish_state": "finished",
                        "base_price": amount,
                        "price_basis": "wholesale",
                        "line_kind": "addon",
                        "notes": "Wholesale Options",
                    }
                )
            continue

        rows.append(
            {
                "vendor": vendor,
                "collection": "Addons",
                "part_number": canonical,
                "description": canonical,
                "option_key": canonical,
                "species": None,
                "finish_state": "finished",
                "base_price": amount,
                "price_basis": "wholesale",
                "line_kind": "addon",
                "notes": (
                    "Wholesale Options · No upcharge" if no_upcharge else "Wholesale Options"
                ),
            }
        )
    return rows


def artisan_chairs_product_rows(data: bytes, *, vendor: str) -> list[dict]:
    """Unpivot the Wholesale Unfinished | Finished species matrix.

    The first collection name (Aberdeen) sits on the species-header row, not on
    its own banner — generic header detection swallowed it and tagged every
    price finished. This pass keeps both finish blocks and that first name.
    """
    try:
        from backend.workbook_sheets import read_sheet

        raw = read_sheet(data, "Wholesale", header=None)
    except (ValueError, OSError):
        return []

    rows: list[dict] = []
    in_matrix = False
    unf_start: Optional[int] = None
    fin_start: Optional[int] = None
    species_unf: list[tuple[int, str]] = []
    species_fin: list[tuple[int, str]] = []
    current_collection: Optional[str] = None

    def _emit(description: str, species: str, finish_state: str, amount: float) -> None:
        rows.append(
            {
                "vendor": vendor,
                "collection": current_collection,
                "part_number": description,
                "description": description,
                "option_key": None,
                "species": species,
                "finish_state": finish_state,
                "base_price": amount,
                "price_basis": "wholesale",
                "line_kind": "item",
                "notes": "Wholesale matrix",
            }
        )

    for _, series in raw.iterrows():
        cells = ["" if pd.isna(value) else str(value).strip() for value in series.tolist()]
        lowered = [cell.lower() for cell in cells]
        if "unfinished" in lowered and "finished" in lowered:
            unf_start = lowered.index("unfinished")
            fin_start = lowered.index("finished")
            in_matrix = True
            continue
        if not in_matrix:
            continue
        if re.search(r"(?i)internet policy", " ".join(cell for cell in cells if cell)):
            break

        wood_cols = [
            idx for idx, cell in enumerate(cells) if cell and looks_like_species_header(cell)
        ]
        if len(wood_cols) >= 4 and unf_start is not None and fin_start is not None:
            if cells and cells[0] and not looks_like_species_header(cells[0]):
                current_collection = cells[0]
            species_unf = [(idx, cells[idx]) for idx in wood_cols if unf_start <= idx < fin_start]
            species_fin = [(idx, cells[idx]) for idx in wood_cols if idx >= fin_start]
            continue

        label = cells[0] if cells else ""
        if not label:
            continue

        def _priced(pairs: list[tuple[int, str]]) -> list[tuple[str, float]]:
            found: list[tuple[str, float]] = []
            for idx, species in pairs:
                if idx >= len(cells):
                    continue
                amount = _to_float(cells[idx])
                if amount is None:
                    continue
                found.append((species, amount))
            return found

        unfinished_prices = _priced(species_unf)
        finished_prices = _priced(species_fin)
        if not unfinished_prices and not finished_prices:
            current_collection = label
            continue
        for species, amount in unfinished_prices:
            _emit(label, species, "unfinished", amount)
        for species, amount in finished_prices:
            _emit(label, species, "finished", amount)
    return rows


def count_artisan_option_lines(data: bytes) -> int:
    """Count priced lines in AC's Options block without building any rows.

    Deliberately independent of ``artisan_chairs_option_addons``: this is the
    "how many should there be" side of the Drop gate, so it must not go dark
    when the row builder does.
    """
    try:
        from backend.workbook_sheets import read_sheet

        raw = read_sheet(data, "Wholesale", header=None)
    except (ValueError, OSError):
        return 0

    count = 0
    in_options = False
    for _, series in raw.iterrows():
        cells = ["" if pd.isna(value) else str(value).strip() for value in series.tolist()]
        text = " ".join(value for value in cells if value)
        if not in_options:
            if re.fullmatch(r"(?i)options", text):
                in_options = True
            continue
        if re.search(r"(?i)internet policy", text):
            break
        if re.search(r"(?i)^no upcharge$", text) or re.search(r"(?i)\bADD\b\s*\$?\s*\d", text):
            count += 1
    return count


def count_priced_option_lines(data: bytes) -> int:
    """Back-compat alias for the Artisan Chairs option-line count."""
    return count_artisan_option_lines(data)


def import_artisan_chairs_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """Artisan Chairs: import Wholesale; view Retail with MARKUP and leave it out."""
    from wide_import import import_workbook

    result = import_workbook(
        data,
        vendor=vendor or "Artisan Chairs",
        default_collection=default_collection,
        sheet_filter=sheet_filter,
        filename=filename,
        force_layout_guess=True,
    )
    result.expected_option_lines = count_artisan_option_lines(data)
    vendor_name = vendor or "Artisan Chairs"
    products = artisan_chairs_product_rows(data, vendor=vendor_name)
    addons = artisan_chairs_option_addons(data, vendor=vendor_name)
    frames = [pd.DataFrame(products)] if products else []
    if addons:
        frames.append(pd.DataFrame(addons))
    if frames:
        result.long_df = pd.concat(frames, ignore_index=True, sort=False)
        result.notes = (
            f"{result.notes} · {len(products)} Wholesale chair rows"
            f"{' · ' + str(len(addons)) + ' Wholesale option rows' if addons else ''}"
        )
    return result
