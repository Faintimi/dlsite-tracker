#!/bin/bash
# 一键更新（应用「开始更新数据」按钮 / 手动执行）：
#   导入最近 N 年（断点续传）→ 销量刷新 → 封面补齐 → 导出 out/works.json
#
# 用法：bash scripts/update-all.sh [1-30|all|since:YYYY|deeper:N]    （默认 1）
# 环境变量：DLST_PYTHON 指定 Python 解释器（默认 python3）
# 状态：全过程写入 out/update-progress.json（应用顶部横幅读取）
# 日志：data/update.log
# 并发：
#   - 链级锁 data/update.lock（内含 pid；按进程存活判定，防同链条重复）
#   - 导入另有 data/import.lock（import-recent 自带；与每日调度互斥）
# 退出码：0 成功；1 某步失败；2 用法错误；3 已有更新/导入在运行
# 备注：若已有进行中的导入任务且范围不同，import-recent 会拒绝（退出码 1）——
#       请先 `python3 -m dlsite_tracker import-recent --cancel` 或加 --restart 处理。
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

YEARS="${1:-1}"
case "$YEARS" in
  all) ;;
  since:*)
    SINCE_YEAR="${YEARS#since:}"
    case "$SINCE_YEAR" in
      ''|*[!0-9]*) echo "用法：bash scripts/update-all.sh [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
    esac
    if [ "$SINCE_YEAR" -lt 2005 ] || [ "$SINCE_YEAR" -gt 2100 ]; then
      echo "since: 年份需在 2005–2100 之间" >&2; exit 2
    fi
    ;;
  deeper:*)
    DEEP_YEARS="${YEARS#deeper:}"
    case "$DEEP_YEARS" in
      ''|*[!0-9]*) echo "用法：bash scripts/update-all.sh [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
    esac
    if [ "$DEEP_YEARS" -lt 2 ] || [ "$DEEP_YEARS" -gt 30 ]; then
      echo "续深目标年数需在 2–30 之间" >&2; exit 2
    fi
    ;;
  ''|*[!0-9]*) echo "用法：bash scripts/update-all.sh [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
  *)
    if [ "$YEARS" -lt 1 ] || [ "$YEARS" -gt 30 ]; then
      echo "年数需在 1–30 之间（更大范围请用 since:YYYY）" >&2; exit 2
    fi
    ;;
esac

if [ -n "${DLST_PYTHON:-}" ]; then
  PYTHON="$DLST_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  PYTHON="/usr/bin/python3"
fi

LOG_FILE="$PROJECT_DIR/data/update.log"
STATE_FILE="$PROJECT_DIR/out/update-progress.json"
LOCK_DIR="$PROJECT_DIR/data/update.lock"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/out"

write_state() { # $1=phase $2=detail
  UPDATE_PHASE="$1" UPDATE_DETAIL="$2" UPDATE_YEARS="$YEARS" \
    UPDATE_STATE="$STATE_FILE" UPDATE_PID="$$" "$PYTHON" - <<'PYEOF'
import json
import os
import time

path = os.environ["UPDATE_STATE"]
payload = {
    "schema_version": 1,
    "phase": os.environ["UPDATE_PHASE"],
    "detail": os.environ["UPDATE_DETAIL"],
    "years": os.environ["UPDATE_YEARS"],
    "pid": int(os.environ["UPDATE_PID"]),
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

# 链级互斥（mkdired 锁 + pid 存活判定；进程已被 kill -9 时自动清理陈旧锁）
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OLD_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过：已有更新在运行（PID ${OLD_PID}） =====" >>"$LOG_FILE"
    write_state "busy" "已有更新在运行（PID ${OLD_PID}）；请稍后再试"
    exit 3
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || { write_state "busy" "无法获取更新锁"; exit 3; }
fi
echo "$$" >"$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

SCOPE="最近 $YEARS 年"
[ "$YEARS" = "all" ] && SCOPE="全部"
case "$YEARS" in
  since:*) SCOPE="自 ${YEARS#since:} 年至今" ;;
  deeper:*) SCOPE="续深至最近 ${YEARS#deeper:} 年（跳过已覆盖段）" ;;
