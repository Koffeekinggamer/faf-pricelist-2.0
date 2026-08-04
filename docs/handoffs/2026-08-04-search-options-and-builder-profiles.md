# Handoff — Search Options upcharge + Builder Profiles (2026-08-04)

Session handoff for the in-flight work on branch **`cursor/hide-finish-keep-options-ee2a`** ([PR #34](https://github.com/Koffeekinggamer/faf-pricelist-2.0/pull/34)). Read `AGENTS.md` and `CONTEXT.md` first; this file covers only the active work.

## TL;DR
- Search-tab work is **built, tested (pytest 50 passed), and verified locally** — but **NOT merged and NOT deployed**. Production `faf-pricebook.fly.dev` is unchanged (earlier deploy: J&M-only catalog, Finish dropdown hidden, dropdowns above search).
- A larger **Builder Profiles** effort is **in design** (destination + storage decided; ADR-0011 written). Implementation not started.

## Branch / PR
- Branch: `cursor/hide-finish-keep-options-ee2a`, based on `origin/main`.
- PR: #34 (base `main`). Working tree clean; local == remote.
- Supersedes the stale PR #33 (was branched off `cursor/fly-deploy-docs-c5bb`, which is behind `main`).

## What shipped into PR #34 (local only)
1. Hide the **Finish** dropdown; always `finished`.
2. **Option add-on fix** — add-on rows bypass Wood/text filters when an Option is selected (ADR-0008).
3. Move **Builder / Wood / Option** dropdowns above the boolean search box.
4. **Option upcharge — all categories** (the main feature):
   - Finish options (`Paint`, `2-tone Stain`, `Paint & Glaze`, `Paint with Rub Through`) apply to **every physical wood item**; charge comes from the item's **matched furniture category** (`Queen Bed +$352`, `9 Drawer Dresser +$406`, `Armoire +$474`, …).
   - Drawer/door options (`Undermount Drawer Slides`, `Extra Drawers or Doors`) apply to drawered/doored items with the flat charge.
   - Matching is **confidence-flagged**; ambiguous/compound items (plain `Dresser`, `5 Piece Set`) render **`approx`**. Distinctive synonyms handled (`Man's Chest → Manschest`, `Chifferobe → Armoire`, `Tri-View → Triview Mirror`).
   - Results show a per-item **Option detail** column + a caption that RETAIL includes the option.
5. Cleanup: removed "accuracy mode" header, footer caption, sidebar collections count; Option label styling; AGENTS.md `## Cursor Cloud specific instructions`.

### Key files
- `backend/repository.py`: `get_addon_charge()`, `get_addon_rows(vendor, option_key)`.
- `backend/service.py`: `search()` → `_search_with_item_option_upcharge()`; `_match_addon_category()` (heuristic + confidence flag). `_DRAWER_DOOR_ITEM_KEYWORDS`, `_ITEM_UPCHARGE_OPTION_KEYWORDS` currently hardcoded (J&M-flavored — to move into Builder Profiles).
- `pricebook_app.py`: Search results Option-detail column + caption; dropdown/layout/caption cleanups.
- `tests/test_option_upcharge.py`: flat drawer option (eligible-only); finish option upcharges every wood item by matched category; non-wood excluded.

## Builder Profiles — design status (NOT built)
Goal: learn each builder's conventions once, persist them, and have both the **Drop-files import** and the **search/upcharge helper** consume them so re-importing/updating a builder is seamless and new builders parse correctly. J&M is the pilot.

- **Decided (ADR-0011, `CONTEXT.md` term "Builder Profile"):** per-builder rules stored as **versioned JSON** at `config/builder_profiles/<vendor>.json` (keyed by `standardize.resolve_builder_vendor`); consumed by Drop-files + search helper; auto-learned on import + hand-tunable. Private catalog stays in DB/Fly (ADR-0005).
- **OPEN QUESTION (answer to resume):** should the profile store **only durable rules** (category synonyms, item→category overrides, per-option eligibility, parse hints) and keep **charges/category list live from the DB** (so re-imports refresh prices automatically, no stale numbers)? (Agent recommended: yes.)
- **Then:** grill how Drop-files captures/applies the profile → then **J&M tracer-bullet refactor**: move today's hardcoded J&M vocabulary (synonyms, keyword sets) into `config/builder_profiles/j-and-m-woodworking.json` with search-upcharge behavior unchanged (no regression), plus percent-adder (`addon_pct`) support for builders that price options as `+%`.
- Note: only **J&M** is loaded locally (other 94 builders were purged during a reset). To validate multi-builder flexibility, pull the full catalog or import a contrasting builder.

## How to run / test / verify
- Deps + run: see `README.md` / `run.sh`. Local: `PORT=8501 ./run.sh` → http://localhost:8501, login `Foothills` / `Amish`.
- Tests: `.venv/bin/python -m pytest -q` (50 passing).
- **Gotcha:** the Streamlit dev server does NOT hot-reload edited `.py` on browser refresh — restart the `streamlit run` process (SIGTERM, then `kill -9` if it ignores it) then `PORT=8501 ./run.sh`. DB changes DO show on refresh. (Also in `AGENTS.md`.)
- Live data: `./scripts/pull_db_from_fly.sh` (needs `flyctl` + a real `FLY_API_TOKEN` starting `FlyV1 ` / `fm2_`). Local catalog is currently the **J&M-only reset**; full pre-reset backup kept at `master_pricebook.full-backup-*.db`.

## To deploy PR #34 (when user says go)
- `fly deploy -a faf-pricebook --remote-only` (needs real `FLY_API_TOKEN`), or merge PR #34 to `main` (triggers the deploy Action if the repo Actions secret is set). Deploys ship **code only**; the Fly volume catalog is untouched.

## Gotchas / notes
- **Cursor Usage Meter BML coach** repeatedly auto-injected "Cursor Usage Meter" skill tasks into THIS FAF cloud agent (wrong repo). All were declined; no changes made. To stop: `CUM_BML_AUTO_CONTINUE=0` (or stop the coach) on the Mac running it.
- Never commit `*.db`, `*.db.gz`, `.env`, `.streamlit/secrets.toml` (repo is public).
