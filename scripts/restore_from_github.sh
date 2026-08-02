#!/usr/bin/env bash
# Restore the local price book DATA from the PRIVATE GitHub backup repo.
# Counterpart to scripts/backup_to_github.sh — run at the start of a session on a
# device that does not have Fly access (otherwise prefer scripts/pull_db_from_fly.sh,
# which always matches the live site).
#
# Requires FAF_BACKUP_REPO (see backup_to_github.sh header).
# USAGE:  ./scripts/restore_from_github.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DB="${FAF_LOCAL_DB:-$ROOT/master_pricebook.db}"
CACHE="${FAF_BACKUP_CACHE:-$ROOT/.faf-backup}"

if [[ -z "${FAF_BACKUP_REPO:-}" ]]; then
  echo "Set FAF_BACKUP_REPO to your PRIVATE backup repo URL first." >&2
  exit 1
fi

if [[ -d "$CACHE/.git" ]]; then
  git -C "$CACHE" remote set-url origin "$FAF_BACKUP_REPO"
  git -C "$CACHE" fetch --quiet origin
  git -C "$CACHE" checkout --quiet -B main "origin/main"
else
  rm -rf "$CACHE"
  git clone --quiet "$FAF_BACKUP_REPO" "$CACHE"
fi

if [[ ! -f "$CACHE/master_pricebook.db.gz" ]]; then
  echo "No backup payload (master_pricebook.db.gz) found in $FAF_BACKUP_REPO." >&2
  exit 1
fi

if [[ -f "$LOCAL_DB" ]]; then
  mv "$LOCAL_DB" "${LOCAL_DB%.db}.prev-$(date +%Y%m%d-%H%M%S).db"
fi
gunzip -c "$CACHE/master_pricebook.db.gz" > "$LOCAL_DB"

echo "Restored $LOCAL_DB. Manifest:"
cat "$CACHE/MANIFEST.md" 2>/dev/null || true
echo ""
echo "Now run: ./run.sh   (http://127.0.0.1:8501 · login Foothills / Amish)"
