#!/usr/bin/env bash
# One-shot: pull Fly DB (optional) → stats → thin catalogs (ADR-0007).
# Mac project root: /FAF-pricelist-2.0 (or this clone).
# Never commit master_pricebook.db.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PULL=1
MAX_ROWS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) PULL=0; shift ;;
    --max-rows) MAX_ROWS="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--no-pull] [--max-rows N]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -d .venv ]]; then
  echo "error: missing .venv — create/activate before running" >&2
  exit 1
fi

if [[ "$PULL" -eq 1 ]]; then
  if command -v flyctl >/dev/null 2>&1 || [[ -x "${HOME}/.fly/bin/flyctl" ]]; then
    echo "== Pull Fly DB =="
    ./scripts/pull_db_from_fly.sh || {
      echo "Pull failed — continuing with local DB if present." >&2
    }
  else
    echo "flyctl not found — skipping pull (use local master_pricebook.db)."
  fi
fi

echo "== Stats =="
.venv/bin/python -m backend.cli stats

echo "== Thin catalogs =="
if [[ -n "$MAX_ROWS" ]]; then
  .venv/bin/python -m backend.cli thin-catalogs --max-rows "$MAX_ROWS"
else
  .venv/bin/python -m backend.cli thin-catalogs
fi

echo ""
echo "Next: triage → grill Judson keep/replace/ignore per builder (ADR-0007)."
echo "Do not commit master_pricebook.db."
