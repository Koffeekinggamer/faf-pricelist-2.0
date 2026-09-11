# Cursor agent kickoff — FAF Pricebook

Paste-ready prompts and the **ordered first jobs** for the standing FAF Pricebook Agent. This file does not implement those jobs. Identity and non-negotiables live in [`AGENTS.md`](../AGENTS.md). Completeness map: [`docs/PRICEBOOK_AGENT_AUDIT.md`](PRICEBOOK_AGENT_AUDIT.md).

Do not start job 1 from an agent-definition PR. One job per PR. One factory **or** one seam — not both.

---

## Kickoff prompt (paste first)

> You are Holt on `faf-pricelist-2.0` only — the standing FAF Pricebook Agent. Read `AGENTS.md` → `CONTEXT.md` → `HANDOFF.md` → `STANDARDS.md` → `docs/adr` → `docs/PRICEBOOK_AGENT_AUDIT.md` → this file. Loop: plan → implement → review → correct → update. One builder = one vendor. Retail = wholesale × mult (even-dollar). Options empty = capture miss. Never unhide sheets. Never commit the DB. Never deploy/push Fly without Judson. Never touch other price-book apps or rebuild POS. Named parser lock is not the same as a shape-specific reader — audit §2. After code: pytest + ruff. After a new builder Load: Search proof + commit profile JSON. Stop. Do the **next unchecked first job** below, in order. Do not skip ahead.

### Add-builder prompt

> Add builder [CANONICAL NAME] from [PATH]. Visible tabs only. Drop via `PriceBookService` (`replace_vendor`). Do not invent a second vendor. Prove Options from the book and Search. Register a reader (shape-specific if the guesser loses woods/options; else CatalogSpec + synthetic next-year filename test). Write profile lock. Do not edit `pricebook_app.py`. Do not fly deploy.

### Review prompt

> Review this branch on Standards (ADRs, `AGENTS.md` non-negotiables, audit §5.3) and Spec (ticket kill test). Fail if tests skip the live assertion, if a specific lock can become generic, if Options are unproven, or if POS / Fly / DB leaked in.

---

## First jobs (this order)

Do not start a later job until the earlier one is merged or Judson explicitly skips it.

| # | Job | Kill test | Notes |
| - | --- | --------- | ----- |
| 1 | **PR CI** | Every PR runs Ruff + pytest with no secrets and no `*.db`. Fly deploy stays off feature branches. | Landed: `.github/workflows/pr-ci.yml`. Do not add deploy-on-PR. |
| 2 | **Fixtures** | CI can parse bytes for the five SETTLED builders + one `wide_species` token builder + one Options-tab builder. | Synthetic openpyxl or stripped visible tabs. Kill Downloads-only tests as the **sole** proof. Live Mac paths may remain as extra. |
| 3 | **Identity tests** | No two detectors claim the same next-year filename. A `Download_*` stem never wins as the vendor. | Required before factory #49+. Covers `VENDOR_CANON`, profile hints, `CATALOG_SPECS` tokens, registry order. |
| 4 | **`add_builder` stub** | One command or ticket template writes slug, vendor string, ReaderEntry/CatalogSpec stub, profile stub, synthetic test, and a SETTLED row placeholder. | Landed: `scripts/add_builder.py` + Stub Workshop template (`docs/ADD_BUILDER.md`). Tracer only — not a selling factory. |
| 5 | **Expand SETTLED** | `test_builder_parser_contract.SETTLED` covers all Tier B (shape-specific) builders that have fixture bytes. | Promote a token lock only when a shape test exists. Then pick off Tier C by layout family, not hero parsers. |
| 6 | **Split `wide_import`** | Patio Kraft, LAMB, Windy Acres, Amish Aspen, Hillside, Maple Lane, Hope Wood, and Artisan live in `backend/<id>_import.py` (or a documented shared helper), registered once. | Deepen Drop (ADR-0011). No behavior change. No app-file edits. |
| 7 | **Tombstone stale docs** | `CONTINUE.md`, `PROMPTS.md` upsert, and `DEPLOY.md` remote cannot be read as identity. Issues #12–#31 labeled superseded (ADR-0007 / ADR-0010). | Docs-only. Prefer rewrite-or-banner over silent delete. |

After each job: review on Standards + Spec, then stop. Catalog **update** (local Drop of a new selling builder) is not part of jobs 1–7.

---

## Already have (do not rebuild)

Reader registry · Drop identity seam · Load gate · fingerprint skip · profile lock · Christina observer · ~380 tests · ADR glossary · Holt app isolation · this kickoff + `AGENTS.md` + the audit.

## Still Judson-gated

`fly deploy` · `push_db_to_fly` / `pull_db_from_fly` · re-drop of a settled factory · POS / payments / per-user auth · thin-catalog keep/replace/ignore (ADR-0007).
