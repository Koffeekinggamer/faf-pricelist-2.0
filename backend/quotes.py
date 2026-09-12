"""Quote builder data access and export."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from backend.db import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _quote_number() -> str:
    return "Q-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_quote_name() -> str:
    return f"Quote {date.today().isoformat()}"


def _line_total(qty: float, unit_retail: float, line_discount_pct: float = 0) -> float:
    qty = float(qty or 0)
    unit = float(unit_retail or 0)
    disc = float(line_discount_pct or 0) / 100.0
    return round(qty * unit * (1.0 - disc), 2)


def _finite_price(value: Any) -> Optional[float]:
    """Coerce a price field; treat None/NaN/non-numeric as missing."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _unit_retail_from_row(row: Optional[dict]) -> Optional[float]:
    """Retail from adjusted_price, else wholesale × multiplier (even-dollar)."""
    if not row:
        return None
    unit_retail = _finite_price(row.get("adjusted_price"))
    if unit_retail is None and _finite_price(row.get("base_price")) is not None:
        from backend.pricing import retail_from_wholesale

        mult = _finite_price(row.get("multiplier")) or 2.7
        unit_retail = retail_from_wholesale(row.get("base_price"), mult)
    return unit_retail


def _options_json(options: Any) -> str:
    if not options:
        return "{}"
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except (TypeError, ValueError):
            options = {str(options): 1}
    return json.dumps(options, sort_keys=True, separators=(",", ":"))


