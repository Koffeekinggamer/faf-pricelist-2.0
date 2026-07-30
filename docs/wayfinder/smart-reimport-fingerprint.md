## Research: Where to store last-import fingerprint per builder

**Verdict:** Store the last successful import fingerprint (plus `source_filename` and `imported_at`) as **new columns on the `vendors` table**, written through `PriceBookService` / `repository` on successful `replace_vendor`. Do **not** put this in `integrations`, Viztech state JSON, or recompute by scanning all pricebook rows on every Drop.

Part of [Smart re-import: skip unchanged builder books](https://github.com/Koffeekinggamer/faf-pricelist-2.0/issues/20).

---

### Current state (codebase)

| Surface                                | What it holds today                                                                                                                                                  | Fit for fingerprint?                                                                                                                                                                               |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`vendors`** (`backend/models.py`)    | `name` PK, `multiplier`, `notes`, `phone`, `updated_at`. Migrated via `VENDOR_NEW_COLUMNS` + `backend/db.py`.                                                        | **Best.** One row per builder (ADR-0001). Already the home for builder-scoped settings.                                                                                                            |
| **`pricebook`**                        | Per-row `source_file`, `imported_at`; identity via `IDENTITY_FIELDS` (`vendor`, `collection`, `part_number`, `species`, `finish_state`, `option_key`, `dimensions`). | Good for **deriving** last filename/timestamp with `GROUP BY vendor`, but **not** a catalog fingerprint. Scanning ~rows-per-builder (or worse, whole book) on every Drop is what we want to avoid. |
| **`integrations`**                     | `key` PK, `status`, `last_ok_at`, `last_error`, `meta_json`. Used by `backend/users.py` for OrderTrac connection health.                                             | **Poor.** Wrong domain (ops/connection, not catalog). Either one giant `meta_json` blob or synthetic keys like `import:<vendor>` — awkward to join with Vendors UI / list settings.                |
| **`viztech_sync_state.json`**          | Mac backup-dir run summary (`last_run`, `ok`/`err`/`skip`, path). Written by `scripts/viztech_sync.py` only.                                                         | **Poor.** Ops telemetry, not per-builder catalog state. Not on Fly volume; Drop on Fly cannot see it. Violates thin-UI / service ownership (ADR-0004) if Drop had to read Mac files.               |
| **On-the-fly hash of current catalog** | Possible via scoped `SELECT … WHERE vendor=?` then hash `IDENTITY_FIELDS` + sellable fields (e.g. `base_price`).                                                     | Correct fallback / backfill, but **every** Drop would re-read that builder’s rows from SQLite. Stored fingerprint makes compare **O(1) lookup + hash inbound once**.                               |

Import path today: Drop and Viztech both end in `svc.add_rows(..., mode="replace_vendor")` → `repository.replace_vendor_rows` (wipe + insert in one transaction). No equality check; no fingerprint write.

---

### Recommendation

**Add columns on `vendors` (via `VENDOR_NEW_COLUMNS`, same pattern as `phone`):**

| Column                    | Purpose                                                                                               |
| ------------------------- | ----------------------------------------------------------------------------------------------------- |
| `last_import_fingerprint` | Stable hash of the **normalized sellable catalog** that was last successfully loaded for this builder |
| `last_import_source`      | Source filename (mirrors row-level `source_file`, but O(1) at builder grain)                          |
| `last_imported_at`        | ISO timestamp of last successful replace                                                              |

Optional (helps map open point on parser invalidation):

| Column                                       | Purpose                                                                                         |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `fingerprint_version` (or `catalog_fp_algo`) | Bump when standardize/parser/identity rules change so stale hashes force a real compare/replace |

**Write path:** After a successful `replace_vendor_rows` (same transaction preferred, or immediately after in the service), upsert fingerprint + source + `imported_at` for that vendor name. Multiplier/phone must remain untouched unless the import path already sets them.

**Read path:** Drop / Viztech / CLI: hash the inbound normalized rows once → `SELECT last_import_fingerprint FROM vendors WHERE name=?` → equal ⇒ skip wipe/reload; unequal or NULL ⇒ `replace_vendor` as today, then store new fingerprint.

**Ownership:** `PriceBookService` (+ repository), not Streamlit widgets and not Viztech-only JSON (ADR-0004). Lives in `master_pricebook.db` on local / Fly volume — never git (ADR-0005).

**Fingerprint content (guidance for implement, not this ticket):** Hash canonical sorted tuples of sellable identity + wholesale price (`IDENTITY_FIELDS` + `base_price`, null-normalized like `identity_key`). Exclude `multiplier` / `adjusted_price` (mult is Vendors/Drop control — out of scope per map). Exclude raw file bytes so Excel/PDF packaging noise does not force reloads.

---

### Tradeoffs

#### A. `vendors` new columns ✅ recommended

- **Pros:** Matches “one builder = one vendor”; natural join with Vendors tab / `list_vendor_settings`; shared by Drop + Viztech + Fly; tiny schema migration already patterned; O(1) compare; no second full scan of pricebook rows.
- **Cons:** Mixes “settings” (mult, phone) with “import cache”; only stores _last_ success (no history). Acceptable for v1 skip-unchanged.
- **FAF fit:** SQLite on Fly volume scales fine for ~180 vendor rows; thin UI unchanged.

#### B. New `vendor_import_meta` table

- **Pros:** Cleaner separation; easy to add history later (`imported_at` versions).
- **Cons:** Extra table + join for a 1:1 with `vendors`; more code for no v1 win. Prefer only if grilling demands import history / audit.

#### C. `integrations.meta_json`

- **Pros:** No ALTER on `vendors`; flexible blob.
- **Cons:** Wrong semantic (OrderTrac health); hard to query; risk of clobbering unrelated keys; fights ADR-0004 clarity. Reject for catalog fingerprints.

#### D. Viztech state file / sidecar JSON

- **Pros:** Zero DB migration; easy for Mac LaunchAgent.
- **Cons:** Not available to Fly Drop; per-machine drift; bypasses service layer; still need a second store for manual Drop. Reject as source of truth.

#### E. Hash current catalog from `pricebook` every time

- **Pros:** Always consistent with rows; no stale fingerprint; no new columns.
- **Cons:** Every Drop/Viztech builder still scans that vendor’s rows (and you hash inbound too — the “twice” cost the ticket calls out). Keep as **backfill** when fingerprint is NULL, or when `fingerprint_version` mismatches — not as the hot path.

---

### Implications for map #20

1. Equality grill can assume **stored fingerprint on `vendors`** as the fast path; full row scan only for NULL/version mismatch.
2. Parser/standardize changes → bump `fingerprint_version` (or clear fingerprints) so false “unchanged” cannot stick.
3. `replace_vendor` remains the update mechanism when fingerprints differ (ADR-0001); fingerprint write is part of successful replace, not a separate policy.
4. Multiplier changes alone must not invalidate catalog fingerprint (map: mult out of scope for equality).

### Out of scope here

Implementing columns, hash algorithm, Drop copy, or Viztech skip wiring — research only.
