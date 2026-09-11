"""J. Troyer & Company: Item# / SKU rows exploded across visible wood groups.

The factory book repeats wholesale prices on the right and uses Stain / Two-Tone
blocks on a few designer tabs. Those labels are not part numbers.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_sheet
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

VENDOR = "J. Troyer & Company"
_SKIP_SHEET = re.compile(r"(?i)^(mark\s*-?\s*up|cover|index|title(\s*page)?)$")
_SKU_HEADER = re.compile(r"(?i)^(item\s*#?|sku|product\s*#?|product\s*no\.?)$")
_INSERT = re.compile(r"(?i)^insert$")
_WOOD_TOKEN = re.compile(
    r"(?i)\b(oak|maple|cherry|walnut|hickory|elm|qswo|pswo|wormy|"
    r"rustic|premium|brown\s*maple|hard\s*maple)\b"
)
_SKU = re.compile(r"^(?:#)?(?=[A-Za-z0-9.\-]*\d)[A-Za-z]{0,4}-?[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*$")
_NOT_SKU = re.compile(
    r"(?i)^(stain|two[\s\-]?tone|paint|glaze|wood door|metal wave door|"
    r"slatted door|wood wave door|options?:|note[s]?:|standard|finished|"
    r"unfinished|description|dimensions?|item#?|sku|product #)$"
)
_TYPOS = (
    (re.compile(r"(?i)jickory"), "Hickory"),
    (re.compile(r"(?i)\bbr\.?\s*maple\b"), "Brown Maple"),
    (re.compile(r"(?i)\br[\.\-\s]*qswo\b"), "Rustic QSWO"),
    (re.compile(r"(?i)\br[\.\-\s]*cherry\b"), "Rustic Cherry"),
    (re.compile(r"(?i)\br[\.\-\s]*hickory\b"), "Rustic Hickory"),
    (re.compile(r"(?i)\br[\.\-\s]*walnut\b"), "Rustic Walnut"),
    (re.compile(r"(?i)\br[\.\-\s]*white\b"), "Rustic White Oak"),
    (re.compile(r"(?i)\bsap\s*cherry\b"), "Sap Cherry"),
    (re.compile(r"(?i)\bwor\s*my\b"), "Wormy"),
)


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()


def _price(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = float(v)
    else:
        try:
            n = float(str(v).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    if n <= 1.05 or n > 200_000:
        return None
    return round(n, 2)


def _wood_label(text: str) -> str:
    raw = _cell(text)
    for pat, repl in _TYPOS:
        raw = pat.sub(repl, raw)
    parts = [p.strip() for p in re.split(r"[\n,/]+", raw) if p.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip(" .")
        if not part or _INSERT.match(part):
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(part)
    return " / ".join(cleaned)


def _is_sku(text: str) -> bool:
    s = _cell(text)
    if not s or _NOT_SKU.match(s) or '"' in s or " x " in s.lower():
        return False
    if re.search(r"\.\d{3,}", s):
        return False
    return bool(_SKU.match(s))


def _header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(min(8, len(raw))):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        if any(_SKU_HEADER.match(c) for c in cells) and any(_WOOD_TOKEN.search(c) for c in cells):
            return i
        woodish = sum(1 for c in cells if _WOOD_TOKEN.search(c) and not _SKU_HEADER.match(c))
        if woodish >= 2:
            return i
    return None


def _wood_cols(raw: pd.DataFrame, header_i: int) -> list[tuple[int, str]]:
    seen: set[str] = set()
    out: list[tuple[int, str]] = []
    for j in range(raw.shape[1]):
        label = _wood_label(_cell(raw.iat[header_i, j]))
        if not label or not _WOOD_TOKEN.search(label) or _INSERT.match(label):
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append((j, label))
    return out


def _sku_col(raw: pd.DataFrame, header_i: int) -> int:
    for j in range(raw.shape[1]):
        if _SKU_HEADER.match(_cell(raw.iat[header_i, j])):
            return j
    return 0


def _desc_col(raw: pd.DataFrame, header_i: int, sku_j: int) -> int:
    for j in range(raw.shape[1]):
        if re.search(r"(?i)^description|^name$", _cell(raw.iat[header_i, j])):
            return j
    return sku_j + 1 if sku_j + 1 < raw.shape[1] else sku_j


def _dims_col(raw: pd.DataFrame, header_i: int) -> Optional[int]:
    for j in range(raw.shape[1]):
        if re.search(r"(?i)^dimensions?$|^size$", _cell(raw.iat[header_i, j])):
            return j
    return None


def _parse_matrix(raw: pd.DataFrame, *, collection: str) -> list[dict]:
    header_i = _header_row(raw)
    if header_i is None:
        return _parse_stain_blocks(raw, collection=collection)
    woods = _wood_cols(raw, header_i)
    if not woods:
        return _parse_stain_blocks(raw, collection=collection)
    sku_j = _sku_col(raw, header_i)
    desc_j = _desc_col(raw, header_i, sku_j)
    dims_j = _dims_col(raw, header_i)
    current = collection
    rows: list[dict] = []
    for i in range(header_i + 1, len(raw)):
        sku = _cell(raw.iat[i, sku_j])
        if not _is_sku(sku):
            title = sku or _cell(raw.iat[i, desc_j] if desc_j < raw.shape[1] else "")
            prices = [_price(raw.iat[i, j]) for j, _ in woods]
            if title and not any(prices) and 3 <= len(title) <= 80 and not _NOT_SKU.match(title):
                current = title
            continue
        desc = _cell(raw.iat[i, desc_j]) if desc_j < raw.shape[1] else ""
        dims = _cell(raw.iat[i, dims_j]) if dims_j is not None else ""
        for j, species in woods:
            price = _price(raw.iat[i, j]) if j < raw.shape[1] else None
            if price is None:
                continue
            rows.append(
                {
                    "vendor": VENDOR,
                    "collection": current or None,
                    "part_number": sku,
                    "description": desc or sku,
                    "dimensions": dims or None,
                    "species": species,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return rows


def _parse_stain_blocks(raw: pd.DataFrame, *, collection: str) -> list[dict]:
    """Ambiance / Tempo: 6105 | Stain | price — never store Stain as the SKU."""
    rows: list[dict] = []
    last_desc = ""
    dims = ""
    for i in range(len(raw)):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        joined = " ".join(c for c in cells if c)
        if re.search(r'\d+"\s*[WHwx]', joined) and not any(_is_sku(c) for c in cells):
            dims = next((c for c in cells if '"' in c), dims)
        for j, cell in enumerate(cells):
            if not _is_sku(cell):
                if cell and not _is_sku(cell) and not _price(cell) and 4 <= len(cell) <= 40:
                    last_desc = cell
                continue
            stain_price = None
            for k in range(j + 1, min(j + 4, len(cells))):
                if re.search(r"(?i)^stain$", cells[k]):
                    if k + 1 < raw.shape[1]:
                        stain_price = _price(raw.iat[i, k + 1])
                    break
            if stain_price is None:
                continue
            rows.append(
                {
                    "vendor": VENDOR,
                    "collection": collection or None,
                    "part_number": cell,
                    "description": last_desc or cell,
                    "dimensions": dims or None,
                    "species": None,
                    "finish_state": "finished",
                    "base_price": stain_price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return rows


def import_j_troyer_workbook(
    data: bytes,
    *,
    vendor: str = VENDOR,
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    names = list_excel_sheets(data)
    rows: list[dict] = []
    tried: list[dict] = []
    for name in names:
        if sheet_filter and name not in sheet_filter:
            continue
        if _SKIP_SHEET.match(str(name).strip()) or re.search(r"(?i)option", str(name)):
            tried.append({"sheet": name, "layout": "skip", "rows": 0})
            continue
        raw = read_sheet(data, name, header=None)
        if raw is None or raw.empty:
            continue
        before = len(rows)
        collection = default_collection or str(name).strip()
        rows.extend(_parse_matrix(raw, collection=collection))
        tried.append({"sheet": name, "rows": len(rows) - before})
    out = pd.DataFrame(rows)
    if not out.empty and vendor and vendor != VENDOR:
        out["vendor"] = vendor
    return tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=None,
            sheet_names=names,
            notes=f"{filename}: J. Troyer Item# × wood · {len(out)} rows",
        ),
        "j_troyer_and_company",
        source="saved",
    )
