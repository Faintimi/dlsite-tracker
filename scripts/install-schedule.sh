#!/bin/bash
# 安装每日调度：macOS launchd 用户代理（无需 sudo）。
# 卸载：scripts/uninstall-schedule.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.dlsite-tracker.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DAILY="$PROJECT_DIR/scripts/daily.sh"
PYTHON="$(command -v python3)"

if [[ ! -f "$PROJECT_DIR/config.ini" ]]; then
  echo "缺少 config.ini：请先执行 cp config.example.ini config.ini 并检查配置。" >&2
  exit 1
fi

chmod +x "$DAILY"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/data"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DAILY</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DLST_PYTHON</key>
    <string>$PYTHON</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>23</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$PROJECT_DIR/data/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$PROJECT_DIR/data/launchd.log</string>
</dict>
</plist>
PLIST_EOF

plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "已安装：${LABEL}（每日 23:30 运行 scripts/daily.sh，日志 data/daily.log）"
