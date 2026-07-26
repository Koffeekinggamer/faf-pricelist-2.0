# Best Overall Layout System — Builder Price Corpus Study

**Date:** 2026-07-16  
**Corpus:** ~500+ price files under Documents / Desktop / Downloads  
**Deep sample:** 37 representative Excel workbooks + major PDF books  
**Key folders:** `AAAA Builder Pricelist Folder` (51), Completed Excel Pricebooks (33), Builder Updates 07172025

---

## Executive answer

**Builders ship WIDE matrices. Your system should STORE LONG rows.**

| Layer | Best layout | Why |
|-------|-------------|-----|
| **Master database / search / export / quotes** | **Long-form sellable row** | One row = one orderable configuration. Filters, multipliers, and PDFs all work. |
| **Source import (what builders send)** | **Wide species matrix** (dominant) | ~⅓ of Excel “primary” sheets; nearly all wood PDF books (Schrock’s, Nisley, Berlin, Salt Creek, Y&M…). |
| **Secondary import** | Long flat SKU+price | Outdoor poly, GVWI, bedding, some specialty. |
| **Retail engine** | Separate multiplier layer | Markup sheets everywhere: **2.7** retail, **1.7** wholesale common. |

Do **not** store the master book as a wide species spreadsheet. That format is great for *human catalogs* and *source files*, terrible for *search, multi-vendor merge, and quoting*.

---

## What the files actually look like

### 1. Wide species matrix — **#1 wood-furniture pattern**

**Shape:**
```
Item # | Description | [Dims] | Species Tier 1 | Species Tier 2 | Species Tier 3 | … | [Est. Finish]
```

**Examples seen:**
| Builder file | Pattern |
|--------------|---------|
| Genuine Oak Master | ITEM # · DESCRIPTION · 5 species groups |
| Schrock’s 2026 | SKU · desc · dims · 5 wood columns · finishing cost |
| FVWW Finished Wholesale | Item · Description · W×D×H · 4 species groups |
| Brookside/BHR bedroom | Part # · Description · 4 species tiers |
| Quality Fabrications | Series · D/W/H · Red Oak · mid · premium · fabric upcharge |
| Premier Office Suites | ITEM # · DESCRIPTION · 2–3 wood columns |
| Nisley / Berlin / Y&M PDFs | Same idea: SKU + multi-`$` by wood |
| J&M / Millwood / Farmside | Collection sheets, wood columns + markup calc |

Species columns are almost never single woods — they are **price tiers**:

| Typical tier | Woods lumped together |
|--------------|------------------------|
| 1 (base) | Oak, Brown Maple, Sap Cherry, Wormy Maple |
| 2 | Rustic QSWO, Rustic Cherry, Rustic Hickory |
| 3 | Cherry, Hickory, Hard Maple, White Oak, QSWO |
| 4 | Walnut / premium |

Top header tokens across the sample: **maple, item, price, cherry, finished, oak, rustic, hickory, unfinished, qswo, description, walnut**.

### 2. Wide finish channel — **#2 wood pattern**

```
Item # | Description | Dims | Fin | Unf | Fin | Unf | Fin | Unf | …  (per species group)
```

**Examples:** Windy Acres Master, FPF Master-bk, Y&M Wren, training table sheets (Double Pedestals / Leg Tables).

Often paired with rule: *“Finished prices — deduct 8% unfinished”* (Brookside) instead of full dual columns.

### 3. Long flat — **clean digital / non-wood**

```
Item / SKU | Description | Wholesale | [Retail] | [Last updated]
```