def _configuration_key(row: dict, options_json: str) -> str:
    identity = {
        "pricebook_id": row.get("pricebook_id", row.get("id")),
        "part_number": row.get("part_number") or "",
        "species": row.get("species") or "",
        "dimensions": row.get("dimensions") or "",
        "finish_state": row.get("finish_state") or "",
        "unit_retail": round(float(row.get("unit_retail", row.get("adjusted_price")) or 0), 4),
        "options": json.loads(options_json or "{}"),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
        quote_name: str = "",
        discount_pct: float = 0,
        tax_pct: float = 0,
    ) -> int:
        now = _now()
        qn = _quote_number()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO quotes (
                    quote_number, quote_name, customer_name, customer_phone, customer_email,
                    status, notes, discount_pct, tax_pct, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
                """,
                (
                    qn,
                    quote_name.strip() or _default_quote_name(),
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
            "quote_name",
            "customer_name",
            "customer_phone",
            "customer_email",
            "status",
            "notes",
            "discount_pct",
            "tax_pct",
            "tax_state",
            "tax_county",
            "tax_exempt",
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
        default_pricebook_row: Optional[dict] = None,
        options: Any = None,
        merge_existing: bool = False,
        qty: float = 1.0,
        line_discount_pct: float = 0.0,
        notes: str = "",
    ) -> int:
        qty = max(1.0, float(qty or 1))
        unit_base = pricebook_row.get("base_price")
        unit_retail = _unit_retail_from_row(pricebook_row)

        default_row = dict(default_pricebook_row or pricebook_row)
        default_unit_base = default_row.get("base_price")
        default_unit_retail = _unit_retail_from_row(default_row)
        # #region agent log
        try:
            import json as _json
            import time as _time

            open("/opt/cursor/logs/debug.log", "a").write(
                _json.dumps(
                    {
                        "hypothesisId": "A",
                        "location": "quotes.py:add_line_from_pricebook",
                        "message": "default retail snapshot at add",
                        "data": {
                            "pricebook_id": pricebook_row.get("id"),
                            "cfg_base": unit_base,
                            "cfg_adj": pricebook_row.get("adjusted_price"),
                            "cfg_unit_retail": unit_retail,
                            "def_base": default_unit_base,
                            "def_adj": default_row.get("adjusted_price"),
                            "def_unit_retail": default_unit_retail,
                            "def_mult": default_row.get("multiplier"),
                            "had_default_row_arg": default_pricebook_row is not None,
                            "runId": "post-fix",
                        },
                        "timestamp": int(_time.time() * 1000),
                    }
                )
                + "\n"
            )
        except Exception:
            pass
        # #endregion
        selected_options = options
        if selected_options is None and pricebook_row.get("option_key"):
            selected_options = {str(pricebook_row["option_key"]): 1}
        default_options = (
            {str(default_row["option_key"]): 1} if default_row.get("option_key") else {}
        )
        selected_options_json = _options_json(selected_options)
        default_options_json = _options_json(default_options)
        configured = {
            **pricebook_row,
            "pricebook_id": pricebook_row.get("id"),
            "unit_retail": unit_retail,
        }
        config_key = _configuration_key(configured, selected_options_json)

        with self._conn() as conn:
            if merge_existing:
                existing = conn.execute(
                    """
                    SELECT id, qty, unit_retail, line_discount_pct
                    FROM quote_lines
                    WHERE quote_id = ? AND configuration_key = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (quote_id, config_key),
                ).fetchone()
                if existing:
                    merged_qty = max(1.0, float(existing["qty"] or 0) + qty)
                    merged_total = _line_total(
                        merged_qty,
                        existing["unit_retail"] or 0,
                        existing["line_discount_pct"] or 0,
                    )
                    conn.execute(
                        "UPDATE quote_lines SET qty = ?, line_total = ? WHERE id = ?",
                        (merged_qty, merged_total, existing["id"]),
                    )
                    conn.execute(
                        "UPDATE quotes SET updated_at = ? WHERE id = ?",
                        (_now(), quote_id),
                    )
                    conn.commit()
                    return int(existing["id"])

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
                    qty, unit_base, unit_retail, line_discount_pct, line_total, notes,
                    options_json, default_options_json, configuration_key,
                    default_unit_base, default_unit_retail, default_species,
                    default_dimensions, default_finish_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    selected_options_json,
                    default_options_json,
                    config_key,
                    default_unit_base,
                    default_unit_retail,
                    default_row.get("species"),
                    default_row.get("dimensions"),
                    default_row.get("finish_state"),
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
            "dimensions",
            "finish_state",
            "vendor",
            "collection",
            "options_json",
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
                    data[k] = _options_json(v) if k == "options_json" else v
            data["line_total"] = _line_total(
                data.get("qty") or 0,
                data.get("unit_retail") or 0,
                data.get("line_discount_pct") or 0,
            )
            data["configuration_key"] = _configuration_key(
                data, data.get("options_json") or "{}"
            )
            conn.execute(
                """
                UPDATE quote_lines SET
                    qty = ?, unit_retail = ?, unit_base = ?,
                    line_discount_pct = ?, description = ?, notes = ?,
                    part_number = ?, species = ?, dimensions = ?, finish_state = ?,
                    vendor = ?, collection = ?, line_total = ?,
                    options_json = ?, configuration_key = ?
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
                    data.get("dimensions"),
                    data.get("finish_state"),
                    data.get("vendor"),
                    data.get("collection"),
                    data.get("line_total"),
                    data.get("options_json") or "{}",
                    data.get("configuration_key"),
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

    def reset_line_options(self, line_id: int) -> bool:
        """Restore a cart line's original catalog configuration in place."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM quote_lines WHERE id = ?", (line_id,)
            ).fetchone()
            if not row:
                return False
            data = dict(row)
            # #region agent log
            try:
                import json as _json
                import time as _time
                open("/opt/cursor/logs/debug.log", "a").write(
                    _json.dumps(
                        {
                            "hypothesisId": "A,C",
                            "location": "quotes.py:reset_line_options:before",
                            "message": "reset inputs from stored defaults",
                            "data": {
                                "line_id": line_id,
                                "before_unit_retail": data.get("unit_retail"),
                                "before_line_total": data.get("line_total"),
                                "default_unit_retail": data.get("default_unit_retail"),
                                "default_unit_base": data.get("default_unit_base"),
                                "default_options_json": data.get("default_options_json"),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            except Exception:
                pass
            # #endregion
            default_unit_retail = data.get("default_unit_retail")
            # Heal lines snapshotted before default retail was computed from
            # wholesale × multiplier (Reset was writing NULL → $0.00).
            if default_unit_retail is None and data.get("default_unit_base") is not None:
                from backend.pricing import retail_from_wholesale

                mult = 2.7
                pb_id = data.get("pricebook_id")
                if pb_id is not None:
                    pb = conn.execute(
                        "SELECT multiplier FROM pricebook WHERE id = ?",
                        (int(pb_id),),
                    ).fetchone()
                    if pb is not None and pb["multiplier"] is not None:
                        mult = float(pb["multiplier"])
                default_unit_retail = retail_from_wholesale(
                    data.get("default_unit_base"), mult
                )
                data["default_unit_retail"] = default_unit_retail
            data.update(
                {
                    "unit_base": data.get("default_unit_base"),
                    "unit_retail": default_unit_retail,
                    "species": data.get("default_species"),
                    "dimensions": data.get("default_dimensions"),
                    "finish_state": data.get("default_finish_state"),
                    "options_json": data.get("default_options_json") or "{}",
                }
            )
            data["line_total"] = _line_total(
                data.get("qty") or 1,
                data.get("unit_retail") or 0,
                data.get("line_discount_pct") or 0,
            )
            data["configuration_key"] = _configuration_key(
                data, data["options_json"]
            )
            conn.execute(
                """
                UPDATE quote_lines SET
                    unit_base = ?, unit_retail = ?, species = ?, dimensions = ?,
                    finish_state = ?, options_json = ?, configuration_key = ?,
                    line_total = ?, default_unit_retail = ?
                WHERE id = ?
                """,
                (
                    data.get("unit_base"),
                    data.get("unit_retail"),
                    data.get("species"),
                    data.get("dimensions"),
                    data.get("finish_state"),
                    data.get("options_json"),
                    data.get("configuration_key"),
                    data.get("line_total"),
                    data.get("default_unit_retail"),
                    line_id,
                ),
            )
            conn.execute(
                "UPDATE quotes SET updated_at = ? WHERE id = ?",
                (_now(), data["quote_id"]),
            )
            conn.commit()
            # #region agent log
            try:
                import json as _json
                import time as _time
                open("/opt/cursor/logs/debug.log", "a").write(
                    _json.dumps(
                        {
                            "hypothesisId": "A,C",
                            "location": "quotes.py:reset_line_options:after",
                            "message": "reset wrote unit_retail/line_total",
                            "data": {
                                "line_id": line_id,
                                "after_unit_retail": data.get("unit_retail"),
                                "after_unit_base": data.get("unit_base"),
                                "after_line_total": data.get("line_total"),
                                "ui_float_or_0": float(data.get("unit_retail") or 0),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            except Exception:
                pass
            # #endregion
            return True

    def clear_quote(self, quote_id: int, *, confirmed: bool = False) -> bool:
        """Clear cart lines and tax only after an explicit confirmation."""
        if not confirmed:
            return False
        with self._conn() as conn:
            conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
            conn.execute(
                """
                UPDATE quotes
                SET tax_pct = 0, tax_state = NULL, tax_county = NULL,
                    tax_exempt = 0, updated_at = ?
                WHERE id = ?
                """,
                (_now(), quote_id),
            )
            conn.commit()
        return True

    def totals(self, quote_id: int) -> dict[str, Any]:
        q = self.get_quote(quote_id) or {}
        lines = self.list_lines(quote_id)
        subtotal = float(lines["line_total"].sum()) if not lines.empty else 0.0
        disc_pct = float(q.get("discount_pct") or 0)
        stored_tax_pct = float(q.get("tax_pct") or 0)
        tax_exempt = bool(q.get("tax_exempt"))
        tax_pct = 0.0 if tax_exempt else stored_tax_pct
        after_disc = round(subtotal * (1.0 - disc_pct / 100.0), 2)
        tax = round(after_disc * (tax_pct / 100.0), 2)
        grand = round(after_disc + tax, 2)
        return {
            "subtotal": round(subtotal, 2),
            "discount_pct": disc_pct,
            "discount_amount": round(subtotal - after_disc, 2),
            "tax_pct": tax_pct,
            "stored_tax_pct": stored_tax_pct,
            "tax_amount": tax,
            "tax_exempt": tax_exempt,
            "tax_label": "Exempt" if tax_exempt else (f"{tax_pct:g}%" if tax_pct else ""),
            "grand_total": grand,
            "line_count": len(lines),
            "item_count": (
                int(lines["qty"].sum())
                if not lines.empty and float(lines["qty"].sum()).is_integer()
                else (float(lines["qty"].sum()) if not lines.empty else 0)
            ),
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
