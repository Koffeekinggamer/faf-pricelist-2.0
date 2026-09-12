# Smart re-import: skip unchanged builder books

When a builder pricelist is dropped or synced, compare the new book to that builder’s last successful import. If the wholesale catalog is unchanged → **skip** (no wipe/reload). If pricing, sellable items, or addon options changed → **`replace_vendor`** for that builder (all rows).

Locked from wayfinder map [Smart re-import: skip unchanged builder books](https://github.com/Koffeekinggamer/faf-pricelist-2.0/issues/20) — Judson accepted **recommended** answers for the frontier (and the then-unblocked tickets).

## Decisions

| Decision                  | Choice                                                                                                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Equality (“no change”)    | **Wholesale fingerprint** — hash of sorted item and addon identities + `base_price` / `addon_pct` after standardize. Ignore `imported_at`, `adjusted_price`, `source_file`, multiplier/retail. |
| Surfaces                  | **All paths through `PriceBookService.add_rows`** (Drop, Viztech, CLI/batch). Optional Drop preflight caption.                                                                   |
| Fingerprint store         | **`vendors` columns** (`last_import_fingerprint`, `last_import_source`, `last_imported_at`; optional `fingerprint_version`). See `docs/wayfinder/smart-reimport-fingerprint.md`. |
| On change                 | **`replace_vendor`** (full builder book swap). Not price-only upsert (orphans).                                                                                                  |
| New filename, same prices | **Skip** — filename alone is not a price change. May update stored `last_import_source` without wiping rows.                                                                     |
| Drop UI on skip           | **Per-file status + toast** (“unchanged, skipped”). No forced confirm for skip.                                                                                                  |

## Out of scope (unchanged)

Multiplier-only changes; OrderTrac; committing DB; cross-builder bulk diff jobs.

## Implementation

The deep Drop Load operation computes the versioned wholesale fingerprint before `replace_vendor`. Addon rows are part of equality: a newly captured Options page must replace a previously item-only catalog even when every sellable row is unchanged. An equal fingerprint skips the catalog wipe/reload, updates the stored source/import time, still applies an explicitly confirmed multiplier, and refreshes safe Builder Profile parser metadata. CLI and Viztech continue through the lower-level `add_rows` path.

**Status:** accepted

Wayfinder issues **#20–#31** are superseded by this ADR. Do not re-open them as a backlog — see [`docs/wayfinder/README.md`](../wayfinder/README.md). The fingerprint research note is tombstoned.
