# Foothills Amish Furniture — Price Book (Floor Cheat Sheet)

## Login
| | |
|---|---|
| **Username** | Foothills |
| **Password** | Amish |
| **Local** | http://localhost:8501 |
| **Public** | Use the share link from the manager (or Streamlit Cloud URL when live) |

Sign out from the left sidebar when done.

---

## Find a price (Search tab)

1. Type a **part number** (best) or product words  
   Examples: `VECG` · `GO-AVNNS` · `LA-ASH-3067-EX` · `oak nightstand`
2. Optional filters:
   - **Builder** — limit to one factory
   - **Collection** — section within that builder
   - **Finish** — default is **finished** (what customers usually buy)
3. Read the **RETAIL** column — that is the customer price.

**Tips**
- Short SKUs rank above dust covers (`VECG` before `VECG-DC`).
- Search shows up to **150** matches. Narrow with Builder or more specific words.
- **Pin builder** (when a builder is selected) keeps that factory at the top of the list for the showroom iPad.

---

## How pricing works

```
RETAIL  =  wholesale  ×  multiplier
```

| Builder type | Typical mult |
|--------------|--------------|
| Most Amish builders | **2.7** |
| Genuine Oak | **1.7** |

Managers change mults on the **Vendors** tab (Save multipliers). Floor staff only need Search.

---

## What floor staff should *not* use
- **Drop files** — manager / office only (imports catalogs)
- **Vendors** — manager only (change mults)
- **Admin** — manager only (backup / cleanup)

---

## If something looks wrong
1. Confirm **Finish** is set to finished (or All).
2. Confirm the correct **Builder**.
3. Ask a manager to check the mult for that builder on Vendors.
4. Managers: **Admin → Backup DB now** before big imports.

*One builder = one catalog. Re-importing replaces that builder’s whole book.*
