#!/bin/zsh
# Install a LaunchAgent that runs Viztech → FAF price book sync every 30 days.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/scripts/viztech_sync.py"
PLIST="$HOME/Library/LaunchAgents/com.faf.pricebook.viztech-sync.plist"
LOG_DIR="$HOME/Documents/FAF-pricebook-backups"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

if [[ ! -x "$PY" ]]; then
  echo "Missing venv python at $PY — create .venv and pip install -r requirements.txt first"
  exit 1
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "Missing $SCRIPT"
  exit 1
fi

# 30 days in seconds
INTERVAL=2592000

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.faf.pricebook.viztech-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SCRIPT</string>
  </array>
  <key>StartInterval</key>
  <integer>$INTERVAL</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>ExitTimeOut</key>
  <integer>14400</integer>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/viztech-sync.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/viztech-sync.err</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:$ROOT/.venv/bin</string>
  </dict>
  <key>Nice</key>
  <integer>10</integer>
</dict>
</plist>
EOF

# Prefer modern launchctl bootstrap; fall back to load
UID_NUM="$(id -u)"
launchctl bootout "gui/${UID_NUM}/com.faf.pricebook.viztech-sync" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
if launchctl bootstrap "gui/${UID_NUM}" "$PLIST" 2>/dev/null; then
  echo "Loaded via launchctl bootstrap"
else
  launchctl load "$PLIST"
  echo "Loaded via launchctl load"
fi

echo ""
echo "Installed: $PLIST"
echo "Schedule: every ${INTERVAL}s (~30 days)"
echo "Script:   $SCRIPT"
echo "Logs:     $LOG_DIR/viztech-sync.log"
echo "          $LOG_DIR/viztech-sync.err"
echo "State:    $LOG_DIR/viztech_sync_state.json"
echo ""
echo "Credentials (required for unattended runs):"
echo "  Edit $ROOT/.streamlit/secrets.toml and add:"
echo ""
echo "  [viztech]"
echo "  username = \"FoothillsAmish\""
echo "  password = \"your-password\""
echo ""
echo "Or: ~/.config/faf-pricebook/viztech.env"
echo "  VIZTECH_USER=..."
echo "  VIZTECH_PASSWORD=..."
echo ""
echo "Manual run now:"
echo "  $PY $SCRIPT --dry-run"
echo "  $PY $SCRIPT"
echo ""
echo "Note: StartInterval first fires ~30 days after load (not immediately)."
echo "      Run once manually today if you want a baseline."
