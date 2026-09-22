#!/bin/bash
# 本地同步导出（应用「更新」按钮先跑它、再重读文件；纯本机、不联网）：
#   数据库 → out/works.json + out/works.csv（原子写入）
# 环境变量：DLST_PYTHON 指定 Python 解释器（默认 python3）
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

if [ -n "${DLST_PYTHON:-}" ]; then
  PYTHON="$DLST_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  PYTHON="/usr/bin/python3"
fi

exec "$PYTHON" -m dlsite_tracker export
