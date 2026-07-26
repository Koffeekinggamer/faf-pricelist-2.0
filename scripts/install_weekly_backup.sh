#!/bin/zsh
# Install a weekly LaunchAgent backup (Sundays 6:00 AM local).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/scripts/backup_db.py"
PLIST="$HOME/Library/LaunchAgents/com.faf.pricebook.backup.plist"
LOG_DIR="$HOME/Documents/FAF-pricebook-backups"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

if [[ ! -x "$PY" ]]; then
  echo "Missing venv python at $PY"
  exit 1
fi

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.faf.pricebook.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SCRIPT</string>
    <string>backup</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>0</integer>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/backup-weekly.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/backup-weekly.err</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed weekly backup: $PLIST"
echo "Runs every Sunday at 6:00 AM → $LOG_DIR"
# smoke one backup now
"$PY" "$SCRIPT" backup
