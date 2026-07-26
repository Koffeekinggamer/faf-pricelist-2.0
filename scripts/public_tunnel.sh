#!/bin/zsh
# Share local FAF Price Book on a public HTTPS URL (this Mac must stay on).
# Writes the live trycloudflare URL to:
#   ~/Documents/FAF-pricebook-backups/CURRENT_PUBLIC_URL.txt
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CF="${HOME}/.local/bin/cloudflared"
PORT=8501
BACKUP="${HOME}/Documents/FAF-pricebook-backups"
URL_FILE="${BACKUP}/CURRENT_PUBLIC_URL.txt"
LOG="${BACKUP}/public_tunnel_run.log"

mkdir -p "$BACKUP"

if ! curl -s -o /dev/null -w '' "http://127.0.0.1:${PORT}/"; then
  echo "Starting Streamlit on :${PORT}..."
  cd "$ROOT"
  nohup .venv/bin/streamlit run pricebook_app.py --server.headless true --server.port "$PORT" \
    >/tmp/faf-streamlit.log 2>&1 &
  sleep 3
fi

if [[ ! -x "$CF" ]]; then
  echo "cloudflared missing at $CF"
  exit 1
fi

echo "Opening public tunnel → http://127.0.0.1:${PORT}"
echo "Login: Foothills / Amish"
echo "(URL will be saved to ${URL_FILE})"

# Stream cloudflared stderr+stdout, capture first trycloudflare URL
: > "$LOG"
"$CF" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate 2>&1 | while IFS= read -r line; do
  echo "$line" | tee -a "$LOG"
  if [[ "$line" == *"trycloudflare.com"* ]]; then
    url=$(echo "$line" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
    if [[ -n "$url" ]]; then
      echo "$url" > "$URL_FILE"
      echo ">>> Public URL saved: $url"
    fi
  fi
done
