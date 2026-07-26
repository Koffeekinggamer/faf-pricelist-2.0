#!/bin/zsh
# Push local master_pricebook.db → Fly volume (/data).
# Requires: flyctl logged in, app faf-pricebook running with volume mounted.
set -euo pipefail

export PATH="${HOME}/.fly/bin:${PATH}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${FLY_APP:-faf-pricebook}"
LOCAL_DB="${FAF_LOCAL_DB:-$ROOT/master_pricebook.db}"
REMOTE_DB="/data/master_pricebook.db"

if [[ ! -f "$LOCAL_DB" ]]; then
  echo "No local DB at $LOCAL_DB"
  exit 1
fi

SIZE=$(du -h "$LOCAL_DB" | awk '{print $1}')
echo "Pushing $LOCAL_DB ($SIZE) → $APP:$REMOTE_DB"

# Ensure app has a running machine (volume must be attached)
fly status -a "$APP" >/dev/null

# SFTP put refuses overwrite — remove remote first
fly ssh console -a "$APP" -C "rm -f $REMOTE_DB ${REMOTE_DB}-wal ${REMOTE_DB}-shm" || true

# Upload via SFTP (works with volume mounts)
fly ssh sftp put "$LOCAL_DB" "$REMOTE_DB" -a "$APP"

echo "Verifying on machine..."
fly ssh console -a "$APP" -C "ls -lh $REMOTE_DB"
fly ssh console -a "$APP" -C "python3 -c 'import sqlite3;c=sqlite3.connect(\"$REMOTE_DB\");print(\"rows\",c.execute(\"select count(*) from pricebook\").fetchone()[0]);print(\"vendors\",c.execute(\"select count(distinct vendor) from pricebook\").fetchone()[0])'"

echo "Restarting app so Streamlit reloads the DB..."
fly apps restart "$APP" || true

echo ""
echo "Done. Public: https://${APP}.fly.dev"
echo "Login: Foothills / Amish (or FAF_APP_* secrets)"
