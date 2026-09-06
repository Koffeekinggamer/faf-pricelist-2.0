#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:${PATH:-}"
# Catalog, images, and secrets live on ExternalSSD when traveling.
# shellcheck source=scripts/faf_portable_data.sh
source "$(dirname "$0")/scripts/faf_portable_data.sh"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/python -c "from backend.login_session import ensure_travel_login_token; ensure_travel_login_token()" >/dev/null || true

PORT="${PORT:-8501}"
exec .venv/bin/streamlit run pricebook_app.py \
  --server.headless true \
  --server.port "$PORT" \
  --browser.gatherUsageStats false
