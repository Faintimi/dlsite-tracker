#!/bin/bash
# 每日数据任务：热榜更新（榜单/分类人气/人气序 + 热榜富化）→ 在榜销量 → 封面 → 导出 → 渐进导入续传。
# 由 launchd 每日调用（默认 23:30，见 install-schedule.sh），也可手动执行；应用「立即更新热榜」按钮同款（P27）。
# 可用环境变量 DLST_PYTHON 指定 Python 解释器（默认 python3）。
# 状态：全过程写 out/update-progress.json（应用顶部横幅读取；years 标记为 daily）
# 日志：data/daily.log
# 并发：链级锁 data/daily.lock（仅防本脚本重复运行；与 update-all.sh 链各自独立）
# 说明：渐进导入放在最后（长时间任务）；无任务时 import-recent --auto 秒退。
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON="${DLST_PYTHON:-python3}"
LOG_FILE="$PROJECT_DIR/data/daily.log"
STATE_FILE="$PROJECT_DIR/out/update-progress.json"
LOCK_DIR="$PROJECT_DIR/data/daily.lock"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/out"

write_state() { # $1=phase $2=detail
  DAILY_PHASE="$1" DAILY_DETAIL="$2" \
    DAILY_STATE="$STATE_FILE" DAILY_PID="$$" "$PYTHON" - <<'PYEOF'
import json
import os
import time

path = os.environ["DAILY_STATE"]
payload = {
    "schema_version": 1,
    "phase": os.environ["DAILY_PHASE"],
    "detail": os.environ["DAILY_DETAIL"],
    "years": "daily",
    "pid": int(os.environ["DAILY_PID"]),
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "updated_ts": int(time.time()),
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.replace(tmp, path)
PYEOF
}

# 链级互斥（仅防本脚本重复：夜间计划与手动/应用触发互斥；进程被 kill -9 留下的陈旧锁自动清理）
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OLD_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过：每日任务已在运行（PID ${OLD_PID}） =====" >>"$LOG_FILE"
    exit 3
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || exit 3
fi
echo "$$" >"$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

FAILED=0

run_step() {
  local name="$1"
  shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    echo "[ok] $name" >>"$LOG_FILE"
  else
    local code=$?
    if [ "$code" -eq 3 ]; then
      echo "[skip] ${name}（已有导入在运行）" >>"$LOG_FILE"
    else
      echo "[warn] $name 失败（退出码 ${code}），继续后续步骤" >>"$LOG_FILE"
      FAILED=1
    fi
  fi
}

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 每日任务开始 =====" >>"$LOG_FILE"

write_state "rankings" "更新热榜：榜单 / 分类人气 / 人气序 + 热榜富化"
run_step "update（增量+富化）" "$PYTHON" -m dlsite_tracker update

write_state "sales" "刷新在榜作品销量（近 7 天上榜）"
run_step "sales（在榜销量）" "$PYTHON" -m dlsite_tracker sales --hot-days 7

write_state "images" "补齐封面（按配置限额）"
run_step "images（封面）" "$PYTHON" -m dlsite_tracker images

write_state "export" "导出 out/works.json"
run_step "export（导出）" "$PYTHON" -m dlsite_tracker export

write_state "import" "渐进导入续传（无任务时秒退）"
run_step "import-recent（渐进导入续传）" "$PYTHON" -m dlsite_tracker import-recent --auto

if [ "$FAILED" -eq 0 ]; then
  write_state "done" "热榜与数据已更新"
else
  write_state "failed" "部分步骤失败；详见 data/daily.log"
fi
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 每日任务结束（FAILED=${FAILED}） =====" >>"$LOG_FILE"
[ "$FAILED" -eq 0 ] || exit 1
