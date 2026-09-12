"""Saved quotes in the app DB. Every mutation checks can()."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from backend.activity.log_activity import ActivityStore
from backend.app_db import get_app_connection, init_app_db
from backend.auth.permissions import AuthDenied, QuoteResource, can, require
from backend.auth.roles import SessionUser, email_local_part
from backend.county_sales_tax import get_county
from backend.quote.cart import CartLine, QuoteCart


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SavedQuote:
    id: int
    owner_id: int
    owner_name: str
    name: str
    client_name: str
    status: str
    tax_county: str | None
    tax_state: str | None
    tax_rate: float
    tax_exempt: bool
    lines: list[CartLine]


class QuoteStore:
    def __init__(self, db_path: Path, activity: ActivityStore | None = None) -> None:
        self.db_path = Path(db_path)
        init_app_db(self.db_path)
        self.activity = activity if activity is not None else ActivityStore(self.db_path)

    def _owner_name(self, owner_id: int) -> str:
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT name, email FROM users WHERE id = ?", (owner_id,)).fetchone()
        if not row:
            return ""
        return str(row["name"] or email_local_part(str(row["email"] or "")))

    def _load_lines(self, quote_id: int) -> list[CartLine]:
        with get_app_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM quote_lines WHERE quote_id = ? ORDER BY sort_order, id",
                (quote_id,),
            ).fetchall()
        lines: list[CartLine] = []
        for row in rows:
            opts = json.loads(row["options_snapshot"] or "{}")
            defaults = json.loads(row["default_options"] or "{}")
            if not isinstance(opts, dict):
                opts = {}
            if not isinstance(defaults, dict):
                defaults = dict(opts)
            lines.append(
                CartLine(
                    id=str(row["id"]),
                    product_id=str(row["product_id"] or ""),
                    sku=str(row["sku"] or ""),
                    name=str(row["name"]),
                    options_snapshot={str(k): str(v) for k, v in opts.items()},
                    default_options={str(k): str(v) for k, v in defaults.items()},
                    unit_price=float(row["unit_price"] or 0),
                    qty=max(1, int(row["qty"] or 1)),
                    notes=str(row["notes"] or ""),
                )
            )
        return lines

    def _saved(self, row: Mapping[str, object], lines: list[CartLine] | None = None) -> SavedQuote:
        owner_id = int(row["owner_id"])
        return SavedQuote(
            id=int(row["id"]),
            owner_id=owner_id,
            owner_name=self._owner_name(owner_id),
            name=str(row["name"] or ""),
            client_name=str(row["client_name"] or ""),
            status=str(row["status"] or "draft"),
            tax_county=str(row["tax_county"]) if row["tax_county"] else None,
            tax_state=str(row["tax_state"]) if row["tax_state"] else None,
            tax_rate=float(row["tax_rate"] or 0),
            tax_exempt=bool(row["tax_exempt"]),
            lines=lines if lines is not None else self._load_lines(int(row["id"])),
        )

    def _row(self, quote_id: int) -> Mapping[str, object] | None:
        with get_app_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
        return dict(row) if row else None

    def _assert_view(self, actor: SessionUser, quote_id: int) -> Mapping[str, object]:
        row = self._row(quote_id)
        if row is None:
            raise AuthDenied("Quote not found.", status_code=404, action="quote.view.own")
        resource = QuoteResource(owner_id=int(row["owner_id"]), quote_id=quote_id)
        if can(actor, "quote.view.team") or can(actor, "quote.view.own", resource):
            return row
        self.activity.log_activity(
            actor,
            action="quote.view.denied",
            status="denied",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="not owner",
        )
        raise AuthDenied("Quote not found.", status_code=404, action="quote.view.own")

    def _assert_edit(self, actor: SessionUser, quote_id: int) -> Mapping[str, object]:
        row = self._assert_view(actor, quote_id)
        resource = QuoteResource(owner_id=int(row["owner_id"]), quote_id=quote_id)
        if can(actor, "quote.edit.any") or can(actor, "quote.edit.own", resource):
            return row
        raise AuthDenied("Not allowed.", status_code=403, action="quote.edit.own")

    def create_quote(self, actor: SessionUser, name: str = "", client_name: str = "") -> int:
        require(actor, "quote.create")
        title = name.strip() or f"Quote {datetime.now().strftime('%Y-%m-%d')}"
        now = _now()
        with get_app_connection(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO quotes (
                    owner_id, name, client_name, status, tax_exempt, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', 0, ?, ?)
                """,
                (actor.id, title, client_name, now, now),
            )
            conn.commit()
            qid = int(cur.lastrowid)
        self.activity.log_activity(
            actor,
            action="quote.create",
            resource_type="quote",
            resource_id=str(qid),
            summary=title,
        )
        return qid

    def list_quotes(self, actor: SessionUser) -> list[SavedQuote]:
        if can(actor, "quote.view.team"):
            sql = "SELECT * FROM quotes ORDER BY updated_at DESC, id DESC"
            params: tuple[object, ...] = ()
        elif can(actor, "quote.view.own"):
            sql = "SELECT * FROM quotes WHERE owner_id = ? ORDER BY updated_at DESC, id DESC"
            params = (actor.id,)
        else:
            return []
        with get_app_connection(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._saved(dict(r), lines=[]) for r in rows]

    def get_quote(self, actor: SessionUser, quote_id: int) -> SavedQuote:
        row = self._assert_view(actor, quote_id)
        return self._saved(row)

    def add_line(
        self,
        actor: SessionUser,
        quote_id: int,
        row: Mapping[str, object],
        *,
        add_as_separate_line: bool = False,
    ) -> CartLine:
        self._assert_edit(actor, quote_id)
        cart = QuoteCart()
        cart.lines = self._load_lines(quote_id)
        line = cart.add_from_row(row, add_as_separate_line=add_as_separate_line)
        self._replace_lines(quote_id, cart.lines)
        self.activity.log_activity(
            actor,
            action="quote.line.add",
            resource_type="quote",
            resource_id=str(quote_id),
            summary=f"added {line.name}",
        )
        return line

    def remove_line(self, actor: SessionUser, quote_id: int, line_id: str) -> None:
        self._assert_edit(actor, quote_id)
        lines = [ln for ln in self._load_lines(quote_id) if ln.id != line_id]
        self._replace_lines(quote_id, lines)
        self.activity.log_activity(
            actor,
            action="quote.line.remove",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="removed line",
        )

    def set_qty(self, actor: SessionUser, quote_id: int, line_id: str, qty: int) -> None:
        self._assert_edit(actor, quote_id)
        cart = QuoteCart()
        cart.lines = self._load_lines(quote_id)
        cart.set_qty(line_id, qty)
        self._replace_lines(quote_id, cart.lines)
        self.activity.log_activity(
            actor,
            action="quote.line.qty",
            resource_type="quote",
            resource_id=str(quote_id),
            summary=f"qty {qty}",
        )

    def reset_line(self, actor: SessionUser, quote_id: int, line_id: str) -> None:
        self._assert_edit(actor, quote_id)
        cart = QuoteCart()
        cart.lines = self._load_lines(quote_id)
        cart.reset_line_options(line_id)
        self._replace_lines(quote_id, cart.lines)
        self.activity.log_activity(
            actor,
            action="quote.line.reset",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="reset options",
        )

    def select_tax(self, actor: SessionUser, quote_id: int, county: str, state: str) -> None:
        require(actor, "tax.select")
        self._assert_edit(actor, quote_id)
        rate = get_county(county, state)
        if rate is None:
            raise AuthDenied("Unknown county.", status_code=400, action="tax.select")
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE quotes
                SET tax_county = ?, tax_state = ?, tax_rate = ?, tax_exempt = 0, updated_at = ?
                WHERE id = ?
                """,
                (rate.county, rate.state, rate.rate, _now(), quote_id),
            )
            conn.commit()
        self.activity.log_activity(
            actor,
            action="quote.tax.select",
            resource_type="quote",
            resource_id=str(quote_id),
            summary=f"{rate.county} {rate.state} {rate.rate}",
            metadata={"county": rate.county, "state": rate.state, "rate": rate.rate},
        )

    def set_exempt(self, actor: SessionUser, quote_id: int, exempt: bool) -> None:
        require(actor, "tax.select")
        self._assert_edit(actor, quote_id)
        with get_app_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE quotes
                SET tax_exempt = ?, tax_rate = CASE WHEN ? THEN 0 ELSE tax_rate END, updated_at = ?
                WHERE id = ?
                """,
                (1 if exempt else 0, 1 if exempt else 0, _now(), quote_id),
            )
            conn.commit()
        self.activity.log_activity(
            actor,
            action="quote.tax.exempt" if exempt else "quote.tax.select",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="Exempt" if exempt else "tax not exempt",
        )

    def clear_quote(self, actor: SessionUser, quote_id: int) -> None:
        self._assert_edit(actor, quote_id)
        with get_app_connection(self.db_path) as conn:
            conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
            conn.execute(
                """
                UPDATE quotes
                SET tax_county = NULL, tax_state = NULL, tax_rate = NULL,
                    tax_exempt = 0, updated_at = ?
                WHERE id = ?
                """,
                (_now(), quote_id),
            )
            conn.commit()
        self.activity.log_activity(
            actor,
            action="quote.clear",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="cleared quote",
        )

    def delete_quote(self, actor: SessionUser, quote_id: int) -> None:
        row = self._assert_view(actor, quote_id)
        resource = QuoteResource(owner_id=int(row["owner_id"]), quote_id=quote_id)
        if not (can(actor, "quote.delete.any") or can(actor, "quote.delete.own", resource)):
            raise AuthDenied("Not allowed.", status_code=403, action="quote.delete.own")
        with get_app_connection(self.db_path) as conn:
            conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
            conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
            conn.commit()
        self.activity.log_activity(
            actor,
            action="quote.delete",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="deleted quote",
        )

    def update_header(
        self,
        actor: SessionUser,
        quote_id: int,
        *,
        name: str | None = None,
        client_name: str | None = None,
    ) -> None:
        self._assert_edit(actor, quote_id)
        sets = ["updated_at = ?"]
        vals: list[object] = [_now()]
        if name is not None:
            sets.append("name = ?")
            vals.append(name)
        if client_name is not None:
            sets.append("client_name = ?")
            vals.append(client_name)
        vals.append(quote_id)
        with get_app_connection(self.db_path) as conn:
            conn.execute(f"UPDATE quotes SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()
        self.activity.log_activity(
            actor,
            action="quote.update",
            resource_type="quote",
            resource_id=str(quote_id),
            summary="updated header",
        )

    def save_from_cart(self, actor: SessionUser, cart: QuoteCart) -> int:
        require(actor, "quote.create")
        if cart.quote_id:
            qid = cart.quote_id
            self._assert_edit(actor, qid)
        else:
            qid = self.create_quote(actor, name=cart.name, client_name=cart.client_name)
            cart.quote_id = qid
        self._replace_lines(qid, cart.lines)
        if cart.exempt:
            self.set_exempt(actor, qid, True)
        elif cart.county:
            self.select_tax(actor, qid, cart.county.county, cart.county.state)
        if cart.name or cart.client_name:
            self.update_header(actor, qid, name=cart.name or None, client_name=cart.client_name)
        return qid

    def _replace_lines(self, quote_id: int, lines: list[CartLine]) -> None:
        with get_app_connection(self.db_path) as conn:
            conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
            for i, line in enumerate(lines):
                conn.execute(
                    """
                    INSERT INTO quote_lines (
                        id, quote_id, product_id, sku, name, options_snapshot,
                        default_options, unit_price, qty, notes, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        line.id,
                        quote_id,
                        line.product_id,
                        line.sku,
                        line.name,
                        json.dumps(line.options_snapshot),
                        json.dumps(line.default_options),
                        line.unit_price,
                        line.qty,
                        line.notes,
                        i,
                    ),
                )
            conn.execute("UPDATE quotes SET updated_at = ? WHERE id = ?", (_now(), quote_id))
            conn.commit()
