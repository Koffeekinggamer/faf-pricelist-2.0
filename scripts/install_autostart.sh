#!/bin/zsh
# Start Streamlit + Cloudflare public tunnel at login on this Mac.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
ST="$ROOT/.venv/bin/streamlit"
CF="${HOME}/.local/bin/cloudflared"
LOGDIR="${HOME}/Documents/FAF-pricebook-backups"
PLIST_DIR="${HOME}/Library/LaunchAgents"
mkdir -p "$LOGDIR" "$PLIST_DIR"

if [[ ! -x "$ST" ]]; then
  echo "Missing streamlit at $ST"
  exit 1
fi
if [[ ! -x "$CF" ]]; then
  echo "Missing cloudflared at $CF — install with: curl cloudflared release into ~/.local/bin"
  exit 1
fi

# --- Streamlit on :8501 ---
cat > "$PLIST_DIR/com.faf.pricebook.streamlit.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.faf.pricebook.streamlit</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ST</string>
    <string>run</string>
    <string>$ROOT/pricebook_app.py</string>
    <string>--server.headless</string>
    <string>true</string>
    <string>--server.port</string>
    <string>8501</string>
    <string>--browser.gatherUsageStats</string>
    <string>false</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOGDIR/streamlit.log</string>
  <key>StandardErrorPath</key>
  <string>$LOGDIR/streamlit.err</string>
</dict>
</plist>
EOF

# --- Cloudflare quick tunnel ---
cat > "$PLIST_DIR/com.faf.pricebook.tunnel.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.faf.pricebook.tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>$CF</string>
    <string>tunnel</string>
    <string>--url</string>
    <string>http://127.0.0.1:8501</string>
    <string>--no-autoupdate</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOGDIR/tunnel.log</string>
  <key>StandardErrorPath</key>
  <string>$LOGDIR/tunnel.err</string>
  <key>ThrottleInterval</key>
  <integer>10</integer>
</dict>
</plist>
EOF

launchctl unload "$PLIST_DIR/com.faf.pricebook.streamlit.plist" 2>/dev/null || true
launchctl unload "$PLIST_DIR/com.faf.pricebook.tunnel.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.faf.pricebook.streamlit.plist"
sleep 2
launchctl load "$PLIST_DIR/com.faf.pricebook.tunnel.plist"

echo "Installed LaunchAgents:"
echo "  com.faf.pricebook.streamlit  → http://localhost:8501"
echo "  com.faf.pricebook.tunnel     → public URL in $LOGDIR/tunnel.log"
echo "Login: Foothills / Amish"
sleep 6
grep -oE 'https://[a-z0-9-]+\.trycloudflare.com' "$LOGDIR/tunnel.log" 2>/dev/null | tail -1 || true
curl -s -o /dev/null -w "local:%{http_code}\n" http://127.0.0.1:8501/ || true
