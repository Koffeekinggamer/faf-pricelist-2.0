# FAF Pricebook — master row standard

Every sellable row in `master_pricebook.db` is normalized to the same shape.

## One builder = one vendor

**Never store the same builder twice** under different names or files.

| Rule | Detail |
|------|--------|
| Canonical name | `Millers Woodshop`, not `MWS 2023` + `Millers Woodshop 2026` |
| Filename → builder | `HW_2025_…` → Hope Wood; `Jan 2026 wholesale` → Rainbow Bedding |
| Re-import | **replace_vendor** (default): deletes that builder’s rows, then loads the new book |
| Batch folder | If two files map to the same builder, only **one** is imported |

CLI / UI defaults use `replace_vendor`. Avoid **append** unless you intend duplicates.

## Canonical row

| Field | Rule |
|-------|------|
| **vendor** | Clean display name (`Hope Wood`, `Genuine Oak`, …) |
| **collection** | Product category only — not sheet names, not option/upcharge lines. Defaults: FN Chair → Seating, Genuine Oak → Casegoods. `Mult-Gun` → Gun Cabinets |
| **part_number** | Trimmed SKU / item code (or full item name if builder has no SKU) |
| **description** | Always filled (falls back to `part_number`) |
| **species** | Wood tier **or** color/fabric option, slash-separated woods, Title Case. Never `col_N` / `FINISHED` |
| **species_tier** | Optional 1…N |
| **finish_state** | `finished` \| `unfinished` only (default `finished`) |
| **base_price** | Builder **wholesale** list |
| **price_basis** | Always `wholesale` |
| **multiplier** | Per-vendor (Genuine Oak **1.7**, others **2.7**) |
| **adjusted_price** | `round(base × mult, 2)` |

## Species examples

| Builder original | Canonical |
|------------------|-----------|
| `OAK BR. MAPLE SAP CHERRY` | `Oak / Brown Maple / Sap Cherry` |
| `Cherry,Hard Maple,Hickory` | `Cherry / Hard Maple / Hickory` |
| `FINISHED (2)` | `Wood Tier 2` (+ finish_state) |
| `Standard Colors` | `Standard Colors` (Patio Kraft) |
| `Premium` | `Premium` (LuxHome fabric) |
| `col_4` | **dropped** (junk) |

## Apply

```bash
# One-shot rewrite of master DB
.venv/bin/python -m backend.cli standardize

# New imports auto-standardize via backend.normalize
```

Code: `backend/standardize.py` · hooked from `normalize_dataframe` / CLI `standardize`.
