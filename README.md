# FAF Price Book

**Foothills Amish Furniture** — floor price book (Streamlit + SQLite).

**Current focus: catalog accuracy.** OrderTrac quoting UI is hidden.

## Live

| Access | URL |
|--------|-----|
| Local | http://localhost:8501 |
| Fly.io | https://faf-pricebook.fly.dev |
| GitHub | https://github.com/Koffeekinggamer/faf-pricelist-2.0 |
| Login | **Foothills** / **Amish** |

## Tabs (accuracy mode)

- **Search** — verify retail prices (builder / wood / finish)
- **Drop files** — import builder Excel/PDF (replace that builder’s catalog)
- **Vendors** — per-builder multipliers + phone
- **Admin** — backup, Viztech sync, data quality

OrderTrac quote / connection UI stays in the codebase behind flags (`SHOW_ORDERTRAC_* = False` in `pricebook_app.py`).

## Run (local)

```bash
./run.sh
# http://127.0.0.1:8501
```

## App entrypoints

| File | Role |
|------|------|
| `pricebook_app.py` | **Main** — accuracy mode (Search · Drop · Vendors · Admin) |
| `pricebook_app_slim.py` | Slim Drop→PDF + Admin only |
| `pricebook_app_legacy.py` | Archive copy |

## Docs

- **[HANDOFF.md](HANDOFF.md)** — agent / operator handoff
- **[DEPLOY.md](DEPLOY.md)** — Fly / Streamlit Cloud
- **[FLOOR_CHEAT_SHEET.md](FLOOR_CHEAT_SHEET.md)** — floor staff
- **[ORDERTRAC_CONNECTION.md](ORDERTRAC_CONNECTION.md)** — OrderTrac setup (hidden in UI for now)

## Safety

Never commit `master_pricebook.db`, `.env`, or `.streamlit/secrets.toml`.
