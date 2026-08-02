#!/usr/bin/env bash
# Back up the local price book DATA (+ a session manifest) to a PRIVATE GitHub repo,
# so every device (either Mac, or a cloud agent) can restore the same catalog.
#
# WHY A SEPARATE PRIVATE REPO:
#   - master_pricebook.db is ~168MB of PRIVATE pricing.
#   - The main code repo (faf-pricelist-2.0) is PUBLIC — data must never go there.
#   - The DB gzips to ~14MB, well under GitHub's 100MB file limit (no LFS needed).
#
# SETUP (once, per machine):
#   1. Create a PRIVATE repo on GitHub, e.g.  <you>/faf-pricebook-backup
#   2. export FAF_BACKUP_REPO="https://<token>@github.com/<you>/faf-pricebook-backup.git"
#      (in a cloud agent, provide the token/URL via a secret instead of a shell profile)
#
# USAGE:  ./scripts/backup_to_github.sh ["optional session note"]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DB="${FAF_LOCAL_DB:-$ROOT/master_pricebook.db}"
CACHE="${FAF_BACKUP_CACHE:-$ROOT/.faf-backup}"   # gitignored working clone
NOTE="${1:-session backup}"

if [[ -z "${FAF_BACKUP_REPO:-}" ]]; then
  echo "Set FAF_BACKUP_REPO to your PRIVATE backup repo URL first (see header)." >&2
  exit 1
fi
if [[ ! -f "$LOCAL_DB" ]]; then
  echo "No local DB at $LOCAL_DB — run ./scripts/pull_db_from_fly.sh first." >&2
  exit 1
fi

# Clone or refresh the backup repo into the cache dir.
if [[ -d "$CACHE/.git" ]]; then
  git -C "$CACHE" remote set-url origin "$FAF_BACKUP_REPO"
  git -C "$CACHE" fetch --quiet origin
  git -C "$CACHE" checkout --quiet -B main "origin/main" 2>/dev/null || git -C "$CACHE" checkout --quiet -B main
else
  rm -rf "$CACHE"
  git clone --quiet "$FAF_BACKUP_REPO" "$CACHE"
fi

# HARD SAFETY GUARD (DEFAULT-DENY): only push data when the repo is CONFIRMED private.
# Strip any embedded token and the trailing .git, then take owner/repo.
slug="$(git -C "$CACHE" remote get-url origin | sed -E -e 's#\.git$##' -e 's#.*github\.com[:/]+##')"
if command -v gh >/dev/null 2>&1; then
  vis="$(gh repo view "$slug" --json visibility -q .visibility 2>/dev/null || echo UNKNOWN)"
else
  vis="NO_GH"
fi
case "$vis" in
  PRIVATE|INTERNAL)
    echo "Backup repo '$slug' visibility: $vis — OK."
    ;;
  *)
    if [[ "${FAF_BACKUP_CONFIRM_PRIVATE:-0}" == "1" ]]; then
      echo "WARN: could not verify '$slug' visibility (got: $vis); proceeding because FAF_BACKUP_CONFIRM_PRIVATE=1." >&2
    else
      echo "REFUSING: '$slug' is not a CONFIRMED private repo (visibility=$vis)." >&2
      echo "Private pricing data must only go to a PRIVATE repo. If you are certain it is private" >&2
      echo "and gh is unavailable, re-run with FAF_BACKUP_CONFIRM_PRIVATE=1." >&2
      exit 1
    fi
    ;;
esac

# Payload: gzipped DB (~14MB) + a human-readable manifest.
gzip -c "$LOCAL_DB" > "$CACHE/master_pricebook.db.gz"
read_rows() { python3 -c "import sqlite3;print(sqlite3.connect('$LOCAL_DB').execute('select count(*) from pricebook').fetchone()[0])"; }
read_vendors() { python3 -c "import sqlite3;print(sqlite3.connect('$LOCAL_DB').execute('select count(distinct vendor) from pricebook').fetchone()[0])"; }
rows="$(read_rows)"; vendors="$(read_vendors)"
code_sha="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)"
{
  echo "# FAF Price Book — backup manifest"
  echo
  echo "- when_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- device: $(hostname)"
  echo "- rows: $rows"
  echo "- vendors: $vendors"
  echo "- code_commit: $code_sha"
  echo "- note: $NOTE"
} > "$CACHE/MANIFEST.md"

git -C "$CACHE" add -A
if git -C "$CACHE" commit --quiet -m "backup: $rows rows / $vendors vendors ($(hostname)) — $NOTE"; then
  git -C "$CACHE" push --quiet origin main
  echo "Backed up to '$slug' (rows=$rows vendors=$vendors)."
else
  echo "Nothing changed since last backup."
fi
