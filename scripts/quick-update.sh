#!/bin/bash
# 即刻更新·快版（应用「立即更新热榜（快）」按钮 / 手动执行）：
#   热榜页面（榜单/列表/人气序）→ 热榜富化 → 在榜销量 → 导出（≈2–4 分钟）。
#   与「完整维护」daily.sh（夜间 23:30）的区别：不抓分类人气页、不补封面、不做导入续传。
# 状态：全过程写 out/update-progress.json（years=quick；应用顶部横幅读取）
# 日志：data/quick-update.log
# 并发：链级锁 data/quick-update.lock（仅防本脚本重复；与 daily.sh / update-all.sh 各自独立）
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON="${DLST_PYTHON:-python3}"
LOG_FILE="$PROJECT_DIR/data/quick-update.log"
STATE_FILE="$PROJECT_DIR/out/update-progress.json"
LOCK_DIR="$PROJECT_DIR/data/quick-update.lock"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/out"

write_state() { # $1=phase $2=detail
  QUICK_PHASE="$1" QUICK_DETAIL="$2" \
    QUICK_STATE="$STATE_FILE" QUICK_PID="$$" "$PYTHON" - <<'PYEOF'
import json
import os
import time

path = os.environ["QUICK_STATE"]
payload = {
    "schema_version": 1,
    "phase": os.environ["QUICK_PHASE"],
    "detail": os.environ["QUICK_DETAIL"],
    "years": "quick",
    "pid": int(os.environ["QUICK_PID"]),
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

# 链级互斥（防重复点击/重复启动；进程被 kill -9 留下的陈旧锁自动清理）
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OLD_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过：快版热榜更新已在运行（PID ${OLD_PID}） =====" >>"$LOG_FILE"
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

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 快版热榜更新开始 =====" >>"$LOG_FILE"

write_state "rankings" "快版：榜单 / 列表 / 人气序 + 热榜富化"
run_step "update（快版：跳过分类人气页）" "$PYTHON" -m dlsite_tracker update --skip-genre

write_state "sales" "刷新在榜作品销量（近 7 天上榜）"
run_step "sales（在榜销量）" "$PYTHON" -m dlsite_tracker sales --hot-days 7

write_state "export" "导出 out/works.json"
run_step "export（导出）" "$PYTHON" -m dlsite_tracker export

if [ "$FAILED" -eq 0 ]; then
  write_state "done" "热榜已更新（快版）"
else
  write_state "failed" "部分步骤失败；详见 data/quick-update.log"
fi
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 快版热榜更新结束（FAILED=${FAILED}） =====" >>"$LOG_FILE"
[ "$FAILED" -eq 0 ] || exit 1
