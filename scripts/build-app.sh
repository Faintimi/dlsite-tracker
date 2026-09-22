#!/bin/bash
# 构建「同人游戏筛选器」桌面应用（源码：app/DoujinGameFinder.swift）。
# 依赖：Xcode Command Line Tools 的 swiftc（无需第三方依赖、无需 sudo）。
# 产物：app/dist/同人游戏筛选器.app（不入库）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$PROJECT_DIR/app/DoujinGameFinder.swift"
DIST="$PROJECT_DIR/app/dist"
APP="$DIST/同人游戏筛选器.app"
BIN="DoujinGameFinder"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "缺少 swiftc：请先安装 Xcode Command Line Tools（xcode-select --install）" >&2
  exit 1
fi
if [[ ! -f "$SRC" ]]; then
  echo "缺少源码：$SRC" >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key><string>同人游戏筛选器</string>
	<key>CFBundleExecutable</key><string>DoujinGameFinder</string>
	<key>CFBundleIdentifier</key><string>local.codex.doujingamefinder</string>
	<key>CFBundleName</key><string>同人游戏筛选器</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>1.0</string>
	<key>CFBundleVersion</key><string>1</string>
	<key>LSMinimumSystemVersion</key><string>15.4</string>
	<key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

echo "[构建] swiftc -O -parse-as-library app/DoujinGameFinder.swift"
swiftc -O -parse-as-library "$SRC" -o "$APP/Contents/MacOS/$BIN"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 \
  || echo "[警告] 临时签名失败（应用仍可右键→打开）"

plutil -lint "$APP/Contents/Info.plist" >/dev/null
echo "已构建：$APP"
echo "打开：  open \"$APP\""
