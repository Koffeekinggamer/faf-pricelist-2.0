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
The long-form SQLite catalog (`master_pricebook.db`) — **many builders** in one app. One sellable row per SKU × species × finish. A new builder Drop **adds** that factory; re-import **replaces that builder only**.
_Avoid_: treating the app as a single-builder book; wiping the whole catalog to add someone; wide workbook as source of truth after import

**Part number**:
Canonical SKU / item code on a row (or full item name when the builder has no SKU).
_Avoid_: sheet name, option-line junk, HTML-entity twin codes

**Collection**:
Product category within a builder (e.g. Seating, Casegoods) — not a spreadsheet tab name.
_Avoid_: sheet title, upcharge section name

**Hidden sheet / hidden row**:
Factory workbooks hide Masters, backups, and leftover tables. Those stay hidden — never unhide on Drop. They often duplicate visible rows. Duplicate cleanup compares the full sellable row, not SKU alone.
_Avoid_: importing hidden tabs as missing catalog; deleting a row because the part number matches

**Species**:
Wood tier **or** color/fabric option on the row (slash-separated woods, Title Case).
_Avoid_: `col_N`, bare `FINISHED`, raw column headers

**Option** / **addon charge**:
Every factory book encodes Options: size-option pricing (+% for custom sizes), finishes (two-tone, glaze, paint, distressing, oil), and flat $ adders, plus Unfinished when unfinished rows exist. Search lists what the catalog captured (addon rows, item `option_key`, option-species, Unfinished). Empty Search Options is a capture miss, not a book with no Options.
_Avoid_: treating zero addon rows as “this builder has no Options”; leaving size/%/finish adders as footnotes; a static/global Options menu; leaking one builder's options onto another; treating finish Cat.N / fabric _tier labels_ as the only meaning of Option; treating raw adder dollars as full chair retail; showing unfinished as the Search default when finished rows exist

**Option group**:
A family of Options that are alternatives, not a stack — declared per builder in the profile's `option_groups` with `selection: single` and a `match` regex. Picking one member drops the other members of that group, in the Options panel and again in `search`, so two members can never price together. FN Chair has two: **finish category** (`Cat. 1/2/3`, different wholesale rows for the same chair) and **fabric tier** (the five fabric/leather upcharge columns). One category plus one fabric is valid; two of either is not. Builders with no groups keep stackable checkboxes.
_Avoid_: summing two members of one group; enforcing exclusivity only in the widget; hardcoding FN's category labels in search code.

**Builder Profile**:
Persistent, per-builder record of what we've learned about a builder — option **charge shapes** (flat `$`, `%`, or per-category), **category synonyms**, **item→category overrides**, **parse hints**, and a **named parser** (which importer to run on the next Drop) — stored as versioned JSON at `config/builder_profiles/<vendor>.json`. A successful Drop Load locks that builder's parser under their canonical name; the next file for that factory reuses it. Search/upcharge also reads the profile. J&M Woodworking is the first profile (`parser: jmw`).
_Avoid_: hardcoding one builder's vocabulary in code; storing profile rules in the gitignored DB; re-guessing a perfected builder's layout on every update.

**Finish state**:
Only `finished` or `unfinished`. Floor Search defaults to **finished** whenever that builder has finished rows. Unfinished is chosen from Options.
_Avoid_: free-text finish names in this field; a Finish dropdown on Search

**Wholesale** / **base price**:
Builder list price before Foothills markup (`price_basis` = `wholesale`).
_Avoid_: retail as import source, “cost” without saying wholesale

**Multiplier**:
Per-vendor markup factor. Default **2.7**; **Genuine Oak 1.7**.
_Avoid_: hardcoded global 2.7 ignoring vendor overrides, workbook markup as silent default over saved mult

**Retail** / **adjusted price**:
Price shown on Search (RETAIL) = wholesale (cost) × multiplier, then rolled up to the next even whole dollar. Exact even dollars stay put. Undermount Drawer Slides: no markup (retail = wholesale).
_Avoid_: calling wholesale “price” in floor-facing copy; documenting `round(base × mult, 2)` — that is not the rule

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
Manager import path for Excel/PDF builder books into the master price book. A single file, several files, or a **folder** of lists all go through the same parse — including the catalog typo/grammar pass (`Occasonial` → `Occasional`).
_Avoid_: floor staff using Drop for day-to-day lookups

**Drop identity**:
The Builder plus the named parser that should run for a Drop file. One seam: locked profile first, else filename and workbook detect. Preview and Load share it so they cannot disagree.
_Avoid_: resolving the Builder in preview and the parser in import independently; treating a Viztech `Download_NNNNN` stem as identity

**Drop parse session**:
One parse of a Drop batch: post-standardize wholesale rows on disk behind an opaque session id; UI keeps only the id plus per-file builder/multiplier widget defaults. The parser is **layout-smart**: one reader registry runs a Builder's locked **named parser** first; otherwise it picks a matching Builder reader or classifies each sheet (wide woods / wide finish / long list). It inventories that Builder's **variants** (items, woods, stains, upcharges, customizations) and records whether that file is ready to Load. Readiness compares source evidence with output: a workbook containing explicit priced Option lines cannot Load with zero addon rows. A settled reader miss blocks only that Builder; other ready Builders in the same batch may Load. A successful Load writes/refreshes safe named-parser metadata locally; a profile-write failure preserves the loaded catalog but remains a blocking warning. Set the builder name and Re-parse to apply a locked parser. Multiplier and Builder bind at commit, not by rewriting the session. Invalidated by schema change, new upload set, markup-preference toggle, explicit Re-parse, successful Load/Clear, or TTL (~24h).
_Avoid_: holding full row lists in Streamlit session state; re-parsing when only the multiplier widget changes; baking retail into the parse cache; a separate write path that only Drop uses; assuming every builder uses the J&M sheet shape; guessing a locked builder from scratch on every update

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
