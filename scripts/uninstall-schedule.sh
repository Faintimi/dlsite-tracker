#!/bin/bash
# 卸载每日调度（launchd 用户代理）。
set -euo pipefail

LABEL="com.dlsite-tracker.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "已卸载：$LABEL"
