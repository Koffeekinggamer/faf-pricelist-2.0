"""Frog Pond Furniture: collection-title wood groups over Finished columns.

Visible bedroom and occasional sheets put two wood lists on the title row and
two Finished prices under them. Unfinished is 10% less. Hidden Master / office
backups stay hidden.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

VENDOR = "Frog Pond Furniture"
_WOOD = re.compile(
    r"(?i)\b(oak|maple|cherry|walnut|hickory|elm|qswo|qsw|wormy|"
    r"rustic|sap\s*cherry|brown\s*maple|hard\s*maple|reclaimed|barnwood)\b"
)
_ITEM_HDR = re.compile(r"(?i)^item\s*#?$")
_PRICE_HDR = re.compile(r"(?i)^(finished|painted\s*(?:and|&)\s*glazed)$")
_UNF_NOTE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*%\s*less\s+(?:for\s+)?unfinish")
_SKIP_SHEET = re.compile(
    r"(?i)^(mark\s*-?\s*up|index|cover|title|instructions?|"
    r"drawer\s*cover|occasionals?\s*cover)$"
)
_SKIP_ROW = re.compile(
    r"(?i)^(standard features|options?:|all tables available|"
    r"prices are for|for elm|for painting|for unfinished|"
    r"with regular footboard add|beds with #|double pedestal|"
    r"desks are standard|anything shipped|for custom sizes|"
    r"any size changes|mailing address)$"
)
_SKU = re.compile(r"^(?:#)?(?=[A-Za-z0-9.\-]*\d)[A-Za-z]{0,6}\d+[A-Za-z0-9]*$")
_NOT_SKU = re.compile(
    r"(?i)^(qs|item\s*#?|description|finished|unfinished|h\"?|w\"?|d\"?|"
    r"king|queen|twin|standard|options?:)$"
)
_TYPOS = (
    (re.compile(r"(?i)\brustic\s*qs\b"), "Rustic QSWO"),
    (re.compile(r"(?i)\brustic\s*hi\b"), "Rustic Hickory"),
    (re.compile(r"(?i)\bquartersawn\b"), "QSWO"),
    (re.compile(r"(?i)\bbr\.?\s*maple\b"), "Brown Maple"),
    (re.compile(r"(?i)\bsap\s*cherry\b"), "Sap Cherry"),
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
    if not raw or not _WOOD.search(raw):
        return ""
    if re.search(r"(?i)add\s+\d|10%\s*less|finished|unfinished|item\s*#", raw):
        return ""
    parts = [
        re.sub(r"(?i)^and\s+", "", p).strip(" .")
        for p in re.split(r"[\n,/]+", raw)
        if p.strip(" .")
    ]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not _WOOD.search(part):
            continue
        key = part.lower()
        if key not in seen:
            seen.add(key)
            out.append(part)
    return " / ".join(out)


def _is_sku(text: str) -> bool:
    t = _cell(text)
    if not t or _NOT_SKU.match(t) or _SKIP_ROW.match(t):
        return False
    return bool(_SKU.match(t))


def _item_header_col(raw: pd.DataFrame, i: int) -> Optional[int]:
    for j in range(min(4, raw.shape[1])):
        if _ITEM_HDR.match(_cell(raw.iat[i, j])):
            return j
    return None


def _collection_title(raw: pd.DataFrame, i: int) -> str:
    for j in range(min(3, raw.shape[1])):
        text = _cell(raw.iat[i, j])
        if text and not _ITEM_HDR.match(text) and not _is_sku(text):
            text = re.sub(r"\*\s*quick\s*ship.*$", "", text, flags=re.I).strip(" *")
            if 3 < len(text) < 80 and not _SKIP_ROW.match(text):
                return text
    return ""


def parse_extra_wood_percentages(raw: pd.DataFrame) -> dict[str, float]:
    """Options-tab woods (Rec. Barnwood Oak +30%) belong on the first price column."""
    from backend.standardize import is_wood_column_label, standardize_species

    extras: dict[str, float] = {}
    if raw is None or raw.empty:
        return extras
    for i in range(len(raw)):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        cells = [c for c in cells if c]
        if not cells:
            continue
        joined = " ".join(cells)
        label = re.sub(r"\.{2,}.*$", "", cells[0])
        label = re.sub(r"(?i)\s*add(?:ing)?\s*$", "", label).strip(" .:-")
        label = re.sub(r"(?i)^for\s+", "", label)
        if not is_wood_column_label(label):
            continue
        pct_m = re.search(r"(?i)(\d+(?:\.\d+)?)\s*%", joined)
        if not pct_m:
            continue
        name = standardize_species(label) or label
        extras[name] = float(pct_m.group(1)) / 100.0
    return extras


def _extra_wood_rows(
    *,
    vendor: str,
    collection: Optional[str],
    part: str,
    desc: str,
    dims: Optional[str],
    first_price: float,
    extra_woods: dict[str, float],
    unf_rate: Optional[float],
) -> list[dict]:
    rows: list[dict] = []
    for species, frac in extra_woods.items():
        amount = round(first_price * (1.0 + frac), 2)
        rows.append(
            {
                "vendor": vendor,
                "collection": collection or None,
                "part_number": part,
                "description": desc,
                "dimensions": dims,
                "option_key": None,
                "species": species,
                "finish_state": "finished",
                "base_price": amount,
                "price_basis": "wholesale",
                "line_kind": "item",
            }
        )
        if unf_rate:
            rows.append(
                {
                    "vendor": vendor,
                    "collection": collection or None,
                    "part_number": part,
                    "description": desc,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species,
                    "finish_state": "unfinished",
                    "base_price": round(amount * (1.0 - unf_rate), 2),
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return rows


def parse_frog_pond_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = VENDOR,
    extra_woods: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    collection = ""
    woods_by_col: dict[int, str] = {}
    price_cols: list[tuple[int, str]] = []
    item_col = 0
    desc_col: Optional[int] = None
    dim_cols: dict[str, int] = {}
    unf_rate: Optional[float] = None

    def bind_header(i: int) -> None:
        nonlocal item_col, desc_col, dim_cols, price_cols, woods_by_col
        item_col = _item_header_col(raw, i) or 0
        desc_col = None
        dim_cols = {}
        found_woods: dict[int, str] = {}
        for src_i in (i - 2, i - 1, i):
            if src_i < 0:
                continue
            for j in range(raw.shape[1]):
                lab = _wood_label(raw.iat[src_i, j])
                if lab:
                    found_woods[j] = lab
        if found_woods:
            woods_by_col = found_woods
        finish_row = i
        if not any(_PRICE_HDR.match(_cell(raw.iat[i, j])) for j in range(raw.shape[1])):
            if i > 0 and any(
                _PRICE_HDR.match(_cell(raw.iat[i - 1, j])) for j in range(raw.shape[1])
            ):
                finish_row = i - 1
        bound: list[tuple[int, str]] = []
        carry = ""
        for j in range(raw.shape[1]):
            cell = _cell(raw.iat[finish_row, j])
            if _PRICE_HDR.match(cell):
                sp = woods_by_col.get(j) or carry
                if not sp:
                    for k in range(j, -1, -1):
                        if k in woods_by_col:
                            sp = woods_by_col[k]
                            break
                if sp:
                    carry = sp
                    bound.append((j, sp))
            elif j in woods_by_col:
                carry = woods_by_col[j]
        for j in range(raw.shape[1]):
            lab = _cell(raw.iat[i, j]).lower().replace('"', "")
            if lab in {"description", "desc"}:
                desc_col = j
            else:
                from backend.standardize import dimension_axis

                axis = dimension_axis(raw.iat[i, j])
                if axis:
                    dim_cols[axis] = j
        if bound:
            price_cols = bound

    for i in range(len(raw)):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        joined = " ".join(c for c in cells if c)
        unf_m = _UNF_NOTE.search(joined)
        if unf_m:
            unf_rate = float(unf_m.group(1)) / 100.0
        header_col = _item_header_col(raw, i)
        title = _collection_title(raw, i)
        if (
            header_col is None
            and title
            and not any(_price(raw.iat[i, j]) for j in range(raw.shape[1]))
        ):
            if re.search(r"(?i)collection|mission|office|weston|lincoln", title) or (
                title[0].isupper() and " " in title
            ):
                collection = re.sub(r"^\d+\s+", "", title).strip()
                for j in range(raw.shape[1]):
                    lab = _wood_label(raw.iat[i, j])
                    if lab:
                        woods_by_col[j] = lab
        if header_col is not None:
            bind_header(i)
            continue
        if not price_cols:
            continue
        part = _cell(raw.iat[i, item_col]) if item_col < raw.shape[1] else ""
        if not _is_sku(part):
            # QS column sits left of Item # on Lincoln / Barn Floor
            for j in range(min(3, raw.shape[1])):
                if _is_sku(cells[j]):
                    part = cells[j]
                    break
        if not _is_sku(part) or _SKIP_ROW.match(part) or _SKIP_ROW.match(joined[:40]):
            continue
        if not any(_price(raw.iat[i, j]) for j, _sp in price_cols if j < raw.shape[1]):
            continue
        desc = part
        if desc_col is not None:
            labeled = _cell(raw.iat[i, desc_col])
            if labeled:
                desc = labeled
        dims_parts = []
        for key in ("H", "W", "D", "HB H", "FB H"):
            if key in dim_cols:
                v = raw.iat[i, dim_cols[key]]
                if pd.notna(v) and _cell(v) not in {"0", ""}:
                    dims_parts.append(f'{key}"{_cell(v)}')
        dims = " × ".join(dims_parts) if dims_parts else None
        for j, species in price_cols:
            price = _price(raw.iat[i, j]) if j < raw.shape[1] else None
            if price is None:
                continue
            rows.append(
                {
                    "vendor": vendor,
                    "collection": collection or None,
                    "part_number": part,
                    "description": desc,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
            if unf_rate:
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": collection or None,
                        "part_number": part,
                        "description": desc,
                        "dimensions": dims,
                        "option_key": None,
                        "species": species,
                        "finish_state": "unfinished",
                        "base_price": round(price * (1.0 - unf_rate), 2),
                        "price_basis": "wholesale",
                        "line_kind": "item",
                    }
                )
        if extra_woods and price_cols:
            first_price = (
                _price(raw.iat[i, price_cols[0][0]]) if price_cols[0][0] < raw.shape[1] else None
            )
            if first_price is not None:
                rows.extend(
                    _extra_wood_rows(
                        vendor=vendor,
                        collection=collection,
                        part=part,
                        desc=desc,
                        dims=dims,
                        first_price=first_price,
                        extra_woods=extra_woods,
                        unf_rate=unf_rate,
                    )
                )
    return pd.DataFrame(rows)


def parse_drawer_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = VENDOR,
    extra_woods: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Left-hand drawer tables: size columns + footnote wood groups."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    section = "Drawer Rails"
    sizes: list[tuple[int, str]] = []
    group1 = "Sap Cherry / Oak / Rustic Cherry / Brown Maple"
    group2 = "Elm / Cherry / Hickory / QSWO / Hard Maple"
    for i in range(len(raw)):
        cells = [_cell(raw.iat[i, j]) for j in range(min(7, raw.shape[1]))]
        joined = " ".join(c for c in cells if c)
        if re.search(r"(?i)^dr\d|^df\d|^drawer", cells[0] if cells else ""):
            if cells[0] and not _price(raw.iat[i, 2] if raw.shape[1] > 2 else None):
                section = cells[0]
        if re.search(r"(?i)prices are for", joined) and _WOOD.search(joined):
            lab = _wood_label(joined.split("for", 1)[-1])
            if lab:
                group1 = lab
            continue
        if re.search(r"(?i)for elm|for cherry", joined) and re.search(r"(?i)add\s+30", joined):
            lab = _wood_label(re.sub(r"(?i)for\s+|add\s+30%.*", " ", joined))
            if lab:
                group2 = lab
            continue
        if re.search(r"(?i)\bking\b", joined) and re.search(r"(?i)queen|twin", joined):
            sizes = []
            for j, cell in enumerate(cells):
                if re.search(r"(?i)king", cell):
                    sizes.append((j, "King"))
                elif re.search(r"(?i)queen", cell):
                    sizes.append((j, "Queen & Full"))
                elif re.search(r"(?i)^twin$", cell):
                    sizes.append((j, "Twin"))
            continue
        if _SKIP_ROW.match(cells[0] if cells else "") or re.search(
            r"(?i)for painting|for unfinished|with regular", joined
        ):
            continue
        label = cells[0] if cells else ""
        if not label or not sizes:
            continue
        sku = cells[6] if len(cells) > 6 and _is_sku(cells[6]) else ""
        if not sku:
            m = re.match(r"^(FP\d+|FB\d+|DR\d+\w+)", label.replace(" ", ""))
            sku = m.group(1) if m else ""
        if not sku:
            continue
        for j, size in sizes:
            price = _price(raw.iat[i, j]) if j < raw.shape[1] else None
            if price is None:
                continue
            desc = f"{label} — {size}"
            for species, amount in ((group1, price), (group2, round(price * 1.3, 2))):
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": section,
                        "part_number": sku,
                        "description": desc,
                        "dimensions": size,
                        "option_key": None,
                        "species": species,
                        "finish_state": "finished",
                        "base_price": amount,
                        "price_basis": "wholesale",
                        "line_kind": "item",
                    }
                )
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": section,
                        "part_number": sku,
                        "description": desc,
                        "dimensions": size,
                        "option_key": None,
                        "species": species,
                        "finish_state": "unfinished",
                        "base_price": round(amount * 0.9, 2),
                        "price_basis": "wholesale",
                        "line_kind": "item",
                    }
                )
            if extra_woods:
                rows.extend(
                    _extra_wood_rows(
                        vendor=vendor,
                        collection=section,
                        part=sku,
                        desc=desc,
                        dims=size,
                        first_price=price,
                        extra_woods=extra_woods,
                        unf_rate=0.10,
                    )
                )
    return pd.DataFrame(rows)


def parse_options_sheet(raw: pd.DataFrame, *, vendor: str = VENDOR) -> pd.DataFrame:
    """Options tab: 'Painting add … | 10% to Fin price' and flat $ adders."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for i in range(len(raw)):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if re.fullmatch(r"(?i)options?:?|bed options:?", cells[0]):
            continue
        if re.search(r"(?i)contact frog pond|shipped to finish|custom sizes", cells[0]):
            continue
        joined = " ".join(cells)
        label = re.sub(r"\.{2,}.*$", "", cells[0])
        label = re.sub(r"(?i)\s*add(?:ing)?\s*$", "", label).strip(" .:-")
        label = re.sub(r"(?i)^for\s+", "", label)
        if not label or len(label) < 3:
            continue
        from backend.standardize import is_wood_column_label

        if is_wood_column_label(label):
            continue
        pct_m = re.search(r"(?i)(\d+(?:\.\d+)?)\s*%", joined)
        dollars = None
        for cell in cells[1:]:
            amount = _price(cell)
            if amount is not None and amount <= 400:
                dollars = amount
                break
        if dollars is None:
            inline = re.search(r"(?i)\$?\s*(\d+(?:\.\d+)?)\s*(?:per\s+\w+)?\s*$", cells[0])
            if inline and not pct_m:
                dollars = float(inline.group(1))
        rec: dict = {
            "vendor": vendor,
            "collection": "Addons",
            "part_number": label,
            "description": label,
            "option_key": label,
            "species": None,
            "finish_state": "finished",
            "price_basis": "wholesale",
            "line_kind": "addon",
            "notes": "book options",
        }
        if pct_m:
            rec["base_price"] = None
            rec["addon_pct"] = float(pct_m.group(1))
        elif dollars is not None:
            rec["base_price"] = dollars
            rec["addon_pct"] = None
        else:
            continue
        rows.append(rec)
    return pd.DataFrame(rows)


