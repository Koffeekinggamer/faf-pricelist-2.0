# FAF Price Book — Cursor agent audit

**Date:** 2026-09-11  
**Scope:** read-only audit of `faf-pricelist-2.0` (this checkout: branch `cursor/hide-finish-keep-options-ee2a`, tip `12d67f2` at investigation start).  
**Purpose:** give Judson a verified map so a Cursor agent can plan → implement → review → correct → update this pricebook over time — without confusing it with POS, other clones, or stale docs.  
**Method:** repo + ADRs + tests + scripts. Live SQLite (`master_pricebook.db`) is gitignored and was **not** on this machine. Catalog counts below come from `HANDOFF.md` (2026-09-10 SSD book). Treat any number that depends on the live DB as a hypothesis until `python -m backend.cli stats` is run against the drive or Fly volume.

**This file is the artifact.** No code churn.

---

## Executive answer

This repo already has the bones of an agent-operable system: a single app entry, a service facade, a reader registry, per-builder JSON profiles, a Drop Load gate, and ~380 pytest cases. It does **not** yet have a safe autonomous loop for 100+ builders.

The binding constraint is not “missing UI.” Search / Drop / Vendors already take any builder that parses. The constraint is **proof**: almost no factory Excel lives in git, the SETTLED parser contract covers 5 of 48 builders, most “named parsers” are filename-token wrappers around the generic unpivot, and GitHub Actions deploys `main` to Fly **without running tests**.

