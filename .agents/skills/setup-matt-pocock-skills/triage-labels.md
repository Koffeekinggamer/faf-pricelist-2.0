# Triage Labels — FAF Price Book

Canonical seed (ADR-0006). Mirror: `docs/agents/triage-labels.md` via `scripts/sync_agent_docs.sh`.

Canonical triage roles for Matt Pocock `/triage`, mapped to GitHub label strings on `Koffeekinggamer/faf-pricelist-2.0`.

| Label in mattpocock/skills | Label in our tracker | Meaning |
| -------------------------- | -------------------- | ------- |
| `needs-triage`             | `needs-triage`       | Judson / maintainer needs to evaluate |
| `needs-info`               | `needs-info`         | Waiting on builder file, screenshot, or floor repro |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified for an AFK Cursor/cloud agent |
| `ready-for-human`          | `ready-for-human`    | Needs Judson (credentials, Viztech login, live DB, design call) |
| `wontfix`                  | `wontfix`            | Will not be actioned |

## FAF triage hints

Mark **ready-for-human** (not agent) when the work needs:

- Viztech / Fly / Streamlit secrets or live `master_pricebook.db` access
- A physical builder workbook only Judson has
- Re-enabling OrderTrac UI (explicit product call — ADR-0003)
- Changing default multipliers or Genuine Oak 1.7 (pricing policy)

Mark **ready-for-agent** when the brief includes:

- Target tab/surface (Search / Drop / Vendors / Admin / backend)
- Builder name if catalog-scoped
- Expected row/behavior checks without requiring the private DB in git
- Explicit “do not commit `*.db` / secrets”

Create missing labels with `gh label create` on first use if they are absent from the repo.
