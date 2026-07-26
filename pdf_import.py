"""
PDF price-list extraction and parsing for Amish / wholesale furniture books.

Strategies (tried in order; best non-empty result wins, others available in UI):
  1. pdfplumber table extraction
  2. Line patterns: part/desc + price(s) on one line
  3. Item-then-prices blocks (Berlin chair style)
  4. Size/item + multi-price lines (Troyer / multi-species tables)
  5. Columnar zip: codes | descriptions | $prices as separate streams (Beaverdam)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

MONEY_RE = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)"
)
# Standalone money or N/A tokens
PRICE_TOKEN_RE = re.compile(
    r"(?:\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\$\s*\d+(?:\.\d{2})?|N/?A)",
    re.IGNORECASE,
)
# Part-ish codes: SU-BT10, 5885, 58824SW, SE-CT36-60, SEM-RT-BA72
PART_CODE_RE = re.compile(
    r"^(?P<code>[A-Z]{1,6}[-/][A-Z0-9][-A-Z0-9/]{1,20}|[A-Z]?\d{3,6}[A-Z]{0,4})\s+"
    r"(?P<desc>.+)$",
    re.IGNORECASE,
)
# Dimension-ish descriptions: 42" X 60", 42"x72"x1-1/4", 36" Round x1"
SIZE_RE = re.compile(
    r"""(?ix)
    ^(?:solid\s+|self[- ]?store\s+|top\s+|1\s*leaf\s+|2\s*leaf\s+|4\s*leaf\s+)?
    (
        \d{1,3}\s*["']?\s*[xX×]\s*\d{1,3}(?:\s*["']?\s*[xX×]\s*[\d./-]+)?\s*["']?
        |
        \d{1,3}\s*["']?\s*(?:round|rd)\b
        |
        \d{1,3}\s*["']\s*[xX×]
    )
    """,
)

SPECIES_HINTS = [
    "brown maple", "red oak", "wormy maple", "walnut", "rustic walnut",
    "cherry", "hard maple", "white oak", "qswo", "pswo", "hickory",
    "rustic cherry", "sap cherry", "elm", "oak", "aspen", "rough sawn",
    "rustic oak", "rustic hickory", "rustic wht oak", "rustic qswo",
]

SKIP_LINE_RE = re.compile(
    r"""(?ix)
    ^(?:page\s+\d+|table of contents|prices?\s+subject|effective\s+|
       phone:|fax:|email:|account executive|main office|new orders|
       pick up|warehouse|index$|markup|upcharge|continued|
       standard features|options:|seat options|please note|
       dims?/size|l\.w\.h|d\.w\.h|std\s*=|std price|finished\s+(?:retail|wholesale)|
       your source for|ph:|www\.|http)
    """
)

COLLECTION_HEADER_RE = re.compile(
    r"""(?ix)
    ^(?!
        item$|leaves?$|red oak|wormy|walnut|cherry|maple|oak|hickory|
        number of|solid$|self.?store|specs?$|overall|sizes?$|base specs
    )
    (
        .+?\s+(?:chairs?|tables?|collection|series|beds?|stools?|benches?)
        |
        [A-Z][A-Za-z &/'-]{2,40}
    )
    $
    """
)


@dataclass
class ParseResult:
    name: str
    label: str
    df: pd.DataFrame
    notes: str = ""
    raw_sample: str = ""
    species_columns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_pdf_pages(data: bytes, max_pages: Optional[int] = None) -> list[str]:
    """Return list of page texts. Prefer pdfplumber; fall back to pypdf."""
    pages: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages):
                if max_pages is not None and i >= max_pages:
                    break
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                pages.append(text)
        if any(p.strip() for p in pages):
            return pages
    except Exception:
        pages = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        for i, page in enumerate(reader.pages):
            if max_pages is not None and i >= max_pages:
                break
            pages.append(page.extract_text() or "")
    except Exception as e:
        raise RuntimeError(f"Could not extract PDF text: {e}") from e

    return pages


def extract_pdfplumber_tables(data: bytes, max_pages: Optional[int] = None) -> list[list[list]]:
    tables: list[list[list]] = []
    try:
        import pdfplumber
    except ImportError:
        return tables

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages):
            if max_pages is not None and i >= max_pages:
                break
            for t in page.extract_tables() or []:
                if t and len(t) >= 2:
                    tables.append(t)
    return tables


def pdf_text_stats(pages: list[str]) -> dict:
    joined = "\n".join(pages)
    money_hits = len(MONEY_RE.findall(joined))
    chars = len(joined.strip())
    return {
        "pages": len(pages),
        "chars": chars,
        "money_hits": money_hits,
        "likely_scanned": chars < 80 * max(len(pages), 1) and money_hits < 5,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _money_to_float(s: str) -> Optional[float]:
    s = s.strip()
    if re.fullmatch(r"N/?A", s, re.I):
        return None
    m = MONEY_RE.search(s)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    m2 = re.search(r"[\d,]+(?:\.\d+)?", s)
    if not m2:
        return None
    try:
        return float(m2.group(0).replace(",", ""))
    except ValueError:
        return None


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        if SKIP_LINE_RE.search(line):
            continue
        # lone page numbers
        if re.fullmatch(r"\d{1,3}", line):
            continue
        lines.append(line)
    return lines


def _looks_like_species_header(line: str) -> bool:
    low = line.lower()
    hits = sum(1 for s in SPECIES_HINTS if s in low)
    return hits >= 1 and len(line) < 80


def _default_species_labels(n: int) -> list[str]:
    defaults = [
        "Brown Maple / Red Oak",
        "Cherry / Wormy Maple",
        "Walnut / Premium",
        "Species 4",
        "Species 5",
        "Species 6",
        "Species 7",
        "Species 8",
    ]
    if n <= len(defaults):
        return defaults[:n]
    return [f"Species {i+1}" for i in range(n)]


# ---------------------------------------------------------------------------
# Strategy 1: pdfplumber tables → DataFrame
# ---------------------------------------------------------------------------

def strategy_tables(data: bytes, max_pages: Optional[int] = None) -> Optional[ParseResult]:
    tables = extract_pdfplumber_tables(data, max_pages=max_pages)
    if not tables:
        return None

    frames = []
    for t in tables:
        # first non-empty row as header if it has text cells
        header = None
        body = t
        first = t[0]
        if first and sum(1 for c in first if c and str(c).strip()) >= 2:
            header = [str(c or f"col_{i}").strip() or f"col_{i}" for i, c in enumerate(first)]
            body = t[1:]
        if not body:
            continue
        if header is None:
            width = max(len(r) for r in body)
            header = [f"col_{i}" for i in range(width)]
        # normalize row widths
        rows = []
        for r in body:
            cells = [ ("" if c is None else str(c).strip()) for c in r ]
            if len(cells) < len(header):
                cells += [""] * (len(header) - len(cells))
            rows.append(cells[: len(header)])
        df = pd.DataFrame(rows, columns=header)
        # drop fully empty
        df = df.replace("", pd.NA).dropna(how="all")
        if len(df) >= 2:
            frames.append(df)

    if not frames:
        return None

    # Prefer frame with most money-like cells
    def money_score(df: pd.DataFrame) -> int:
        score = 0
        for col in df.columns:
            for v in df[col].astype(str).head(40):
                if MONEY_RE.search(v) or re.fullmatch(r"[\d,]+\.?\d*", v.replace(",", "")):
                    score += 1
        return score

    best = max(frames, key=lambda d: (money_score(d), len(d)))
    if money_score(best) < 3:
        return None

    return ParseResult(
        name="tables",
        label="PDF tables (pdfplumber)",
        df=best.reset_index(drop=True),
        notes=f"Found {len(tables)} table(s); showing best with {len(best)} rows.",
    )


# ---------------------------------------------------------------------------
# Strategy 2: single-line part/desc + one or more prices
# ---------------------------------------------------------------------------

def strategy_inline_prices(pages: list[str]) -> Optional[ParseResult]:
    rows = []
    current_collection = None
    species_labels: list[str] = []

    for page in pages:
        for line in _clean_lines(page):
            if _looks_like_species_header(line) and not MONEY_RE.search(line):
                # capture species names from header-ish lines
                continue

            prices = MONEY_RE.findall(line)
            if not prices:
                # possible collection header
                if (
                    not re.search(r"\d", line)
                    and 3 <= len(line) <= 50
                    and COLLECTION_HEADER_RE.match(line)
                ):
                    current_collection = line.strip()
                continue

            # strip prices from right for description
            desc_part = MONEY_RE.sub("", line).strip(" -–|\t")
            desc_part = re.sub(r"\s+", " ", desc_part).strip()
            if not desc_part or len(desc_part) < 2:
                continue
            # skip pure option lines like "Add $20"
            if re.match(r"(?i)^(for |add |deduct |no |upcharge|paint )", desc_part):
                continue

            part = None
            desc = desc_part
            m = PART_CODE_RE.match(desc_part)
            if m:
                part = m.group("code").strip()
                desc = m.group("desc").strip()

            price_vals = []
            for p in prices:
                try:
                    price_vals.append(float(p.replace(",", "")))
                except ValueError:
                    pass
            if not price_vals:
                continue

            if len(price_vals) == 1:
                rows.append({
                    "part_number": part,
                    "description": desc,
                    "base_price": price_vals[0],
                    "species": None,
                    "collection": current_collection,
                    "notes": None,
                })
            else:
                if not species_labels or len(species_labels) != len(price_vals):
                    species_labels = _default_species_labels(len(price_vals))
                for i, pv in enumerate(price_vals):
                    rows.append({
                        "part_number": part,
                        "description": desc,
                        "base_price": pv,
                        "species": species_labels[i],
                        "collection": current_collection,
                        "notes": f"species_col={i+1}",
                    })

    if len(rows) < 3:
        return None

    df = pd.DataFrame(rows)
    n_species = df["species"].nunique(dropna=True)
    return ParseResult(
        name="inline_prices",
        label="Inline prices (line-based)",
        df=df,
        notes=f"Parsed {len(df)} price rows"
              + (f" across {n_species} species columns." if n_species else "."),
        species_columns=sorted(s for s in df["species"].dropna().unique()),
    )


# ---------------------------------------------------------------------------
# Strategy 3: Berlin-style "Item line" then N price lines / N/A
# ---------------------------------------------------------------------------

def strategy_item_price_blocks(pages: list[str]) -> Optional[ParseResult]:
    """
    Pattern:
      5885 Albany Side Chair
      $499
      $524
      $611
    Or with N/A mixed in.
    Also table sizes:
      42" X 60"
      Solid | 1 | 2
      $2,289
      ...
    """
    rows = []
    current_collection = None
    # rolling buffer of non-price lines that might be item
    pending_item: Optional[str] = None
    pending_leaves: Optional[str] = None
    price_buf: list[Optional[float]] = []

    def flush():
        nonlocal pending_item, pending_leaves, price_buf
        if not pending_item or not price_buf:
            pending_item = None
            pending_leaves = None
            price_buf = []
            return
        # need at least one real price
        if all(p is None for p in price_buf):
            pending_item = None
            pending_leaves = None
            price_buf = []
            return

        part = None
        desc = pending_item
        m = PART_CODE_RE.match(pending_item)
        if m:
            part = m.group("code").strip()
            desc = m.group("desc").strip()
        if pending_leaves:
            leaf = str(pending_leaves).strip()
            if leaf.lower() == "solid":
                desc = f"{desc} — Solid"
            else:
                desc = f"{desc} — {leaf} leaf"

        labels = _default_species_labels(len(price_buf))
        for i, pv in enumerate(price_buf):
            if pv is None:
                continue
            rows.append({
                "part_number": part,
                "description": desc,
                "base_price": pv,
                "species": labels[i] if len(price_buf) > 1 else None,
                "collection": current_collection,
                "notes": None,
            })
        pending_item = None
        pending_leaves = None
        price_buf = []

    leaf_re = re.compile(r"^(Solid|\d{1,2})$", re.I)

    for page in pages:
        lines = _clean_lines(page)
        i = 0
        while i < len(lines):
            line = lines[i]

            # price or N/A only
            if re.fullmatch(r"\$?\s*[\d,]+(?:\.\d{2})?", line) or re.fullmatch(r"N/?A", line, re.I):
                if pending_item:
                    if re.fullmatch(r"N/?A", line, re.I):
                        price_buf.append(None)
                    else:
                        # ensure $ for parser
                        tok = line if line.startswith("$") else f"${line}"
                        price_buf.append(_money_to_float(tok))
                i += 1
                continue

            # starting a new item — flush previous
            if price_buf and pending_item:
                flush()

            if leaf_re.match(line) and pending_item and not price_buf:
                pending_leaves = line
                i += 1
                continue

            if MONEY_RE.search(line) and PRICE_TOKEN_RE.search(line):
                # multi prices on one line attached to previous item
                if pending_item:
                    for tok in PRICE_TOKEN_RE.findall(line):
                        if re.fullmatch(r"N/?A", tok, re.I):
                            price_buf.append(None)
                        else:
                            price_buf.append(_money_to_float(tok))
                    flush()
                i += 1
                continue

            # collection / section header
            if (
                not re.search(r"\d", line)
                and 3 <= len(line) <= 55
                and not _looks_like_species_header(line)
            ):
                if re.search(r"(?i)chairs?|tables?|collection|beds?|stools?", line) or (
                    line[0].isupper() and " " in line and len(line.split()) <= 5
                ):
                    if price_buf:
                        flush()
                    current_collection = line
                    pending_item = None
                    i += 1
                    continue

            # species header junk
            if _looks_like_species_header(line) or line.lower() in {
                "item", "leaves", "number of leaves", "red oak", "wormy maple",
                "rustic walnut", "walnut",
            }:
                i += 1
                continue

            # treat as item description
            if price_buf:
                flush()
            pending_item = line
            pending_leaves = None
            i += 1

        if price_buf:
            flush()

    if len(rows) < 5:
        return None

    df = pd.DataFrame(rows)
    return ParseResult(
        name="item_blocks",
        label="Item → price blocks (Berlin-style)",
        df=df,
        notes=f"Parsed {len(df)} rows from item/price stacks.",
        species_columns=sorted(s for s in df["species"].dropna().unique()),
    )


# ---------------------------------------------------------------------------
# Strategy 4: description line then multi-price line (Troyer-style)
# ---------------------------------------------------------------------------

def strategy_desc_then_price_line(pages: list[str]) -> Optional[ParseResult]:
    rows = []
    current_collection = None
    pending_desc = None
    pending_part = None

    for page in pages:
        for line in _clean_lines(page):
            tokens = PRICE_TOKEN_RE.findall(line)
            money_only = MONEY_RE.findall(line)

            # Pure or mostly price line
            stripped = PRICE_TOKEN_RE.sub("", line).strip()
            if money_only and len(money_only) >= 2 and len(stripped) < 8:
                if not pending_desc:
                    continue
                labels = _default_species_labels(len(money_only))
                for i, p in enumerate(money_only):
                    try:
                        pv = float(p.replace(",", ""))
                    except ValueError:
                        continue
                    rows.append({
                        "part_number": pending_part,
                        "description": pending_desc,
                        "base_price": pv,
                        "species": labels[i],
                        "collection": current_collection,
                        "notes": None,
                    })
                pending_desc = None
                pending_part = None
                continue

            # single price on same line handled elsewhere
            if money_only and len(money_only) == 1 and len(stripped) > 3:
                continue  # leave for inline strategy

            if not money_only:
                if (
                    not re.search(r"\d", line)
                    and 3 <= len(line) <= 50
                    and re.search(r"(?i)table|chair|collection|pedestal|trestle|bench", line)
                ):
                    current_collection = line
                    continue
                if SIZE_RE.search(line) or PART_CODE_RE.match(line) or (
                    len(line) >= 4 and not _looks_like_species_header(line)
                ):
                    m = PART_CODE_RE.match(line)
                    if m:
                        pending_part = m.group("code")
                        pending_desc = m.group("desc")
                    else:
                        pending_part = None
                        pending_desc = line

    if len(rows) < 5:
        return None

    df = pd.DataFrame(rows)
    return ParseResult(
        name="desc_price_lines",
        label="Description → multi-price line (Troyer-style)",
        df=df,
        notes=f"Parsed {len(df)} species-expanded rows.",
        species_columns=sorted(s for s in df["species"].dropna().unique()),
    )


# ---------------------------------------------------------------------------
# Strategy 5: columnar zip (Beaverdam) — codes, descs, prices as runs
# ---------------------------------------------------------------------------

def strategy_columnar_zip(pages: list[str]) -> Optional[ParseResult]:
    """
    Many outdoor poly PDFs extract as:
      [codes block]
      [descriptions block]
      [prices block]
    We zip equal-length runs of part-like codes with descriptions and $prices.
    """
    rows = []
    current_collection = None

    code_line = re.compile(
        r"^[A-Z]{1,6}[-/][A-Z0-9][-A-Z0-9/]{1,24}$", re.I
    )
    dim_line = re.compile(
        r"""^\d{1,3}(?:\.\d+)?["']?\s*[xX×]\s*\d""",
    )
    price_only = re.compile(r"^\$\s*[\d,]+(?:\.\d{2})?$")

    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        codes: list[str] = []
        descs: list[str] = []
        prices: list[float] = []
        dims: list[str] = []

        for line in lines:
            if SKIP_LINE_RE.search(line) or re.fullmatch(r"\d{1,3}", line):
                continue
            if re.fullmatch(r"(?i)std price|code|description/?name|dims?/size|l\.w\.h|d\.w\.h", line):
                continue
            if code_line.match(line):
                codes.append(line.upper())
                continue
            if price_only.match(line):
                pv = _money_to_float(line)
                if pv is not None:
                    prices.append(pv)
                continue
            if dim_line.match(line) or re.match(r"""^\d{1,3}(?:\.\d+)?["']?[xX×]""", line):
                dims.append(line)
                continue
            # collection header
            if re.search(r"(?i)collection$", line) or (
                re.search(r"(?i)collection", line) and not MONEY_RE.search(line)
            ):
                current_collection = line.replace("Collection", "").strip() or line
                continue
            # description candidates
            if (
                not MONEY_RE.search(line)
                and 4 <= len(line) <= 80
                and not _looks_like_species_header(line)
                and not re.match(r"(?i)^(ph:|fax:|email:|std=)", line)
            ):
                # skip pure headers that are all caps short
                descs.append(line)

        # Align by minimum length of codes & prices; descs may include headers
        # Prefer zip(codes, prices) and best-effort desc match by index
        if len(codes) >= 5 and len(prices) >= 5:
            n = min(len(codes), len(prices))
            # if descs count close to n, zip them; else use code as desc
            use_descs = descs
            # filter descs that look like collection headers already used
            if abs(len(descs) - n) > max(3, n * 0.3):
                # try to pick a contiguous run of descs of length n
                use_descs = descs[-n:] if len(descs) >= n else descs

            for i in range(n):
                desc = use_descs[i] if i < len(use_descs) else None
                dim = dims[i] if i < len(dims) else None
                notes = dim
                rows.append({
                    "part_number": codes[i],
                    "description": desc or codes[i],
                    "base_price": prices[i],
                    "species": None,
                    "collection": current_collection,
                    "notes": notes,
                })

    if len(rows) < 5:
        return None

    df = pd.DataFrame(rows)
    return ParseResult(
        name="columnar_zip",
        label="Columnar zip (code + desc + price streams)",
        df=df,
        notes=f"Zipped {len(df)} rows from columnar PDF text. Spot-check part/desc pairing.",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def parse_pdf_pricelist(
    data: bytes,
    max_pages: Optional[int] = None,
) -> tuple[list[ParseResult], dict]:
    """
    Run all strategies. Returns (results sorted by row count desc, stats).
    """
    pages = extract_pdf_pages(data, max_pages=max_pages)
    stats = pdf_text_stats(pages)
    stats["raw_preview"] = "\n".join(pages[:2])[:4000]

    results: list[ParseResult] = []

    # tables first
    try:
        r = strategy_tables(data, max_pages=max_pages)
        if r is not None and not r.df.empty:
            results.append(r)
    except Exception as e:
        stats["tables_error"] = str(e)

    strategies = (
        strategy_inline_prices,
        strategy_item_price_blocks,
        strategy_desc_then_price_line,
        strategy_columnar_zip,
    )
    for fn in strategies:
        try:
            r = fn(pages)
            if r is not None and not r.df.empty:
                r.raw_sample = stats["raw_preview"][:1500]
                results.append(r)
        except Exception as e:
            stats[f"err_{fn.__name__}"] = str(e)

    # de-dupe by name keeping largest
    by_name: dict[str, ParseResult] = {}
    for r in results:
        if r.name not in by_name or len(r.df) > len(by_name[r.name].df):
            by_name[r.name] = r
    results = sorted(by_name.values(), key=lambda r: len(r.df), reverse=True)

    return results, stats


def expand_species_choice(
    df: pd.DataFrame,
    mode: str = "all",
    species_keep: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    mode: 'all' | 'first' | 'select'
    """
    if "species" not in df.columns or df["species"].dropna().empty:
        return df

    if mode == "all":
        return df
    if mode == "first":
        # keep first species per part+description group
        key = [c for c in ("part_number", "description") if c in df.columns]
        return df.groupby(key, dropna=False, as_index=False).first()
    if mode == "select" and species_keep:
        return df[df["species"].isin(species_keep) | df["species"].isna()].copy()
    return df


def result_to_import_df(result: ParseResult) -> pd.DataFrame:
    """Normalize strategy output to columns expected by the app mapper."""
    df = result.df.copy()
    # If still wide table from pdfplumber, leave columns as-is for manual map
    if result.name == "tables":
        return df

    # Already long-form with standard names
    wanted = [
        "part_number", "description", "base_price", "species",
        "collection", "notes", "unit",
    ]
    for c in wanted:
        if c not in df.columns:
            df[c] = None
    return df[wanted]
