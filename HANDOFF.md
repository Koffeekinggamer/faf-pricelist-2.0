# Agent Handoff — FAF Price Book

**Date:** 2026-09-10  
**Owner / user:** Judson (Foothills Amish Furniture)  
**Working copy:** `~/FAF-pricelist-2.0`  
**Canonical git remote:** `origin` → https://github.com/Koffeekinggamer/faf-pricelist-2.0  
**Active branch:** `cursor/hide-finish-keep-options-ee2a`  
**Tip:** `db9026f` — named readers + 0–100% upload quality  
**Main UI:** `pricebook_app.py` — accuracy mode (Search · Drop · Vendors · Admin)  
**OrderTrac:** UI flags still **off** — do not re-enable unless Judson asks  
**Live app:** https://faf-pricebook.fly.dev · Login **Foothills** / **Amish**

Traveling catalog, images, secrets, and the signed-in session live on the price-book drive at `FAF-pricebook/` (usually `/Volumes/ExternalSSD/FAF-pricebook`).

**As of 2026-09-10 (SSD catalog):** **210,188 rows · 48 builders · 67 source files.**  
Retail = wholesale × mult (2.7 default, Genuine Oak 1.7). One builder = one vendor.

---

## Switch to another computer (do this first)

Plug the **ExternalSSD** in before `./run.sh`. Do not pull Fly over this book unless you intend to replace the drive catalog.

```bash
# 1) Code
git clone https://github.com/Koffeekinggamer/faf-pricelist-2.0.git ~/FAF-pricelist-2.0
cd ~/FAF-pricelist-2.0
git checkout cursor/hide-finish-keep-options-ee2a
git pull

# 2) Python env + hooks
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install   # husky / lint-staged only

# 3) Plug ExternalSSD. Catalog + secrets are on that drive.
./run.sh
# http://127.0.0.1:8501 · Foothills / Amish
```

`./run.sh` finds `FAF-pricebook/master_pricebook.db` on the drive, links secrets, and signs back in from the remember-me token stored there.

**Do not commit:** `*.db`, `.env`, `.streamlit/secrets.toml`.

Thin scan: `./scripts/ready_catalog.sh --no-pull`.

Refresh Fly catalog from this drive:  
`FAF_LOCAL_DB=/Volumes/ExternalSSD/FAF-pricebook/master_pricebook.db ./scripts/push_db_to_fly.sh`  
Deploy **code** only: `fly deploy -a faf-pricebook --remote-only`

---

## 30-second local start (this Mac)

```bash
cd ~/FAF-pricelist-2.0
./run.sh
# http://127.0.0.1:8501 · Foothills / Amish
```

```bash
.venv/bin/python -m backend.cli stats
```

---

## What this app is

Streamlit + SQLite **floor price book** for Amish furniture builders. One app, many builders. Each Drop **adds** a builder; re-drop replaces that builder only. After a good Load, the named parser locks in `config/builder_profiles/<vendor>.json`.

| Layer | Path                       | Role                                                                 |
| ----- | -------------------------- | -------------------------------------------------------------------- |
| UI    | `pricebook_app.py`         | Accuracy mode (Search / Drop / Vendors / Admin); OrderTrac flags off |
| Logic | `backend.PriceBookService` | All real operations                                                  |
| Excel | `wide_import.py`           | Wide builder matrices → long rows                                    |
| PDF   | `pdf_import.py`            | PDF price lists                                                      |
| DB    | SSD `master_pricebook.db`  | Long-form: SKU × species × finish                                    |

**Rules (locked):**

- One builder = one vendor (`replace_vendor` on re-import)
- Retail = wholesale × multiplier (even whole dollars)
- Default mult **2.7**; **Genuine Oak 1.7**
- **Undermount Drawer Slides** = no markup
- Every builder Excel encodes Options — empty Search Options is a capture miss
- Never unhide a sheet or row
- H" / W" / D" = Height × Width × Depth, never Wood
- All woods belong in the Wood column, never Options
- Steel, Metal, and Cushion are row materials (Wood column)
- Mixed woods show in the Wood dropdown as `wood/wood`
- Upload quality is 0–100% on Vendors and Drop (100% = nothing left to fix)
- Local DB never committed; backups on the drive under `FAF-pricebook/backups/`

Thin KEEP (do not treat as broken): Amish Aspen, Maple Lane, Signature Designs, Ebony Woodworking. Patio Kraft KEEP (poly outdoor).

Docs: `AGENTS.md` → `CONTEXT.md` → this file → `STANDARDS.md` · `docs/adr/`

---

## Session (2026-09-10)

- Named readers: Brookside, Frog Pond, J. Troyer (3 books), Windy Acres, LAMB Options + Walnut as Wood, Patio Kraft Cushion, Stone River Metal, Troyer Design Steel.
- Mixed-wood dropdown (`Cherry/Hickory`). Drop Options unpack fix. Vendors Quality column.
- Reloaded 25 factories where the new parse did not lose rows or explode twins. Left alone: J. Troyer live (3 books already in Search), Kidron (8 books), Farmside, Genuine Oak, Dutch Creek, Criswell, Frog Pond, Red Barn, Troyer Ridge, FN, Artisan, Ashery (live file newer than some SSD copies), Hermies / Elite / Meadow Lane / Crystal Valley / AJ’s / Five Star (parse inflate), Nisley (would shrink).
- Code: GitHub `db9026f` · Fly image deployed 2026-09-10.

---

## Credentials (do not commit)

| System    | Where                                                                            |
| --------- | -------------------------------------------------------------------------------- |
| App login | defaults **Foothills** / **Amish** · optional drive `FAF-pricebook/secrets.toml` |
| Viztech   | drive secrets `[viztech]` or env `VIZTECH_USER` / `VIZTECH_PASSWORD`             |
| Fly / gh  | drive `FAF-pricebook/credentials/` — `./run.sh` links them onto a new laptop     |

Secrets files are gitignored. Example only: `.streamlit/secrets.toml.example`.

---

## Known issues / next work

1. **Reminder — do not build yet:** per-user login/password; pins per user; invite link; billing.
2. Ashery / FN Chair source files in Downloads may be newer than the SSD Viztech copy — do not re-drop from the older file.
3. OrderTrac UI remains off by design.
4. Streamlit: after Python edits, **restart** `./run.sh`.

---

## Do / don’t

| Do                                     | Don’t                                  |
| -------------------------------------- | -------------------------------------- |
| Work in `~/FAF-pricelist-2.0`          | Commit `master_pricebook.db`           |
| Plug ExternalSSD, then `./run.sh`      | Pull Fly onto a different app          |
| `replace_vendor` for builder re-import | Duplicate same builder under two names |
| Backup before bulk ops                 | Re-drop a settled factory              |
| Keep OrderTrac flags off unless asked  | Unhide Excel sheets or rows            |
