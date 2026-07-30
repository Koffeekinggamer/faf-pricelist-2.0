# Domain Docs — FAF Price Book

Canonical seed: `.agents/skills/setup-matt-pocock-skills/domain.md` (ADR-0006). Synced to `docs/agents/domain.md` via `scripts/sync_agent_docs.sh`.

How Matt Pocock engineering skills should consume this repo’s domain documentation.

## Before exploring, read these (in order)

1. **`AGENTS.md`** — hard product rules for agents
2. **`CONTEXT.md`** — FAF ubiquitous language (builder, retail, replace vendor, …)
3. **`HANDOFF.md`** — current ops state, known issues, do/don’t
4. **`STANDARDS.md`** — master row shape (vendor / collection / species / finish / prices)

Then **`docs/adr/`** as needed for locked decisions that touch the change. Read **`FLOOR_CHEAT_SHEET.md`** when the change affects floor Search behavior.

If a file is missing mid-task, proceed — but **do not invent synonyms** that contradict `CONTEXT.md` / `STANDARDS.md`. Prefer `/domain-modeling` or `/grill-with-docs` to add terms or ADRs.

## File structure

Single-context repo:

```
/
├── CONTEXT.md                 ← FAF glossary (required for skill vocabulary)
├── HANDOFF.md / STANDARDS.md  ← ops + row canon (FAF-specific; always respect)
├── docs/adr/                  ← locked product/architecture decisions
├── docs/agents/               ← mirrored skill config (from this seed tree)
├── pricebook_app.py           ← thin UI
└── backend/                   ← PriceBookService + import/search/standardize
```

## Use the glossary's vocabulary

When naming concepts in issues, PR titles, specs, tickets, or code:

- Say **builder** / **vendor** (one identity), not “manufacturer entry”
- Say **retail** / **adjusted price** for customer price; **wholesale** / **base price** for builder list
- Say **replace vendor** for re-import, not “merge catalog”
- Say **accuracy mode** for the live UI; do not treat OrderTrac as current floor UX
- Prefer terms from `CONTEXT.md`; if missing, note the gap for `/domain-modeling`

## Flag ADR conflicts

If a proposal contradicts an ADR under `docs/adr/`, surface it explicitly:

> _Contradicts ADR-0001 (one builder = one vendor) — but worth reopening because…_

Do not silently re-enable OrderTrac UI (ADR-0003), commit the master DB (ADR-0005), or put business logic only in Streamlit (ADR-0004).
