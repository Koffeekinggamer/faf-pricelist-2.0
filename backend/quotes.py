"""Quote builder data access and export."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from backend.db import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _quote_number() -> str:
    return "Q-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _line_total(qty: float, unit_retail: float, line_discount_pct: float = 0) -> float:
    qty = float(qty or 0)
    unit = float(unit_retail or 0)
    disc = float(line_discount_pct or 0) / 100.0
    return round(qty * unit * (1.0 - disc), 2)


def _pdf_safe(text) -> str:
    """Helvetica core fonts are latin-1 only — strip fancy punctuation."""
    if text is None:
        return ""
    s = str(text)
    repl = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "×": "x",
        "–": "-",
        "—": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")


class QuoteRepository:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ------------------------------------------------------------------ quotes
    def create_quote(
        self,
        *,
        customer_name: str = "",
        customer_phone: str = "",
        customer_email: str = "",
        notes: str = "",
        discount_pct: float = 0,
        tax_pct: float = 0,
    ) -> int:
        now = _now()
        qn = _quote_number()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO quotes (
                    quote_number, customer_name, customer_phone, customer_email,
                    status, notes, discount_pct, tax_pct, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
                """,
                (
                    qn,
                    customer_name or None,
                    customer_phone or None,
                    customer_email or None,
                    notes or None,
                    discount_pct,
                    tax_pct,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_quote(self, quote_id: int, **fields) -> None:
        allowed = {
            "customer_name",
            "customer_phone",
            "customer_email",
            "status",
            "notes",
            "discount_pct",
            "tax_pct",
            "ordertrac_guid",
            "ordertrac_so_id",
            "ordertrac_url",
            "ordertrac_pushed_at",
        }
        sets = []
        vals = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        sets.append("updated_at = ?")
        vals.append(_now())
        vals.append(quote_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE quotes SET {', '.join(sets)} WHERE id = ?", vals
            )
            conn.commit()

    def delete_quote(self, quote_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
            conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
            conn.commit()

    def get_quote(self, quote_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM quotes WHERE id = ?", (quote_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def list_quotes(self, limit: int = 100) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                """
                SELECT q.*,
                       (SELECT COUNT(*) FROM quote_lines ql WHERE ql.quote_id = q.id) AS line_count,
                       (SELECT COALESCE(SUM(ql.line_total), 0) FROM quote_lines ql
                        WHERE ql.quote_id = q.id) AS lines_subtotal
                FROM quotes q
                ORDER BY q.updated_at DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )

    def quote_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]

    # ------------------------------------------------------------------ lines
    def list_lines(self, quote_id: int) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                """
                SELECT * FROM quote_lines
                WHERE quote_id = ?
                ORDER BY line_no, id
                """,
                conn,
                params=(quote_id,),
            )

    def add_line_from_pricebook(
        self,
        quote_id: int,
        pricebook_row: dict,
        *,
        qty: float = 1.0,
        line_discount_pct: float = 0.0,
        notes: str = "",
    ) -> int:
        unit_base = pricebook_row.get("base_price")
        unit_retail = pricebook_row.get("adjusted_price")
        if unit_retail is None and unit_base is not None:
            from backend.pricing import retail_from_wholesale

            mult = pricebook_row.get("multiplier") or 2.7
            unit_retail = retail_from_wholesale(unit_base, mult)

        with self._conn() as conn:
            max_no = conn.execute(
                "SELECT COALESCE(MAX(line_no), 0) FROM quote_lines WHERE quote_id = ?",
                (quote_id,),
            ).fetchone()[0]
            line_no = int(max_no) + 1
            total = _line_total(qty, unit_retail or 0, line_discount_pct)
            cur = conn.execute(
                """
                INSERT INTO quote_lines (
                    quote_id, line_no, pricebook_id, vendor, collection,
                    part_number, description, species, dimensions, finish_state,
                    qty, unit_base, unit_retail, line_discount_pct, line_total, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    line_no,
                    pricebook_row.get("id"),
                    pricebook_row.get("vendor"),
                    pricebook_row.get("collection"),
                    pricebook_row.get("part_number"),
                    pricebook_row.get("description"),
                    pricebook_row.get("species"),
                    pricebook_row.get("dimensions"),
                    pricebook_row.get("finish_state"),
                    qty,
                    unit_base,
                    unit_retail,
                    line_discount_pct,
                    total,
                    notes or None,
                ),
            )
            conn.execute(
                "UPDATE quotes SET updated_at = ? WHERE id = ?", (_now(), quote_id)
            )
            conn.commit()
            return int(cur.lastrowid)

    def add_custom_line(
        self,
        quote_id: int,
        *,
        description: str,
        qty: float = 1.0,
        unit_retail: float = 0.0,
        vendor: str = "",
        part_number: str = "",
        notes: str = "",
    ) -> int:
        with self._conn() as conn:
            max_no = conn.execute(
                "SELECT COALESCE(MAX(line_no), 0) FROM quote_lines WHERE quote_id = ?",
                (quote_id,),
            ).fetchone()[0]
            line_no = int(max_no) + 1
            total = _line_total(qty, unit_retail, 0)
            cur = conn.execute(
                """
                INSERT INTO quote_lines (
                    quote_id, line_no, description, vendor, part_number,
                    qty, unit_retail, line_total, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    line_no,
                    description,
                    vendor or None,
                    part_number or None,
                    qty,
                    unit_retail,
                    total,
                    notes or None,
                ),
            )
            conn.execute(
                "UPDATE quotes SET updated_at = ? WHERE id = ?", (_now(), quote_id)
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_line(self, line_id: int, **fields) -> None:
        allowed = {
            "qty",
            "unit_retail",
            "unit_base",
            "line_discount_pct",
            "description",
            "notes",
            "part_number",
            "species",
            "finish_state",
            "vendor",
            "collection",
        }
        # load current for recalc
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM quote_lines WHERE id = ?", (line_id,)
            ).fetchone()
            if not row:
                return
            data = dict(row)
            for k, v in fields.items():
                if k in allowed:
                    data[k] = v
            data["line_total"] = _line_total(
                data.get("qty") or 0,
                data.get("unit_retail") or 0,
                data.get("line_discount_pct") or 0,
            )
            conn.execute(
                """
                UPDATE quote_lines SET
                    qty = ?, unit_retail = ?, unit_base = ?,
                    line_discount_pct = ?, description = ?, notes = ?,
                    part_number = ?, species = ?, finish_state = ?,
                    vendor = ?, collection = ?, line_total = ?
                WHERE id = ?
                """,
                (
                    data.get("qty"),
                    data.get("unit_retail"),
                    data.get("unit_base"),
                    data.get("line_discount_pct"),
                    data.get("description"),
                    data.get("notes"),
                    data.get("part_number"),
                    data.get("species"),
                    data.get("finish_state"),
                    data.get("vendor"),
                    data.get("collection"),
                    data.get("line_total"),
                    line_id,
                ),
            )
            conn.execute(
                "UPDATE quotes SET updated_at = ? WHERE id = ?",
                (_now(), data["quote_id"]),
            )
            conn.commit()

    def delete_line(self, line_id: int) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT quote_id FROM quote_lines WHERE id = ?", (line_id,)
            ).fetchone()
            conn.execute("DELETE FROM quote_lines WHERE id = ?", (line_id,))
            if row:
                conn.execute(
                    "UPDATE quotes SET updated_at = ? WHERE id = ?",
                    (_now(), row["quote_id"]),
                )
            conn.commit()

    def totals(self, quote_id: int) -> dict[str, Any]:
        q = self.get_quote(quote_id) or {}
        lines = self.list_lines(quote_id)
        subtotal = float(lines["line_total"].sum()) if not lines.empty else 0.0
        disc_pct = float(q.get("discount_pct") or 0)
        tax_pct = float(q.get("tax_pct") or 0)
        after_disc = round(subtotal * (1.0 - disc_pct / 100.0), 2)
        tax = round(after_disc * (tax_pct / 100.0), 2)
        grand = round(after_disc + tax, 2)
        return {
            "subtotal": round(subtotal, 2),
            "discount_pct": disc_pct,
            "discount_amount": round(subtotal - after_disc, 2),
            "tax_pct": tax_pct,
            "tax_amount": tax,
            "grand_total": grand,
            "line_count": len(lines),
        }

    def export_excel(self, quote_id: int) -> bytes:
        q = self.get_quote(quote_id)
        lines = self.list_lines(quote_id)
        totals = self.totals(quote_id)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            meta = pd.DataFrame(
                [
                    {
                        "Quote #": q.get("quote_number") if q else "",
                        "Customer": q.get("customer_name") if q else "",
                        "Phone": q.get("customer_phone") if q else "",
                        "Email": q.get("customer_email") if q else "",
                        "Status": q.get("status") if q else "",
                        "Notes": q.get("notes") if q else "",
                        "Subtotal": totals["subtotal"],
                        "Discount %": totals["discount_pct"],
                        "Tax %": totals["tax_pct"],
                        "Grand Total": totals["grand_total"],
                    }
                ]
            )
            meta.to_excel(writer, index=False, sheet_name="Quote")
            if not lines.empty:
                show = lines.drop(columns=["id", "quote_id", "pricebook_id"], errors="ignore")
                show.to_excel(writer, index=False, sheet_name="Lines")
        return buf.getvalue()

    def export_pdf(self, quote_id: int) -> bytes:
        q = self.get_quote(quote_id) or {}
        lines = self.list_lines(quote_id)
        totals = self.totals(quote_id)

        try:
            from fpdf import FPDF
        except ImportError:
            text = [
                f"Quote {q.get('quote_number', '')}",
                f"Customer: {q.get('customer_name', '')}",
                f"Phone: {q.get('customer_phone', '')}",
                "",
            ]
            for _, r in lines.iterrows():
                text.append(
                    f"{r.get('qty')} x {r.get('part_number') or ''} "
                    f"{r.get('description') or ''} @ ${float(r.get('unit_retail') or 0):,.2f} "
                    f"= ${float(r.get('line_total') or 0):,.2f}"
                )
            text.append("")
            text.append(f"Subtotal: ${totals['subtotal']:,.2f}")
            text.append(f"Grand Total: ${totals['grand_total']:,.2f}")
            return "\n".join(text).encode("utf-8")

        pdf = FPDF(orientation="P", unit="mm", format="Letter")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        from backend.config import STORE

        store_name = _pdf_safe(STORE.get("name") or "Foothills Amish Furniture")
        tagline = _pdf_safe(STORE.get("tagline") or "Customer Price Quote")
        store_phone = _pdf_safe(STORE.get("phone") or "")
        store_email = _pdf_safe(STORE.get("email") or "")
        store_addr = _pdf_safe(STORE.get("address") or "")
        store_footer = _pdf_safe(
            STORE.get("footer")
            or "Prices subject to change. Thank you for your business."
        )

        # FAF brand header
        pdf.set_fill_color(45, 74, 48)  # deep green
        header_h = 28 if not (store_phone or store_addr) else 34
        pdf.rect(0, 0, 216, header_h, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(12, 7)
        pdf.set_font("Helvetica", "B", 16)
        self._cell(pdf, 0, 7, store_name.upper()[:48], ln=True)
        pdf.set_x(12)
        pdf.set_font("Helvetica", "", 10)
        self._cell(pdf, 0, 5, tagline, ln=True)
        contact_bits = [b for b in (store_addr, store_phone, store_email) if b]
        if contact_bits:
            pdf.set_x(12)
            pdf.set_font("Helvetica", "", 8)
            self._cell(pdf, 0, 4, "  |  ".join(contact_bits)[:90], ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_y(header_h + 6)

        pdf.set_font("Helvetica", "B", 12)
        self._cell(pdf, 0, 7, _pdf_safe(f"Quote #: {q.get('quote_number') or ''}"), ln=True)
        pdf.set_font("Helvetica", "", 11)
        self._cell(pdf, 0, 6, _pdf_safe(f"Customer: {q.get('customer_name') or ''}"), ln=True)
        if q.get("customer_phone"):
            self._cell(pdf, 0, 6, _pdf_safe(f"Phone: {q['customer_phone']}"), ln=True)
        if q.get("customer_email"):
            self._cell(pdf, 0, 6, _pdf_safe(f"Email: {q['customer_email']}"), ln=True)
        self._cell(
            pdf,
            0,
            6,
            _pdf_safe(f"Date: {(q.get('updated_at') or q.get('created_at') or '')[:10]}"),
            ln=True,
        )
        pdf.ln(4)

        # column header band
        pdf.set_fill_color(232, 236, 230)
        pdf.set_font("Helvetica", "B", 8)
        cols = [
            ("Qty", 12),
            ("Part #", 28),
            ("Description", 70),
            ("Wood / Option", 35),
            ("Each", 22),
            ("Total", 22),
        ]
        for label, w in cols:
            pdf.cell(w, 7, label, border=1, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for _, r in lines.iterrows():
            qty = r.get("qty") or 0
            part = _pdf_safe(r.get("part_number") or "")[:18]
            desc = _pdf_safe(r.get("description") or "")[:48]
            species = _pdf_safe(r.get("species") or "")[:22]
            each = float(r.get("unit_retail") or 0)
            tot = float(r.get("line_total") or 0)
            vals = [
                (f"{qty:g}", 12),
                (part, 28),
                (desc, 70),
                (species, 35),
                (f"${each:,.2f}", 22),
                (f"${tot:,.2f}", 22),
            ]
            for text, w in vals:
                pdf.cell(w, 6, _pdf_safe(text), border=1)
            pdf.ln()

        pdf.ln(6)
        pdf.set_font("Helvetica", "", 10)
        self._cell(pdf, 0, 6, f"Subtotal: ${totals['subtotal']:,.2f}", ln=True)
        if totals["discount_pct"]:
            self._cell(
                pdf,
                0,
                6,
                f"Discount ({totals['discount_pct']:g}%): -${totals['discount_amount']:,.2f}",
                ln=True,
            )
        if totals["tax_pct"]:
            self._cell(
                pdf,
                0,
                6,
                f"Tax ({totals['tax_pct']:g}%): ${totals['tax_amount']:,.2f}",
                ln=True,
            )
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(45, 74, 48)
        self._cell(pdf, 0, 9, f"Grand Total: ${totals['grand_total']:,.2f}", ln=True)
        pdf.set_text_color(0, 0, 0)

        if q.get("notes"):
            pdf.ln(4)
            pdf.set_font("Helvetica", "I", 9)
            self._cell(pdf, 0, 5, _pdf_safe(f"Notes: {q['notes']}"), ln=True)

        pdf.set_font("Helvetica", "", 8)
        pdf.ln(8)
        self._cell(pdf, 0, 5, store_footer[:120], ln=True)

        out = io.BytesIO()
        pdf.output(out)
        return out.getvalue()

    @staticmethod
    def _cell(pdf, w, h, text, ln=False):
        try:
            if ln:
                pdf.cell(w, h, text, new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(w, h, text)
        except TypeError:
            pdf.cell(w, h, text, ln=1 if ln else 0)
