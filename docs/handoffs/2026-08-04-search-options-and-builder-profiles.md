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

## Builder Profiles — design + first slice
Goal: learn each builder's conventions once, persist them, and have both the **Drop-files import** and the **search/upcharge helper** consume them so re-importing/updating a builder is seamless and new builders parse correctly. J&M is the pilot.

- **Locked (2026-08-05):** profile stores **only durable rules** (category synonyms, item→category overrides, per-option eligibility, parse hints, charge *shapes*); **charges/category list stay live in the DB**. Recorded in ADR-0011.
- **Locked:** Drop auto-updates profiles on successful Load, **local/Mac only** → commit → deploy; Fly production reads shipped profiles, never writes.
- **Locked first slice:** search/upcharge only (Drop read/write follow-up).
- **Shipped in this branch (tracer bullet):** `config/builder_profiles/j-and-m-woodworking.json` + `backend/builder_profiles.py`; search upcharge reads the profile (defaults preserve prior behaviour for builders without a file); `addon_pct` percent adders raise eligible item retail by pct.

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
