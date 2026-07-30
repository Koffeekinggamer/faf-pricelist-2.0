#!/usr/bin/env bash
# Prefer project venv ruff, else PATH (FAF pre-commit).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUFF="$ROOT/.venv/bin/ruff"
if [[ ! -x "$RUFF" ]]; then
  RUFF=ruff
fi
exec "$RUFF" "$@"
