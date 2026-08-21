"""Named readers for catalog builders whose books already parse as generic.

Each in-book factory gets its own parser id, detector, and lock. The reader
reuses the generic unpivot (force_layout_guess) so next year's Drop hits the
same builder without guessing layout or matching Viztech Download_NNNNN names.

Detection is filename/folder tokens plus xlsx XML needles of the factory name.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
from functools import partial
from typing import Optional, Sequence

from backend.builder_reader_registry import ReaderEntry
from backend.workbook_sheets import excel_engine


def _haystack(filename: str = "", sheet_names: Optional[Sequence[str]] = None) -> str:
    parts = [filename or ""]
    parts.extend(str(n) for n in (sheet_names or []))
    s = " ".join(parts).lower().replace("&", " and ").replace("'", " ")
    s = s.replace("_", " ").replace("-", " ").replace("/", " ")
    s = re.sub(r"\b0*39\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _xlsx_mentions(data: Optional[bytes], needles: Sequence[bytes]) -> bool:
    if not data or not needles:
        return False
    if excel_engine(data) != "openpyxl":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                blob = archive.read(name)
                if any(n in blob for n in needles):
                    return True
    except (OSError, ValueError):
        return False
    return False


@dataclass(frozen=True)
class CatalogSpec:
    parser_id: str
    vendor: str
    extra_tokens: tuple[str, ...] = ()
    xml_needles: tuple[bytes, ...] = ()
    # Dotted path to a shape-specific reader. Detection and the lock stay here
    # so the folder name still resolves the builder; only parsing moves out.
    reader: str = ""

    def tokens(self) -> tuple[str, ...]:
        vend = self.vendor.lower().replace("&", " and ").replace("'", " ")
        vend = re.sub(r"[^a-z0-9]+", " ", vend)
        vend = re.sub(r"\s+", " ", vend).strip()
        compact = re.sub(r"[^a-z0-9]+", "", self.vendor.lower())
        out = [vend, compact, *self.extra_tokens]
        return tuple(dict.fromkeys(t.strip().lower() for t in out if len(t.strip()) >= 3))

    def matches(
        self,
        filename: str = "",
        sheet_names: Optional[Sequence[str]] = None,
        data: Optional[bytes] = None,
    ) -> bool:
        hay = _haystack(filename, sheet_names)
        for token in self.tokens():
            if token.replace(" ", "") in hay.replace(" ", "") or token in hay:
                return True
        needles = self.xml_needles or (self.vendor.encode("utf-8"),)
        return _xlsx_mentions(data, needles)


# Builders currently in the master price book that were locked as generic.
# Shape-specific readers (FN, Artisan, Criswell, J&M, Ashery, Patio Kraft,
# LAMB, Windy Acres) stay in builder_reader_registry and are not listed here.
CATALOG_SPECS: tuple[CatalogSpec, ...] = (
    CatalogSpec(
        "ajs_furniture",
        "AJ's Furniture",
        extra_tokens=("ajs furniture", "aj furniture"),
        reader="backend.ajs_import:import_ajs_workbook",
    ),
    CatalogSpec("black_horse_furniture", "Black Horse Furniture"),
    CatalogSpec("brookside_home_furnishings", "Brookside Home Furnishings", extra_tokens=("brookside",)),
    CatalogSpec("crystal_valley_hardwoods", "Crystal Valley Hardwoods", extra_tokens=("cvh",)),
    CatalogSpec("dutch_creek_design", "Dutch Creek Design", extra_tokens=("dcd",)),
    CatalogSpec("ebony_woodworking", "Ebony Woodworking"),
    CatalogSpec("elite_designs", "Elite Designs"),
    CatalogSpec("farmside_wood", "Farmside Wood"),
    CatalogSpec("five_star_tables", "Five Star Tables"),
    CatalogSpec("fredericksburg_furniture", "Fredericksburg Furniture"),
    CatalogSpec("frog_pond_furniture", "Frog Pond Furniture"),
    CatalogSpec("genuine_oak", "Genuine Oak"),
    CatalogSpec("hermies_table_shop", "Hermies Table Shop", extra_tokens=("hermie", "hts")),
    CatalogSpec("hogback_design_and_finishing", "Hogback Design And Finishing", extra_tokens=("hogback",)),
    CatalogSpec("hoosier_crafts", "Hoosier Crafts"),
    CatalogSpec("integ_wood_products", "INTEG Wood Products", extra_tokens=("integ",)),
    CatalogSpec("j_troyer_and_company", "J. Troyer & Company", extra_tokens=("j troyer",)),
    CatalogSpec("kidron_woodcraft", "Kidron Woodcraft"),
    CatalogSpec("meadow_lane_furniture", "Meadow Lane Furniture"),
    CatalogSpec("millcraft", "Millcraft"),
    CatalogSpec("millwood_quality_furniture", "Millwood Quality Furniture"),
    CatalogSpec("mirror_lake_woodworks", "Mirror Lake Woodworks"),
    CatalogSpec("nisley_cabinet_llc", "Nisley Cabinet LLC", extra_tokens=("nisley",)),
    CatalogSpec("old_town_oak", "Old Town Oak"),
    CatalogSpec("premier_woodcraft", "Premier Woodcraft"),
    CatalogSpec("quality_fabrications", "Quality Fabrications"),
    CatalogSpec("red_barn_woodworking", "Red Barn Woodworking"),
    CatalogSpec("rh_yoder", "RH Yoder", extra_tokens=("rhyoder",)),
    CatalogSpec("sharp_run_wood", "Sharp Run Wood"),
    CatalogSpec("signature_designs", "Signature Designs"),
    CatalogSpec("stone_river_furniture", "Stone River Furniture"),
    CatalogSpec("stoney_acres_furniture", "Stoney Acres Furniture"),
    CatalogSpec("superior_woodcrafts", "Superior Woodcrafts"),
    CatalogSpec("townline_furniture", "Townline Furniture"),
    CatalogSpec("troyer_design_company", "Troyer Design Company", extra_tokens=("tdc",)),
    CatalogSpec("troyer_ridge_furniture", "Troyer Ridge Furniture"),
)


def spec_for_vendor(vendor: str) -> Optional[CatalogSpec]:
    key = (vendor or "").strip().lower()
    for spec in CATALOG_SPECS:
        if spec.vendor.lower() == key:
            return spec
    return None


_SHEET_COLLECTION = re.compile(r"(?i)^(pricelist|price list)$")


def apply_piece_name_collections(df):
    """Millcraft: Collection is the piece name, not the sheet title.

    Casegoods have no suite banner, so Collection is the description
    (1 Drw Nightstand). Bed styles already land as section headers
    (Panel Bed). Add-on rows stay Addons.
    """
    if df is None or getattr(df, "empty", True):
        return df
    if "description" not in df.columns:
        return df
    out = df.copy()
    if "collection" not in out.columns:
        out["collection"] = None
    desc = out["description"].fillna("").astype(str).str.strip()
    coll = out["collection"]
    coll_s = coll.fillna("").astype(str).str.strip()
    if "line_kind" in out.columns:
        kind = out["line_kind"].fillna("item").astype(str).str.lower()
    else:
        kind = "item"
    blank = coll.isna() | coll_s.eq("") | coll_s.str.fullmatch(_SHEET_COLLECTION)
    use = blank & desc.ne("")
    if not isinstance(kind, str):
        use = use & (kind != "addon")
    out.loc[use, "collection"] = desc[use]
    return out


def _context_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value).strip())


def integ_product_context(data: bytes) -> dict[tuple[str, str], str]:
    """Visible INTEG item headers keyed by sheet + repeated/ditto SKU."""
    from backend.workbook_sheets import read_all_sheets

    context: dict[tuple[str, str], str] = {}
    for view in read_all_sheets(data):
        raw = view.raw
        if raw is None or getattr(raw, "empty", True):
            continue
        rows = raw.values.tolist()
        headers: list[tuple[int, int, str]] = []
        for row_i, values in enumerate(rows):
            for col_i, value in enumerate(values):
                if _context_text(value).lower() != "item #":
                    continue
                label = ""
                for previous in range(row_i - 1, max(-1, row_i - 5), -1):
                    if col_i >= len(rows[previous]):
                        continue
                    candidate = _context_text(rows[previous][col_i])
                    if candidate and candidate.lower() not in {
                        "item #",
                        "integ wood products, llc",
                    }:
                        label = candidate
                        break
                if label:
                    headers.append((row_i, col_i, label))
                break
        for header_i, (row_i, col_i, label) in enumerate(headers):
            stop = headers[header_i + 1][0] if header_i + 1 < len(headers) else len(rows)
            current_part = ""
            for values in rows[row_i + 1 : stop]:
                value = _context_text(values[col_i]) if col_i < len(values) else ""
                if re.fullmatch(r'(?:""|“”|″|〃)', value):
                    value = current_part
                elif value and value.lower() not in {"option", "options"}:
                    current_part = value
                if current_part:
                    context[(view.name, current_part)] = label
    return context


_HERMIES_CONTEXT_JUNK = re.compile(
    r"""(?ix)
    ^(?:item|size|leaves?|unfinished|finished|options?)\b|
    ^[•#]|additional\s+shapes|no\s+extra\s+charge|self-store|
    standard\s+(?:edge|shape|pedestal)|slides?|for\s+\d+["']?\s+high|
    add\s+\$?|subject\s+to|available\s+at|^\d+\s*["']?\s*x
    """
)


def hermies_product_context(data: bytes) -> dict[tuple[str, str], str]:
    """Visible Hermies style banners keyed by their following HTS SKUs."""
    from backend.workbook_sheets import read_all_sheets

    context: dict[tuple[str, str], str] = {}
    for view in read_all_sheets(data):
        raw = view.raw
        if raw is None or getattr(raw, "empty", True):
            continue
        current_label = ""
        for values in raw.values.tolist():
            texts = [_context_text(value) for value in values]
            first = next((value for value in texts if value), "")
            if not first:
                continue
            sku = re.fullmatch(r"(?i)(HTS[A-Z0-9-]+)", first)
            if sku:
                if current_label:
                    context[("", sku.group(1).upper())] = current_label
                continue
            numeric = sum(
                1
                for value in values[1:]
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not (isinstance(value, float) and math.isnan(value))
                and float(value) > 1
            )
            if (
                numeric == 0
                and 3 <= len(first) <= 70
                and not _HERMIES_CONTEXT_JUNK.search(first)
            ):
                current_label = first
    return context


def apply_catalog_description_fixes(
    df,
    vendor: str,
    *,
    product_context: Optional[dict[tuple[str, str], str]] = None,
):
    """Correct builder layouts before shared row standardization.

    These are source-column corrections, not description inventions.  Rich
    wording is assembled later from the canonical fields.
    """
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    if vendor == "AJ's Furniture":
        for column in ("part_number", "description", "option_key"):
            if column not in out.columns:
                out[column] = None
        part = out["part_number"].fillna("").astype(str).str.strip()
        desc = out["description"].fillna("").astype(str).str.strip()
        fabric_tier = part.str.fullmatch(
            r"(?i)(?:standard|premium|leather|com)"
        ) & desc.ne("")
        option_blank = (
            out["option_key"].isna()
            | out["option_key"].fillna("").astype(str).str.strip().eq("")
        )
        out.loc[fabric_tier & option_blank, "option_key"] = part[
            fabric_tier & option_blank
        ]
        out.loc[fabric_tier, "part_number"] = desc[fabric_tier]
    elif vendor in {"INTEG Wood Products", "Hermies Table Shop"} and product_context:
        if "collection" not in out.columns:
            out["collection"] = None
        if "part_number" not in out.columns:
            return out
        for index, row in out.iterrows():
            collection = _context_text(row.get("collection"))
            part_number = _context_text(row.get("part_number"))
            label = product_context.get(
                (collection, part_number)
            ) or product_context.get(("", part_number.upper()))
            if label:
                out.at[index, "collection"] = label
    return out


def import_catalog_workbook(
    spec: CatalogSpec,
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
):
    from wide_import import import_workbook, tag_import_result

    result = import_workbook(
        data,
        vendor=vendor or spec.vendor,
        default_collection=default_collection,
        sheet_filter=sheet_filter,
        filename=filename,
        force_layout_guess=True,
    )
    if spec.parser_id == "millcraft":
        result.long_df = apply_piece_name_collections(result.long_df)
    if spec.vendor == "INTEG Wood Products":
        product_context = integ_product_context(data)
    elif spec.vendor == "Hermies Table Shop":
        product_context = hermies_product_context(data)
    else:
        product_context = None
    result.long_df = apply_catalog_description_fixes(
        result.long_df,
        spec.vendor,
        product_context=product_context,
    )
    return tag_import_result(result, spec.parser_id)


def _spec_reader(spec: CatalogSpec):
    if not spec.reader:
        return partial(import_catalog_workbook, spec)
    from backend.builder_reader_registry import _symbol

    return _symbol(spec.reader)


def catalog_reader_entries() -> tuple[ReaderEntry, ...]:
    return tuple(
        ReaderEntry(
            spec.parser_id,
            spec.vendor,
            layouts=(spec.parser_id,),
            detect_fn=spec.matches,
            reader_fn=_spec_reader(spec),
        )
        for spec in CATALOG_SPECS
    )
