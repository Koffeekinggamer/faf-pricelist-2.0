# FAF Price Book

Floor price book for **Foothills Amish Furniture** — Streamlit + SQLite catalog so showroom staff can look up **retail** prices by builder, wood, and finish. Current product focus is **catalog accuracy** (Search · Drop files · Vendors · Admin). OrderTrac quoting stays in code but is UI-hidden.

## Language

### Catalog & pricing

**Builder**:
The Amish factory / manufacturer whose price list we sell. Same entity as **vendor** in the DB — always one canonical display name.
_Avoid_: manufacturer (in UI copy), supplier, brand alias, filename stem as a second identity

**Vendor**:
DB / code name for a **builder**. One builder = one vendor forever.
_Avoid_: second vendor row for the same factory under a different spelling

**Master price book**:
The long-form SQLite catalog (`master_pricebook.db`) — one sellable row per SKU × species × finish.
_Avoid_: wide workbook as source of truth, “pricelist file” after import

**Part number**:
Canonical SKU / item code on a row (or full item name when the builder has no SKU).
_Avoid_: sheet name, option-line junk, HTML-entity twin codes

**Collection**:
Product category within a builder (e.g. Seating, Casegoods) — not a spreadsheet tab name.
_Avoid_: sheet title, upcharge section name

**Species**:
Wood tier **or** color/fabric option on the row (slash-separated woods, Title Case).
_Avoid_: `col_N`, bare `FINISHED`, raw column headers

**Option** / **addon charge**:
A builder upcharge or specialty adder — e.g. +% over base for certain woods, or a listed specialty change that is not the main SKU×wood×finish sellable row. Floor **Option** dropdown should surface these when present.
_Avoid_: treating finish Cat.N / fabric _tier labels_ as the only meaning of Option; treating raw adder dollars as full chair retail (FN fabric adder columns are skipped on purpose)

**Finish state**:
Only `finished` or `unfinished` (default `finished` for floor search).
_Avoid_: free-text finish names in this field

**Wholesale** / **base price**:
Builder list price before Foothills markup (`price_basis` = `wholesale`).
_Avoid_: retail as import source, “cost” without saying wholesale

**Multiplier**:
Per-vendor markup factor. Default **2.7**; **Genuine Oak 1.7**.
_Avoid_: hardcoded global 2.7 ignoring vendor overrides, workbook markup as silent default over saved mult

**Retail** / **adjusted price**:
Customer price = `round(wholesale × multiplier, 2)`. What Search shows as RETAIL.
_Avoid_: calling wholesale “price” in floor-facing copy

**Replace vendor**:
Default re-import mode: delete that builder’s rows, then load the new book. One builder = one catalog.
_Avoid_: append (creates duplicates), upsert as the everyday default

**Thin catalog**:
A builder with fewer than **150** sellable rows in the master price book (after standardize). Candidates for keep / replace / ignore decisions.
_Avoid_: treating every small specialty line as broken; conflating with IGNORE_BUILDERS (PDF-only / deliberate skip)

### Product surfaces

**Accuracy mode**:
The live UI: Search · Drop files · Vendors · Admin. OrderTrac tabs/flags off.
_Avoid_: re-enabling OrderTrac UI without explicit ask from Judson

**Search**:
Floor lookup with boolean query + builder/collection/finish filters; pinned builders on the right.
_Avoid_: putting business logic only in Streamlit widgets

**Drop files**:
Manager import path for Excel/PDF builder books into the master price book.
_Avoid_: floor staff using Drop for day-to-day lookups

**Vendors tab**:
Edit per-builder multiplier and phone; items/collections counts are informational.
_Avoid_: creating a second vendor for a renamed file

**Viztech**:
Preferred-dealer portal used for monthly builder pricelist sync (`scripts/viztech_sync.py`).
_Avoid_: wiping non-Viztech builders during sync

**OrderTrac**:
External order/quote system — backend kept, UI gated by `SHOW_ORDERTRAC_* = False`.
_Avoid_: treating OrderTrac as the current floor workflow

### Engineering seams

**PriceBookService**:
Facade for all real operations (`backend/service.py`). UI stays thin.
_Avoid_: embedding import/search/pricing rules only in `pricebook_app.py`

**Standardize**:
Canonicalization of vendor/species/finish (`backend/standardize.py` + `STANDARDS.md`).
_Avoid_: leaving raw builder column junk in the master DB

**Agent skills config**:
FAF overlays for installed agent skills — canonical under `.agents/skills/setup-matt-pocock-skills/`, mirrored to `docs/agents/` (ADR-0006).
_Avoid_: editing only `docs/agents/` and letting seeds drift; treating upstream generic seed examples as live FAF rules

## Locked vocabulary pointers

- Row shape rules: `STANDARDS.md`
- Operator / agent handoff: `HANDOFF.md`
- Floor staff: `FLOOR_CHEAT_SHEET.md`
- Architecture decisions: `docs/adr/`
