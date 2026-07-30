# Agent instructions — FAF Price Book (main)

1. Read in order: **AGENTS.md** (this file) → **CONTEXT.md** → **HANDOFF.md** → **STANDARDS.md**. Consult **`docs/adr/`** as needed.
2. **This repo is the main FAF Price Book.** Mac/project path: **`/FAF-pricelist-2.0`**. Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Drop→PDF-only experiment: branch `backup/phase1-slim-2026-07-26` / `pricebook_app_slim.py`.
7. Thin UI; put logic in `backend.PriceBookService`. One builder = one vendor; retail = wholesale × mult (2.7 default, Genuine Oak 1.7).

## Fast ops (Mac)

```bash
cd /FAF-pricelist-2.0
./scripts/ready_catalog.sh          # pull Fly DB → stats → thin catalogs
./scripts/ready_catalog.sh --no-pull   # local DB only
.venv/bin/python -m backend.cli thin-catalogs
```

Thin = rows &lt; 150 (ADR-0007). Then triage → grill Judson keep/replace/ignore. Never commit the DB.

## Agent skills

Skills live under `.agents/skills/` ([mattpocock/skills](https://github.com/mattpocock/skills) + [juliusbrussee/caveman](https://github.com/juliusbrussee/caveman)). Configured for **this** price book (ADR-0006). Update with `npx skills update`, then re-apply FAF overlays on setup-skill seeds and run `scripts/sync_agent_docs.sh`.

Recommended FAF flows (full pack stays installed; these are reach-for-first):

| Goal                                                        | Skill                         |
| ----------------------------------------------------------- | ----------------------------- |
| Sharpen a catalog/import/Search change + grow glossary/ADRs | `/grill-with-docs`            |
| Unsure which skill fits                                     | `/ask-matt`                   |
| Spec → GitHub Issues                                        | `/to-spec` then `/to-tickets` |
| Implement a ticket test-first                               | `/implement` or `/tdd`        |
| Hard bug / bad import / wrong retail                        | `/diagnosing-bugs`            |
| Review a PR against standards + spec                        | `/code-review`                |
| Multi-session roadmap                                       | `/wayfinder`                  |
| Terse replies (less fluff)                                  | `/caveman`                    |

### Pre-commit hooks

Husky: **lint-staged** (Ruff via `scripts/run_ruff.sh` — `.venv/bin/ruff` then PATH; Prettier on other text) then **`npm test`** → pytest. No JS typecheck. `package.json` is hooks-only. After clone: `npm install` + `.venv` with `ruff` / `pytest`.

### Issue tracker

GitHub Issues on `Koffeekinggamer/faf-pricelist-2.0` via `gh`. See `docs/agents/issue-tracker.md` (mirrored from setup-skill seed).

### Triage labels

`needs-triage` · `needs-info` · `ready-for-agent` · `ready-for-human` · `wontfix`. Secrets / live DB / Viztech → `ready-for-human`. See `docs/agents/triage-labels.md`.

### Domain docs

Reading order above. Detail in `docs/agents/domain.md` (mirror). **Canonical seeds:** `.agents/skills/setup-matt-pocock-skills/` — sync with `scripts/sync_agent_docs.sh` (ADR-0006).
