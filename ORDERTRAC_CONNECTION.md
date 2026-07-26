# OrderTrac ↔ FAF Price Book

Connect the company OrderTrac account to FAF so staff can log into the price
book with accounts derived from OrderTrac sales users.

## What this does

| Piece | Purpose |
|-------|---------|
| `[ordertrac]` in secrets | Company login (email/password) for automation |
| Playwright session | Survives reCAPTCHA (`~/Documents/ordertrac-session/`) |
| `app_users` table | Multi-user FAF logins (admin / sales / floor) |
| Sync from OrderTrac | Reads OT **UserGUID** list → creates FAF users |

OrderTrac remains the sales system. FAF remains the price engine. The bridge
stores **who** can use FAF and links them to OT display names / GUIDs for future
quote push.

## One-time setup

### 1. Secrets (gitignored)

`.streamlit/secrets.toml`:

```toml
[auth]
username = "Foothills"
password = "Amish"

[ordertrac]
username = "you@company.com"
password = "…"
base_url = "https://app.ordertracinventory.com"
```

Copy from `secrets.toml.example` if needed.

### 2. OrderTrac browser session

```bash
cd ~/FAF-pricebook
source .venv/bin/activate
python scripts/ordertrac_login.py
```

Complete captcha if prompted. Session is saved to:

`~/Documents/ordertrac-session/storage_state.json`

### 3. Sync users

**CLI:**

```bash
python scripts/ordertrac_sync_users.py --check   # list OT users only
python scripts/ordertrac_sync_users.py           # create/update FAF accounts
```

**UI:** Sign in as **admin** → **Admin** tab → **Sync users from OrderTrac**.

New accounts get a **temporary password** (shown once). On first login they must
set a new password.

### 4. How usernames are made

From OrderTrac display name `Miller, Judson` → FAF username `judson.miller`.

Linked fields on each user:

- `ordertrac_user_guid` — OT UserGUID when available  
- `ordertrac_display_name` — e.g. `Miller, Judson`  
- `source` = `ordertrac`

## Roles

| Role | Access |
|------|--------|
| `admin` | Full app + OrderTrac connection + user management |
| `sales` | Floor price book (default for OT-synced users) |
| `floor` | Same as sales for now (reserved for tighter limits later) |

Seed admin (if no users yet) comes from `[auth]` or defaults **Foothills / Amish**.

## Check connection

Admin → **Check OrderTrac session**, or:

```bash
python scripts/ordertrac_session.py check
python scripts/ordertrac_sync_users.py --check
```

## Security notes

- Do **not** commit `secrets.toml` or `storage_state.json`.
- FAF passwords are **not** the same as OrderTrac passwords (OT does not expose them).
- Synced users get random temp passwords; admins can reset under **Create / reset a user**.
- Only **admin** role can run sync / manage users in the UI.

## Push FAF prices → OrderTrac QUOTE

### Admin UI
**Admin → Push FAF lines → OrderTrac QUOTE**
- Enter FAF pricebook IDs + qtys + wood/stain
- Pick OrderTrac sales user (from synced staff)
- Creates a **Quote** (not a sale) with custom lines + Manufacture Vendor

### CLI
```bash
# By FAF row ids
python scripts/ordertrac_push_quote.py --faf-ids 479060,482875 --qtys 1,4

# By internal FAF quote id
python scripts/ordertrac_push_quote.py --quote-id 1
```

### Vendor map
`config/ordertrac_vendor_map.json` — FAF vendor name → OrderTrac Manufacture Vendor label.

### Login handoff
After user sync / password re-issue:
`~/Documents/ordertrac-session/faf-login-handoff.txt` (gitignored machine folder)

## Architecture

```
OrderTrac ──session──▶ FAF (sync users, push quotes)
FAF SQLite ──prices──▶ OrderTrac custom ORDER lines (QUOTE only)
app_users  ◀── OT staff list (roles mapped)
```
