"""Export master rows to Excel / CSV / PDF bytes."""

from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd

RENAME = {
    "vendor": "Vendor",
    "collection": "Collection",
    "part_number": "Part #",
    "description": "Description",
    "dimensions": "Dimensions",
    "option_key": "Option",
    "species": "Species",
    "species_tier": "Tier",
    "finish_state": "Finish",
    "base_price": "Base / Wholesale",
    "price_basis": "Price Basis",
    "multiplier": "Multiplier",
    "adjusted_price": "Retail (Adjusted)",
    "unit": "Unit",
    "notes": "Notes",
    "source_file": "Source",
    "imported_at": "Imported",
}

# Helvetica (core PDF font) is Latin-1 only — map common furniture-list Unicode.
_PDF_UNICODE_MAP = str.maketrans(
    {
        "\u2018": "'",  # ‘
        "\u2019": "'",  # ’
        "\u201c": '"',  # “
        "\u201d": '"',  # ”
        "\u2013": "-",  # –
        "\u2014": "-",  # —
        "\u2026": "...",  # …
        "\u00a0": " ",  # nbsp
        "\u00b7": "-",  # ·
        "\u2022": "*",  # •
        "\u00d7": "x",  # ×
        "\u2212": "-",  # −
        "\u00bd": "1/2",  # ½
        "\u00bc": "1/4",  # ¼
        "\u00be": "3/4",  # ¾
        "\u2153": "1/3",
        "\u2154": "2/3",
        "\u215b": "1/8",
        "\u215c": "3/8",
        "\u215d": "5/8",
        "\u215e": "7/8",
        "\u2033": '"',  # ″
        "\u2032": "'",  # ′
        "\ufb01": "fi",
        "\ufb02": "fl",
    }
)


def _pdf_safe(text: str, max_chars: int | None = None) -> str:
    """Make text safe for Helvetica / Latin-1 PDF core fonts."""
    if text is None:
        return ""
    s = str(text)
    s = s.translate(_PDF_UNICODE_MAP)
    # Drop anything outside Latin-1 (Helvetica core font range)
    s = "".join(ch if ord(ch) < 256 else "" for ch in s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_chars is not None and len(s) > max_chars:
        s = s[: max(1, max_chars - 3)] + "..."
    return s


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    export = df.copy()
    if "id" in export.columns:
        export = export.drop(columns=["id"])
    export = export.rename(columns={k: v for k, v in RENAME.items() if k in export.columns})
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Price Book")
    return buf.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    export = df.copy()
    if "id" in export.columns:
        export = export.drop(columns=["id"])
    return export.to_csv(index=False).encode("utf-8")


def to_pdf_bytes(df: pd.DataFrame, title: str = "Price Book Export") -> bytes:
    try:
        from fpdf import FPDF
    except ImportError:
        lines = [title, "=" * len(title), ""]
        cols = [c for c in df.columns if c != "id"]
        lines.append(" | ".join(cols))
        lines.append("-" * 80)
        for _, row in df.iterrows():
            lines.append(" | ".join(str(row.get(c, "") or "")[:40] for c in cols))
        return "\n".join(lines).encode("utf-8")

    pdf = FPDF(orientation="L", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    title_s = _pdf_safe(title)
    try:
        pdf.cell(0, 10, title_s, new_x="LMARGIN", new_y="NEXT")
    except TypeError:
        pdf.cell(0, 10, title_s, ln=True)
    pdf.set_font("Helvetica", "", 8)
    gen = _pdf_safe(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {len(df)} rows"
    )
    try:
        pdf.cell(0, 6, gen, new_x="LMARGIN", new_y="NEXT")
    except TypeError:
        pdf.cell(0, 6, gen, ln=True)
    pdf.ln(2)

    show_cols = [
        c
        for c in [
            "vendor",
            "collection",
            "part_number",
            "description",
            "species",
            "base_price",
            "multiplier",
            "adjusted_price",
        ]
        if c in df.columns
    ]
    labels = {
        "vendor": "Vendor",
        "collection": "Collection",
        "part_number": "Part #",
        "description": "Description",
        "species": "Species",
        "base_price": "Base",
        "multiplier": "Mult",
        "adjusted_price": "Retail",
    }
    widths = {
        "vendor": 28,
        "collection": 30,
        "part_number": 24,
        "description": 70,
        "species": 32,
        "base_price": 20,
        "multiplier": 14,
        "adjusted_price": 20,
    }

    pdf.set_font("Helvetica", "B", 7)
    for c in show_cols:
        pdf.cell(widths.get(c, 25), 6, _pdf_safe(labels.get(c, c)), border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for _, row in df.iterrows():
        for c in show_cols:
            val = row.get(c, "")
            if c in ("base_price", "adjusted_price") and val is not None and val != "":
                try:
                    text = f"${float(val):,.2f}"
                except (TypeError, ValueError):
                    text = str(val)
            elif c == "multiplier" and val is not None and val != "":
                try:
                    text = f"{float(val):.2f}"
                except (TypeError, ValueError):
                    text = str(val)
            else:
                text = str(val if val is not None else "")
            max_chars = max(4, int(widths.get(c, 25) / 1.6))
            text = _pdf_safe(text, max_chars=max_chars)
            pdf.cell(widths.get(c, 25), 5, text, border=1)
        pdf.ln()

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()