esac
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 一键更新开始（${SCOPE}） =====" >>"$LOG_FILE"

if ! "$PYTHON" -c "import dlsite_tracker" >/dev/null 2>&1; then
  echo "[错误] 无法导入 dlsite_tracker（PYTHON=${PYTHON}）" >>"$LOG_FILE"
  write_state "failed" "无法导入 dlsite_tracker（检查 Python 与项目目录）"
  exit 1
fi

# 1) 渐进导入（断点续传；锁占用时退出码 3）
write_state "import" "导入 ${SCOPE}（断点续传）"
case "$YEARS" in
  deeper:*)
    "$PYTHON" -m dlsite_tracker import-recent --years "${YEARS#deeper:}" --continue-deeper >>"$LOG_FILE" 2>&1
    ;;
  *)
    "$PYTHON" -m dlsite_tracker import-recent --years "$YEARS" >>"$LOG_FILE" 2>&1
    ;;
esac
code=$?
if [ "$code" -eq 3 ]; then
  echo "[跳过] 导入锁被占用（另一导入在运行）" >>"$LOG_FILE"
  write_state "busy" "已有导入在运行；本次未执行。可稍后重试"
  exit 3
fi
if [ "$code" -eq 130 ]; then
  echo "[中断] 导入被中断；断点已保存" >>"$LOG_FILE"
  write_state "failed" "导入被中断；断点已保存（重跑可继续）"
  exit 130
fi
if [ "$code" -ne 0 ]; then
  echo "[错误] 导入失败（退出码 ${code}）" >>"$LOG_FILE"
  write_state "failed" "导入失败（退出码 ${code}）；详见 data/update.log"
  exit "$code"
fi

# 2) 销量刷新（P20 做减法：只维持在榜作品）
write_state "sales" "刷新在榜作品销量（近 7 天上榜，每件每天最多一次）"
if ! "$PYTHON" -m dlsite_tracker sales --hot-days 7 >>"$LOG_FILE" 2>&1; then
  echo "[错误] 销量刷新失败" >>"$LOG_FILE"
  write_state "failed" "销量刷新失败；详见 data/update.log"
  exit 1
fi

# 3) 封面补齐（按配置限额）
write_state "images" "补齐封面（按配置限额）"
if ! "$PYTHON" -m dlsite_tracker images >>"$LOG_FILE" 2>&1; then
  echo "[错误] 封面下载失败" >>"$LOG_FILE"
  write_state "failed" "封面下载失败；详见 data/update.log"
  exit 1
fi

# 4) 导出（应用读取 out/works.json）
write_state "export" "导出 out/works.json"
if ! "$PYTHON" -m dlsite_tracker export >>"$LOG_FILE" 2>&1; then
  echo "[错误] 导出失败" >>"$LOG_FILE"
  write_state "failed" "导出失败；详见 data/update.log"
  exit 1
fi

# 5) 完成（汇总导入成果供横幅显示）
DETAIL="$(UPDATE_OUT_DIR="$PROJECT_DIR/out" "$PYTHON" - <<'PYEOF'
import json
import os

try:
    with open(os.path.join(os.environ["UPDATE_OUT_DIR"], "import-progress.json"), encoding="utf-8") as handle:
        job = json.load(handle)
    print(
        "新增入库 {0} 部 · 排除非游戏 {1} · 忽略低销旧作 {2}".format(
            job.get("enriched", 0), job.get("excluded", 0), job.get("skipped", 0)
        )
    )
except Exception:
    print("数据已更新")
PYEOF
)"
write_state "done" "$DETAIL"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 一键更新结束（${SCOPE}） =====" >>"$LOG_FILE"
exit 0
