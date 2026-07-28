#!/usr/bin/env bash
# Pull Fly volume DB → local master_pricebook.db (gitignored).
# Requires: flyctl logged in (or FLY_API_TOKEN), app faf-pricebook with volume.
set -euo pipefail

export PATH="${HOME}/.fly/bin:${PATH:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${FLY_APP:-faf-pricebook}"
LOCAL_DB="${FAF_LOCAL_DB:-$ROOT/master_pricebook.db}"
REMOTE_DB="/data/master_pricebook.db"
BACKUP_DIR="${FAF_BACKUP_DIR:-$HOME/Documents/FAF-pricebook-backups}"

if [[ -n "${FLY_API_TOKEN:-}" ]]; then
  export FLY_API_TOKEN
fi

mkdir -p "$(dirname "$LOCAL_DB")"
mkdir -p "$BACKUP_DIR"

if [[ -f "$LOCAL_DB" ]]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  cp -f "$LOCAL_DB" "$BACKUP_DIR/master_pricebook-before-pull-${stamp}.db"
  echo "Backed up existing local DB → $BACKUP_DIR/master_pricebook-before-pull-${stamp}.db"
fi

echo "Pulling $APP:$REMOTE_DB → $LOCAL_DB"
flyctl status -a "$APP" >/dev/null

# sftp get to a temp path then move (avoid partial overwrite)
tmp="${LOCAL_DB}.flypull"
rm -f "$tmp"
flyctl ssh sftp get "$REMOTE_DB" "$tmp" -a "$APP"
mv -f "$tmp" "$LOCAL_DB"

echo "Verifying…"
python3 - <<PY
import sqlite3
from pathlib import Path
p = Path("${LOCAL_DB}")
con = sqlite3.connect(str(p))
rows = con.execute("select count(*) from pricebook").fetchone()[0]
vendors = con.execute("select count(distinct vendor) from pricebook").fetchone()[0]
fn = con.execute("select count(*) from pricebook where vendor = 'FN Chair'").fetchone()[0]
print(f"OK  size={p.stat().st_size:,} bytes  rows={rows:,}  vendors={vendors}  FN Chair={fn:,}")
PY

echo ""
echo "Local app DB ready. Restart Streamlit if it is already running:"
echo "  ./run.sh"
echo "DB is gitignored — do not commit master_pricebook.db"
