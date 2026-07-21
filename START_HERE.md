# Fresh start — FAF Pricelist 2.0

**This is the only active pricelist project for new work.**

| | |
|--|--|
| Folder | `~/FAF-pricelist-2.0` |
| GitHub | https://github.com/Koffeekinggamer/faf-pricelist-2.0 |
| Port | **8510** (leave v1 alone on 8501) |

## Not this project

| Path | Status |
|------|--------|
| `~/FAF-pricebook` | **Legacy v1** — reference only, do not build 2.0 features there |

## What to build (phase 1)

1. **Drop Excel** (`.xls` / `.xlsx` / `.xlsm`)
2. Show a **formatted PDF on screen** for the team (not a row table)
3. **Builder** name controls the book
4. **Admin**: backup DB + multiplier per builder
5. Login: **Foothills** / **Amish**

Details: [docs/HANDOFF.md](docs/HANDOFF.md) · [docs/PRODUCT.md](docs/PRODUCT.md)

## Run scaffold

```bash
cd ~/FAF-pricelist-2.0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8510
```

Open http://127.0.0.1:8510
