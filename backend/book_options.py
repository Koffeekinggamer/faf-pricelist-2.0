"""Size-option pricing and finishes → Search Options (addon rows) for every builder.

Factory books put +10%/+20% size changes, two-tone, glaze, paint, distressing,
and flat $ adders in front matter or Options tabs. Those are Options, not
catalog footnotes. Extract them as line_kind=addon so Search lists them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets

_ADD_PCT_HEADER = re.compile(r"(?i)^\s*ADD\s+(\d+(?:\.\d+)?)\s*%\s*$")
_INLINE_ADD_PCT = re.compile(
    r"(?i)(?:for\s+)?(?P<label>.{3,40}?)\s*[,:\-–]?\s*add(?:ing)?\s+(?P<pct>\d+(?:\.\d+)?)\s*%"
)
_INLINE_ADD_DOLLAR = re.compile(
    r"(?i)(?:for\s+)?(?P<label>.{3,40}?)\s*[,:\-–]?\s*add(?:ing)?\s+\$?\s*(?P<amt>\d+(?:\.\d+)?)"
)
_LABELED_DOLLAR = re.compile(
    r"(?i)^\s*(?:[•\-\*]\s*)?(?:(?P<sku>[A-Z]{2,8}\d+[A-Z]{0,6})[\s\-]+)?(?P<label>[^:$]{3,48}?)\s*:\s*\$?\s*(?P<amt>\d+(?:\.\d+)?)\s*(?:each)?\s*$"
)
_DASH_DOLLAR = re.compile(r"(?i)(?P<label>.{3,40}?)\s*[\-–]\s*add\s+\$?\s*(?P<amt>\d+(?:\.\d+)?)")

_SKIP_LABEL = re.compile(
    r"(?i)^(oak|maple|cherry|walnut|hickory|alder|qswo|standard wood|premium wood|"
    r"description|item number|item\s*#|collection|wholesale|retail|cover|index|"
    r"password|price|to|prices? for the year)$"
)
_JUNK_LABEL = re.compile(r"(?i)password|price list|option\s*:|past due accounts|^terms$|^net\s*30$")
_UNFINISHED_DEDUCT = re.compile(r"(?i)unfinish")
_NO_UPCHARGE = re.compile(r"(?i)no\s+upcharge")
_ADD_ON_BANNER = re.compile(r"(?i)add[\s\-]*on\s+options?")
_OPTIONS_BANNER = re.compile(r"(?i)^options?$")
_FINISH_SECTION = re.compile(
    r"(?i)premium\s+finish|finish(?:ing)?\s+(?:choices|options)|optional\s+finish"
)
_SIZE_UP_TO = re.compile(r"(?i)size\s*changes?|up to\s*10|customized up to")
_SIZE_OVER = re.compile(r"(?i)over\s*10")
_TWO_TONE = re.compile(r"(?i)two[\s\-]*ton")
_DISTRESS = re.compile(r"(?i)^distressing$")
_OIL = re.compile(r"(?i)hand[\s\-]*rubbed\s*oil")
_CATALOG_HDR = re.compile(r"(?i)item\s*(number|#)|standard\s*wood")
_SKUISH = re.compile(r"^[A-Z]{2,6}\d{2,}")
# Real choices the book refuses to price. They belong on the floor as Options
# with no charge, so the salesperson knows to call rather than assume $0.
_QUOTE_ONLY = re.compile(
    r"(?i)\bcall\s+(?:for|us|the\s+(?:office|factory))\b|\bcall\s+for\s+(?:pricing|price|quote)\b"
    r"|\b(?:tbd|t\.b\.d\.?|quote\s+required|price\s+on\s+request|market\s+price)\b"
    r"|\bfax\s+(?:for\s+)?quote\b|\bask\s+for\s+(?:pricing|quote)\b"
)
# A leading catalog code (10-36, #PS2, 110 CSF) means the row prices a piece,
# even when a per-SKU finish markup sits in the same row.
_SKU_CODE = re.compile(r"^#?(?=.*\d)[A-Z0-9]+(?:[-/.][A-Z0-9]+)*(?:\s+[A-Z]{2,8})?$")
_BUILDER_NAMES: Optional[frozenset[str]] = None


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).replace("\n", " ").strip()
    if s.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", s)


def _builder_names() -> frozenset[str]:
    """Canonical builder names, from the reader registry — not a hand-kept list."""
    global _BUILDER_NAMES
    if _BUILDER_NAMES is None:
        try:
            from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

            _BUILDER_NAMES = frozenset(
                entry.vendor.casefold() for entry in DEFAULT_READER_REGISTRY.entries if entry.vendor
            )
        except Exception:
            _BUILDER_NAMES = frozenset()
    return _BUILDER_NAMES


def _is_builder_name(label: str) -> bool:
    """A builder is a factory, never one of its Options."""
    name = (label or "").casefold().strip()
    if not name:
        return False
    return any(name == builder or name.startswith(builder + " ") for builder in _builder_names())


def _norm_label(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip(" -–:•*"))
    s = re.sub(r"(?i)\s*add(?:ing)?\s*$", "", s).strip(" -–:")
    s = re.sub(r"(?i)^for\s+", "", s).strip(" ,;:-–")
    aliases = {
        r"(?i)^painting$": "Paint",
        r"(?i)^locks?\s+on\s+drawers?$": "Drawer lock",
        r"(?i)^two[\s\-]*toning$": "Two-tone",
        r"(?i)^two[\s\-]*tone$": "Two-tone",
        r"(?i)^two[\s\-]*tone staining$": "Two-tone",
        r"(?i)^hand[\s\-]*rubbed\s*oil$": "Hand-rubbed oil",
        r"(?i)^glazing\s*&\s*painting$": "Glaze & paint",
        r"(?i)^paint and glaze$": "Paint and glaze",
        r"(?i)^size changes?$": 'Size change (up to 10")',
        r"(?i)^3 or 60 sheen$": "30 or 60 Sheen",
    }
    for pat, label in aliases.items():
        if re.fullmatch(pat, s):
            return label
    if len(s) > 48:
        s = s[:45].rstrip() + "…"
    return s


def _addon(
    vendor: str,
    label: str,
    *,
    dollars: Optional[float] = None,
    pct: Optional[float] = None,
    notes: str = "",
    quote_only: bool = False,
) -> Optional[dict[str, Any]]:
    name = _norm_label(label)
    if not name or _UNFINISHED_DEDUCT.search(name):
        return None
    # Wood names are valid Options when the book prices a % adder (Walnut +50%).
    if _SKIP_LABEL.fullmatch(name) and pct is None:
        return None
    if _is_builder_name(name):
        return None
    if _JUNK_LABEL.search(name):
        return None
    if name[:1].islower() or name[:1] in {",", '"', "'", "(", ")"}:
        return None
    if dollars is None and pct is None and not quote_only:
        return None
    rec: dict[str, Any] = {
        "vendor": vendor,
        "collection": "Addons",
        "part_number": name,
        "description": name,
        "option_key": name,
        "species": None,
        "finish_state": "finished",
        "price_basis": "wholesale",
        "line_kind": "addon",
        "notes": notes or "book options",
    }
    if dollars is not None:
        rec["base_price"] = float(dollars)
        rec["addon_pct"] = None
    elif pct is not None:
        rec["base_price"] = None
        rec["addon_pct"] = float(pct)
    else:
        rec["base_price"] = None
        rec["addon_pct"] = None
    return rec


def _is_sku_price_row(cells: list[str]) -> bool:
    nums = 0
    sku = False
    for c in cells:
        if _SKUISH.match(c):
            sku = True
        try:
            float(c.replace(",", ""))
            nums += 1
        except ValueError:
            pass
    return sku and nums >= 2


def extract_from_frame(raw: Optional[pd.DataFrame], *, vendor: str) -> list[dict[str, Any]]:
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    out: list[dict[str, Any]] = []
    current_pct: Optional[float] = None
    finish_section = False
    no_upcharge = False
    in_addons = False

    for i in range(len(df)):
        cells = [_cell(df.iat[i, j]) for j in range(df.shape[1])]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if _SKU_CODE.fullmatch(cells[0]):
            continue
        if _is_sku_price_row(cells):
            continue
        joined = " | ".join(cells)

        soft_close = re.search(
            r"(?i)add\s+\$(\d+(?:\.\d+)?)\s*/\s*drawer\s+for\s+side\s+mount"
            r".*?\$(\d+(?:\.\d+)?)\s*/\s*drawer\s+for\s+undermount",
            joined,
        )
        if soft_close:
            for label, amount in (
                ("Side Mount Soft Close Slides", soft_close.group(1)),
                ("Undermount Soft Close Slides", soft_close.group(2)),
            ):
                rec = _addon(
                    vendor,
                    label,
                    dollars=float(amount),
                    notes="per drawer from visible source note",
                )
                if rec:
                    out.append(rec)

        # Visible option tables often put the label in one cell and the charge
        # in the next (or repeat the same amount across wood columns).
        label_cell = next(
            (
                cell
                for cell in cells
                if not re.fullmatch(r"[$]?\s*-?\d+(?:\.\d+)?%?", cell)
                and not re.fullmatch(r"(?i)add\s+\d+(?:\.\d+)?%", cell)
                and not re.fullmatch(r"(?i)\$?\d+(?:\.\d+)?\s+less", cell)
                and not _NO_UPCHARGE.fullmatch(cell)
            ),
            "",
        )
        row_label = re.sub(r"(?i)^option\s*:\s*", "", label_cell)
        row_label = re.sub(r"(?i)[,\s]+add\s*$", "", row_label).strip()
        explicit_pct = re.search(r"(?i)\badd\s+(\d+(?:\.\d+)?)\s*%", joined)
        less = re.search(r"(?i)\$?\s*(\d+(?:\.\d+)?)\s+less\b", joined)
        numeric = []
        for cell in cells:
            try:
                numeric.append(float(cell.replace("$", "").replace(",", "")))
            except ValueError:
                pass
        row_rec = None
        if row_label and _QUOTE_ONLY.search(joined) and not explicit_pct:
            row_rec = _addon(
                vendor,
                row_label,
                quote_only=True,
                notes="quote required — factory does not publish a price",
            )
        elif row_label and explicit_pct:
            row_rec = _addon(
                vendor,
                row_label,
                pct=float(explicit_pct.group(1)),
                notes="percent option from visible row",
            )
        elif row_label and less:
            row_rec = _addon(
                vendor,
                row_label,
                dollars=-float(less.group(1)),
                notes="deduction from visible row",
            )
        elif row_label and _NO_UPCHARGE.search(joined):
            row_rec = _addon(
                vendor,
                row_label,
                dollars=0,
                notes="no upcharge from visible row",
            )
        elif (
            row_label
            and numeric
            and 0 < numeric[0] <= 2
            and (
                finish_section
                or in_addons
                or re.search(r"(?i)paint|glaze|two[\s-]?tone|color|sheen", row_label)
            )
        ):
            row_rec = _addon(
                vendor,
                row_label,
                pct=numeric[0] * 100,
                notes="formatted percent option from visible row",
            )
        elif (
            row_label
            and numeric
            and re.search(r"(?i)\b(?:option|upgrade|add)\b", label_cell)
            and len({round(value, 4) for value in numeric if value > 0}) == 1
        ):
            row_rec = _addon(
                vendor,
                row_label,
                dollars=numeric[0],
                notes="flat option from visible row",
            )
        if row_rec:
            out.append(row_rec)

        if _NO_UPCHARGE.search(joined):
            no_upcharge = True
            current_pct = None
            continue
        if _ADD_ON_BANNER.search(joined) or any(_OPTIONS_BANNER.fullmatch(cell) for cell in cells):
            in_addons = True
            no_upcharge = False
        if _FINISH_SECTION.search(joined):
            finish_section = True
            no_upcharge = False

        hdr = None
        for c in cells:
            m = _ADD_PCT_HEADER.match(c)
            if m:
                hdr = m
                break
        if hdr:
            current_pct = float(hdr.group(1))
            no_upcharge = False
            continue

        if any(_CATALOG_HDR.search(c) for c in cells) and any(
            re.search(r"(?i)premium\s*wood|standard\s*wood|item", c) for c in cells
        ):
            finish_section = False
            current_pct = None
            in_addons = False
            continue

        for c in cells:
            if _UNFINISHED_DEDUCT.search(c) and re.search(r"(?i)deduct|less|%", c):
                continue

            labeled = _LABELED_DOLLAR.match(c) or _DASH_DOLLAR.search(c)
            if labeled:
                rec = _addon(
                    vendor,
                    labeled.group("label"),
                    dollars=float(labeled.group("amt")),
                    notes="flat add-on",
                )
                if rec:
                    out.append(rec)
                continue

            inline_p = _INLINE_ADD_PCT.search(c)
            if inline_p:
                rec = _addon(
                    vendor,
                    inline_p.group("label"),
                    pct=float(inline_p.group("pct")),
                    notes="percent option",
                )
                if rec:
                    out.append(rec)
                continue

            inline_d = _INLINE_ADD_DOLLAR.search(c)
            if inline_d and "%" not in c:
                rec = _addon(
                    vendor,
                    inline_d.group("label"),
                    dollars=float(inline_d.group("amt")),
                    notes="flat add-on",
                )
                if rec:
                    out.append(rec)
                continue

            if no_upcharge and not in_addons:
                continue

            if current_pct is not None:
                if _SIZE_OVER.search(c) or (
                    current_pct >= 15 and _SIZE_OVER.search(joined) and _SIZE_UP_TO.search(c)
                ):
                    rec = _addon(
                        vendor,
                        'Size change (over 10")',
                        pct=current_pct,
                        notes="size option",
                    )
                    if rec:
                        out.append(rec)
                    continue
                if _SIZE_UP_TO.search(c):
                    rec = _addon(
                        vendor,
                        'Size change (up to 10")',
                        pct=current_pct,
                        notes="size option",
                    )
                    if rec:
                        out.append(rec)
                    continue
                if _TWO_TONE.search(c):
                    rec = _addon(vendor, "Two-tone", pct=current_pct, notes="finish option")
                    if rec:
                        out.append(rec)
                    continue
                if finish_section and _DISTRESS.search(c):
                    rec = _addon(vendor, "Distressing", pct=current_pct, notes="finish option")
                    if rec:
                        out.append(rec)
                    continue
                if finish_section and _OIL.search(c):
                    rec = _addon(vendor, "Hand-rubbed oil", pct=current_pct, notes="finish option")
                    if rec:
                        out.append(rec)
                    continue

    return _dedupe(out)


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("option_key") or "").strip().lower()
        if not key:
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = row
            continue
        if prev.get("base_price") is None and row.get("base_price") is not None:
            seen[key] = row
        elif prev.get("addon_pct") is None and row.get("addon_pct") is not None:
            seen[key] = row
    return list(seen.values())


def extract_book_options(data: bytes, *, vendor: str = "") -> list[dict[str, Any]]:
    """Pull size-option % and finish/flat adders from every tab."""
    rows: list[dict[str, Any]] = []
    try:
        views = read_all_sheets(data)
    except Exception:
        return []
    for view in views:
        if view.role in {"cover", "markup", "empty", "error"}:
            continue
        rows.extend(extract_from_frame(view.raw, vendor=vendor))
    return _dedupe(rows)


def merge_book_options(result: Any, data: bytes, *, vendor: str = "") -> Any:
    extra = extract_book_options(data, vendor=vendor)
    if not extra:
        return result
    df = result.long_df
    existing = set()
    if df is not None and not df.empty and "option_key" in df.columns:
        existing = {str(x).strip().lower() for x in df["option_key"].dropna() if str(x).strip()}
    new = [r for r in extra if r["option_key"].lower() not in existing]
    if not new:
        return result
    add = pd.DataFrame(new)
    if df is None or df.empty:
        result.long_df = add
    else:
        result.long_df = pd.concat([df, add], ignore_index=True)
    return result
