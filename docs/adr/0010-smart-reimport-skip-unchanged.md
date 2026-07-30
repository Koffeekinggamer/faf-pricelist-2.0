# Smart re-import: skip unchanged builder books

When a builder pricelist is dropped or synced, compare the new book to that builder’s last successful import. If the wholesale catalog is unchanged → **skip** (no wipe/reload). If pricing or sellable items changed → **`replace_vendor`** for that builder (all items).

Locked from wayfinder map [Smart re-import: skip unchanged builder books](https://github.com/Koffeekinggamer/faf-pricelist-2.0/issues/20) — Judson accepted **recommended** answers for the frontier (and the then-unblocked tickets).

## Decisions

| Decision                  | Choice                                                                                                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Equality (“no change”)    | **Wholesale fingerprint** — hash of sorted sellable identities + `base_price` after standardize. Ignore `imported_at`, `adjusted_price`, `source_file`, multiplier/retail.       |
| Surfaces                  | **All paths through `PriceBookService.add_rows`** (Drop, Viztech, CLI/batch). Optional Drop preflight caption.                                                                   |
| Fingerprint store         | **`vendors` columns** (`last_import_fingerprint`, `last_import_source`, `last_imported_at`; optional `fingerprint_version`). See `docs/wayfinder/smart-reimport-fingerprint.md`. |
| On change                 | **`replace_vendor`** (full builder book swap). Not price-only upsert (orphans).                                                                                                  |
| New filename, same prices | **Skip** — filename alone is not a price change. May update stored `last_import_source` without wiping rows.                                                                     |
| Drop UI on skip           | **Per-file status + toast** (“unchanged, skipped”). No forced confirm for skip.                                                                                                  |

## Out of scope (unchanged)

Multiplier-only changes; OrderTrac; committing DB; cross-builder bulk diff jobs.

**Status:** accepted
