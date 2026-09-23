#!/bin/bash
# 封面补齐链（应用「首次初始化」完成后自动接续调用；也可手动执行）。
#   等价于：python -m dlsite_tracker task covers
#     → images（按配置限额补齐封面）→ export（导出 out/works.json）
# 状态：全过程写入 out/update-progress.json（应用横幅读取）
# 日志：data/covers.log
# 并发：data/covers.lock（与其它任务链互不影响）
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

exec "$PYTHON" -m dlsite_tracker task covers
