# Wayfinder issues #12–#31 — superseded

> **Do not pick up GitHub issues #12–#31 as a backlog.** Those tickets were the thin-catalog and smart-reimport wayfinder maps. The decisions are already **accepted** ADRs. An agent that “starts issue 20” will re-litigate shipped work and may choose price-only upsert.
>
> Read instead:
>
> - [`AGENTS.md`](../../AGENTS.md)
> - [`docs/PRICEBOOK_AGENT_AUDIT.md`](../PRICEBOOK_AGENT_AUDIT.md)
> - [`docs/CURSOR_AGENT_KICKOFF.md`](../CURSOR_AGENT_KICKOFF.md)
> - [`docs/adr/0007-thin-catalogs-triage.md`](../adr/0007-thin-catalogs-triage.md) — issues #12–#19
> - [`docs/adr/0010-smart-reimport-skip-unchanged.md`](../adr/0010-smart-reimport-skip-unchanged.md) — issues #20–#31

GitHub label/close of #12–#31 is Judson-gated (`gh` write is not available to agents). This index is the in-repo tombstone.

The fingerprint research note ([`smart-reimport-fingerprint.md`](./smart-reimport-fingerprint.md)) is archived history for ADR-0010. Do not implement from it.

## Thin catalogs — ADR-0007

| # | Title (as filed) | Why not a backlog |
| - | ---------------- | ----------------- |
| 12 | `[wayfinder:task] Provide live master DB for thin-catalog scan` | Live DB is Judson-gated; thin scan is `ready_catalog.sh` / CLI. Do not commit the DB. |
| 13 | `[wayfinder:grilling] Confirm thin-list test seams` | Accepted: Admin + CLI, no floor badge. |
| 14 | `[wayfinder:research] Scan builders under 150 rows` | Threshold locked at &lt;150. |
| 15 | `[wayfinder:grilling] Keep/replace/ignore: Amish Aspen` | Judson-only keep/replace/ignore. Do not re-grill from the issue. |
| 16 | `[wayfinder:grilling] Keep/replace/ignore: Hillside Chair` | Same. |
| 17 | `[wayfinder:grilling] Keep/replace/ignore: Maple Lane` | Same. |
| 18 | `[wayfinder:grilling] Keep/replace/ignore for other scanned thins` | Same. |
| 19 | `[wayfinder:grilling] Where to record a keep decision` | Process is triage → grill Judson; `IGNORE_BUILDERS` only when he says ignore. |

## Smart re-import — ADR-0010

| # | Title (as filed) | Why not a backlog |
| - | ---------------- | ----------------- |
| 20 | `[wayfinder:map] Smart re-import: skip unchanged builder books` | Map locked; implement from the ADR, not the issue. |
| 21 | `[wayfinder:grilling] What counts as unchanged for a builder book?` | Wholesale fingerprint after standardize. |
| 22 | `[wayfinder:grilling] Which import surfaces get compare-and-skip?` | All `PriceBookService.add_rows` paths. |
| 23 | `[wayfinder:research] Persist last-import fingerprint per builder` | `vendors` columns. Research note tombstoned. |
| 24 | `[wayfinder:grilling] On change: full replace_vendor or price-only upsert?` | **`replace_vendor`**. Price-only upsert is forbidden (orphans). |
| 25 | `[wayfinder:grilling] Same prices, new filename — skip or reload?` | Skip; filename alone is not a price change. |
| 26 | `[wayfinder:grilling] Drop UI when Load would skip` | Per-file status + toast. |
| 27 | `[wayfinder:grilling] On change: full replace_vendor or price-only upsert?` | Duplicate of #24. Still **`replace_vendor`**. |
| 28 | `[wayfinder:grilling] Same prices, new filename — skip or reload?` | Duplicate of #25. |
| 29 | `[wayfinder:grilling] Drop UI when Load would skip` | Duplicate of #26. |
| 30 | `[wayfinder:map-index] Smart re-import — child tickets for #20` | Index only. |
| 31 | `[wayfinder:decisions] Smart re-import — frontier locked (recommended)` | Decisions live in ADR-0010. |

New wayfinder maps (after this range) are fine. These twenty issues are not.
