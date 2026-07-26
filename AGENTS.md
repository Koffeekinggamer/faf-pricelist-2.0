# Agent instructions — FAF Price Book (main)

1. Read **HANDOFF.md** first.
2. **This repo is the main FAF Price Book** (full floor app: Search · OrderTrac quote · Drop files · Vendors · Admin).
3. Default entry: `pricebook_app.py` (matches the live Fly model).
4. Never commit `*.db`, `.env`, or `.streamlit/secrets.toml`.
5. Local port **8501** (Fly: https://faf-pricebook.fly.dev).
6. Slim Phase‑1 Drop→PDF-only experiment is preserved on branch `backup/phase1-slim-2026-07-26` and as `pricebook_app_slim.py`.
