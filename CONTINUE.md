# FAF Pricebook — LIVE

**Updated:** 2026-07-18  
**Folder:** `~/FAF-pricebook`  
**GitHub:** https://github.com/Koffeekinggamer/pricebook-system (`origin`)  
**Status:** LIVE · Viztech-backed catalog · boolean search · monthly sync  
**Book size:** **~476,824 rows · 155 vendors · 3,104 collections**

> **Full agent handoff:** [HANDOFF.md](./HANDOFF.md) — read that first when starting a new session.

## Run

```bash
cd ~/FAF-pricebook
source .venv/bin/activate
streamlit run pricebook_app.py --server.port 8501
# http://127.0.0.1:8501
# Login: Foothills / Amish
```

Public tunnel (ephemeral): `~/Documents/FAF-pricebook-backups/CURRENT_PUBLIC_URL.txt`

## Backup (local only — never GitHub)

```bash
.venv/bin/python -m backend.cli backup-db
# → ~/Documents/FAF-pricebook-backups/master_pricebook-YYYYMMDD-HHMMSS.db
```

## CLI

```bash
.venv/bin/python -m backend.cli stats
.venv/bin/python -m backend.cli vendors
.venv/bin/python -m backend.cli search "nightstand" --vendor "Genuine Oak"
.venv/bin/python -m backend.cli standardize
.venv/bin/python -m backend.cli backup-db
.venv/bin/python scripts/viztech_sync.py --dry-run
.venv/bin/python scripts/viztech_sync.py
```

## Decisions locked in

- One builder = one vendor (`replace_vendor` default)
- Mult: default **2.7**; Genuine Oak **1.7**
- FN Chair = **Level One only** on Viztech import
- Viztech sync keeps builders not on Viztech
- Local DB gitignored; backup to Documents only
- Search: boolean; Collection column first; sidebar collapsed by default
- Vendors: Phone + Multiplier editable; Items/Collections locked

## Next work (priority)

1. Fix ~26 Viztech files that import as 0 rows (formula sheets)
2. Commit/push product code (no DB/secrets) if user wants
3. Fill builder phones / better scrape
4. Confirm hosted deploy strategy (local DB is source of truth)

## Next prompt (copy-paste)

```
Continue FAF Price Book at ~/FAF-pricebook.
Read HANDOFF.md first.
Next: [failed Viztech parsers / git commit / phones / deploy / user request]
```
