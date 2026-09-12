# FAF Price Book

**Foothills Amish Furniture** — floor price book (Streamlit + SQLite).

**Current focus: catalog accuracy.** OrderTrac quoting UI is hidden.

## Live

| Access | URL                                                                                         |
| ------ | ------------------------------------------------------------------------------------------- |
| Local  | http://localhost:8501                                                                       |
| Fly.io | https://faf-pricebook.fly.dev                                                               |
| GitHub | https://github.com/Koffeekinggamer/faf-pricelist-2.0                                        |
| Login  | Email + password · local first admin `foothills@faf.local` / **Amish** (from floor secrets) |

Deploy: push to `main` (needs repo secret `FLY_API_TOKEN`) or from Mac: `fly deploy -a faf-pricebook`. See [DEPLOY.md](DEPLOY.md).

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

| File               | Role                                                              |
| ------------------ | ----------------------------------------------------------------- |
| `pricebook_app.py` | **Main (only)** — accuracy mode (Search · Drop · Vendors · Admin) |

## Docs

- **[HANDOFF.md](HANDOFF.md)** — agent / operator handoff
- **[DEPLOY.md](DEPLOY.md)** — Fly (canonical). Streamlit Cloud / `pricebook-system` sections are historical.
- **[FLOOR_CHEAT_SHEET.md](FLOOR_CHEAT_SHEET.md)** — floor staff
- **[ORDERTRAC_CONNECTION.md](ORDERTRAC_CONNECTION.md)** — OrderTrac setup (hidden in UI for now)

## Login, quotes, tax, and activity

- **First admin:** empty users table in `pricebook_app.db` (sibling of the catalog, or `PRICEBOOK_APP_DB`) creates one admin from `ADMIN_EMAIL` + `ADMIN_PASSWORD`. Local/dev also reads `[auth]` in secrets.toml (Foothills → `foothills@faf.local`). If those are missing and this is not Fly, the documented default is `foothills@faf.local` / `Amish`.
- **Login is email + password only.** No username field. Case-insensitive email lookup. New passwords must be at least 10 characters (bootstrap may keep the existing floor password).
- **Roles:** admin (users, activity, all quotes) · manager (team quotes, no user admin) · sales (own quotes, cart, tax) · viewer (catalog only).
- **Activity → Problems only:** Admin → Activity, tick Problems only to see `failure` / `denied` / `error`. Export CSV of the current filter.
- **GA county tax:** `backend/county_sales_tax.py` lists all 159 counties. Counties without a specified combined rate are **8%** with notes `VERIFY on GA DOR general rate chart before production`. Check those on the GA DOR chart before production use.
- Catalog stays `master_pricebook.db`. Users / quotes / activity never overwrite catalog rows.

Creating a user emails them a link to https://faf-pricebook.fly.dev (or `APP_PUBLIC_URL`). Invite-only creates include `?invite=` so they set a password. Temporary passwords are never put in the email or the activity log. Requires `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` (or `[smtp]` in secrets). Account create still succeeds if mail is not configured.

See `.env.example` for `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `PRICEBOOK_APP_DB`, and SMTP.

## Safety

Never commit `master_pricebook.db`, `.env`, or `.streamlit/secrets.toml`.
