# County-level combined general merchandise sales tax rates — NC, SC, GA

**As-of / research date:** 2026-09-12  
**Scope:** Combined state + county (and county transit where levied) **general merchandise** sales/use tax rates for every county in North Carolina, South Carolina, and Georgia.  
**Out of scope (excluded from picker recommendations):** city/municipal overlays, reservation-only rates, taxes collected only by localities (not by the state DOR), prepared-food / meal taxes, motor-fuel / energy / jet-fuel specialty charts, and any rate not published on an official state Revenue/DOR page or form cited below.

**Rule:** Do not guess. If a destination-specific rate is not published as a **county** combined general rate, mark **TBD** and exclude it from county pickers.

---

## County-level-only limitation (city overlays excluded)

This note documents sources for **one combined rate per county** for general tangible merchandise, as published by each state’s Department of Revenue (or equivalent).

| State  | What “county rate” means here                                                                                                             | Explicitly excluded overlays                                                                                                                                                                                                                                                                                                                            |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **NC** | Total general rate = 4.75% state + county local articles + county transit (where levied). NCDOR publishes this **by county**.             | Prepared meal taxes “imposed and administered by local jurisdictions” (NCDOR disclaimer on the current-rates page). NC does **not** publish separate municipal general sales tax rates on top of the county rate for the ordinary county table.                                                                                                         |
| **SC** | Statewide 6% + SCDOR-collected **county** local sales taxes (LO, CP, SD, TT, ECI, etc.), as listed on ST-500 / Sales & Use Tax Index.     | **Horry–Myrtle Beach** municipal Tourism Development / related overlay (listed separately at 9% while Horry County is 8%); **Catawba Indian Reservation** rates; local taxes **collected directly by counties or municipalities** (ST-500 disclaimer). Use ST-575 only for municipality-level work — **not** for county pickers.                        |
| **GA** | Jurisdiction codes **001–159** on the quarterly General Rate Chart (state 4% included in the printed total except as noted for code 803). | City / special jurisdiction rows: **044A** DeKalb (Atlanta), **060A** Fulton (Atlanta), **800** Hapeville, **801** College Park (Fulton), **802** East Point, **803** Centennial Yards, **804** Clayton (College Park). For Fulton, county-level picker uses **060 Fulton\*** (outside Atlanta / Hapeville / College Park / East Point), not city rows. |

**Picker policy:** Recommend only verified county rows from the primary sources below. Treat city overlay destinations, reservation sales, and non-DOR-collected locals as **TBD** (exclude from county pickers).

---

## North Carolina (NCDOR)

### Primary official sources

| Role                                                               | Citation                                                                                                                        | URL                                                                                                                                                                                                      |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Primary — county combined rates (HTML table, all 100 counties)** | NCDOR, _Current Sales and Use Tax Rates_                                                                                        | https://www.ncdor.gov/taxes-forms/sales-and-use-tax/sales-and-use-tax-rates/current-sales-and-use-tax-rates                                                                                              |
| **Effective-date / Mecklenburg +1% notice**                        | NCDOR Important Notice (issued 2026-03-02): additional 1.00% county rate effective **2026-07-01**; total general rate **8.25%** | https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/important-notices-issued-sales-and-use-tax-division/important-notice-mecklenburg-county-sales-and-use-tax-increase |
| **Historical county totals (column `7/1/2026 - Current`)**         | NCDOR, _Historical Total General State, Local, and Transit Sales and Use Tax Rates_                                             | https://www.ncdor.gov/taxes-forms/sales-and-use-tax/sales-and-use-tax-rates/historical-total-general-state-local-and-transit-sales-and-use-tax-rates                                                     |
| **Machine-readable SST rate CSV (jurisdiction-level)**             | NCDOR _Sales Tax Rate Database_ → download `Rate Database` (`/rate-database/open`)                                              | https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/streamlined-sales-tax-information/sales-tax-rate-database                                                          |
| **CSV layout / update rules**                                      | NCDOR _Rate and Boundary Database Information_                                                                                  | https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/streamlined-sales-tax-information/rate-and-boundary-database-information                                           |

**Verified download (2026-09-12):** `https://www.ncdor.gov/rate-database/open` returns `Content-Type: text/csv` with `Content-Disposition: attachment; filename="NCR2026Q3APR23.csv"` (Q3 2026 SST rate file; `Last-Modified: 2026-04-30`).

### Effective-date caveats (NC)

- As of **September 2026**, use rates reflecting **2026-07-01** (Mecklenburg additional 1% → **8.25%\*** with transit). Confirmed on the current-rates page and the Important Notice.
- Asterisk (`*`) = includes **0.50% transit** (Durham, Mecklenburg, Orange, Wake on the current table).
- Current-rates page states rates **do not include** prepared meal taxes administered locally.
- SST Rate Database updates on a quarterly SST schedule (local changes generally with ≥60 days’ notice before a calendar quarter). Prefer the **Current Sales and Use Tax Rates** HTML table for simple **county combined** general rates; use the CSV when integrating with SST FIPS/jurisdiction codes.

### Extraction methodology (NC)

