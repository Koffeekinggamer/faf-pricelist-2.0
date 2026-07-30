# Agent instructions — FAF Price Book (main)

1. Read **HANDOFF.md** first, then **CONTEXT.md** (domain language) and **`docs/adr/`** (locked decisions).
2. **This repo is the main FAF Price Book.** Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Drop→PDF-only experiment: branch `backup/phase1-slim-2026-07-26` / `pricebook_app_slim.py`.
7. Thin UI; put logic in `backend.PriceBookService`. One builder = one vendor; retail = wholesale × mult (2.7 default, Genuine Oak 1.7).

## Agent skills

Matt Pocock skills are installed under `.agents/skills/` from [mattpocock/skills](https://github.com/mattpocock/skills), configured for **this** price book (not a generic TypeScript app). Update with `npx skills update`.

Recommended FAF flows:

| Goal                                                        | Skill                         |
| ----------------------------------------------------------- | ----------------------------- |
| Sharpen a catalog/import/Search change + grow glossary/ADRs | `/grill-with-docs`            |
| Unsure which skill fits                                     | `/ask-matt`                   |
| Spec → GitHub Issues                                        | `/to-spec` then `/to-tickets` |
| Implement a ticket test-first                               | `/implement` or `/tdd`        |
| Hard bug / bad import / wrong retail                        | `/diagnosing-bugs`            |
| Review a PR against standards + spec                        | `/code-review`                |
| Multi-session roadmap                                       | `/wayfinder`                  |

### Pre-commit hooks

Husky runs on every commit: **lint-staged** (Ruff on `*.py`, Prettier on other text) then **`npm test`** → pytest. App remains Python — `package.json` is hooks-only. After clone: `npm install` (installs Husky) and ensure `.venv` has `ruff` / `pytest`.

### Issue tracker

GitHub Issues on `Koffeekinggamer/faf-pricelist-2.0` via `gh`. Use FAF vocabulary in titles/bodies. See `docs/agents/issue-tracker.md`.

### Triage labels

`needs-triage` · `needs-info` · `ready-for-agent` · `ready-for-human` · `wontfix`. Secrets, live DB, and Viztech login → `ready-for-human`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context FAF glossary: root **`CONTEXT.md`**, ops in **`HANDOFF.md`** / **`STANDARDS.md`**, locked decisions in **`docs/adr/`**. Reading order in `docs/agents/domain.md`.
