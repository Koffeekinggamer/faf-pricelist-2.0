# Agent instructions — FAF Price Book (main)

1. Read **HANDOFF.md** first.
2. **This repo is the main FAF Price Book.** Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Drop→PDF-only experiment: branch `backup/phase1-slim-2026-07-26` / `pricebook_app_slim.py`.

## Agent skills

Matt Pocock engineering/productivity skills live under `.agents/skills/` (from [mattpocock/skills](https://github.com/mattpocock/skills)). Update with `npx skills update`.

### Issue tracker

GitHub Issues on `koffeekinggamer/faf-pricelist-2.0` via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/` (created lazily by `/grill-with-docs` / `/domain-modeling`). See `docs/agents/domain.md`.
