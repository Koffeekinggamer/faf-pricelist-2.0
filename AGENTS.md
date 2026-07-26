# Agent instructions — FAF Price Book (main)

1. Read **HANDOFF.md** first.
2. **This repo is the main FAF Price Book.** Current focus: **catalog accuracy** (Search · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py`. OrderTrac UI flags are **off** — do not re-enable unless Judson asks.
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Drop→PDF-only experiment: branch `backup/phase1-slim-2026-07-26` / `pricebook_app_slim.py`.
