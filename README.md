# FAF Price Book

**Foothills Amish Furniture** — floor price book (Streamlit + SQLite).

This repository is the **main** Price Book app (full UI matching production).

## Live

| Access | URL |
|--------|-----|
| Local | http://localhost:8501 |
| Fly.io | https://faf-pricebook.fly.dev |
| GitHub | https://github.com/Koffeekinggamer/faf-pricelist-2.0 |
| Login | **Foothills** / **Amish** (or OrderTrac-synced staff) |

## Tabs

- **Search** — retail prices, builder / wood / finish filters, pinned builders
- **OrderTrac quote** — stage FAF lines → push Quote (not a sale)
- **Drop files** — import builder Excel/PDF (replace that builder’s catalog)
- **Vendors** — per-builder multipliers + phone
- **Admin** — backup, Viztech sync, OrderTrac connection, data quality

## Run (local)

```bash
cd ~/FAF-pricelist-2.0   # or this checkout
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh
# http://127.0.0.1:8501
```

## App entrypoints

| File | Role |
|------|------|
| `pricebook_app.py` | **Main** — full UI (Search · OrderTrac · Drop · Vendors · Admin) |
| `pricebook_app_slim.py` | Slim Drop→PDF + Admin only (Phase 1 experiment) |
| `pricebook_app_legacy.py` | Archive copy of the pre-restore accuracy-mode UI |

Slim Phase‑1 greenfield history: branch `backup/phase1-slim-2026-07-26`.

## Docs

- **[HANDOFF.md](HANDOFF.md)** — agent / operator handoff
- **[DEPLOY.md](DEPLOY.md)** — Fly / Streamlit Cloud
- **[FLOOR_CHEAT_SHEET.md](FLOOR_CHEAT_SHEET.md)** — floor staff
- **[ORDERTRAC_CONNECTION.md](ORDERTRAC_CONNECTION.md)** — OrderTrac setup

## Safety

Never commit `master_pricebook.db`, `.env`, or `.streamlit/secrets.toml`.
