#!/bin/bash
# 构建桌面端内嵌管道（PyInstaller 单文件）并放置到 Tauri 的 sidecar 目录。
#
# 用法：bash scripts/build-sidecar.sh
# 说明：
#   - 本地 `npm run tauri build` 打包桌面版前需先跑本脚本（产物不入库）；
#   - 仅 `npm run tauri dev` 开发时不需要（开发态回退「仓库 + 系统 Python」）；
#   - PyInstaller 只是构建期工具（运行期仍为零第三方依赖），安装在临时 venv 中；
#   - Windows（Git Bash / CI）同样可用。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) EXE_SUFFIX=".exe" ;;
  *) EXE_SUFFIX="" ;;
esac

PYTHON="${DLST_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON=python
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 Python（可用 DLST_PYTHON 指定解释器）" >&2
  exit 1
fi

VENV="${TMPDIR:-/tmp}/radar-sidecar-venv"
if [ -n "$EXE_SUFFIX" ]; then
  VENV_BIN="$VENV/Scripts"
else
  VENV_BIN="$VENV/bin"
fi
if [ ! -x "$VENV_BIN/pyinstaller$EXE_SUFFIX" ]; then
  echo "首次构建：创建打包 venv 并安装 PyInstaller…"
  "$PYTHON" -m venv "$VENV"
  "$VENV_BIN/pip" install -q --disable-pip-version-check pyinstaller
fi

"$VENV_BIN/pyinstaller$EXE_SUFFIX" \
  --onefile --name radar-pipeline --clean --noconfirm \
  --paths "$PROJECT_DIR" \
  --distpath "$PROJECT_DIR/packaging/dist" \
  --workpath "$PROJECT_DIR/packaging/build" \
  --specpath "$PROJECT_DIR/packaging/spec" \
  --log-level WARN \
  "$PROJECT_DIR/packaging/pipeline_entry.py"

TARGET="$(rustc -vV | sed -n 's/^host: //p')"
BIN_DIR="$PROJECT_DIR/desktop/src-tauri/binaries"
mkdir -p "$BIN_DIR"
SIDECAR="$BIN_DIR/radar-pipeline-$TARGET$EXE_SUFFIX"
cp "$PROJECT_DIR/packaging/dist/radar-pipeline$EXE_SUFFIX" "$SIDECAR"
chmod +x "$SIDECAR"
echo "已生成 sidecar：${SIDECAR}（$(du -h "$SIDECAR" | cut -f1)）"
