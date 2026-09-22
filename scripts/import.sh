#!/bin/bash
# 渐进导入开关后端（应用「渐进导入」开关 / 手动执行）：
#   start [N|all|since:YYYY|deeper:N]  启动或续传（N=1–30 年数；since:YYYY=自该年至今；deeper:N=续深至最近 N 年，跳过已覆盖段；后台运行；日志 data/import.log；PID 写入 data/import.pid）
#   pause            暂停当前进程（优雅中断，断点自动保存）
#   cancel           取消任务（删除任务定义；已入库作品保留）
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

ACTION="${1:-}"
shift || true

case "$ACTION" in
  start)
    YEARS="${1:-1}"
    case "$YEARS" in
      all) ;;
      since:*)
        SINCE_YEAR="${YEARS#since:}"
        case "$SINCE_YEAR" in
          ''|*[!0-9]*) echo "用法：import.sh start [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
        esac
        ;;
      deeper:*)
        DEEP_YEARS="${YEARS#deeper:}"
        case "$DEEP_YEARS" in
          ''|*[!0-9]*) echo "用法：import.sh start [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
        esac
        if [ "$DEEP_YEARS" -lt 2 ] || [ "$DEEP_YEARS" -gt 30 ]; then
          echo "续深目标年数需在 2–30 之间" >&2; exit 2
        fi
        ;;
      ''|*[!0-9]*) echo "用法：import.sh start [1-30|all|since:YYYY|deeper:N]" >&2; exit 2 ;;
      *)
        if [ "$YEARS" -lt 1 ] || [ "$YEARS" -gt 30 ]; then
          echo "年数需在 1–30 之间（更大范围请用 since:YYYY）" >&2; exit 2
        fi
        ;;
    esac
    mkdir -p "$PROJECT_DIR/data"
    rm -f "$PROJECT_DIR/data/import.pause"   # P22.3：清掉上次遗留的暂停标志再启动
    case "$YEARS" in
      deeper:*)
        nohup "$PYTHON" -m dlsite_tracker import-recent --years "${YEARS#deeper:}" --continue-deeper >>"$PROJECT_DIR/data/import.log" 2>&1 &
        ;;
      *)
        nohup "$PYTHON" -m dlsite_tracker import-recent --years "$YEARS" >>"$PROJECT_DIR/data/import.log" 2>&1 &
        ;;
    esac
    echo $! >"$PROJECT_DIR/data/import.pid"
    echo "已启动渐进导入（范围 ${YEARS}；PID $(cat "$PROJECT_DIR/data/import.pid")）"
    ;;
  pause)
    exec "$PYTHON" -m dlsite_tracker import-recent --pause
    ;;
  cancel)
    exec "$PYTHON" -m dlsite_tracker import-recent --cancel
    ;;
  *)
    echo "用法：import.sh start [1-30|all|since:YYYY|deeper:N] | pause | cancel" >&2
    exit 2
    ;;
esac
