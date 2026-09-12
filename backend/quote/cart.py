"""In-memory quote cart: merge rules, qty, tax selection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Mapping

from backend.county_sales_tax import CountyRate, format_county_selection, get_county
from backend.pricing import catalog_retail, retail_from_wholesale


@dataclass
class CartLine:
    id: str
    product_id: str
    sku: str
    name: str
    options_snapshot: dict[str, str]
    unit_price: float
    qty: int = 1
    notes: str = ""
    default_options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.qty < 1:
            self.qty = 1
        if not self.default_options:
            self.default_options = dict(self.options_snapshot)


def line_total(line: CartLine) -> float:
    return round(float(line.unit_price) * int(line.qty), 2)


def priced_catalog_row(
    *,
    sku: str,
    name: str,
    wholesale: float,
    multiplier: float = 2.7,
    options: Mapping[str, str] | None = None,
    product_id: str = "",
    line_kind: str = "item",
    option_key: str = "",
) -> dict[str, object]:
    """Build a Search-shaped row using the existing retail engine (not a second formula)."""
    retail = catalog_retail(
        wholesale,
        multiplier,
        line_kind=line_kind,
        option_key=option_key or (options or {}).get("option_key"),
    )
    if retail is None:
        retail = retail_from_wholesale(wholesale, multiplier)
    opts = {str(k): str(v) for k, v in dict(options or {}).items()}
    return {
        "id": product_id or sku,
        "part_number": sku,
        "description": name,
        "base_price": float(wholesale),
        "multiplier": float(multiplier),
        "adjusted_price": retail,
        "species": opts.get("wood", ""),
        "finish_state": opts.get("finish", ""),
        "option_key": opts.get("option_key", option_key),
        "dimensions": opts.get("size", ""),
        "options_snapshot": opts,
        "line_kind": line_kind,
    }


def _options_from_row(row: Mapping[str, object]) -> dict[str, str]:
    snap = row.get("options_snapshot")
    if isinstance(snap, Mapping):
        return {str(k): str(v) for k, v in snap.items()}
    return {
        "wood": str(row.get("species") or ""),
        "finish": str(row.get("finish_state") or ""),
        "size": str(row.get("dimensions") or ""),
        "option_key": str(row.get("option_key") or ""),
    }


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unit_price_from_row(row: Mapping[str, object]) -> float:
    retail = row.get("adjusted_price")
    parsed = _as_float(retail)
    if parsed is not None:
        return parsed
    priced = catalog_retail(
        _as_float(row.get("base_price")),
        _as_float(row.get("multiplier")),
        line_kind=str(row.get("line_kind") or "item"),
        option_key=row.get("option_key"),
    )
    if priced is None:
        raise ValueError("catalog row has no retail price")
    return float(priced)


def _options_key(
    product_id: str, options: Mapping[str, str]
) -> tuple[str, tuple[tuple[str, str], ...]]:
    items = tuple(sorted((str(k), str(v)) for k, v in options.items()))
    return (product_id, items)


class QuoteCart:
    """Scratch-pad cart. Persist via QuoteStore; session_state wraps this."""

    def __init__(self) -> None:
        self.lines: list[CartLine] = []
        self.name: str = ""
        self.client_name: str = ""
        self.county: CountyRate | None = None
        self.exempt: bool = False
        self.quote_id: int | None = None

    @property
    def badge_count(self) -> int:
        return len(self.lines)

    @property
    def tax_rate(self) -> float:
        if self.exempt or self.county is None:
            return 0.0
        return float(self.county.rate)

    @property
    def tax_label(self) -> str:
        if self.exempt:
            return "Exempt"
        if self.county is None:
            return "Select delivery county"
        return format_county_selection(self.county)

    def line(self, line_id: str) -> CartLine:
        for row in self.lines:
            if row.id == line_id:
                return row
        raise KeyError(line_id)

    def add_from_row(
        self,
        row: Mapping[str, object],
        *,
        qty: int = 1,
        add_as_separate_line: bool = False,
        notes: str = "",
    ) -> CartLine:
        options = _options_from_row(row)
        product_id = str(row.get("id") or row.get("part_number") or "")
        sku = str(row.get("part_number") or product_id)
        name = str(row.get("description") or row.get("name") or sku)
        unit = _unit_price_from_row(row)
        amount = max(1, int(qty))
        if not add_as_separate_line:
            key = _options_key(product_id, options)
            for existing in self.lines:
                if _options_key(existing.product_id, existing.options_snapshot) == key:
                    existing.qty += amount
                    return existing
        line = CartLine(
            id=uuid.uuid4().hex,
            product_id=product_id,
            sku=sku,
            name=name,
            options_snapshot=dict(options),
            default_options=dict(options),
            unit_price=unit,
            qty=amount,
            notes=notes,
        )
        self.lines.append(line)
        return line

    def set_qty(self, line_id: str, qty: int) -> CartLine:
        line = self.line(line_id)
        line.qty = max(1, int(qty))
        return line

    def set_notes(self, line_id: str, notes: str) -> CartLine:
        line = self.line(line_id)
        line.notes = notes
        return line

    def set_line_options(self, line_id: str, options: Mapping[str, str]) -> CartLine:
        line = self.line(line_id)
        line.options_snapshot = {str(k): str(v) for k, v in options.items()}
        return line

    def reset_line_options(self, line_id: str) -> CartLine:
        line = self.line(line_id)
        line.options_snapshot = dict(line.default_options)
        return line

    def remove_line(self, line_id: str) -> None:
        self.lines = [row for row in self.lines if row.id != line_id]

    def select_county(self, county: str, state: str) -> CountyRate:
        row = get_county(county, state)
        if row is None:
            raise ValueError(f"unknown county {county}, {state}")
        self.county = row
        self.exempt = False
        return row

    def set_exempt(self, exempt: bool) -> None:
        self.exempt = bool(exempt)

    def clear_quote(self) -> None:
        self.lines = []
        self.county = None
        self.exempt = False
        self.client_name = ""
        self.quote_id = None

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "client_name": self.client_name,
            "quote_id": self.quote_id,
            "exempt": self.exempt,
            "county": (
                {"county": self.county.county, "state": self.county.state} if self.county else None
            ),
            "lines": [
                {
                    "id": ln.id,
                    "product_id": ln.product_id,
                    "sku": ln.sku,
                    "name": ln.name,
                    "options_snapshot": dict(ln.options_snapshot),
                    "default_options": dict(ln.default_options),
                    "unit_price": ln.unit_price,
                    "qty": ln.qty,
                    "notes": ln.notes,
                }
                for ln in self.lines
            ],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object] | None) -> QuoteCart:
        cart = cls()
        if not payload:
            return cart
        cart.name = str(payload.get("name") or "")
        cart.client_name = str(payload.get("client_name") or "")
        qid = payload.get("quote_id")
        cart.quote_id = int(qid) if qid is not None else None
        cart.exempt = bool(payload.get("exempt"))
        county = payload.get("county")
        if isinstance(county, Mapping):
            cart.county = get_county(
                str(county.get("county") or ""), str(county.get("state") or "")
            )
        for raw in payload.get("lines") or []:
            if not isinstance(raw, Mapping):
                continue
            opts = {str(k): str(v) for k, v in dict(raw.get("options_snapshot") or {}).items()}
            defaults = {str(k): str(v) for k, v in dict(raw.get("default_options") or opts).items()}
            cart.lines.append(
                CartLine(
                    id=str(raw.get("id") or uuid.uuid4().hex),
                    product_id=str(raw.get("product_id") or ""),
                    sku=str(raw.get("sku") or ""),
                    name=str(raw.get("name") or ""),
                    options_snapshot=opts,
                    default_options=defaults,
                    unit_price=float(raw.get("unit_price") or 0),
                    qty=max(1, int(raw.get("qty") or 1)),
                    notes=str(raw.get("notes") or ""),
                )
            )
        return cart

    def clone(self) -> QuoteCart:
        copy = QuoteCart.from_payload(self.to_payload())
        copy.lines = [replace(ln) for ln in copy.lines]
        return copy
