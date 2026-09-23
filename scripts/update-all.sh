#!/bin/bash
# 一键更新（薄包装）：实际逻辑见 dlsite_tracker/jobs.py（跨平台，P32）。
# 链路：导入最近 N 年（断点续传）→ 销量刷新 → 封面补齐 → 导出 out/works.json
#
# 用法：bash scripts/update-all.sh [1-30|all|since:YYYY|deeper:N]    （默认 1）
# 环境变量：DLST_PYTHON 指定 Python 解释器（默认 python3）
# 状态：out/update-progress.json；日志：data/update.log；链级锁：data/update.lock
# 退出码：0 成功；1 某步失败；2 用法错误；3 已有更新/导入在运行
# Windows 直接运行：python -m dlsite_tracker task update-all deeper:7
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

exec "$PYTHON" -m dlsite_tracker task update-all "${1:-1}"
