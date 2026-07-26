#!/usr/bin/env bash
# Private local backup of master_pricebook.db (never pushed to GitHub).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="$ROOT/master_pricebook.db"
BACKUP_DIR="${FAF_PRICEBOOK_BACKUP_DIR:-$HOME/Documents/FAF-pricebook-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [[ ! -f "$DB" ]]; then
  echo "No database at $DB" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
DEST="$BACKUP_DIR/master_pricebook-$STAMP.db"
cp -p "$DB" "$DEST"

# Keep last 20 backups
ls -1t "$BACKUP_DIR"/master_pricebook-*.db 2>/dev/null | tail -n +21 | while read -r old; do
  rm -f "$old"
done

SIZE="$(du -h "$DEST" | awk '{print $1}')"
COUNT="$(ls -1 "$BACKUP_DIR"/master_pricebook-*.db 2>/dev/null | wc -l | tr -d ' ')"
echo "Backed up → $DEST ($SIZE)"
echo "Backups in $BACKUP_DIR: $COUNT (keeping newest 20)"
