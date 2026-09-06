#!/usr/bin/env bash
# Point this checkout at the traveling ExternalSSD data volume.
# Sourced by run.sh. Does not print secret file contents.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_faf_has_catalog() {
  local root="${1:-}"
  [[ -n "$root" && -f "$root/FAF-pricebook/master_pricebook.db" ]]
}

_faf_find_ssd_root() {
  local vol cand
  if [[ -n "${FAF_SSD_ROOT:-}" ]] && _faf_has_catalog "$FAF_SSD_ROOT"; then
    printf '%s\n' "$FAF_SSD_ROOT"
    return 0
  fi
  if _faf_has_catalog /Volumes/ExternalSSD; then
    printf '%s\n' /Volumes/ExternalSSD
    return 0
  fi
  for vol in /Volumes/*; do
    if _faf_has_catalog "$vol"; then
      printf '%s\n' "$vol"
      return 0
    fi
  done
  for cand in /media/*/* /run/media/*/* /mnt/*; do
    if _faf_has_catalog "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

_faf_link_if_absent() {
  local src="$1"
  local dest="$2"
  [[ -f "$src" ]] || return 0
  mkdir -p "$(dirname "$dest")"
  if [[ -L "$dest" ]]; then
    ln -sfn "$src" "$dest"
    return 0
  fi
  if [[ ! -e "$dest" ]]; then
    ln -sfn "$src" "$dest" 2>/dev/null || cp "$src" "$dest"
  fi
}

if [[ -n "${FLY_APP_NAME:-}${FLY_ALLOC_ID:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

SSD_ROOT="${FAF_SSD_ROOT:-}"
if [[ -z "$SSD_ROOT" ]] || ! _faf_has_catalog "$SSD_ROOT"; then
  SSD_ROOT="$(_faf_find_ssd_root || true)"
fi

if [[ -z "$SSD_ROOT" ]]; then
  echo "Plug in the price-book drive, then retry." >&2
  echo "Looking for FAF-pricebook/master_pricebook.db on /Volumes/ExternalSSD (or any mounted volume)." >&2
  exit 1
fi

DATA="${FAF_DATA_DIR:-$SSD_ROOT/FAF-pricebook}"
if [[ ! -f "$DATA/master_pricebook.db" ]]; then
  echo "Catalog missing at $DATA/master_pricebook.db" >&2
  exit 1
fi

mkdir -p "$DATA/image_assets" "$DATA/backups" "$DATA/ordertrac-session" "$DATA/credentials"

export FAF_SSD_ROOT="$SSD_ROOT"
export FAF_DATA_DIR="$DATA"
export FAF_DB_PATH="${FAF_DB_PATH:-$DATA/master_pricebook.db}"
export FAF_LOCAL_DB="${FAF_LOCAL_DB:-$FAF_DB_PATH}"
export FAF_PRICEBOOK_BACKUP_DIR="${FAF_PRICEBOOK_BACKUP_DIR:-$DATA/backups}"
export FAF_BACKUP_DIR="${FAF_BACKUP_DIR:-$DATA/backups}"
export FAF_ORDERTRAC_SESSION_DIR="${FAF_ORDERTRAC_SESSION_DIR:-$DATA/ordertrac-session}"
export FAF_VIZTECH_DOWNLOADS="${FAF_VIZTECH_DOWNLOADS:-$DATA/viztech-downloads}"

if [[ ! -f "$DATA/secrets.toml" && -f "$ROOT/.streamlit/secrets.toml.example" ]]; then
  cp "$ROOT/.streamlit/secrets.toml.example" "$DATA/secrets.toml"
  chmod 600 "$DATA/secrets.toml" 2>/dev/null || true
fi
if [[ -f "$DATA/secrets.toml" ]]; then
  export FAF_SECRETS_PATH="${FAF_SECRETS_PATH:-$DATA/secrets.toml}"
fi

mkdir -p "$ROOT/.streamlit"
if [[ -f "$DATA/secrets.toml" ]]; then
  ln -sfn "$DATA/secrets.toml" "$ROOT/.streamlit/secrets.toml"
fi

_faf_link_if_absent "$DATA/credentials/fly/config.yml" "$HOME/.fly/config.yml"
_faf_link_if_absent "$DATA/credentials/fly/state.yml" "$HOME/.fly/state.yml"
_faf_link_if_absent "$DATA/credentials/gh/hosts.yml" "$HOME/.config/gh/hosts.yml"
_faf_link_if_absent "$DATA/credentials/gh/config.yml" "$HOME/.config/gh/config.yml"

if [[ -d "$DATA/credentials/ssh" ]]; then
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh" 2>/dev/null || true
  if ! ls "$HOME/.ssh"/id_* >/dev/null 2>&1; then
    if ls "$DATA/credentials/ssh"/id_* >/dev/null 2>&1; then
      rsync -a --exclude='agent' --exclude='*.sock' "$DATA/credentials/ssh/" "$HOME/.ssh/"
      chmod 600 "$HOME/.ssh"/id_* 2>/dev/null || true
    fi
  fi
fi
