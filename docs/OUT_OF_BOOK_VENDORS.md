# Out-of-book vendors

`VENDOR_CANON` still names factories that are **not** in the 48-builder SSD
catalog and do **not** have a SETTLED fixture contract. Do not invent a catalog
for them. Do not silently delete the identity aliases — STANDARDS and filename
examples still use them.

| Vendor | Code today | Disposition |
| ------ | ---------- | ----------- |
| **Millers Woodshop** | `looks_like_millers` + `enhance_millers_long_df` in `backend/millers_import.py`; CatalogSpec `millers_woodshop`; locked `config/builder_profiles/millers-woodshop.json` | Real reader. Locked for the next selling Drop. **Not SETTLED** (no in-book golden file). STANDARDS identity example (`MWS 2023` → Millers). |
| **Rainbow Bedding** | `VENDOR_CANON` + filename hint `jan 2026 wholesale` | **Out-of-book.** No reader, no profile. LAYOUT_SYSTEM mentions item+price pairs as a historical layout family — that is not a named parser. Keep the alias. Do not Drop a guessed book. |
| **Charleston Forge** | `VENDOR_CANON` only | Alias / old vendor. No reader, no profile. Do not invent a catalog. |
| **Beaverdam** | `VENDOR_CANON` only | Alias / old vendor. `pdf_import` names a columnar-zip *strategy* after Beaverdam; that is not a factory lock. |
| **GVWI** / Gable Valley | `VENDOR_CANON` (`gvwi`, `gable valley`) | Alias / old vendor. No reader, no profile. Do not invent a catalog. |

LuxHome was the other Tier D name; it is now locked (`luxhome` → `backend.luxhome_import`) on the LuxHome branch.

Green Meadows and Simple Living stay in `scripts/viztech_sync.py` `IGNORE_BUILDERS` (PDF-only / not needed on floor). ADR-0007: agents never auto-ignore a thin catalog.
