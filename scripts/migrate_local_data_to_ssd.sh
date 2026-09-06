#!/usr/bin/env bash
# Move local catalog, images, secrets, and sessions onto ExternalSSD.
# Prints paths and sizes only — never file contents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSD_ROOT="${FAF_SSD_ROOT:-/Volumes/ExternalSSD}"
DATA="${FAF_DATA_DIR:-$SSD_ROOT/FAF-pricebook}"

copy_if_present() {
  local src="$1"
  local dest="$2"
  if [[ -e "$src" || -L "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    rsync -a "$src" "$dest"
    echo "copied $(du -sh "$dest" 2>/dev/null | awk '{print $1}')  $dest"
  fi
}

replace_with_link() {
  local src="$1"
  local dest="$2"
  if [[ ! -e "$dest" ]]; then
    return 0
  fi
  if [[ -L "$src" ]]; then
    ln -sfn "$dest" "$src"
    return 0
  fi
  if [[ -e "$src" ]]; then
    rm -rf "$src"
  fi
  mkdir -p "$(dirname "$src")"
  ln -sfn "$dest" "$src"
}

if [[ ! -d "$SSD_ROOT" ]]; then
  echo "Plug in ExternalSSD. Expected $SSD_ROOT" >&2
  exit 1
fi

mkdir -p "$DATA/image_assets" "$DATA/backups" "$DATA/ordertrac-session" "$DATA/viztech-downloads"
chmod 700 "$DATA"

echo "Destination: $DATA"

copy_if_present "$ROOT/master_pricebook.db" "$DATA/master_pricebook.db"
copy_if_present "$ROOT/master_pricebook.db-wal" "$DATA/master_pricebook.db-wal"
copy_if_present "$ROOT/master_pricebook.db-shm" "$DATA/master_pricebook.db-shm"
if [[ -d "$ROOT/image_assets" && ! -L "$ROOT/image_assets" ]]; then
  rsync -a "$ROOT/image_assets/" "$DATA/image_assets/"
  echo "copied $(du -sh "$DATA/image_assets" | awk '{print $1}')  $DATA/image_assets"
fi
copy_if_present "$ROOT/christina_lessons.jsonl" "$DATA/christina_lessons.jsonl"
copy_if_present "$ROOT/.streamlit/secrets.toml" "$DATA/secrets.toml"
copy_if_present "$ROOT/.streamlit/secrets.toml.example" "$DATA/secrets.toml.example"
copy_if_present "$HOME/.fly/config.yml" "$DATA/credentials/fly/config.yml"
copy_if_present "$HOME/.fly/state.yml" "$DATA/credentials/fly/state.yml"
copy_if_present "$HOME/.config/gh/hosts.yml" "$DATA/credentials/gh/hosts.yml"
copy_if_present "$HOME/.config/gh/config.yml" "$DATA/credentials/gh/config.yml"
if [[ -d "$HOME/.ssh" && ! -L "$HOME/.ssh" ]]; then
  mkdir -p "$DATA/credentials/ssh"
  rsync -a --exclude='agent' --exclude='*.sock' "$HOME/.ssh/" "$DATA/credentials/ssh/"
  echo "copied $(du -sh "$DATA/credentials/ssh" | awk '{print $1}')  $DATA/credentials/ssh"
fi
copy_if_present "$ROOT/.login_secret" "$DATA/.login_secret"
copy_if_present "$ROOT/.login_token" "$DATA/.login_token"
copy_if_present "$ROOT/.floor_favorites.json" "$DATA/.floor_favorites.json"
copy_if_present "$HOME/Documents/FAF-pricebook-backups/" "$DATA/backups/"
copy_if_present "$HOME/Documents/ordertrac-session/" "$DATA/ordertrac-session/"
if [[ -d "$HOME/Documents/viztech-downloads" && ! -L "$HOME/Documents/viztech-downloads" ]]; then
  rsync -a "$HOME/Documents/viztech-downloads/" "$DATA/viztech-downloads/"
  echo "copied $(du -sh "$DATA/viztech-downloads" | awk '{print $1}')  $DATA/viztech-downloads"
fi

if [[ -f "$DATA/secrets.toml" ]]; then
  chmod 600 "$DATA/secrets.toml"
fi
if [[ -f "$DATA/.login_secret" ]]; then
  chmod 600 "$DATA/.login_secret"
fi
if [[ -f "$DATA/.login_token" ]]; then
  chmod 600 "$DATA/.login_token"
fi

cat > "$DATA/TRAVEL.txt" <<'EOF'
FAF price book traveling data
=============================

Plug this drive in, then from a git checkout of FAF-pricelist-2.0:

  ./run.sh

The app looks for FAF-pricebook/master_pricebook.db on this drive
(any volume name is fine). Do not copy secrets.toml into git.

On a laptop:
  1. Clone FAF-pricelist-2.0
  2. Plug this drive in
  3. ./run.sh

That signs the floor back in from the remember-me token on this drive
and wires Fly / GitHub CLI files if the laptop does not already have them.
EOF

echo "Replacing Mac copies with links into the SSD…"
replace_with_link "$ROOT/master_pricebook.db" "$DATA/master_pricebook.db"
replace_with_link "$ROOT/master_pricebook.db-wal" "$DATA/master_pricebook.db-wal"
replace_with_link "$ROOT/master_pricebook.db-shm" "$DATA/master_pricebook.db-shm"
replace_with_link "$ROOT/image_assets" "$DATA/image_assets"
replace_with_link "$ROOT/christina_lessons.jsonl" "$DATA/christina_lessons.jsonl"
replace_with_link "$ROOT/.streamlit/secrets.toml" "$DATA/secrets.toml"
replace_with_link "$HOME/.fly/config.yml" "$DATA/credentials/fly/config.yml"
replace_with_link "$HOME/.fly/state.yml" "$DATA/credentials/fly/state.yml"
replace_with_link "$HOME/.config/gh/hosts.yml" "$DATA/credentials/gh/hosts.yml"
replace_with_link "$HOME/.config/gh/config.yml" "$DATA/credentials/gh/config.yml"
replace_with_link "$ROOT/.login_secret" "$DATA/.login_secret"
replace_with_link "$ROOT/.login_token" "$DATA/.login_token"
replace_with_link "$ROOT/.floor_favorites.json" "$DATA/.floor_favorites.json"
replace_with_link "$HOME/Documents/FAF-pricebook-backups" "$DATA/backups"
replace_with_link "$HOME/Documents/ordertrac-session" "$DATA/ordertrac-session"
replace_with_link "$HOME/Documents/viztech-downloads" "$DATA/viztech-downloads"

echo "SSD data folder:"
du -sh "$DATA" "$DATA"/* 2>/dev/null | sed 's#/Volumes/ExternalSSD/FAF-pricebook#FAF-pricebook#'
echo "Done. On a laptop: clone the repo, plug this drive in, run ./run.sh"
