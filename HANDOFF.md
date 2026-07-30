# Agent Handoff — FAF Price Book

**Date:** 2026-07-26 (restored as main)  
**Owner / user:** Judson (Foothills Amish Furniture)  
**Working copy:** this repo (`faf-pricelist-2.0`) or `~/FAF-pricelist-2.0` on the Mac  
**Canonical git remote:** `origin` → https://github.com/Koffeekinggamer/faf-pricelist-2.0  
**Sibling remotes (reference):** `pricebook-system`, `faf-pricebook-system`  
**Main UI:** `pricebook_app.py` — **accuracy mode** (Search · Drop · Vendors · Admin)  
**OrderTrac:** hidden in UI (`SHOW_ORDERTRAC_* = False`); backend kept for later  
**Backup of slim Phase‑1 experiment:** branch `backup/phase1-slim-2026-07-26`

---

## 30-second start

```bash
./run.sh
# http://127.0.0.1:8501
# Login: Foothills / Amish
```

Autostart LaunchAgents may already be running Streamlit on **8501**.  
**Online (Mac can be closed):** https://faf-pricebook.fly.dev · Login Foothills / Amish  
Refresh Fly after local catalog updates: `./scripts/push_db_to_fly.sh`  
**Deploy code to Fly:** `fly deploy -a faf-pricebook` (Mac), or GitHub Action on `main` once `FLY_API_TOKEN` is set (see `DEPLOY.md`)  
Mac tunnel (optional): `~/Documents/FAF-pricebook-backups/CURRENT_PUBLIC_URL.txt`

**Live DB (gitignored):** `~/FAF-pricelist-2.0/master_pricebook.db`  
**As of 2026-07-18 (finish pass):** ~**390,509 rows · 181 vendors · 3,459 collections · 165 phones**  
Cleaned dups + thin-catalog reimports (Hillside Chair 3040, Maple Lane 76, Amish Aspen 40).  
Public: `~/Documents/FAF-pricebook-backups/CURRENT_PUBLIC_URL.txt` · Backup: `master_pricebook-20260718-133324.db`

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
- Local DB never committed; backups under `~/Documents/FAF-pricebook-backups/`

Docs: `STANDARDS.md` · `LAYOUT_SYSTEM.md` · `PROMPTS.md` · `FLOOR_CHEAT_SHEET.md` · `README.md`

---

## Session work completed (2026-07-17 → 18)

### Viztech bulk import

1. Logged into **viztechfurniture.com** (Preferred Dealer).
2. Downloaded builder pricelists → `~/Documents/viztech-downloads/all-20260717/`.
3. Imported into master DB (`replace_vendor`).
4. Kept builders **not** on Viztech (e.g. Millers Woodshop, LuxHome, Beaverdam, Charleston Forge, GVWI).
5. **FN Chair** = Level One only (not Level Two).

### Monthly Viztech automation

| Item             | Location                                                            |
| ---------------- | ------------------------------------------------------------------- |
| Sync script      | `scripts/viztech_sync.py`                                           |
| Install schedule | `scripts/install_viztech_monthly_sync.sh`                           |
| LaunchAgent      | `com.faf.pricebook.viztech-sync` · every **2,592,000 s (~30 days)** |
| Credentials      | `.streamlit/secrets.toml` → `[viztech]` (**gitignored**)            |
| Logs             | `~/Documents/FAF-pricebook-backups/viztech-sync.{log,err}`          |
| State            | `~/Documents/FAF-pricebook-backups/viztech_sync_state.json`         |

```bash
.venv/bin/python scripts/viztech_sync.py --dry-run   # login + list builders
.venv/bin/python scripts/viztech_sync.py             # full download + import
```

**Note:** LaunchAgent first fire is ~30 days after install (not immediate). Mac must be on/logged in.

### UI changes

- **Search:** Boolean (`AND` default, `OR`/`|`, `NOT`/`-term`, `"phrases"`, parentheses); matches all pricelist fields; LIKE wildcards escaped.
- **Search layout:** Main column = search bar + filters + results; **right column = Pinned builders** (separate list).
- **Pin click:** Clears search box, sets Builder to pin, Finish → finished (via `_pin_select` **before** widgets — avoids Streamlit session_state error).
- **Results columns:** Collection first, then Part #, …
- **Vendors tab:** Phone column (editable) next to Builder; Items/Collections locked; mult + phone save together.
- **Sidebar:** Collapsed by default; Viztech status **not** on floor sidebar (Admin only).
- **Admin:** Viztech check / full sync / install 30-day schedule buttons.

