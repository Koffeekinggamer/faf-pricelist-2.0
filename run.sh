#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:${PATH:-}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

PORT="${PORT:-8510}"
exec .venv/bin/streamlit run app.py \
  --server.headless true \
  --server.port "$PORT" \
  --browser.gatherUsageStats false
