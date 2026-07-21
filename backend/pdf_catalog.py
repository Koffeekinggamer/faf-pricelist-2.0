"""Floor-facing catalog PDF (Part / Description / Wood / Finish / Retail)."""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd

_PDF_UNICODE_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u00b7": "-",
        "\u2022": "*",
        "\u00d7": "x",
        "\u2212": "-",
        "\u00bd": "1/2",
        "\u00bc": "1/4",
        "\u00be": "3/4",
        "\u2033": '"',
        "\u2032": "'",
    }
)


def _pdf_safe(text: str, max_chars: Optional[int] = None) -> str:
    if text is None:
        return ""
    s = str(text).translate(_PDF_UNICODE_MAP)
    s = "".join(ch if ord(ch) < 256 else "" for ch in s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_chars is not None and len(s) > max_chars:
        s = s[: max(1, max_chars - 3)] + "..."
    return s


def catalog_pdf_bytes(df: pd.DataFrame, title: str = "Price List") -> bytes:
    """Generate landscape PDF for floor viewing."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("fpdf2 required: pip install fpdf2") from exc

    work = df.copy()
    # Prefer retail-facing columns
    col_map = {
        "part_number": "Part #",
        "description": "Description",
        "species": "Wood",
        "finish_state": "Finish",
        "adjusted_price": "Retail",
    }
    show = [c for c in col_map if c in work.columns]
    if not show:
        show = [c for c in work.columns if c != "id"][:6]
        labels = {c: c for c in show}
    else:
        labels = col_map

    widths = {
        "part_number": 28,
        "description": 95,
        "species": 36,
        "finish_state": 28,
        "adjusted_price": 28,
    }

    pdf = FPDF(orientation="L", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    def _line(text: str, h: float = 6, bold: bool = False) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", 16 if bold else 9)
        try:
            pdf.cell(0, h, text, new_x="LMARGIN", new_y="NEXT")
        except TypeError:
            pdf.cell(0, h, text, ln=True)

    _line(_pdf_safe(title), h=10, bold=True)
    _line(
        _pdf_safe(
            f"Foothills Amish Furniture  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {len(work)} items"
        ),
        h=6,
        bold=False,
    )
    pdf.ln(3)

    pdf.set_fill_color(45, 74, 48)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for c in show:
        pdf.cell(widths.get(c, 30), 7, _pdf_safe(labels.get(c, c)), border=1, fill=True)
    pdf.ln()

    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "", 8)
    fill = False
    for _, row in work.iterrows():
        if fill:
            pdf.set_fill_color(240, 244, 240)
        else:
            pdf.set_fill_color(255, 255, 255)
        for c in show:
            val = row.get(c, "")
            if c == "adjusted_price" and val is not None and val != "":
                try:
                    text = f"${float(val):,.0f}"
                except (TypeError, ValueError):
                    text = str(val)
            else:
                text = str(val if val is not None else "")
            max_chars = max(4, int(widths.get(c, 30) / 1.5))
            pdf.cell(
                widths.get(c, 30),
                5.5,
                _pdf_safe(text, max_chars=max_chars),
                border=1,
                fill=True,
            )
        pdf.ln()
        fill = not fill

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()
