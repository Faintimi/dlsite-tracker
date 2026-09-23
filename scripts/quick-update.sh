#!/bin/bash
# 即刻更新·快版（薄包装）：实际逻辑见 dlsite_tracker/jobs.py（跨平台，P32）。
# 链路：热榜页面（榜单/列表/人气序）→ 热榜富化 → 在榜销量 → 导出（≈2–4 分钟，不抓分类人气页/封面/导入）。
# 应用「立即更新热榜（快）」按钮 / 手动执行同款。
# 状态：out/update-progress.json（years=quick）；日志：data/quick-update.log；链级锁：data/quick-update.lock
# Windows 直接运行：python -m dlsite_tracker task quick
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON="${DLST_PYTHON:-python3}"
exec "$PYTHON" -m dlsite_tracker task quick