def import_frog_pond_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    from wide_import import detect_markup_from_workbook

    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or VENDOR
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    views = list(read_all_sheets(data))
    extra_woods: dict[str, float] = {}
    for view in views:
        if view.role == "options":
            extra_woods.update(parse_extra_wood_percentages(view.raw))
    for view in views:
        name = view.name
        if sheet_filter is not None and name not in sheet_filter:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered"})
            continue
        if view.role in {"cover", "markup", "empty", "error"} or _SKIP_SHEET.match(
            str(name).strip()
        ):
            tried.append(
                {
                    "sheet": name,
                    "layout": view.role if view.role != "catalog" else "skip",
                    "rows": 0,
                    "note": view.note or "non-product",
                }
            )
            continue
        if view.role == "options":
            long = parse_options_sheet(view.raw, vendor=vendor_name)
            n = 0 if long is None or long.empty else len(long)
            tried.append({"sheet": name, "layout": "options", "rows": n, "note": "book Options"})
            if n:
                frames.append(long)
            continue
        if re.search(r"(?i)drawer\s*pricelist", str(name)):
            long = parse_drawer_sheet(view.raw, vendor=vendor_name, extra_woods=extra_woods)
            layout = "frog_pond_drawers"
        else:
            long = parse_frog_pond_sheet(view.raw, vendor=vendor_name, extra_woods=extra_woods)
            layout = "frog_pond_wood_groups"
        n = 0 if long is None or long.empty else len(long)
        tried.append(
            {"sheet": name, "layout": layout, "rows": n, "note": "wood groups over Finished"}
        )
        if n:
            frames.append(long)
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=detect_markup_from_workbook(data, names),
            sheet_names=names,
            notes=f"{filename + ': ' if filename else ''}Frog Pond wood-group import · {len(out)} rows",
        ),
        "frog_pond_furniture",
        source="saved",
    )
