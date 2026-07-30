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
A builder upcharge or specialty adder — e.g. +% over base for certain woods, or a listed specialty change that is not the main SKU×wood×finish sellable row. Stored as `line_kind=addon` (ADR-0008). Floor **Option** dropdown surfaces these when present; Search hides them unless Option is filtered to that adder.
_Avoid_: treating finish Cat.N / fabric _tier labels_ as the only meaning of Option; treating raw adder dollars as full chair retail

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

**Drop parse session**:
One parse of a Drop batch: post-standardize wholesale rows on disk behind an opaque session id; UI keeps only the id plus per-file builder/multiplier widget defaults. Multiplier and builder bind at commit (via the write path), not by rewriting the session. Invalidated by new upload set, markup-preference toggle, explicit Re-parse, successful Load/Clear, or TTL (~24h).
_Avoid_: holding full row lists in Streamlit session state; re-parsing when builder/mult widgets change; baking retail into the parse cache; a separate write path that only Drop uses

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

**User-invoked skill**:
Typed by Judson / the human as a primary flow step (`/grill-with-docs`, `/implement`, …). See `docs/agents/skill-process.md`.
_Avoid_: typing model-invoked skills (`/tdd`, `/code-review`, `/domain-modeling`) as the main entry

**Model-invoked skill**:
Reached by an orchestrator skill or the agent (`/tdd` from `/implement`, `/domain-modeling` from `/grill-with-docs`).
_Avoid_: treating these as the preferred typed chain

**Tracer-bullet ticket**:
Vertical slice with one-sentence user-observable behavior + recorded blockers (binary kill test).
_Avoid_: horizontal tickets (“fix all importers”) with no observable floor outcome

## Locked vocabulary pointers

- Row shape rules: `STANDARDS.md`
- Operator / agent handoff: `HANDOFF.md`
- Floor staff: `FLOOR_CHEAT_SHEET.md`
- Architecture decisions: `docs/adr/`
- Skill operating process: `docs/agents/skill-process.md`