1. Prefer the HTML county table on _Current Sales and Use Tax Rates_ (one row per county, combined %).
2. Cross-check Mecklenburg and any asterisk counties against the Important Notice / historical `7/1/2026 - Current` column.
3. Optional: join SST CSV via `/rate-database/open` for jurisdiction codes — **not required** for a county-only picker if the HTML table is used.

### Machine-readable extraction?

| Source               | Complete county coverage?                                  | Structured machine-readable?                                                             |
| -------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Current-rates HTML   | **Yes** (100 counties)                                     | **Yes** (HTML `<table>`; trivial parse)                                                  |
| `NCR2026Q3APR23.csv` | Jurisdiction-level (SST), not a one-row-per-county summary | **Yes** (official CSV), but requires mapping/aggregation to county combined general rate |

**Verdict:** Complete machine-readable extraction of **county combined** rates is **possible** from the official HTML table (and secondarily from the official SST CSV with mapping).

### TBD / exclude from picker

- Any **city meal-tax** add-on (not on the county general table) → **TBD** for destination meal tax; do not fold into county general merchandise picker.
- Non–general-rate categories listed in the Mecklenburg notice (qualifying food 2%, boats, etc.) → not general merchandise county rates.

---

## South Carolina (SCDOR)

### Primary official sources

| Role                                                      | Citation                                                                                                      | URL                                                      |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Primary — county rates HTML (`5/1/26 & after` column)** | SCDOR _Sales & Use Tax Index_ (statewide base **6%** + locals)                                                | https://dor.sc.gov/sales-use-tax-index                   |
| **Primary — county map/chart PDF**                        | SCDOR **ST-500**, _South Carolina Local Tax Designation by County_, Effective **May 1, 2026** (Rev. 3/9/2026) | https://dor.sc.gov/sites/dor/files/forms/ST500.pdf       |
| **Local tax program index / change notices**              | SCDOR _Local Sales Taxes_                                                                                     | https://dor.sc.gov/sales-use-tax-index/local-sales-taxes |
| **Municipality rates (NOT for county pickers)**           | SCDOR **ST-575**, _South Carolina Sales Tax Rate by Municipality_                                             | https://dor.sc.gov/sites/dor/files/forms/ST575.pdf       |

### Effective-date caveats (SC)

- For **September 2026**, use the **`5/1/26 & after`** column on the Sales & Use Tax Index and **ST-500 Effective May 1, 2026**.
- Documented SCDOR changes relevant to that window: Lexington SD extension effective **2026-03-01** (rate remains 7%); Aiken CP reimposition and **Williamsburg** new 1% CP effective **2026-05-01** (Williamsburg total **8%**).
- ST-500 states it **does not** contain Catawba Reservation rates or locals collected directly by counties/municipalities.
- Index lists **Horry–Myrtle Beach** as a separate **9%** line; **Horry County** county rate is **8%**. County pickers must use **Horry 8%** only; Myrtle Beach destinations are **city overlay → TBD / exclude**.

### Extraction methodology (SC)

1. Extract the **`5/1/26 & after`** column from the Sales & Use Tax Index HTML for all **46 counties**.
2. Confirm against ST-500 PDF text (same effective date).
3. Drop the **Horry–Myrtle Beach** row from county datasets.
4. Do **not** use ST-575 to populate county pickers (city-level; also verify revision date vs May 2026 county changes before any municipal use).

### Machine-readable extraction?

| Source                           | Complete county coverage?                        | Structured machine-readable?                                                   |
| -------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| Sales & Use Tax Index HTML table | **Yes** (46 counties + Myrtle Beach overlay row) | **Yes** (HTML table)                                                           |
| ST-500 PDF                       | **Yes** for SCDOR-collected county totals        | **Partial** — official PDF only; text-extractable, no SCDOR CSV/API for ST-500 |

**Verdict:** Complete machine-readable extraction of **county** combined rates is **possible** from the official HTML index table (preferred). ST-500 is authoritative PDF confirmation, not a clean official dataset.

### TBD / exclude from picker

- **Horry–Myrtle Beach** (and any ST-575-only municipal differential) → **TBD** / exclude from county picker.
- **Catawba Indian Reservation** → **TBD** (not on ST-500).
- Locals collected only by a county/municipality (ST-500 disclaimer) → **TBD**.

---

## Georgia (Georgia Department of Revenue)

### Primary official sources

| Role                                       | Citation                                                                         | URL                                                                                                                      |
| ------------------------------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Index of quarterly general rate charts** | GADOR _Sales Tax Rates - General_                                                | https://dor.georgia.gov/sales-tax-rates-general                                                                          |
| **Primary for September 2026**             | _General Rate Chart — Effective July 1, 2026 through September 30, 2026_ (PDF)   | https://dor.georgia.gov/document/document/general-rate-chart-effective-july-1-2026-through-september-30-2026pdf/download |
| **Next quarter (do not use for Sep 2026)** | _General Rate Chart — Effective October 1, 2026 through December 31, 2026_ (PDF) | Linked from https://dor.georgia.gov/sales-tax-rates-general                                                              |
| **Rate posting hub**                       | GADOR _Sales Tax Rates — Current, Historical, and Upcoming_                      | https://dor.georgia.gov/sales-tax-rates-current-historical-and-upcoming                                                  |