### Data cleanup done

- Removed HTML-entity twin vendors (`D amp E` vs `D & E`, `J amp R`, etc.).
- Removed Meadow Wood changelog junk (`Updated`/`Blocked`/`Skipped`).
- Removed FN Chair empty-SKU junk rows.
- Seeded a few real phones from Viztech (many blank — floor can edit).

### Break-test (last pass)

Backend search/vendor/phone/stress checks passed after fixes for:

- Operator-only queries returning whole catalog → now `1=0`
- `%`/`_` as LIKE wildcards → escaped
- Pin session_state after widget create → deferred `_pin_select`

---

## Architecture reminders

```
pricebook_app.py          # UI only
backend/service.py        # facade
backend/repository.py     # SQL + boolean search
backend/import_service.py # Excel/PDF orchestration
backend/standardize.py    # vendor/species/finish canon
wide_import.py            # wide → long
scripts/viztech_sync.py   # monthly Viztech pipeline
scripts/backup_db.py      # local backups
```

Import modes: `replace_vendor` (default), `upsert`, `append`, `replace_source`.

---

## Credentials (do not commit)

| System    | Where                                                                                                |
| --------- | ---------------------------------------------------------------------------------------------------- |
| App login | defaults **Foothills** / **Amish** · optional `.streamlit/secrets.toml` `[auth]`                     |
| Viztech   | `.streamlit/secrets.toml` `[viztech]` username/password (or env `VIZTECH_USER` / `VIZTECH_PASSWORD`) |

Secrets files are gitignored. Example only: `.streamlit/secrets.toml.example`.

---

## Git status at handoff (uncommitted)

Many local changes **not pushed** (and DB never goes to GitHub):

**Modified (examples):** `pricebook_app.py`, `backend/repository.py`, `backend/service.py`, `backend/db.py`, `backend/models.py`, `README.md`, …

**Untracked:** `scripts/viztech_sync.py`, `scripts/install_viztech_monthly_sync.sh`, `assets/`, …

**Next agent should:**

1. Review `git status` / `git diff`
2. Commit product code **without** `*.db` / secrets / downloads
3. Confirm user wants push to `origin/main`

---

## Known issues / next work

### High value

1. **Still-fail Viztech imports — FIXED (2026-07-18):** Deep header scan, desc-as-id, multi name|price catalogs, HW Chair markup calculator, `_to_float` no longer eats `1/4 Sawn`. Recovered **16/16** remaining builders (E&I 4850, L&N 4455, Interior 3990, Outdoor Retreat 5125, E&S 4448, HW Chair 535, …). Report: `~/Documents/viztech-downloads/still_fail_import_report.json`. A few catalogs remain thin (Amish Aspen ~16, Hillside Chair ~5, Maple Lane ~6). **Green Meadows** and **Simple Living** (PDF-only) are **deleted + ignored** — `IGNORE_BUILDERS` in `scripts/viztech_sync.py`.
2. **Phones:** **153/181** vendors have phone numbers (HQ spam cleared; scrape filled most). Rest for floor entry.
3. **Git not synced** — large uncommitted UI/backend/sync/import work (commit product code, never DB/secrets).
4. **Cloud/Fly deploy** may still have **old small DB** if anyone uses a hosted deploy; authoritative catalog is **local** `master_pricebook.db`. Streamlit Cloud does not get the private DB automatically.
5. **Quick Cloudflare URL** is ephemeral; re-run tunnel if dead: `scripts/public_tunnel.sh` or cloudflared quick tunnel → update `CURRENT_PUBLIC_URL.txt`.
6. **Streamlit disconnect mid Drop:** parsed rows used to live in `session_state` (huge shuttle on every Mult click). Fixed with disk cache (`backend/drop_cache.py`) + `websocketPingInterval` / `fileWatcherType=none`. Prefer **localhost:8501** for large Drops; Cloudflare tunnel stays flaky for long ops. Fly VM raised to **2gb** in `fly.toml` (redeploy to apply). Diagnose: `scripts/diagnose_streamlit_disconnect.py`.

