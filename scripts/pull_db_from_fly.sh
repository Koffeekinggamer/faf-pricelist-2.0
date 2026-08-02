#!/usr/bin/env bash
# Pull the live master_pricebook.db from the Fly volume (/data) → local.
#
# Fly is the single source of truth for catalog DATA. The DB is never committed
# to git (see .gitignore: *.db) — the repo is public and the file is ~168MB of
# private pricing. Any machine (either Mac, or a cloud agent) gets the exact
# live catalog by running this script.
#
# Requires: flyctl authenticated. Either:
#   - run `fly auth login` once on the machine, OR
#   - set FLY_API_TOKEN to a real Fly token — create one at
#     https://fly.io/user/personal_access_tokens (or: fly tokens create deploy -a "$FLY_APP")
#
# Usage:  ./scripts/pull_db_from_fly.sh
set -euo pipefail

export PATH="${HOME}/.fly/bin:${PATH}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${FLY_APP:-faf-pricebook}"
LOCAL_DB="${FAF_LOCAL_DB:-$ROOT/master_pricebook.db}"
REMOTE_DB="/data/master_pricebook.db"

FLY="$(command -v flyctl || command -v fly || echo "${HOME}/.fly/bin/flyctl")"
if [[ ! -x "$FLY" ]] && ! command -v "$FLY" >/dev/null 2>&1; then
  echo "flyctl not found. Install it with: curl -L https://fly.io/install.sh | sh" >&2
  exit 1
fi

# Confirm we can authenticate before doing anything destructive locally.
if ! "$FLY" status -a "$APP" >/dev/null 2>&1; then
  echo "Cannot reach Fly app '$APP'. Run 'fly auth login' or set FLY_API_TOKEN." >&2
  exit 1
fi

# fly ssh sftp get refuses to overwrite, so move any existing local DB aside.
if [[ -f "$LOCAL_DB" ]]; then
  ts="$(date +%Y%m%d-%H%M%S)"
  bak="${LOCAL_DB%.db}.prev-${ts}.db"
  echo "Existing local DB → backup: $bak"
  mv "$LOCAL_DB" "$bak"
fi

echo "Pulling $APP:$REMOTE_DB → $LOCAL_DB"
"$FLY" ssh sftp get "$REMOTE_DB" "$LOCAL_DB" -a "$APP"

echo "Verifying local copy..."
python3 - "$LOCAL_DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db)
rows = con.execute("select count(*) from pricebook").fetchone()[0]
vendors = con.execute("select count(distinct vendor) from pricebook").fetchone()[0]
print(f"  rows={rows:,}  vendors={vendors}")
PY

echo ""
echo "Done. Now run: ./run.sh   (http://127.0.0.1:8501 · login Foothills / Amish)"