**Examples:** GVWI, Gable Valley, Rainbow Bedding (item+price pairs), Ashery Oak Products sheet (Model # · Description · Size · Regular), Beaverdam poly (Code · Description · Std Price).

This is the **only** layout that imports cleanly without unpivoting — but it is a minority of Amish casegoods/dining books.

### 4. Markup calculator workbooks — **your floor’s habit**

Almost every “digital” Excel has:
- `Markup` / `MarkUp` / `Multiplier` sheet
- Values **2.7** (retail) or **1.7** (dealer) or per-species % adders
- Sometimes per-column markup (Premier) or furniture vs finishing markup (LAMB)

**Implication:** Base price in master = **builder list (usually wholesale finished or unfinished)**; retail is always `base × multiplier` (and optional finish adder).

### 5. Catalog PDF structure (human book)

```
Collection header
  → Options / upcharges page
  → SKU | Description | Dims | $ $ $ $ (by species)
```

Same data model as wide Excel — just harder to parse. Schrock’s Ashton page is the gold-standard PDF line:

`A591-Q Queen Bed 49" HB, 23" FB $1,647 $1,831 $1,944 $2,390 $2,522 $422`

→ SKU + desc + optional dim note + N species prices + sometimes finish estimate.

### 6. Specialty / secondary

| Type | Layout | Examples |
|------|--------|----------|
| Outdoor poly (simple) | Code · Description · Size · Std/WG price | Beaverdam, Luxcraft |
| Outdoor poly (Patio Kraft) | Multi-section **Item # · Description · color tiers** (Standard / Bright / Woodgrain; or Black / Poly / Woodgrain). Sheets: Retail + Wholesale. Prefer **Wholesale** as base; FAF mult on top. Parser: `import_patio_kraft_workbook` in `wide_import.py`. | Patio Kraft 2026 |
| Tables by size×leaves | Size · Leaves · prices by wood | Berlin Anson, Salt Creek, Troyer Design |
| Metal + top options | SKU · top option · standard/premium metal | Charleston Forge Digital |
| Options only | % or $ adders | Custom size charts, two-tone, leather seats |

---

## Recommended master layout (canonical)

**One row = one sellable configuration** (SKU × species tier × finish state × key option).

| Field | Required | Source |
|-------|----------|--------|
| `vendor` | ✅ | Sidebar / filename / cover |
| `collection` | ✅ | Section header (“Ashton”, “Canyon Creek”) |
| `part_number` | ✅ | Item # / SKU / Code |
| `description` | ✅ | Product name |
| `dimensions` | ○ | W×D×H, bed size, table size |
| `option_key` | ○ | Leaves, footboard type, top thickness, glass vs wood |
| `species` | ✅* | Exact wood **or** tier label |
| `species_tier` | ○ | 1–5 normalized tier for reporting |
| `finish_state` | ○ | `finished` / `unfinished` / `glazed` |
| `base_price` | ✅ | Builder list price (wholesale unless noted) |
| `price_basis` | ○ | `wholesale` / `retail` / `net` |
| `multiplier` | ✅ | Default 2.7 (or vendor override) |
| `adjusted_price` | ✅ | base × multiplier |
| `unit` | ○ | each, set, yard |
| `notes` | ○ | upcharges, N/A woods, quick-ship |
| `source_file` | ✅ | import provenance |
| `imported_at` | ✅ | timestamp |

\*For pure single-price poly/bedding, `species` may be null.

### Why long-form wins for *your* use cases

1. **Search** “oak queen nightstand” works without knowing which column was oak.  
2. **Merge 80 builders** into one book without 40 different column sets.  
3. **Multiplier engine** applies cleanly per row.  
4. **Quote / PDF export** is a filtered long list, not a broken matrix.  
5. **Re-import** replace-by-source-file is trivial.  
6. Wide catalogs still display-friendly via pivot *on demand* (export view), not as storage.

### How import should treat source layouts

```
Wide species Excel/PDF  ──unpivot──►  long rows (1 per species column with $)
Wide finish×species     ──unpivot──►  long rows (species + finish_state)
Long flat               ──map─────►  long rows (direct)
Size×leaf matrix        ──unpivot──►  long rows (option_key = leaves/size)
Markup sheet            ──read─────►  default multiplier for that vendor
```

---

## “Gold standard” source templates (when a builder will share Excel)

If you could standardize *one* outbound template for vendors or for your digital upload pipeline, use this hybrid (inspired by best of FVWW + Genuine Oak + Charleston Forge + Gable Valley):

### Sheet: `Items` (wide is OK for humans; you unpivot on import)

| Item # | Description | Collection | W | D | H | Notes | Oak / BM / Sap Cherry | Rustic tier | Cherry / Hickory / Maple | Walnut | Finish est. |
|--------|-------------|------------|---|---|---|-------|----------------------|-------------|--------------------------|--------|-------------|

### Sheet: `Markup`

| Channel | Multiplier |
|---------|------------|
| Wholesale | 1.0 |
| Retail | 2.7 |

### Sheet: `SpeciesTiers` (optional)

| Tier | Woods included | % adder vs tier 1 |
|------|----------------|-------------------|

### Sheet: `Options` (optional long list)

| Applies to | Option | Add $ or % |

**Best pure-digital long sheet** (GVWI/Gable style) for non-wood or simple catalogs:

| Item # | Description | Wholesale | Retail | Last updated |

---

## Layout scores (from 37-file Excel sample)

**Primary layout per file:**
| Layout | Count | Role |
|--------|------:|------|
| wide_species | 12 | Dominant casegoods/dining/office |
| headers_no_price_detected* | 11 | Covers, markup, indexes (not product data) |
| long_flat | 5 | Best clean digital |
| wide_finish_channel | 4 | Finished vs unfinished |
| price_present_other | 3 | Mixed / training |
| wide_color_matrix | 1 | Poly colors |
| matrix_size_options | 1 | Size grids |

\*Many workbooks have product sheets that *are* wide_species; covers inflated the “no price” count.

**Sheet-level:** wide_species (37) + long_flat (16) + wide_finish (11) confirm the same ranking for real product tabs.

---

## Recommendation for Price Book System product design

1. **Keep SQLite long-form** (already correct direction).  
2. **Upgrade schema** with: `vendor`, `dimensions`, `option_key`, `finish_state`, `price_basis`, `species_tier`.  
3. **Import priority:** unpivot wide species (Excel + PDF) before OCR.  
4. **Default multiplier 2.7**, allow per-vendor override (read Markup sheet when present).  
5. **Species normalization table** mapping builder column headers → standard tier names.  
6. **Export modes:**  
   - Long CSV/Excel (system of record)  
   - Optional pivot-by-species sheet for sales floor (recreate catalog view)  
7. **Do not** chase one universal wide template for storage — you’ll fight every new builder.

---

## Practical pick for “best overall”

| If you mean… | Winner |
|--------------|--------|
| Best **source** format builders already use | **Wide species matrix** (Genuine Oak / Schrock’s / FVWW) |
| Best **internal system** format | **Long-form SKU × species × finish** |
| Best **simple digital** when no wood matrix | **Item · Desc · Wholesale · Retail** (GVWI) |
| Best **retail math** | **Base + multiplier sheet** (2.7), not baked-only retail |

**Overall system to build toward:**  
**Long-form master + wide-matrix importer + markup layer + optional catalog pivot export.**

That is the only design that fits both Schrock’s-style wood books and Beaverdam-style poly codes without two competing systems.
