# DEPRECATED — not an identity source

> **Do not use this file as identity or as the everyday import script.** Older copies said **Mode: upsert**, which conflicts with the Load path (`replace_vendor`, ADR-0001). Everyday `upsert` / `append` is forbidden.
>
> Read instead:
>
> - [`AGENTS.md`](./AGENTS.md) — identity, Load path, non-negotiables
> - [`docs/PRICEBOOK_AGENT_AUDIT.md`](./docs/PRICEBOOK_AGENT_AUDIT.md) — completeness, forbidden moves
> - [`docs/CURSOR_AGENT_KICKOFF.md`](./docs/CURSOR_AGENT_KICKOFF.md) — paste-ready Holt / add-builder / review prompts
>
> Prompts below are rewritten so a copy-paste cannot select upsert. First jobs still live in the kickoff, not here.

# Prompts for Holt — FAF Price Book

Copy any block below into chat. Fill in the `[brackets]` when you see them.

---

## Everyday ops

### Run / fix the app

```
FAF Pricebook is at ~/FAF-pricelist-2.0.
[I can't run it / it crashed / import failed / search is empty.]
Here's what I did and any error text:
[paste error or screenshot description]
Fix it and tell me the exact commands to run.
Do not pull Fly or deploy without Judson.
```

### Import a builder file

```
Import this builder price list into the master price book:
Path: [full path to .xlsx or .pdf]
Vendor name: [canonical display name — never a Download_* stem]
Use the saved vendor multiplier if present, else [2.7] (Genuine Oak 1.7).
Mode: replace_vendor.
Visible sheets only. Never unhide a sheet or row.
Report row counts and spot-check 3 sample SKUs.
Prove Options from the book and Search (empty Options = capture miss).
```

### Batch import a folder

```
Import all Excel price lists from:
[folder path]
View Cover/Markup/Options/Percentage/visible backups; skip only true duplicates.
Vendor name = canonical display name (confirm; never filename stem / Download_*).
Mode: replace_vendor (one builder = one vendor; never everyday upsert/append).
Print a table: file → rows replaced → errors.
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
Continue FAF Pricebook at ~/FAF-pricelist-2.0.
Read AGENTS.md → CONTEXT.md → HANDOFF.md → STANDARDS.md → docs/PRICEBOOK_AGENT_AUDIT.md → docs/CURSOR_AGENT_KICKOFF.md.
Do the next unchecked first job in the kickoff. Do not start from CONTINUE.md or this file.
Use the existing backend.PriceBookService — don't put logic only in Streamlit.
Keep long-form master storage. One builder = one vendor. Mode: replace_vendor.
When done: smoke-test and give me run commands. No Fly / no DB commit.
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
Do not re-enable OrderTrac UI unless Judson asks.
```

### Per-vendor multipliers UI

```
Improve vendor multipliers in ~/FAF-pricelist-2.0:
- List all vendors with saved mult and row counts
- Edit mult and recompute that vendor only
- Default 2.7 if unset; Genuine Oak 1.7
- Import should prefer saved vendor mult over workbook markup unless I check "use workbook markup"
```

### Fix bad import for one builder

```
This builder file imports wrong:
Path: [path]
Problem: [wrong species pairing / missing SKUs / doubled rows / prices off / …]
Inspect the real visible columns/layout, fix the named reader (not a generic Load under a specific lock),
re-test on that file only, show before/after sample rows.
Mode on re-import: replace_vendor.
```

---

## Data quality

### Find and clean duplicates

```
Scan master_pricebook.db for duplicate identity groups
(vendor + part + species + finish + collection).
Show the worst 20. Offer a safe cleanup: keep newest imported_at, delete older dups.
Read the full row before removing. Don't delete without summarizing what would go.
```

### Compare two price list versions

```
Compare two versions of the same builder:
Old: [path]
New: [path]
Vendor: [name]
Report: new SKUs, dropped SKUs, price changes > [5]%.
On Load of the new book: replace_vendor (not upsert).
```

---

## How to talk to me (meta)

### Keep building (short)

```
Keep building the next unchecked first job from docs/CURSOR_AGENT_KICKOFF.md.
Read AGENTS.md and docs/PRICEBOOK_AGENT_AUDIT.md first.
Don't ask unless blocked. No Fly / no DB commit / no other price-book app.
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
Verify the last changes on ~/FAF-pricelist-2.0:
- run backend CLI stats/search
- import one real Excel with replace_vendor twice (must not double rows)
- note any failures and fix them
Do not use upsert / append.
```

### Explain like I'm on the floor

```
Explain [feature / how multipliers work / how to import Schrock's]
in plain language for a furniture store owner — short steps, no jargon.
```

---

## Project context (paste once if starting a new chat)

Prefer the kickoff prompt in [`docs/CURSOR_AGENT_KICKOFF.md`](./docs/CURSOR_AGENT_KICKOFF.md). If you still need a short paste:

```
You are Holt on faf-pricelist-2.0 only — Streamlit + SQLite floor price book for Amish furniture builders.

Repo: ~/FAF-pricelist-2.0
- UI: pricebook_app.py (thin)
- Backend: backend.PriceBookService (all real logic)
- Parsers: named readers + wide_import.py (Excel matrices), pdf_import.py
- DB: master_pricebook.db — long-form rows (SKU × species × finish)
- Typical mult: 2.7 retail; Genuine Oak 1.7
- Re-import default: replace_vendor (ADR-0001). Everyday upsert / append is forbidden.

Read AGENTS.md → CONTEXT.md → HANDOFF.md → STANDARDS.md → docs/PRICEBOOK_AGENT_AUDIT.md → docs/CURSOR_AGENT_KICKOFF.md.
Continue from current code. Prefer backend changes over stuffing the UI.
```

---

## Tips for better answers

1. **Paste the path** to the file, not just “the Nisley PDF.”
2. **Paste errors** in full.
3. Re-import is **replace_vendor**. Do not ask for upsert / append.
4. Say **plan only** if you don’t want code yet.
5. Say **keep going** if you want the next unchecked kickoff job without asking.
