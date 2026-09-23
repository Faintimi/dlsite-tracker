#!/bin/bash
# 每日数据任务（薄包装）：实际逻辑见 dlsite_tracker/jobs.py（跨平台，P32）。
# 链路：热榜更新（榜单/分类人气/人气序 + 富化）→ 在榜销量 → 封面 → 导出 → 渐进导入续传。
# 由 launchd 每日调用（默认 23:30，见 install-schedule.sh）；应用「完整维护」按钮同款。
# 可用环境变量 DLST_PYTHON 指定 Python 解释器（默认 python3）。
# 状态：out/update-progress.json（years=daily）；日志：data/daily.log；链级锁：data/daily.lock
# Windows 直接运行：python -m dlsite_tracker task daily
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON="${DLST_PYTHON:-python3}"
exec "$PYTHON" -m dlsite_tracker task daily
