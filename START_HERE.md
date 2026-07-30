# FAF Price Book — start here

**Main app · content accuracy mode** (OrderTrac UI hidden).

|       |                                       |
| ----- | ------------------------------------- |
| App   | `pricebook_app.py`                    |
| Port  | **8501** (`./run.sh`)                 |
| Live  | https://faf-pricebook.fly.dev         |
| Login | **Foothills** / **Amish**             |
| Tabs  | Search · Drop files · Vendors · Admin |

```bash
cd ~/FAF-pricelist-2.0
git pull origin main
./scripts/pull_db_from_fly.sh   # live catalog (gitignored)
./run.sh
```

Thin-catalog scan (after DB pull): `./scripts/ready_catalog.sh --no-pull`

Or: GitHub Actions → **Pull Fly DB** → download artifact `fly-master-pricebook` → save as `master_pricebook.db`.

Never commit `*.db` / secrets. Details: [HANDOFF.md](HANDOFF.md).
