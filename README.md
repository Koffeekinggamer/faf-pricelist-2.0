# FAF Pricelist 2.0

**Foothills Amish Furniture** — next-generation floor pricelist app.

> Greenfield project. Not a fork of the legacy Streamlit app — start clean, reuse lessons from v1.

## Product goal (v2.0 phase 1)

| Tab | Purpose |
|-----|---------|
| **Drop files** | Drop builder Excel (`.xls` / `.xlsx`) → **show a formatted PDF on screen** for the team (not a raw row grid) |
| **Admin** | Backup the master DB after updates · set **multiplier per builder** |

Out of scope for phase 1 UI (keep in design notes / later):
- OrderTrac quote push
- Full catalog search / pins
- Viztech bulk sync UI

## Login (phase 1 defaults)

| | |
|--|--|
| Username | `Foothills` |
| Password | `Amish` |

## Related projects on this Mac

| Path | Role |
|------|------|
| `~/FAF-pricebook` | **v1** live app (legacy) — port 8501, Fly `faf-pricebook.fly.dev` |
| `~/FAF-pricebook/pricebook_app_legacy.py` | Full v1 UI archive |
| `~/FAF-pricelist-2.0` | **This repo** — clean rebuild |

## Run (local)

```bash
cd ~/FAF-pricelist-2.0
./run.sh
# http://127.0.0.1:8510
```

Login: **Foothills** / **Amish**

## Docs

- **[docs/HANDOFF.md](docs/HANDOFF.md)** — full agent handoff (read first)
- **[docs/PRODUCT.md](docs/PRODUCT.md)** — product decisions and non-goals

## GitHub

https://github.com/Koffeekinggamer/faf-pricelist-2.0
