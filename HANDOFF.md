# Agent Handoff — FAF Price Book

**Date:** 2026-08-05  
**Owner / user:** Judson (Foothills Amish Furniture)  
**Working copy:** `~/FAF-pricelist-2.0`  
**Canonical git remote:** `origin` → https://github.com/Koffeekinggamer/faf-pricelist-2.0  
**Active branch this session:** `cursor/hide-finish-keep-options-ee2a`  
**Main UI:** `pricebook_app.py` — accuracy mode (Search · Drop · Vendors · Admin)  
**OrderTrac:** UI flags still **off** — do not re-enable unless Judson asks  
**Live app:** https://faf-pricebook.fly.dev · Login **Foothills** / **Amish**

---

## Switch to another computer (do this first)

```bash
# 1) Clone / pull code
git clone https://github.com/Koffeekinggamer/faf-pricelist-2.0.git ~/FAF-pricelist-2.0
cd ~/FAF-pricelist-2.0
git checkout cursor/hide-finish-keep-options-ee2a   # or main after merge
git pull

# 2) Python env + hooks
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install   # husky / lint-staged only

# 3) Live catalog (gitignored — never in GitHub)
export PATH="$HOME/.fly/bin:$PATH"
fly auth login   # once
./scripts/pull_db_from_fly.sh

# 4) Run
./run.sh
# http://127.0.0.1:8501
```

J&M catalog photos ship in git under `assets/catalog_images/` (public catalog art).  
Re-extract only if matching more SKUs: `.venv/bin/python scripts/match_jm_catalog_images.py /path/to/JM_catalog.pdf`

**Do not commit:** `*.db`, `.env`, `.streamlit/secrets.toml`.

Thin scan after pull: `./scripts/ready_catalog.sh --no-pull`.

---

## 30-second local start (this Mac)

```bash
cd ~/FAF-pricelist-2.0
./run.sh
# http://127.0.0.1:8501 · Foothills / Amish
```

Refresh Fly catalog after local DB changes: `./scripts/push_db_to_fly.sh`  
Deploy **code** only: `fly deploy -a faf-pricebook --remote-only`

**As of 2026-08-05 (this workspace):** ~**4,723 rows · 1 builder (J & M Woodworking)** on both local + Fly.  
Full multi-builder book may live on another Mac / backup — confirm before overwriting Fly.

```bash
.venv/bin/python -m backend.cli stats
```

---

## What this app is

Streamlit + SQLite **floor price book** for Amish furniture builders.

| Layer | Path                       | Role                                                                 |
| ----- | -------------------------- | -------------------------------------------------------------------- |
| UI    | `pricebook_app.py`         | Accuracy mode (Search / Drop / Vendors / Admin); OrderTrac flags off |
| Logic | `backend.PriceBookService` | All real operations                                                  |
| Excel | `wide_import.py`           | Wide builder matrices → long rows                                    |
| PDF   | `pdf_import.py`            | PDF price lists                                                      |
| DB    | `master_pricebook.db`      | Long-form: SKU × species × finish                                    |

**Rules (locked):**

- One builder = one vendor (`replace_vendor` on re-import)
- Retail = wholesale × multiplier (even whole dollars)
- Default mult **2.7**; **Genuine Oak 1.7**
- **Undermount Drawer Slides** = no markup (retail = wholesale) for all builders, now and on future imports
- Local DB never committed; backups under `~/Documents/FAF-pricebook-backups/`

Docs: `AGENTS.md` → `CONTEXT.md` → this file → `STANDARDS.md` · `docs/adr/`

---

## Session work completed (2026-08-05)

### J&M catalog images

- New table `catalog_images` (vendor + part_number PK → `image_path`, source/page/match_method).
- Matcher: `backend/catalog_images.py` + `scripts/match_jm_catalog_images.py` (pdfplumber + Pillow).
- **59** SKUs matched/extracted under `assets/catalog_images/j-and-m-woodworking/` (committed — public catalog art).
- Search UI: `ImageColumn` via **inline JPEG data-URI thumbnails** (Streamlit cannot load bare filesystem paths).
- Image column **stays visible** for builders that have any photos, even when the current search hits only un-photographed SKUs (cells blank, not dropped).
- Coverage gap: Antique Mission / many beds (e.g. 1024–1027) have **no** PDF photo yet — blank Image cells are expected.

### Pricing

- `backend/pricing.py`: `is_no_markup_option` / `catalog_multiplier` / `catalog_retail` for **Undermount Drawer Slides**.
- Wired through `standardize_row`, batch import, search upcharge, and SQL `reapply_multiplier` / `recompute_adjusted`.

### Search UX

- Clear button next to the search box (session_state safe).
- Theme: white background + dark text again (`.streamlit/config.toml` + CSS in `pricebook_app.py`). Earlier royal-blue experiment reverted.

### Tests

- `tests/test_catalog_images.py`, undermount coverage in `tests/test_option_upcharge.py`.
- Full suite green locally (~68 tests).

---

## Architecture reminders

```
pricebook_app.py              # UI only (thumbs, Clear, theme)
backend/service.py            # facade + _with_catalog_images
backend/repository.py         # SQL + catalog_images CRUD
backend/catalog_images.py     # PDF caption↔image matching
backend/pricing.py            # multipliers + no-markup options
scripts/match_jm_catalog_images.py
```

Import modes: `replace_vendor` (default), `upsert`, `append`, `replace_source`.

---

## Credentials (do not commit)

| System    | Where                                                                                                |
| --------- | ---------------------------------------------------------------------------------------------------- |
| App login | defaults **Foothills** / **Amish** · optional `.streamlit/secrets.toml` `[auth]`                     |
| Viztech   | `.streamlit/secrets.toml` `[viztech]` username/password (or env `VIZTECH_USER` / `VIZTECH_PASSWORD`) |
| Fly       | `fly auth login` · deploy token may live in GitHub Actions `FLY_API_TOKEN`                           |

Secrets files are gitignored. Example only: `.streamlit/secrets.toml.example`.

---

## Fly notes (images)

`assets/catalog_images/` is in the Docker image via `fly deploy` (public catalog art in git).  
Push DB so live has `catalog_images` rows pointing at those paths:

```bash
./scripts/push_db_to_fly.sh
```

Only push when local catalog is the intended live book (this workspace: ~4.7k J&M rows).

---

## Known issues / next work

1. **Raise J&M photo match rate** — Antique Mission and other collections still missing; improve caption geometry / re-run matcher on full catalog PDF.
2. **Confirm full multi-builder DB** before treating this 4.7k-row J&M book as production forever — restore from `~/Documents/FAF-pricebook-backups/` if needed.
3. **Merge feature branch → `main`** when ready so GitHub Actions auto-deploy + other machines default to the same tip.
4. OrderTrac UI remains off by design.
5. Streamlit: after Python edits, **restart** `./run.sh` (no reliable hot reload for backend).

---

## Do / don’t

| Do                                                        | Don’t                                             |
| --------------------------------------------------------- | ------------------------------------------------- |
| Work in `~/FAF-pricelist-2.0`                             | Commit `master_pricebook.db`                      |
| `replace_vendor` for builder re-import                    | Duplicate same builder under two names            |
| Backup before bulk ops: `python -m backend.cli backup-db` | Wipe vendors Viztech doesn’t have during sync     |
| Keep OrderTrac flags off unless asked                     | Re-enable OrderTrac UI casually                   |
| Pull includes `assets/catalog_images/`                    | Commit `*.db` / secrets                           |