### Data quality (ongoing)

- **FN Chair (2026-07-28):** Authoritative import is **PL Print** via `backend/fn_chair_import.py` — Part # = `{Style} {Chair type}`, `option_key` = Cat. 1/2/3 (finish/stain tier), Unf → unfinished. Fabric adder columns → `line_kind=addon` (ADR-0008; not sellable retail). Legacy Cat-only rows still healed in `standardize_row`. Search **Option** lists addon charges + Cat.N. Re-Drop the Level One Blue `.xlsm` (replace builder) on Fly/Mac to refresh the catalog.
- **J & M Woodworking (2026-07-30):** Dedicated import `backend/jmw_import.py` — Br. Maple base × **Percentage** wood table (17 woods), panel **option_key** (Fabric/Crypton/Leather/Flat Panel), Specialty Finish Options + Custom adders as `line_kind=addon`. Re-Drop `JMW_2026_Pricelist_*.xlsx` (replace builder) to refresh Wood/Option dropdowns.
- Meadow Wood reduced but not necessarily perfect.
- Boolean search is powerful but floor staff may need a one-line tip only (caption already there).

### Product / UI polish (optional)

- Pin list: drag-reorder, more than 24 pins.
- Search: optional “Finish = All” default for pin browse when finished is empty (hint already shown).
- Quote builder polish (exists in backend/UI history — verify still smoke-tested).

---

## Do / don’t

| Do                                                        | Don’t                                             |
| --------------------------------------------------------- | ------------------------------------------------- |
| Work in `~/FAF-pricelist-2.0`                             | Commit `master_pricebook.db`                      |
| `replace_vendor` for builder re-import                    | Duplicate same builder under two names            |
| Backup before bulk ops: `python -m backend.cli backup-db` | Wipe vendors Viztech doesn’t have during sync     |
| Keep FN Chair Level One                                   | Import FN Level Two as same vendor without asking |
| Thin Streamlit; logic in `PriceBookService`               | Put business logic only in the UI                 |

---

## Handoff checklist for next agent

- [ ] `cd ~/FAF-pricelist-2.0 && source .venv/bin/activate`
- [ ] `python -m backend.cli stats` → expect ~**518k / ~181 vendors**
- [ ] Open http://127.0.0.1:8501 · login Foothills / Amish
- [ ] Smoke: boolean search, pin a builder (clears query), Vendors phone column, Admin Viztech status
- [ ] Smoke: search **E & I**, **HW Chair**, **Interior Hardwoods**, **L & N**
- [ ] Read this file + `STANDARDS.md` + current `git status`
- [ ] Ask user priority: **git commit** · deploy/tunnel · remaining thin catalogs · something else

---

## Copy-paste prompt for next agent

```
Continue FAF Price Book at ~/FAF-pricelist-2.0.

Read HANDOFF.md first (full session handoff, 2026-07-18).

Context:
- Streamlit + SQLite floor price book for Foothills Amish Furniture
- origin: github.com/Koffeekinggamer/pricebook-system
- DB: master_pricebook.db (~476k rows · 155 vendors) — gitignored
- UI: pricebook_app.py · logic: backend.PriceBookService
- Viztech monthly sync: scripts/viztech_sync.py + LaunchAgent every 30d
- Login Foothills/Amish · local http://127.0.0.1:8501

Do not re-litigate: one builder=one vendor, mult 2.7 (Genuine Oak 1.7),
FN Chair Level One only, keep non-Viztech builders on sync.

Next: [name priority from HANDOFF known issues or user request]
```

---

## Quick contacts / paths

| What              | Path / value                                      |
| ----------------- | ------------------------------------------------- |
| Project           | `~/FAF-pricelist-2.0`                             |
| Backups           | `~/Documents/FAF-pricebook-backups/`              |
| Viztech downloads | `~/Documents/viztech-downloads/`                  |
| Streamlit log     | `~/Documents/FAF-pricebook-backups/streamlit.log` |
| LaunchAgents      | `~/Library/LaunchAgents/com.faf.pricebook.*`      |

**End of handoff.**
