# Handoff — FAF Pricelist 2.0

**For the next agent:** read this file end-to-end before coding.

> **Fresh start (2026-07-21):** User wants a clean greenfield pricelist.  
> Work **only** in this repo. Do **not** keep developing `~/FAF-pricebook` for 2.0.

| | |
|--|--|
| **Project** | FAF Pricelist 2.0 |
| **Owner machine** | Judson’s Mac (`lordjudsonmiller`) |
| **Local path** | `/Users/lordjudsonmiller/FAF-pricelist-2.0` |
| **GitHub** | https://github.com/Koffeekinggamer/faf-pricelist-2.0 |
| **Date** | 2026-07-21 |
| **Status** | Scaffold only — implement phase 1 from here |
| **Prior app** | `~/FAF-pricebook` (v1 legacy — reference only) |

---

## Mission

Build a **clean** Streamlit (or similar) app for **Foothills Amish Furniture**:

1. Staff drop a builder **Excel** pricelist.
2. App shows a **formatted PDF on screen** (team view) — **not** a giant parsed row table.
3. Choosing/editing **builder** updates what they see (title + book identity).
4. **Admin**: backup DB when lists change + edit **multiplier per builder**.

OrderTrac / quoting / full search are **out of phase-1 UI**. Backend ideas can live later.

---

## What the user already decided (from v1 sessions)

| Decision | Detail |
|----------|--------|
| Content accuracy first | Paused quoting/OrderTrac in v1; focus on trustworthy lists |
| PDF on screen | Explicit: *show PDF for the team, don’t show everything as rows* |
| Drop Excel | `.xls` / `.xlsx` / `.xlsm` primary input |
| Multipliers | Store markup; typical **2.7**, Genuine Oak often **1.7** |
| One builder = one vendor | Re-import replaces that builder’s catalog |
| Secrets / DB | Never git-commit `master_pricebook.db` or `.streamlit/secrets.toml` |
| Login | v1 used **Foothills** / **Amish** (seed admin) |

### v1 location (reference only)

```
~/FAF-pricebook/
  pricebook_app.py          # last slim UI (drop → PDF + admin)
  pricebook_app_legacy.py   # full v1 UI (search, quotes, OrderTrac)
  backend/                  # parsers, pricing, OrderTrac, SQLite
  wide_import.py, pdf_import.py
  master_pricebook.db       # local only; was purged then partially refilled
```

v1 remotes: `pricebook-system`, `faf-pricebook-system`  
v1 local URL: http://127.0.0.1:8501 · Fly: https://faf-pricebook.fly.dev  

**Do not** keep bolting features onto v1 for 2.0 — implement here.

---

## Suggested architecture (phase 1)

```
FAF-pricelist-2.0/
  app.py                 # Streamlit entry
  backend/
    db.py                # SQLite schema: items + vendors (mult, phone)
    import_excel.py      # Excel → structured rows (or reuse patterns from v1)
    pdf_catalog.py       # rows → polished multi-page retail PDF (fpdf2)
    service.py           # orchestration
  scripts/
    backup_db.py
  data/                  # gitignored DBs
  assets/                # logo/favicon (copied from v1)
  docs/
    HANDOFF.md           # this file
    PRODUCT.md
```

### PDF viewer

Streamlit **1.50+** has `st.pdf(bytes)`. Use a tall viewer (~700px). Fallback: base64 iframe.

### Excel parsing

v1 has battle-tested **wide species matrix** unpivot in `wide_import.py` + `backend/import_service.py`. Options:

1. **Copy** only the import/pricing modules into 2.0 (preferred if speed matters).  
2. **Reimplement** a thinner importer for the common layouts you care about first.

Do **not** surface long-form rows as the main UI even if you parse under the hood.

### PDF content (floor-facing)

Prefer columns like:

- Part # · Description · Wood · Finish · **Retail**

Avoid dumping wholesale + mult + every internal field on the PDF unless Admin asks.

Retail = `wholesale × multiplier` (round policy: v1 used “next even dollar” in places — check `backend/pricing.py` in v1).

---

## Implementation checklist for the fresh agent

- [ ] Confirm Python 3.9+ and create `.venv`; `pip install -r requirements.txt`
- [ ] Implement SQLite schema + backup script (local path under `~/Documents/FAF-pricelist-2.0-backups` or `data/backups`)
- [ ] Excel drop → parse → **PDF bytes** → `st.pdf` + download
- [ ] Builder name field updates PDF header and save identity
- [ ] Multiplier control affects retail on PDF
- [ ] Admin: list builders, edit mult, recompute retail, backup now
- [ ] Optional: “Save into master” after drop (replace that builder)
- [ ] Login gate (simple)
- [ ] Run on a free port (e.g. **8510**) so v1 on **8501** can keep running
- [ ] Commit and push to `origin` on this repo only

---

## Auth / tools on this machine

- **GitHub user:** `Koffeekinggamer`
- **gh / git push:** token often via macOS keychain `github.com` (`GH_TOKEN` + `gh api` works)
- **gh binary:** `~/.local/bin/gh`
- **Python:** system 3.9 + project `.venv`
- Do **not** print secrets or commit tokens

---

## Repo hygiene

```bash
# Never
git add master_pricebook.db .streamlit/secrets.toml .env

# Always
.gitkeep in data/ if needed; DB gitignored
```

---

## Success criteria (phase 1 done)

1. Floor user logs in, drops a real builder Excel, **sees PDF on screen** without a row-dump UI.  
2. Changing builder name refreshes the on-screen PDF title/book.  
3. Admin can back up DB and change a multiplier.  
4. GitHub `main` is up to date; handoff notes match reality.

---

## Out of band / ask the user if unclear

- Exact retail rounding rules for 2.0  
- Whether PDF should be portrait catalog style vs landscape table  
- Which builders to prioritize for import fidelity  
- Whether 2.0 replaces v1 on Fly or runs side-by-side  

---

## Message for the user when 2.0 is ready to demo

Open http://127.0.0.1:8510 · login Foothills / Amish · Drop files → PDF on screen · Admin → backup / mults.