### Effective-date caveats (GA)

- GADOR updates general rates **by calendar quarter**. For **as-of September 2026**, the controlling chart is **2026-07-01 through 2026-09-30**.
- The **2026-10-01** chart is already posted on the same index page — **do not** apply it before October 1, 2026.
- Printed jurisdiction totals **include** the 4% state rate except as noted for **803 Fulton (Cent. Yards)**.
- County pickers: use codes **001–159** only. Rows **044A, 060A, 800–804** are city/special overlays → exclude; if a sale is known to be inside those overlays, destination rate is **not** the plain county rate → mark **TBD** for county-only mode or use the overlay row only in a city-aware system.

### Extraction methodology (GA)

1. Download the Jul–Sep 2026 General Rate Chart PDF from the official GADOR document URL above.
2. Parse jurisdiction lines for codes **001–159** (159 counties; verified complete on 2026-09-12 extract).
3. Discard overlay codes **044A, 060A, 800, 801, 802, 803, 804**.
4. For Fulton / DeKalb / Clayton naming: keep **044 Dekalb (Not Atlanta)**, **060 Fulton\***, **031 Clayton (Not Clg Prk)** as the county-level picker rates.

### Machine-readable extraction?

| Source                              | Complete county coverage? | Structured machine-readable?                                                                                                                                                |
| ----------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jul–Sep 2026 General Rate Chart PDF | **Yes** for codes 001–159 | **No official CSV/API** — PDF only. Text extraction works but layout can glue columns (fragile). Not “complete clean machine-readable” from GADOR without a PDF parse step. |

**Verdict:** County rates are **officially complete in PDF** for Sep 2026, but **complete first-party machine-readable (CSV/JSON) extraction is not available**. Downstream must PDF-parse or manually encode; treat fragile parses as needing human verification before picker use.

### TBD / exclude from picker

- Atlanta portions of DeKalb/Fulton (**8.9%** rows), Fulton cities (Hapeville / College Park / East Point **8.75%**), Centennial Yards (**3.9%**), Clayton College Park (**9%**) → **exclude** from county picker; destination inside those zones → **TBD** under county-only policy.
- Specialty GADOR charts (energy, jet fuel, prepaid local motor fuel, etc.) → out of scope.

---

## Cross-state summary for implementers

| State  | As-of Sep 2026 controlling publication                                  | Counties | Official structured data?                | County-picker ready?                                                                    |
| ------ | ----------------------------------------------------------------------- | -------- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| **NC** | NCDOR Current Sales and Use Tax Rates (+ 2026-07-01 Mecklenburg notice) | 100      | **Yes** — HTML table; also SST CSV       | **Yes** — all counties verifiable                                                       |
| **SC** | SCDOR Index `5/1/26 & after` + ST-500 (Eff. 2026-05-01)                 | 46       | **Yes** — HTML table; ST-500 PDF confirm | **Yes** — exclude Myrtle Beach / Catawba / non-SCDOR locals (**TBD**)                   |
| **GA** | GADOR General Rate Chart **2026-07-01 – 2026-09-30**                    | 159      | **PDF only** (no official county CSV)    | **Yes for county codes 001–159 after verified extract**; city overlays **TBD**/excluded |

### Complete machine-readable extraction possible?

- **NC:** **Yes** (official HTML + official SST CSV).
- **SC:** **Yes** for county rows (official HTML); PDF is backup.
- **GA:** **No** official machine-readable county file; **Yes** only via **PDF text extraction** of the quarterly chart (verify before production use).

---

## Sources used (official only)

1. https://www.ncdor.gov/taxes-forms/sales-and-use-tax/sales-and-use-tax-rates/current-sales-and-use-tax-rates
2. https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/important-notices-issued-sales-and-use-tax-division/important-notice-mecklenburg-county-sales-and-use-tax-increase
3. https://www.ncdor.gov/taxes-forms/sales-and-use-tax/sales-and-use-tax-rates/historical-total-general-state-local-and-transit-sales-and-use-tax-rates
4. https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/streamlined-sales-tax-information/sales-tax-rate-database
5. https://www.ncdor.gov/rate-database/open (`NCR2026Q3APR23.csv`)
6. https://www.ncdor.gov/taxes-forms/sales-and-use-tax/other-sales-and-use-tax-resources/streamlined-sales-tax-information/rate-and-boundary-database-information
7. https://dor.sc.gov/sales-use-tax-index
8. https://dor.sc.gov/sites/dor/files/forms/ST500.pdf
9. https://dor.sc.gov/sales-use-tax-index/local-sales-taxes
10. https://dor.sc.gov/sites/dor/files/forms/ST575.pdf (municipality reference only; excluded from county pickers)
11. https://dor.georgia.gov/sales-tax-rates-general
12. https://dor.georgia.gov/document/document/general-rate-chart-effective-july-1-2026-through-september-30-2026pdf/download
13. https://dor.georgia.gov/sales-tax-rates-current-historical-and-upcoming

No third-party tax aggregators were used for rate values.
