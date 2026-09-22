#!/bin/bash
# 分类人气「现导入 / 载入更多 / 加入每日刷新」后端（应用按钮调用；P19.2）
#   import（默认）：抓分类人气页（前 N 页或 --more 续一页）→ 定向富化新作品 →
#                    定向补封面 → 导出 out/works.json
#   watch <id>     ：把分类加入每日刷新列表（写入 config 的 genre_rank_ids）
#
# 用法：bash scripts/genre-import.sh <genre_id> [--more] [--pages N]
#       bash scripts/genre-import.sh watch <genre_id>
# 环境变量：DLST_PYTHON 指定 Python 解释器（默认 python3）
# 状态：全过程写入 out/genre-progress.json（应用横幅读取）
# 日志：data/genre.log
# 并发：data/genre-fetch.lock（仅防本脚本重复；与更新/导入可并行——现导入流量小）
# 退出码：0 成功；1 失败；2 用法错误；3 已有分类任务在运行
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

if [ "${1:-}" = "watch" ]; then
  shift
  GENRE="${1:-}"
  [ -n "$GENRE" ] || { echo "用法：bash scripts/genre-import.sh watch <genre_id>" >&2; exit 2; }
  exec "$PYTHON" -m dlsite_tracker watch-genre "$GENRE"
fi

GENRE="${1:-}"
[ -n "$GENRE" ] || { echo "用法：bash scripts/genre-import.sh <genre_id> [--more] [--pages N]" >&2; exit 2; }
shift || true
MORE_FLAG=""
PAGES_FLAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --more) MORE_FLAG="--more" ;;
    --pages)
      shift
      PAGES_FLAG="--pages ${1:-}"
      ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift || true
done

LOG_FILE="$PROJECT_DIR/data/genre.log"
STATE_FILE="$PROJECT_DIR/out/genre-progress.json"
LOCK_DIR="$PROJECT_DIR/data/genre-fetch.lock"
WORKNOS_FILE="$PROJECT_DIR/data/genre-worknos.txt"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/out"

write_state() { # $1=phase $2=detail $3=running $4=done $5=error $6=genre_name
  GENRE_PROGRESS_ID="$GENRE" GENRE_PROGRESS_NAME="${6:-}" \
    GENRE_PROGRESS_PHASE="$1" GENRE_PROGRESS_DETAIL="$2" \
    GENRE_PROGRESS_RUNNING="$3" GENRE_PROGRESS_DONE="$4" GENRE_PROGRESS_ERROR="$5" \
    GENRE_PROGRESS_MORE="$MORE_BOOL" \
    GENRE_PROGRESS_STATE="$STATE_FILE" GENRE_PROGRESS_PID="$$" "$PYTHON" - <<'PYEOF'
import json
import os
import time

path = os.environ["GENRE_PROGRESS_STATE"]
payload = {
    "schema_version": 1,
    "genre_id": os.environ["GENRE_PROGRESS_ID"],
    "genre_name": os.environ.get("GENRE_PROGRESS_NAME", ""),
    "phase": os.environ["GENRE_PROGRESS_PHASE"],
    "detail": os.environ["GENRE_PROGRESS_DETAIL"],
    "running": os.environ["GENRE_PROGRESS_RUNNING"] == "true",
    "done": os.environ["GENRE_PROGRESS_DONE"] == "true",
    "error": os.environ["GENRE_PROGRESS_ERROR"],
    "more": os.environ.get("GENRE_PROGRESS_MORE", "false") == "true",
    "pid": int(os.environ["GENRE_PROGRESS_PID"]),
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

# 防重复触发（与更新/导入可并行；陈旧锁自动清理）
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OLD_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过：已有分类任务在运行（PID ${OLD_PID}） =====" >>"$LOG_FILE"
    write_state "busy" "已有分类任务在运行（PID ${OLD_PID}）；请稍等" "false" "false" ""
    exit 3
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || { write_state "busy" "无法获取任务锁" "false" "false" ""; exit 3; }
fi
echo "$$" >"$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

MODE="现导入"
MORE_BOOL="false"
[ -n "$MORE_FLAG" ] && MODE="载入更多" && MORE_BOOL="true"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 分类人气开始（${MODE} · ${GENRE}） =====" >>"$LOG_FILE"

if ! "$PYTHON" -c "import dlsite_tracker" >/dev/null 2>&1; then
  echo "[错误] 无法导入 dlsite_tracker（PYTHON=${PYTHON}）" >>"$LOG_FILE"
  write_state "failed" "无法导入 dlsite_tracker（检查 Python 与项目目录）" "false" "false" "无法导入 dlsite_tracker"
  exit 1
fi

# 1) 抓取分类人气页（含登记与销量）
write_state "fetch" "正在抓取人气榜（约 10–40 秒）" "true" "false" ""
FETCH_OUT="$("$PYTHON" -m dlsite_tracker fetch-genre "$GENRE" $MORE_FLAG $PAGES_FLAG 2>>"$LOG_FILE")"
FETCH_CODE=$?
echo "$FETCH_OUT" >>"$LOG_FILE"
if [ "$FETCH_CODE" -ne 0 ]; then
  write_state "failed" "抓取失败（退出码 ${FETCH_CODE}）；详见 data/genre.log" "false" "false" "抓取失败"
  exit 1
fi
GENRE_NAME="$(printf '%s\n' "$FETCH_OUT" | sed -n 's/^\[分类人气\] [^ ]* 名称 \(.*\)$/\1/p' | head -1)"
GENRE_NAME="${GENRE_NAME:-$GENRE}"
FETCHED="$(printf '%s\n' "$FETCH_OUT" | sed -n 's/.*名次 \([0-9]*\) 条.*/\1/p' | head -1)"
FETCHED="${FETCHED:-0}"

# 2) 定向富化新作品（跳过已富化；时长取决于新作品数）
write_state "enrich" "正在导入新作品入库（新作较多时需数分钟）" "true" "false" "" "$GENRE_NAME"
if ! "$PYTHON" -m dlsite_tracker enrich --source "genre-rank:maniax:$GENRE" --limit 800 >>"$LOG_FILE" 2>&1; then
  echo "[警告] 定向富化失败（继续补封面与导出）" >>"$LOG_FILE"
fi

# 3) 定向补封面
write_state "images" "正在补齐新作品封面…" "true" "false" "" "$GENRE_NAME"
if ! "$PYTHON" -m dlsite_tracker images --worknos-file "$WORKNOS_FILE" --limit 600 >>"$LOG_FILE" 2>&1; then
  echo "[警告] 封面补齐失败（继续导出）" >>"$LOG_FILE"
fi

# 4) 导出（应用检测到完成后自动重读）
write_state "export" "正在导出数据…" "true" "false" "" "$GENRE_NAME"
if ! "$PYTHON" -m dlsite_tracker export >>"$LOG_FILE" 2>&1; then
  write_state "failed" "导出失败；详见 data/genre.log" "false" "false" "导出失败" "$GENRE_NAME"
  exit 1
fi

write_state "done" "「${GENRE_NAME}」名次 ${FETCHED} 条已更新" "false" "true" "" "$GENRE_NAME"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 分类人气完成（${GENRE}） =====" >>"$LOG_FILE"
exit 0
