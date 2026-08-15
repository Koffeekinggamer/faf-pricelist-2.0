"""Verify duplicate groups before any cleanup.

The identity key (vendor + collection + part + species + finish + option
+ dimensions) can collide for legitimate catalog rows:

- One SKU × wood species is the catalog, not a duplicate.
- Queen vs Full can share a part number when size lives in description
  and ``dimensions`` is empty.

Always inspect the actual rows. Cleanup may delete only when every row
is the same sellable configuration.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Fields that distinguish a real sellable row from a copy.
VERIFY_FIELDS = (
    "part_number",
    "collection",
    "description",
    "dimensions",
    "species",
    "finish_state",
    "option_key",
    "line_kind",
    "base_price",
)

VERIFY_SELECT = (
    "id, imported_at, part_number, collection, description, dimensions, "
    "species, finish_state, option_key, line_kind, base_price"
)


def _norm(field: str, value: Any) -> Any:
    if field == "base_price":
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None
    s = str(value or "").strip().lower()
    if s in {"none", "nan", "null"}:
        return ""
    return " ".join(s.split())


def verify_duplicate_group(rows: Sequence[Mapping[str, Any]]) -> tuple[bool, str]:
    """True only when every row is the same sellable configuration."""
    if len(rows) < 2:
        return False, "need two or more rows"
    first = {field: _norm(field, rows[0].get(field)) for field in VERIFY_FIELDS}
    for row in rows[1:]:
        for field in VERIFY_FIELDS:
            if _norm(field, row.get(field)) != first[field]:
                return False, f"distinct catalog rows: {field} differs"
    return True, ""
