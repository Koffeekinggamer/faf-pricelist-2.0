# Agent instructions — FAF Price Book (main)

**Holt owns this app only.** Fly app `faf-pricebook`. Path `~/FAF-pricelist-2.0`. This book holds **many builders** — each Drop of a new builder **adds** to the catalog; re-drop replaces that builder only. After a good Load, Drop locks a **named parser** to that builder (`config/builder_profiles/<vendor>.json`) so the next update reuses it. Never open another price-book app. Add builders via Drop, not by overwriting the DB.

1. Read in order: **AGENTS.md** (this file) → **CONTEXT.md** → **HANDOFF.md** → **STANDARDS.md**. Consult **`docs/adr/`** as needed.
2. **This repo is the main FAF Price Book.** Mac/project path: **`~/FAF-pricelist-2.0`**. Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`. Traveling catalog, images, secrets, and the signed-in session live on the price-book drive at `FAF-pricebook/` (usually `/Volumes/ExternalSSD/FAF-pricebook`). Plug the drive in, then `./run.sh` — the laptop signs back in from that folder.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. `pricebook_app.py` is the **only** app entrypoint. Old variations (`pricebook_app_slim.py`, `pricebook_app_legacy.py`) were purged; the slim experiment history remains on branch `backup/phase1-slim-2026-07-26` if ever needed.
7. Thin UI; put logic in `backend.PriceBookService`. One builder = one vendor; retail = wholesale × mult (2.7 default, Genuine Oak 1.7). Every builder Excel encodes Options; empty Search Options is a capture miss, not “no Options.” Never unhide a sheet or row (hidden leftovers are often duplicates). Duplicate cleanup reads the full row first.

## Pricebook image alignment — hard rules

**R1 — Part / item number match → attach image.** Match exact normalized catalog keys within the same builder. If part and item numbers both exist, both must match; otherwise match the populated field. Attach one key to every sibling row carrying it. Never cross builders or use fuzzy product-name matching.

**R2 — Every ingest path, including manual parser.** Run image binding after automated ingest, manual parser materialization, PDF upload, and single-image descriptor upload.

**R3 — Always scan VizTech for the book.** Resolve the builder identity, scan VizTech, then cache/refresh its catalog, feed, pricelist, and image status before applying image policy.

**R4 — Builder not on VizTech means ignore VizTech images only.** Operator PDF and single-image uploads remain enabled. Log `viztech_images_skipped: builder_not_on_viztech`.

**R5 — PDF catalog part number on image maps to the pricebook row.** Extract product figures and explicit nearby part/item keys, attach exact keys for that builder even when VizTech misses, and skip covers, contents, charts, and unkeyed figures.

**R6 — Prompt after successful pricebook upload.** After every successful automatic or manual parse show exactly `Do you want to add pdf of images?` with `Yes` and `Not now`. Yes focuses the sibling uploader without leaving the result. Not now dismisses the prompt; the uploader remains available.

**R7 — Editable descriptor on single-image upload.** Require builder and item(s), allow notes, and keep the descriptor editable. Saving removes stale binds, reparses, rebinds, and reruns Christina.

**R8 — Christina verifies alignment before final.** Use Christina's existing identity, lesson log, and service path. Binds remain draft until she passes or an authenticated operator overrides a flag with a required reason. Replacing a passed hero reruns Christina.

### Christina image-alignment contract

Give Christina builder, row part/item keys and context, asset/storage key, extracted keys, descriptor, source, and prior hero. She checks exact key, builder, descriptor fidelity, silent extra attaches, and hero replacement. Run visual plausibility/group-shot checks only through a real vision path; otherwise record `pending_vision` and never fake a pass.

Persist her actual response projection: `pass|flag`, score, findings, and raw run id. Show findings in the uploader. Flagged actions: override with required reason, remove, or edit descriptor and retry. Search shows only final/override heroes; drafts are Drop-preview-only.

## Fast ops (Mac)

```bash
cd ~/FAF-pricelist-2.0
# Plug in ExternalSSD first. Catalog + secrets are on that drive.
./run.sh
```

Thin scan after pull: `./scripts/ready_catalog.sh --no-pull` (or full `./scripts/ready_catalog.sh`).

Thin = rows < 150 (ADR-0007). Triage → grill Judson keep/replace/ignore. Never commit the DB.

## Agent skills

**Packages:** `.agents/skills/` = [mattpocock/skills](https://github.com/mattpocock/skills) + [caveman](https://github.com/juliusbrussee/caveman) (ADR-0006).  
**Process:** [Practical-Office/Cursor-AI-dev](https://github.com/Practical-Office/Cursor-AI-dev) living process adapted in `docs/agents/skill-process.md` (ADR-0009). That repo teaches the chain — it does **not** replace the skill packages.

Update packages with `npx skills update`, then re-apply FAF overlays on setup-skill seeds and run `scripts/sync_agent_docs.sh`.

### Preferred chain

`setup` → **triage** (`/wayfinder` if foggy / multi-session, else `/grill-with-docs`) → `/to-spec` → `/to-tickets` → `/implement` (Red→Green; reaches `/tdd` + `/code-review`). Unsure? `/ask-matt`.

**User-invoked** (type these): `/ask-matt` · `/grill-with-docs` · `/wayfinder` · `/triage` · `/to-spec` · `/to-tickets` · `/implement` · `/caveman` · setup / architecture skills.  
**Model-invoked** (do not type as primary step): `/tdd` · `/code-review` · `/diagnosing-bugs` · `/domain-modeling` · `/prototype` · …

| Goal                                                        | Skill                      |
| ----------------------------------------------------------- | -------------------------- |
| Sharpen a catalog/import/Search change + grow glossary/ADRs | `/grill-with-docs`         |
| Foggy / multi-session roadmap                               | `/wayfinder`               |
| Unsure which skill fits                                     | `/ask-matt`                |
| Spec → GitHub Issues                                        | `/to-spec` → `/to-tickets` |
| Implement a ticket (test-first)                             | `/implement`               |
| Terse replies (less fluff)                                  | `/caveman`                 |

Full non-negotiables (spec gates, ticket kill test, no refactor inside implement): `docs/agents/skill-process.md`.

### Pre-commit hooks

Husky: **lint-staged** (Ruff via `scripts/run_ruff.sh` — `.venv/bin/ruff` then PATH; Prettier on other text) then **`npm test`** → pytest. No JS typecheck. `package.json` is hooks-only. After clone: `npm install` + `.venv` with `ruff` / `pytest`.

### Issue tracker

GitHub Issues on `Koffeekinggamer/faf-pricelist-2.0` via `gh`. See `docs/agents/issue-tracker.md` (mirrored from setup-skill seed).

### Triage labels

`needs-triage` · `needs-info` · `ready-for-agent` · `ready-for-human` · `wontfix`. Secrets / live DB / Viztech → `ready-for-human`. See `docs/agents/triage-labels.md`.

### Domain docs

Reading order above. Detail in `docs/agents/domain.md` (mirror). **Canonical seeds:** `.agents/skills/setup-matt-pocock-skills/` — sync with `scripts/sync_agent_docs.sh` (ADR-0006).

## Cursor Cloud specific instructions

- The Streamlit dev server (`./run.sh`, port 8501) does **not** hot-reload edited Python on a browser refresh in this environment. After changing `pricebook_app.py` or `backend/*.py`, **restart the server** for the change to render: kill the `streamlit run pricebook_app.py` PID (SIGTERM, then `kill -9` if it ignores it — it sometimes does), then `PORT=8501 ./run.sh`. DB/data changes are read per request, so those DO appear on refresh without a restart.
- Restarting the server briefly drops any forwarded `localhost:8501` (`ERR_CONNECTION_REFUSED`); the app itself is fine (listens dual-stack on `:::8501`). Re-forward the port in Cursor, or use the **Desktop pane**, which hits the VM's localhost directly and doesn't depend on the forward.
- Live data lives on Fly, not git: `./scripts/pull_db_from_fly.sh` / `./scripts/push_db_to_fly.sh` need `flyctl` (installed at `~/.fly/bin`) authenticated via a real `FLY_API_TOKEN` secret (value starts with `FlyV1 ` or the raw `fm2_…`). Deploy code with `fly deploy -a faf-pricebook --remote-only`; deploys ship code only and never touch the catalog volume.