An agent that “just Drops the next Travis file” will eventually wipe a good catalog with a bad parse. Do not turn that loose until the checklist in [What you need before a hard-driving agent](#9-what-you-need-before-a-hard-driving-agent) is met.

**Keep POS out of this repo.** `backend/pricing.py` is the retail math (wholesale × multiplier, even-dollar ceil). There is no `faf-pos-system` code here. Rebuild POS against this pricing contract; do not grow a second catalog in POS.

---

## 1. Architecture (verified)

### 1.1 What this app is

One Streamlit + SQLite **floor price book** for many Amish factories. One builder = one vendor. A new Drop **adds** a factory; a re-Drop **replaces that factory only**. Retail shown on Search = wholesale × per-vendor multiplier, then even-dollar ceil (default **2.7**, Genuine Oak **1.7**; Undermount Drawer Slides = no markup).

Live: https://faf-pricebook.fly.dev (`fly.toml` app `faf-pricebook`, region `iad`).  
Local: `~/FAF-pricelist-2.0`, port **8501**, `./run.sh`.  
Holt owns **this** app only. Other clones (`pricebook-system`, `Developer/faf-pricelist-2.0`) are out of bounds.

Accuracy-mode UI (locked, ADR-0003): **Search · Drop files · Vendors · Admin**. OrderTrac flags in `pricebook_app.py` are `SHOW_ORDERTRAC_QUOTE = False` and `SHOW_ORDERTRAC_ADMIN = False`. Do not flip them unless Judson asks.

### 1.2 Folder layout (ownership)

| Path | Owns | Do not put here |
| ---- | ---- | --------------- |
| `pricebook_app.py` (~3449 lines) | Streamlit tabs, widgets, login | Import/search/pricing rules |
| `backend/service.py` (~1975) | `PriceBookService` facade | Excel cell heuristics |
| `backend/import_service.py` | Excel/PDF → row dicts (no DB write) | Commit / replace_vendor |
| `backend/drop_parse_session.py` | Parse-once cache, readiness gate | Pricing math |
| `backend/builder_parsers.py` | Identity seam: vendor + parser + source | Sheet unpivot |
| `backend/builder_reader_registry.py` | One registry of reader ids | New heuristics inline |
| `backend/catalog_readers.py` | Token readers for “generic-but-named” factories | FN/J&M/Criswell shapes |
| `backend/builder_profiles.py` | Load/save `config/builder_profiles/*.json` | Dollar charges |
| `config/builder_profiles/` | Durable rules + named-parser lock | Live prices |
| `wide_import.py` (~4220) | Generic unpivot + several shape-specific readers still living here | New builder UI |
| `backend/*_import.py` | Shape-specific readers that already escaped `wide_import.py` | Shared pricing |
| `backend/book_options.py` | Front-matter / Options-tab → `line_kind=addon` | Vendor identity |
| `backend/pricing.py` | Retail math only | Parser dispatch |
| `backend/standardize.py` / `STANDARDS.md` | Canonical row + vendor aliases | Fly deploy |
| `backend/christina.py` | Lesson log + next-step prose; **reads** the Load gate, never overrides it | Human UI |
| `backend/cli.py` | `stats` / `search` / `import-xlsx` / `batch` / `thin-catalogs` | Secrets |
| `scripts/viztech_sync.py` | Monthly dealer-portal download → Drop Load | Direct `add_rows` |
| `scripts/pull_db_from_fly.sh` / `push_db_to_fly.sh` | Volume sync for `faf-pricebook` only | Other Fly apps |
| `tests/` | 53 files, **380 collected** | Live `*.db` |
| `docs/adr/` | Locked decisions | Prompt scratch |
| `pdf_import.py` | PDF lists | Excel builders |

Root leftovers that still matter: `wide_import.py` and `pdf_import.py` were never moved under `backend/`. New readers should register in `DEFAULT_READER_REGISTRY`, not grow another root module.

### 1.3 Entrypoints

| Surface | Command / file | Notes |
| ------- | -------------- | ----- |
| Floor UI | `./run.sh` → `streamlit run pricebook_app.py` | Restart after Python edits (no hot reload on Cloud) |
| Service | `from backend import PriceBookService` | UI must stay thin (ADR-0004) — **aspirational**; the app file is still huge |
| CLI | `.venv/bin/python -m backend.cli <cmd>` | Default import mode `replace_vendor` |
| Drop Load | `PriceBookService.commit_drop_load` | One operation: concatenate same-builder files, gate, fingerprint, replace, lock parser |
| Tests | `npm test` → `.venv/bin/python -m pytest -q` | Husky pre-commit; **no GitHub pytest workflow** |
| Deploy code | `fly deploy -a faf-pricebook --remote-only` | Needs Judson sign-off. Auto on push to `main` only |
| Deploy catalog | `./scripts/push_db_to_fly.sh` | Code deploy never ships the DB (ADR-0005) |

### 1.4 How builders are registered (three layers)

Identity is **not** a single table. An agent must hit all three, in this order:

1. **Canonical name** — `backend/standardize.py` `resolve_builder_vendor` (`VENDOR_CANON` + `_VENDOR_FILENAME_HINTS`). This map is **incomplete** vs the 48 loaded factories. It still aliases early names (Hope Wood, FN, J&M, Millers Woodshop, LuxHome, Rainbow Bedding, …) and is the place filename years collapse (`MWS 2023` → Millers). Most later factories resolve via profile filename hints or catalog-spec tokens instead.

2. **Named reader** — `DEFAULT_READER_REGISTRY` in `backend/builder_reader_registry.py`. Shape-specific entries first (FN, Artisan, Criswell, J&M, Ashery, Patio Kraft, Amish Aspen, Hillside, Maple Lane, Hope Wood, LAMB, LuxHome, Windy Acres), then `catalog_reader_entries()` from `CATALOG_SPECS`, then fallthrough `generic` / `pdf`. First detector win. Token collisions get worse as the list grows.

3. **Builder Profile** — `config/builder_profiles/<slug>.json`. After a good local Load, `save_named_parser` writes `parser.importer`, `filename_hints`, `layouts`, `locked: true`. Fly **reads** shipped JSON and does **not** write (ephemeral container FS; volume is catalog-only). A settled specific importer can never be overwritten by `generic`/`pdf`.

`identify_reader` (`backend/builder_parsers.py`) is the **one Drop identity seam**. Preview and Load both call it. Do not resolve the builder in the UI and the parser in `import_workbook` independently.

### 1.5 Parser pattern

```
Excel/PDF bytes
    → identify_reader (profile lock first, else guess)
    → run_named_parser  OR  registry.detect/run  OR  layout guess (wide_species / wide_finish / long_flat / pdf)
    → book_options.merge_book_options (priced Options → addon rows)
    → normalize / standardize (vendor, species, finish_state, collection typos)
    → drop_parse_session (rows on disk; UI keeps session id)
    → evaluate_readiness (gate)
    → commit_drop_load (fingerprint skip or replace_vendor; bind multiplier; lock parser)
    → Search reads SQLite + profile option_groups / finish_as_option
```

Two reader families:

- **Shape-specific** — dedicated `import_*_workbook` + `looks_like_*`. Real layout knowledge (FN Level-One PL Print, J&M wood-percent expand, Criswell multi-book, etc.).
- **Catalog-token** — `CatalogSpec` matches factory name in filename / sheet / xlsx XML, then `import_catalog_workbook` calls `import_workbook(..., force_layout_guess=True)` and tags the result with that factory’s parser id. Optional post-passes (Five Star oak tables, Millcraft piece-name collections, INTEG/Hermies product context). The “named parser” here is a **stable id around the guesser**, not a perfected layout reader.

Generic ids: `generic`, `pdf`. Specific ids must never be downgraded to those on Load.

### 1.6 Data flow: Excel → parse → quote UI

Floor path today is **Search**, not quoting.

1. Manager drops `.xlsx/.xls/.xlsm/.pdf` (or a folder) on **Drop files**.
2. Session schema v2 stores post-standardize wholesale rows behind an opaque id (TTL ~24h). Multiplier / builder widgets do **not** re-parse.
3. Christina observes the same payload and prints one next step. The **gate** (`evaluate_readiness`) is authoritative: parse error, 0 rows, priced Options with 0 addon rows, promised finish state missing, ≥50% items missing species, or settled-reader miss → that builder is blocked. Other ready builders in the batch may still Load.
4. Load concatenates several files bound to one name (Criswell’s four books). Wholesale fingerprint (ADR-0010) skips wipe if the book is unchanged; otherwise `replace_vendor`.
5. Search: boolean query + builder / collection / wood / Options. Finished is the default whenever finished rows exist; Unfinished is an Option (`finish_as_option`). Option groups (`selection: single`) are exclusive in the widget **and** again in `PriceBookService.search`.

OrderTrac quote code and `quotes` / `quote_lines` tables still exist. UI is gated off. Treat quoting as dormant, not deleted.

### 1.7 Tests

| Fact | Evidence |
| ---- | -------- |
| 380 tests collected | `.venv/bin/python -m pytest --collect-only -q` (2026-09-11) |
| Hook | `.husky/pre-commit` → `npx lint-staged` then `npm test` → pytest |
| Lint | Ruff via `scripts/run_ruff.sh`; Prettier on other text |
| CI pytest | **Missing.** `.github/workflows/` is only `fly-deploy.yml` (push to `main`) and `pull-fly-db.yml` (manual artifact) |
| Live-book tests | Skip when Mac `~/Downloads/...` or `/Users/lordjudsonmiller/...` is absent (`test_builder_parser_contract`, `test_ashery_oak_import`, `test_artisan_chairs`, `test_criswell`, `test_option_group_contract`, `test_issue_builder_accuracy`) |
| Fixture workbooks in git | **Zero** `.xlsx/.xls` files |

Synthetic workbooks (openpyxl in-memory) cover routing, gates, and several shapes. They do **not** prove next year’s factory file.

### 1.8 Deploy (Fly)

Verified from `fly.toml`, `Dockerfile`, `DEPLOY.md`, workflows:

- Image: Python 3.11-slim, `CMD streamlit run pricebook_app.py`.
- Env: `FAF_DB_PATH=/data/master_pricebook.db`, upload 400 MB, 2 GB RAM (1 GB previously OOM’d on Drop).
- Volume `pricebook_data` → `/data` (3 GB). Catalog is **not** in the image.
- `auto_stop_machines = 'off'` — Streamlit websocket dies if Fly soft-stops the machine.
- Code auto-deploy: push to **`main` only**, no test job, needs `FLY_API_TOKEN`.
- Holt rule: do not `fly deploy` or merge the current working branch without Judson.
- `DEPLOY.md` still mentions GitHub `Koffeekinggamer/pricebook-system` and Streamlit Cloud. Canonical remote in `HANDOFF.md` / `AGENTS.md` is `Koffeekinggamer/faf-pricelist-2.0`. Trust the latter.

---

## 2. Builder inventory

**Hypothesis (HANDOFF 2026-09-10):** 194,898 rows · **48 builders** · 2,262 collections on the SSD book.  
**Verified in git:** 48 profile JSON files, all `parser.locked: true`, all importers present in the registry. 49 specific reader ids (48 profiled + **LuxHome**). 36 `CATALOG_SPECS`. 15 `backend/*_import.py` modules.

No sample factory workbook is in the repo, so “has a book” means “profile `source_file` points at a Mac/Viztech path,” not “CI can parse it.”

### 2.1 Completeness rubric

| Column | Meaning |
| ------ | ------- |
| Reader | `shape` = dedicated layout reader; `catalog+` = CatalogSpec with its own `reader=`; `token` = CatalogSpec wrapping generic unpivot |
| Profile | Locked JSON in `config/builder_profiles/` |
| Rich | Extra durable rules (`option_groups`, charge shapes, synonyms) — not just parser lock |
| Tests | Dedicated `tests/test_<builder>*` or a named case in `test_issue_builder_accuracy.py` |
| SETTLED | Listed in `tests/test_builder_parser_contract.py` (next-year filename + no-downgrade + live-book parse when present) |
| UI | Per-builder Streamlit code required? **No** for all 48 — Search/Drop are data-driven |
| Book in git | Always **no** |

### 2.2 Tier A — perfected lock (SETTLED contract)

These are the only factories the repo **promises** will keep their own reader on next year’s file.

| Builder | Importer | Reader | Rich profile | Dedicated tests | SETTLED |
| ------- | -------- | ------ | ------------ | --------------- | ------- |
| FN Chair | `fn_chair` | shape (`fn_chair_import`) | option_groups | `test_fn_chair`, `test_fn_pl_print_import` | yes |
| Ashery Oak | `ashery_oak` | shape (`ashery_oak_import`) | no | `test_ashery_oak_import` | yes |
| J & M Woodworking | `jmw` | shape (`jmw_import`) | **yes** (first full profile) | `test_jmw_import` | yes |
| Artisan Chairs | `artisan_chairs` | shape (`wide_import`) | option_groups + finish_as_option | `test_artisan_chairs` | yes |
| Criswell Bedroom | `criswell` | shape (`criswell_import`) | no | `test_criswell`, `test_criswell_left_pane` | yes |

### 2.3 Tier B — shape-specific or dedicated module, not SETTLED

Named reader is real code. Next-year filename contract is **not** in `SETTLED`. Several still live in `wide_import.py`.

| Builder | Importer | Reader home | Dedicated tests |
| ------- | -------- | ----------- | --------------- |
| AJ's Furniture | `ajs_furniture` | `ajs_import` | `test_ajs_furniture` |
| Amish Aspen | `amish_aspen` | `wide_import` | `test_issue_builder_accuracy` (live path) |
| Brookside Home Furnishings | `brookside_home_furnishings` | `brookside_import` | `test_brookside_import` |
| Fredericksburg Furniture | `fredericksburg_furniture` | `fredericksburg_import` | none |
| Frog Pond Furniture | `frog_pond_furniture` | `frog_pond_import` | `test_frog_pond_import` |
| Hillside Chair | `hillside_chair` | `wide_import` | none |
| Hogback Design And Finishing | `hogback_design_and_finishing` | `hogback_import` | `test_issue_builder_accuracy` |
| Hope Wood | `hw_chair_markup` | `wide_import` | none |
| J. Troyer & Company | `j_troyer_and_company` | `j_troyer_import` | `test_j_troyer_import` |
| Kidron Woodcraft | `kidron_woodcraft` | `kidron_import` | `test_kidron_woodcraft` |
| LAMB | `lamb` | `wide_import` | `test_issue_builder_accuracy` |
| Maple Lane | `maple_lane` | `wide_import` | none |
| Patio Kraft | `patio_kraft` | `wide_import` | none |
| Superior Woodcrafts | `superior_woodcrafts` | `superior_import` | `test_issue_builder_accuracy` |
| Townline Furniture | `townline_furniture` | `townline_import` | `test_townline_furniture` |
| Troyer Ridge Furniture | `troyer_ridge_furniture` | `troyer_ridge_import` | none |
| Windy Acres Furniture | `windy_acres` | `wide_import` | `test_windy_acres_import` |
| Five Star Tables | `five_star_tables` | token + `apply_five_star_oak_tables` | `test_issue_builder_accuracy` |

### 2.4 Tier C — catalog-token lock (generic unpivot underneath)

Profile says “named parser.” Implementation is factory-name detect + `force_layout_guess`. Fine for a stable wide-species book; fragile when next year’s file adds a new Options sheet or splits woods.

Black Horse Furniture · Crystal Valley Hardwoods · Dutch Creek Design · Ebony Woodworking · Elite Designs · Farmside Wood · Genuine Oak · Hermies Table Shop · Hoosier Crafts · INTEG Wood Products · Meadow Lane Furniture · Millcraft · Millwood Quality Furniture · Mirror Lake Woodworks · Nisley Cabinet LLC · Old Town Oak · Premier Woodcraft · Quality Fabrications · Red Barn Woodworking · RH Yoder · Sharp Run Wood · Signature Designs · Stone River Furniture · Stoney Acres Furniture · Troyer Design Company

Hermies / INTEG / Millcraft have small post-passes in `catalog_readers.py`. None of these have a SETTLED row. Almost none have a dedicated test file.

### 2.5 Tier D — code exists, not in the 48-builder book

| Name | Evidence | Status |
| ---- | -------- | ------ |
| **LuxHome** | Registry `luxhome` + `wide_import` / `luxhome_import` + `test_luxhome_seating` | **No profile JSON.** Not one of the 48 locks. Treat as a selling builder waiting for Drop + profile, or a leftover from an older book. |
| **Millers Woodshop** | `VENDOR_CANON`, `looks_like_millers`, `enhance_millers_long_df` | No profile, no registry id. STANDARDS still uses it as the identity example. |
| **Rainbow Bedding** | `VENDOR_CANON` + filename hint `jan 2026 wholesale` | No profile / reader. |
| **Charleston Forge**, **Beaverdam**, **GVWI** | `VENDOR_CANON` only | Aliases / old vendors. Do not invent catalogs for them. |

### 2.6 Deliberate skips

`scripts/viztech_sync.py` `IGNORE_BUILDERS`: **Green Meadows**, **Simple Living** (PDF-only / not needed on floor). ADR-0007: agents never auto-ignore.

Thin KEEP (do not treat as broken): Amish Aspen, Maple Lane, Signature Designs, Ebony Woodworking. Patio Kraft KEEP (poly outdoor). Source: `HANDOFF.md`. Confirm with `python -m backend.cli thin-catalogs` on the live DB before arguing size.

### 2.7 UI wiring

**Hypothesis rejected:** “each builder needs Search/Drop code.”  
**Verified:** no per-builder branches in the nav. Builder-specific floor behavior is profile-driven (`option_groups`, `finish_as_option`) plus catalog rows. Adding a 49th factory must not edit `pricebook_app.py` unless the widget model itself changes.

### 2.8 Options completeness (standing rule)

Every factory Excel encodes Options. Empty Search Options is a **capture miss**, not “this builder has no Options.” Prove from the book **and** Search: addon rows, `option_key`, option-species, Unfinished. Only J&M, FN, and Artisan ship rich option-group profiles. The other 45 rely on `book_options.py` regexes + whatever the reader emitted. That does not scale to 100 without per-builder proof.

---

## 3. Pain points that block 100+ builders

Ranked by how hard they make an autonomous agent unsafe.

### 3.1 No golden books in git

Live-book tests skip on Cloud / CI / any laptop without Judson’s Downloads tree. Absolute paths (`/Users/lordjudsonmiller/Documents/viztech-downloads/...`) are a second machine’s filesystem. An agent can ship a parser that is green in pytest and empty on the real file.

### 3.2 “Named parser” inflation

ADR-0011 says every in-book factory has its own reader id. True. Most ids are **tags on the guesser**. A lock of `signature_designs` does not mean Signature’s layout is understood. At 100 factories this creates false confidence: Load succeeds, Options vanish, Christina has nothing specific to say.

### 3.3 `wide_import.py` is still the gravitational well

~4220 lines, ~70 functions, detectors + unpivot + Patio/LAMB/Windy/Aspen/Hillside/Maple/Hope/Artisan/Millers. New “quick” readers land here. The registry + `*_import.py` split is the intended deepening; it is half-done.

### 3.4 Thin-UI ADR vs 3449-line app

ADR-0004 is accepted. `pricebook_app.py` still owns a lot of Search/Drop presentation **and** option-widget keying. Agents that “just add a checkbox” will keep fattening the UI.

### 3.5 Split identity maps

Four places can name a factory: `VENDOR_CANON`, profile `filename_hints`, `CATALOG_SPECS.tokens`, registry detect order. Viztech `Download_NNNNN` stems are correctly banned from hints (`test_catalog_readers`). A new Travis file named `Download_2027_Pricelist_123.xlsx` still depends on **xlsx XML / cover text** containing the factory name. If it doesn’t, identity falls through to the stem — the exact failure ADR-0011 forbids.

### 3.6 Incomplete `VENDOR_CANON`

~20 aliases. 48 in-book factories. Filename regexes are skewed to the first wave (FN, J&M, Ashery, Artisan, Criswell, Hope Wood). Later factories lean on profile hints. A first-time Drop of a new factory with a messy filename will mint a bad vendor string (`Download 2027 Pricelist 123`) unless the agent types the canonical name before Load.

### 3.7 Detection order / token collisions

`BuilderReaderRegistry.detect` returns the **first** `specific` match. Short tokens (`ac`, `ao`, `fnc`, `tdc`, `jmw`) plus XML needles will collide as the 50th–100th factory arrives. There is no collision test across all specs.

### 3.8 No PR test gate

`fly-deploy.yml` deploys `main` with checkout + `flyctl deploy`. A green hook on one laptop is the only pytest gate. Cloud agents that push to a feature branch never get CI signal. `docs/agents/skill-process.md` says “local verification matches CI” — CI for tests does not exist.

### 3.9 Stale operator docs (agent trap)

| File | Drift |
| ---- | ----- |
| `CONTINUE.md` | Dated 2026-07-18; ~476k rows / **155 vendors**; GitHub `pricebook-system`; “Windy Acres generic fall-through” (now locked `windy_acres`) |
| `DEPLOY.md` | Mixes `pricebook-system` + Streamlit Cloud with the real Fly app |
| `PROMPTS.md` | Import prompts say **Mode: upsert** — forbidden as the everyday default (ADR-0001 / CLI default `replace_vendor`) |
| `STANDARDS.md` | `finish_state` is `finished` \| `unfinished` only |
| `backend/standardize.py` | Still maps **glazed** as a finish_state |
| GitHub issues #12–#31 | Wayfinder tickets for thin catalogs + smart re-import; ADRs 0007 + 0010 already **accepted**. An agent that “picks up issue 20” will re-litigate shipped work |

### 3.10 Fragile Excel assumptions (standing, still true)

- Never unhide sheets/rows (hidden Masters duplicate visible catalog).
- Cover / Markup / Options / Percentage / visible backups are **viewed**; only true duplicates (Retail when Wholesale exists) stay out.
- H" / W" / D" are dimensions, never Wood.
- Steel / Metal / Cushion are row materials (Wood column).
- Mixed woods: `Cherry/Hickory` in the Wood dropdown.
- Formula-only Viztech sheets historically import as 0 rows (`CONTINUE.md` item; still a class of failure the gate catches as `zero_rows`).
- OLE `.xls` vs zip `.xlsx` needs `excel_engine` (`workbook_sheets.py`); filename suffix lies.

### 3.11 Missing contracts

- SETTLED list is 5 builders, not 48.
- Option-group contract only runs for profiles that declare `option_groups` (FN, Artisan).
- No machine-readable “builder completeness” table in repo (this audit is the first).
- No published pricing **API** for POS — only `backend/pricing.py` functions.

### 3.12 Operational sharp edges

- Local source of truth is the **Mac/SSD** book. Pulling Fly onto the drive without intent overwrites a larger catalog (`HANDOFF.md` already records one such incident: 210k-row file lost; Sep 1 backup restored).
- Fly Drop cannot persist a new profile lock. A factory perfected only on Fly is unlocked again on the next image.
- Shared login (Foothills / Amish). Per-user auth is explicitly “do not build yet.”
- 2 GB / 3 GB volume: 100+ builders × wide unpivot can OOM or fill the volume if someone dumps PDFs/images onto `/data`.

---

## 4. Update workflows today

### 4.1 Golden path — new Travis / dealer Excel (new factory)

1. Confirm the **canonical display name** with Judson (one builder = one vendor). Do not use the filename stem.
2. Open **every visible** tab. Do not unhide anything. Note Cover, Markup, Options, Percentage, product sheets, visible backups.
3. Drop the file (or folder) on **Drop files**. If identity guessed wrong, type the builder name and **Re-parse** (applies the lock / detector).
4. Check upload quality (0–100% on Drop/Vendors; 100% = nothing left). Empty Options = miss.
5. If ready, Load. Mode is `replace_vendor` for that name (first Load = insert).
6. Search: one SKU, wood dropdown, Options, Unfinished if the book has it. Retail = wholesale × mult.
7. On **local/Mac** only: commit the new/updated `config/builder_profiles/<slug>.json` (parser lock, hints). Deploy that JSON with code; do not commit the DB.
8. Christina’s next step: demo that builder, then the next selling file — **do not re-drop a settled factory**.
9. After a good Load, architecture skill on Drop / profile / parser; present candidates; wait for Judson to pick. Do not auto-refactor.

### 4.2 Golden path — next year’s file for a settled factory

1. Do **not** invent a second vendor. Same name.
2. Drop. Locked importer **must** run (`parser_source=saved`). If the gate says settled-reader miss → **stop**. Fix the reader or the book; do not Load generic rows under that name.
3. Unchanged wholesale fingerprint → skip wipe (ADR-0010). Changed Options or prices → full replace of that builder.
4. Refresh profile lock metadata (importer stays; hints/layouts may update). Never let `generic` overwrite a specific lock.

### 4.3 Viztech monthly

`scripts/viztech_sync.py`: login → download under `~/Documents/viztech-downloads/` → Drop Load (never raw `add_rows`) → keep non-Viztech builders. `IGNORE_BUILDERS` only for Green Meadows / Simple Living. Credentials from env or drive secrets — not git. LaunchAgent: `scripts/install_viztech_monthly_sync.sh`.

### 4.4 CLI (agent-friendly)

```bash
.venv/bin/python -m backend.cli stats
.venv/bin/python -m backend.cli vendors
.venv/bin/python -m backend.cli search "nightstand" --vendor "Genuine Oak"
.venv/bin/python -m backend.cli import-xlsx FILE.xlsx --vendor "Canonical Name"
.venv/bin/python -m backend.cli batch FOLDER --excel-only
.venv/bin/python -m backend.cli thin-catalogs
.venv/bin/python -m backend.cli standardize
```

Default mode is `replace_vendor`. `append` / `upsert` exist and will duplicate if used casually.

### 4.5 What breaks often (from code + handoff, not folklore)

| Failure | Why | What the system does |
| ------- | --- | -------------------- |
| Viztech `Download_NNNNN` identity | Stem is not a factory | Hints drop `download*`; XML/cover must carry the name or the human types it |
| Formula / cover-only sheet | 0 sellable numbers | Gate: `zero_rows` — do not Load |
| Options tab not captured | `book_options` miss or reader skipped the sheet | Gate: `options_missing` if source had priced option lines |
| Locked reader returns empty, guesser would “work” | Layout changed or wrong book | Gate: `settled_reader_miss` — Christina: “Do not Load” |
| Species blank on ≥50% items | Wide unpivot grabbed dims / `col_N` | Gate: `species_quality` |
| Unfinished promised in filename, no unfinished rows | Finish filter / reader | Gate: `finish_state_missing` |
| Two vendors for one factory | Typed name ≠ canon | `resolve_builder_vendor` + replace_vendor policy; still happens if canon is missing |
| Fly profile write | Container FS ephemeral | Catalog may Load; lock does not persist — repair on Mac and deploy JSON |
| Pull Fly onto SSD | Smaller/older volume copy | Documented data-loss event; never pull onto a different app or a book you mean to keep |
| Streamlit after Python edit | No hot reload | Restart `./run.sh` |

### 4.6 Missing automation

- No CI pytest / Ruff on PR.
- No fixture pack of anonymized/minimal factory sheets.
- No `add-builder` checklist script (register + profile stub + SETTLED row + synthetic test).
- No collision check on detector tokens.
- Viztech sync does not fail closed on quality < N; it relies on the Drop gate per file.
- No POS consumer test that `catalog_retail` stays stable.

---

## 5. What a hard-driving Cursor agent MUST know

### 5.1 Who it is

Holt. Talks only to Judson. Christina is Holt’s child (lesson log + one next step), never a human interface. No 8th agent. Every prompt is seven-reviewed unless Judson says Holt only. Holt runs Drop/Load/parse/test without asking Judson to click. **Deploy, Fly DB push/pull, payments, deleting important files** still need sign-off.

### 5.2 Golden paths (do these)

1. Read `AGENTS.md` → `CONTEXT.md` → `HANDOFF.md` → `STANDARDS.md` → `docs/adr/`.
2. Work only in `~/FAF-pricelist-2.0` / this checkout. Branch from the current pricebook branch; do not silently retarget `main` for Fly.
3. Catalog changes via Drop Load / `commit_drop_load` / CLI `replace_vendor` — never dump a mystery multi-builder DB over the volume.
4. After a good new-builder Load: Search demo → commit profile JSON → Christina’s next selling builder. Do not re-drop a settled factory.
5. Test-first for parser/gate/profile changes (`/implement` → `/tdd`). Grill catalog language with `/grill-with-docs`.
6. Retail math only in `backend/pricing.py` (and tests). POS can import that module later; do not copy formulas into Streamlit or POS.

### 5.3 Forbidden moves

- Open, clone, or push to another price-book **app**.
- `fly deploy`, merge the working Fly-bound PR, or `push_db_to_fly` / `pull_db_from_fly` without Judson.
- Commit `*.db`, `.env`, `.streamlit/secrets.toml`, Christina lesson logs.
- Unhide Excel sheets or rows.
- Treat empty Options as “no Options.”
- `append` / everyday `upsert` for a builder update.
- Overwrite a specific named parser with `generic`/`pdf`.
- Load when the gate or Christina says the settled reader missed.
- Re-enable OrderTrac UI flags.
- Hardcode one factory’s vocabulary in `service.py` / Search widgets (belongs in the profile).
- Put dollar charges in profile JSON (ADR-0011: charges live in SQLite).
- Drive-by refactors inside `/implement`.
- Re-ask settled catalog facts (KEEP thins, Genuine Oak 1.7, FN Level One only, etc.).

### 5.4 File ownership map (where to edit)

| Job | Edit | Usually do not edit |
| --- | ---- | ------------------- |
| New shape-specific reader | New `backend/<id>_import.py` + `ReaderEntry` **or** `CatalogSpec.reader` | `pricebook_app.py` |
| Token-only first lock | `CATALOG_SPECS` + profile JSON after Load | `wide_import.py` (unless unpivot is wrong for everyone) |
| Option groups / finish-as-option | That builder’s profile JSON + `test_option_group_contract` | Search widget code |
| Vendor alias / filename | `VENDOR_CANON` + `_VENDOR_FILENAME_HINTS` **and** profile hints | Random string replace in UI |
| Readiness / Load | `drop_parse_session.evaluate_readiness`, `commit_drop_load` | Christina prose |
| Retail math | `backend/pricing.py` | Parser |
| Row shape | `standardize.py` + `STANDARDS.md` together | Only one of them |
| Agent glossary | `.agents/skills/setup-matt-pocock-skills/` then `scripts/sync_agent_docs.sh` | `docs/agents/` alone (mirror) |

### 5.5 How to add a builder safely

**Minimum (first Drop, guesser OK):**

1. Canonical name from Judson.
2. Visible-tab inventory (including Options).
3. Drop → correct name → Load when gate is green.
4. Commit profile lock (local).
5. Synthetic test: detector claims a next-year filename; `identify_reader` returns this importer; Load of a tiny lookalike workbook is ready.

**Before calling it settled (required to scale):**

6. Move unique layout code out of `wide_import.py` if it is factory-specific.
7. Add the builder to `SETTLED` in `test_builder_parser_contract.py` (or a successor table driven by profiles).
8. Check in a **minimal fixture** workbook (or a private fixture store the agent can read) that is not the full dealer book if legal/size forbids — but **some** bytes the CI can parse.
9. Prove Options from book + Search.
10. Run upload quality; do not declare 100% if Options are empty.

### 5.6 How to review a change

Dual-axis (`/code-review`): **Standards** (ADRs, glossary, thin UI, no secrets) and **Spec** (the ticket’s kill test). Extra pricebook checks:

- Did identity stay one vendor?
- Did a settled lock stay specific?
- Did hidden sheets stay hidden?
- Did Options survive?
- Did retail examples still even-dollar ceil (`715 × 2.7 → 1932`)?
- Did tests skip the real assertion (`pytest.skip` because Downloads missing)?
- Is this POS? If yes, stop.

### 5.7 How to validate (commands)

```bash
# always
.venv/bin/python -m pytest -q
./scripts/run_ruff.sh

# parser / identity you touched
.venv/bin/python -m pytest -q tests/test_builder_parser_contract.py tests/test_builder_parsers.py tests/test_catalog_readers.py

# Drop / Load
.venv/bin/python -m pytest -q tests/test_drop_parse_session.py tests/test_drop_commit.py tests/test_replace_vendor.py

# Options / money
.venv/bin/python -m pytest -q tests/test_option_group_contract.py tests/test_book_options.py tests/test_pricing.py

# live catalog (Mac/SSD or after pull — never commit)
.venv/bin/python -m backend.cli stats
.venv/bin/python -m backend.cli thin-catalogs
./scripts/ready_catalog.sh --no-pull

# floor proof (restart Streamlit after Python edits)
PORT=8501 ./run.sh
# Search that builder: SKU + Wood + Options + Unfinished
```

Do not treat “380 passed with 20 skipped live-book tests” as “the factory file works.”

---

## 6. Proposed agent operating system

### 6.1 AGENTS.md / Cursor rules outline (do not replace blindly)

Current `AGENTS.md` + `.cursor/rules/holt.mdc` are already strong on **app identity, Drop rules, secrets, Fly**. They are weak on **builder completeness, CI, fixture books, and POS boundary**. Suggested additions (outline only):

1. **POS boundary** — pricing contract lives here (`backend/pricing.py` + `STANDARDS.md`). No POS rebuild in this repo.
2. **Completeness tiers** — point at this audit §2; refuse to call a token wrapper “settled.”
3. **Fixture rule** — a new specific reader ships with a synthetic **or** checked-in sample; live-Downloads tests are extra, not the only proof.
4. **CI rule** — PR must run Ruff + pytest (no DB); Fly deploy stays human-gated.
5. **Add-builder recipe** — the 10 steps in §5.5, one screen.
6. **Stale-doc rule** — `CONTINUE.md` / `PROMPTS.md` / `DEPLOY.md` are not identity sources; `CONTEXT.md` + ADRs + `HANDOFF.md` date win.
7. **Issue hygiene** — closed/superseded wayfinder issues are not a backlog.

Keep Holt’s never-list and the Drop/Options/unhide rules verbatim.

### 6.2 Suggested loop (plan → implement → review → correct → update)

This matches skills already installed (`docs/agents/skill-process.md`) with pricebook-specific gates.

```
PLAN
  /triage  or  /wayfinder (foggy / multi-session)
  /grill-with-docs  (catalog language, Options, identity)
  /to-spec  →  /to-tickets   (vertical kill test, one factory or one seam)

IMPLEMENT
  /implement → /tdd
  Red: failing test on registry / gate / profile / synthetic book
  Green: reader + profile + tests
  No refactor. No Fly. No DB commit.

REVIEW
  /code-review  (standards + spec)
  Pricebook extras in §5.6
  If live book is on the machine: parse it; do not skip silently

CORRECT
  Must-fix items get a new commit on the same branch
  Re-run the same pytest slice
  If the gate would block Load, the PR is not done

UPDATE (catalog, not code)
  Local Drop Load only after tests
  Commit profile JSON
  Christina next step
  Stop. Wait for Judson before Fly code or volume push
```

Do **not** let the agent loop “update” by pulling Fly or re-dropping settled factories.

### 6.3 What “update” means in this product

| Update | Agent may | Needs Judson |
| ------ | --------- | ------------ |
| Parser / profile / tests | yes | — |
| Local Drop of a **new** selling builder | yes (Holt admin) | confirm **name** if ambiguous |
| Re-drop settled factory | no | explicit ask |
| Push profile JSON to git | yes | — |
| `fly deploy` / merge to the live image | no | sign-off |
| `push_db_to_fly` / `pull_db_from_fly` | no | sign-off |
| POS / payments / per-user auth | no | “do not build yet” |

---

## 7. Top 10 backlog (leverage for scaling builders)

1. **Checked-in fixture corpus + kill Downloads-only tests as the sole proof.** Highest leverage. Until CI can parse *something* that looks like FN / J&M / a token-wide book, autonomous parser work is theater. Legal/size: strip dealer-only sheets; keep one visible product tab + Options.

2. **GitHub Actions: Ruff + pytest on every PR; keep Fly deploy off feature branches.** Cheap. Makes Cloud agents honest. Do not add a Fly deploy-on-PR.

3. **Promote token locks to SETTLED only when a shape test exists; expand `test_builder_parser_contract.SETTLED` from 5 → all Tier B, then pick off Tier C by layout family (wide_species / wide_finish / long_flat), not one-off hero parsers.** Stops false “named parser” confidence.

4. **Single identity module.** Generate filename hints + `VENDOR_CANON` entries from profiles + `CATALOG_SPECS` (or the reverse). Add a collision test: no two detectors claim the same next-year filename.

5. **`add_builder` tracer.** One command or ticket template: slug, vendor string, ReaderEntry/CatalogSpec stub, profile stub, synthetic test, SETTLED row. The missing automation in §4.6.

6. **Finish extracting factory readers from `wide_import.py`.** Patio Kraft, LAMB, Windy Acres, Amish Aspen, Hillside, Maple Lane, Hope Wood, Artisan already have registry ids; the code still sits in the 4k-line file. Deepen the Drop module (ADR-0011 already said this shipped at the registry layer — the implementations did not all move).

7. **Options proof per builder.** Extend the option-group contract idea: every profile records `expected_option_kinds` (size %, finish, Unfinished, fabric, …). Gate already counts priced option lines; persist the expected kinds so next year’s miss fails a test, not the floor.

8. **Doc hygiene pass (docs-only).** Rewrite or tombstone `CONTINUE.md` / `PROMPTS.md` upsert / `DEPLOY.md` remote. Close or label GitHub #12–#31 as superseded by ADR-0007/0010. An agent that reads those files today will do the wrong import mode.

9. **LuxHome / Millers / Rainbow decision.** Profile + Drop, or explicit IGNORE/out-of-book. Dead aliases in `VENDOR_CANON` without a catalog confuse identity.

10. **Pricing package boundary for POS.** Extract or freeze `backend/pricing.py` + row identity fields as the only contract POS may import. No Streamlit, no SQLite, no Drop. Do this *before* anyone copies even-dollar logic into `faf-pos-system`.

**Not in the top 10:** per-user auth, OrderTrac UI, billing, invite links (`HANDOFF` / `CONTINUE`: do not build yet). Thin-catalog KEEP/replace/ignore remains Judson-only (ADR-0007).

---

## 8. Concrete recommendations (prompts Judson can paste)

**Agent system prompt (short):**

> You are Holt on `faf-pricelist-2.0` only. Read AGENTS.md → CONTEXT.md → HANDOFF.md → STANDARDS.md → docs/adr → docs/PRICEBOOK_AGENT_AUDIT.md. One builder = one vendor. Retail = wholesale × mult (even-dollar). Options empty = capture miss. Never unhide sheets. Never commit the DB. Never deploy/push Fly without Judson. Never touch other price-book apps or faf-pos-system. Named parser lock is not the same as a shape-specific reader — see audit §2. After code: pytest + ruff. After a new builder Load: Search proof + commit profile JSON. Stop.

**Add-builder prompt:**

> Add builder [CANONICAL NAME] from [PATH]. Visible tabs only. Drop via PriceBookService (replace_vendor). Do not invent a second vendor. Prove Options from the book and Search. Register a reader (shape-specific if the guesser loses woods/options; else CatalogSpec + synthetic next-year filename test). Write profile lock. Do not edit pricebook_app.py. Do not fly deploy.

**Review prompt:**

> Review this branch on Standards (ADRs, audit §5.3 forbidden) and Spec (ticket kill test). Fail if tests skip the live assertion, if a specific lock can become generic, if Options are unproven, or if POS/Fly/DB leaked in.

---

## 9. What you need before a hard-driving agent

Do not claim the loop is safe until most of these exist. **Must** vs **should**:

### Must (safety)

- [ ] PR CI: Ruff + pytest, no secrets, no DB.
- [ ] Fixture bytes for at least the five SETTLED builders + one wide_species token builder + one Options-tab builder.
- [ ] This audit (or a trimmed Holt rule) linked from `AGENTS.md` so agents do not prefer `CONTINUE.md` / `PROMPTS.md`.
- [ ] Explicit POS / Fly / DB-push denylist in the agent prompt (already in Holt; keep it).
- [ ] Identity collision test before adding factory #49+.
- [ ] Judson-confirmed canonical names for any new Travis file (agent must not guess from `Download_*`).

### Should (speed)

- [ ] `SETTLED` generated from profiles, or ≥ all Tier B in the contract.
- [ ] `add_builder` stub script / ticket template.
- [ ] Tombstone stale docs and wayfinder issues.
- [ ] LuxHome / Millers / Rainbow disposition.
- [ ] `backend/pricing.py` documented as the POS import surface.
- [ ] Volume/size budget note (3 GB / 2 GB) before 100 full books + images.

### Already have (do not rebuild)

- Reader registry + Drop identity seam + Load gate + fingerprint skip + profile lock + Christina observer + 380 tests + ADR glossary + Holt app isolation.

---

## 10. Hypotheses that were checked

| Hunch | Verdict |
| ----- | ------- |
| Need per-builder UI to add a factory | **False.** Data + registry + profile. |
| All 48 “named parsers” are shape-specific | **False.** ~25 are token wrappers on the generic unpivot. |
| CI runs the test suite | **False.** Only Fly deploy on `main` + manual DB pull. |
| Sample workbooks are in the repo | **False.** Zero. |
| CONTINUE.md / PROMPTS.md are safe for agents | **False.** Stale counts, wrong remote, upsert. |
| LuxHome is one of the 48 | **False.** Reader + tests, no profile. |
| POS already shares this catalog | **Unverified / out of repo.** Pricing math is here; no POS code. Keep them separate. |
| Thin catalogs are bugs | **False** for listed KEEP names; confirm on live DB. |
| Fly Drop locks parsers | **False.** Reads shipped JSON only. |

---

## 11. Reading order for the next agent

1. This file.  
2. `AGENTS.md` + `.cursor/rules/holt.mdc`  
3. `CONTEXT.md` (glossary)  
4. `HANDOFF.md` (dated catalog facts)  
5. `STANDARDS.md` + `docs/adr/0001`–`0011`  
6. `backend/builder_reader_registry.py` + `backend/catalog_readers.py` + `config/builder_profiles/`  
7. `tests/test_builder_parser_contract.py` + `tests/test_drop_parse_session.py` + `tests/test_pricing.py`

Then implement **one** builder or **one** seam. Not both.
