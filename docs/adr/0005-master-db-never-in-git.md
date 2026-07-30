# Master DB never in git

`master_pricebook.db` (and other `*.db`), `.env`, and `.streamlit/secrets.toml` stay local / Fly volume only. Agents must not commit them. Live catalog sync uses `scripts/pull_db_from_fly.sh` / `scripts/push_db_to_fly.sh` or documented GitHub Actions artifacts — not the git tree.

**Status:** accepted
