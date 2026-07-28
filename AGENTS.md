# Agent instructions — FAF Price Book (main)

1. Read **HANDOFF.md** first.
2. **This repo is the main FAF Price Book.** Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Drop→PDF-only experiment: branch `backup/phase1-slim-2026-07-26` / `pricebook_app_slim.py`.

## Cursor Cloud specific instructions

- Pure-Python Streamlit + SQLite app. Deps live in a `.venv` (the startup update script creates/refreshes it). Run everything with `.venv/bin/...`.
- Start the app: `PORT=8501 ./run.sh` (wraps `streamlit run pricebook_app.py`). Health check: `curl http://localhost:8501/_stcore/health` → `ok`. Log in with `Foothills` / `Amish`.
- Lint/tests: `.venv/bin/python -m pytest -q` (config in `pytest.ini`, tests in `tests/`). There is no separate linter configured.
- Backend CLI (useful without the UI): `.venv/bin/python -m backend.cli stats|search|import-xlsx|batch` (see `backend/cli.py`).
- `master_pricebook.db` is gitignored and NOT in the repo, so a fresh clone starts with an empty catalog (`stats` → 0 rows). The schema is auto-created on first service init / app start; seed data by importing a builder Excel/PDF via the "Drop files" tab or `backend.cli import-xlsx`.
- The `python3-venv` system package is required to build `.venv` and is baked into the environment snapshot; it is intentionally not in the update script.
- Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
