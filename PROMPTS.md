# Prompts for Grok — Price Book System

Copy any block below into chat. Fill in the `[brackets]` when you see them.

---

## Everyday ops

### Run / fix the app
```
FAF Pricebook is at ~/FAF-pricebook.
[I can't run it / it crashed / import failed / search is empty.]
Here's what I did and any error text:
[paste error or screenshot description]
Fix it and tell me the exact commands to run.
```

### Import a builder file
```
Import this builder price list into the master price book:
Path: [full path to .xlsx or .pdf]
Vendor name: [e.g. Genuine Oak]
Use workbook markup if present, else multiplier [2.7].
Mode: upsert.
Only import sheet(s): [Master / all product sheets / leave blank for auto].
Report row counts and spot-check 3 sample SKUs.
```

### Batch import a folder
```
Import all Excel price lists from:
[folder path]
Skip Markup/Cover/Index sheets.
Vendor name = filename stem (or better if cover has a name).
Mode: upsert.
Print a table: file → rows inserted/updated → errors.
```

### Search like the floor would
```
Search the master price book as if I'm on the sales floor:
Query: [oak queen nightstand / A591 / Ashton dresser]
Vendor filter: [All / Schrock's / …]
Show top 15 with base, mult, retail. If nothing hits, suggest better search terms.
```

---

## Build features

### Next feature (default phrasing)
```
Continue FAF Pricebook at ~/FAF-pricebook.
Next feature: [duplicate cleanup UI / quote builder / batch folder import / OCR / …]
Use the existing backend.PriceBookService — don't put logic only in Streamlit.
Keep long-form master storage. Match LAYOUT_SYSTEM.md.
When done: smoke-test and give me run commands.
```

### Quote builder
```
Add a Quote Builder to the price book app:
- Search/add lines from master (part, desc, species, qty, base, retail)
- Edit qty and optional line discount
- Customer name + notes
- Totals
- Export quote PDF + Excel
Backend methods on PriceBookService; thin Streamlit tab.
```

### Per-vendor multipliers UI
```
Improve vendor multipliers in ~/FAF-pricebook:
- List all vendors with saved mult and row counts
- Edit mult and recompute that vendor only
- Default 2.7 if unset
- Import should prefer saved vendor mult over sidebar unless I check "use workbook markup"
```

### Fix bad import for one builder
```
This builder file imports wrong:
Path: [path]
Problem: [wrong species pairing / missing SKUs / doubled rows / prices off / …]
Inspect the real columns/layout, fix wide_import or PDF parser as needed,
re-test on that file only, show before/after sample rows.
```

---

## Data quality

### Find and clean duplicates
```
Scan master_pricebook.db for duplicate identity groups
(vendor + part + species + finish + collection).
Show the worst 20. Offer a safe cleanup: keep newest imported_at, delete older dups.
Don't delete without summarizing what would go.
```

### Compare two price list versions
```
Compare two versions of the same builder:
Old: [path]
New: [path]
Vendor: [name]
Report: new SKUs, dropped SKUs, price changes > [5]%.
```

---

## How to talk to me (meta)

### Keep building (short)
```
Keep building the next part of the price book. You pick the highest-value next step from LAYOUT_SYSTEM.md / PROMPTS.md and ship it. Don't ask unless blocked.
```

### Plan only (no code yet)
```
Don't write code yet. Propose a plan for [feature] with:
- files you'll touch
- risks
- test plan on my real builder files
Wait for my OK.
```

### Check your work
```
Verify the last changes on ~/FAF-pricebook:
- run backend CLI stats/search
- import one real Excel with upsert twice (must not double rows)
- note any failures and fix them
```

### Explain like I'm on the floor
```
Explain [feature / how multipliers work / how to import Schrock's]
in plain language for a furniture store owner — short steps, no jargon.
```

---

## Project context (paste once if starting a new chat)

```
I'm building Sir's Private Multiplier Engine — a Streamlit + SQLite price book for Amish furniture builders.

Repo: ~/FAF-pricebook
- UI: pricebook_app.py (thin)
- Backend: backend.PriceBookService (all real logic)
- Parsers: wide_import.py (Excel matrices), pdf_import.py
- DB: master_pricebook.db — long-form rows (SKU × species × finish)
- Layout rules: LAYOUT_SYSTEM.md (builders ship WIDE; we store LONG)
- Typical mult: 2.7 retail, sometimes 1.7 wholesale from markup sheets
- Commit default: upsert (don't double rows)

Continue from current code. Prefer backend changes over stuffing the UI.
```

---

## Tips for better answers

1. **Paste the path** to the file, not just “the Nisley PDF.”
2. **Paste errors** in full.
3. Say **upsert** vs **replace** if you care about re-imports.
4. Say **plan only** if you don’t want code yet.
5. Say **keep going** if you want me to pick the next step without asking.
