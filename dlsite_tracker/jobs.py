"""链式任务：daily / quick / update-all（跨平台实现）。

背景（P32）：三条链原先由 bash 脚本实现（``scripts/daily.sh`` 等）；为支持 Windows，
执行逻辑迁入本模块，脚本变为薄包装（``exec python3 -m dlsite_tracker task <chain>``）。

对外契约（与 bash 版本保持一致，应用横幅/调度均依赖）：
- 状态文件 ``out/update-progress.json``：
  ``schema_version / phase / detail / years / pid / updated_at / updated_ts``
- 日志：``data/daily.log``、``data/quick-update.log``、``data/update.log``（追加写）
- 链级锁：``data/daily.lock``、``data/quick-update.lock``、``data/update.lock``
  （目录锁 + pid 存活判定；进程被强杀留下的陈旧锁会自动清理）
- 退出码：0 成功；1 有步骤失败；2 用法错误（仅 update-all）；3 已有同类任务在运行；130 中断

跨平台：进程存活探测在 Windows 上使用 OpenProcess（避免 ``os.kill(pid, 0)`` 的
误杀语义）；其余逻辑（目录锁、状态写入、子进程执行）不依赖 POSIX。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .progress import write_task_progress

# 步骤执行器：(日志文件, 步骤名, CLI 参数) -> 退出码（负责写 [ok]/[skip]/[warn] 行）
StepRunner = Callable[[Path, str, Sequence[str]], int]
# 原样执行器：(日志文件, CLI 参数) -> 退出码（不追加结果行，供 update-all 使用）
RawRunner = Callable[[Path, Sequence[str]], int]

# 单步定义：(状态 phase, 状态 detail, 日志步骤名, CLI 参数)
_Step = Tuple[str, str, str, Sequence[str]]

DAILY_STEPS: Sequence[_Step] = (
    ("rankings", "更新热榜：榜单 / 分类人气 / 人气序 + 热榜富化", "update（增量+富化）", ("update", "--progress-label", "daily")),
    ("sales", "刷新在榜作品销量（近 7 天上榜）", "sales（在榜销量）", ("sales", "--hot-days", "7")),
    ("images", "补齐封面（按配置限额）", "images（封面）", ("images", "--progress-label", "daily")),
    ("export", "导出 out/works.json", "export（导出）", ("export",)),
    (
        "import",
        "渐进导入续传（无任务时秒退）",
        "import-recent（渐进导入续传）",
        ("import-recent", "--auto"),
    ),
)

QUICK_STEPS: Sequence[_Step] = (
    ("rankings", "快版：榜单 / 列表 / 人气序 + 热榜富化", "update（快版：跳过分类人气页）", ("update", "--skip-genre", "--progress-label", "quick")),
    ("sales", "刷新在榜作品销量（近 7 天上榜）", "sales（在榜销量）", ("sales", "--hot-days", "7")),
    ("export", "导出 out/works.json", "export（导出）", ("export",)),
)

COVERS_STEPS: Sequence[_Step] = (
    ("images", "补齐封面（按配置限额）", "images（封面）", ("images", "--progress-label", "covers")),
    ("export", "导出 out/works.json", "export（导出）", ("export",)),
)


@dataclass(frozen=True)
class JobPaths:
    """任务使用的目录（来自配置）。"""

    data_dir: Path
    out_dir: Path
    config_path: Optional[Path] = None


def _default_python() -> str:
    return sys.executable or "python3"


def _self_launcher(python: Optional[str], config_path: Optional[Path] = None) -> List[str]:
    """重启自身继续执行下一步的命令前缀。

    - 源码运行：``<python> -m dlsite_tracker``
    - PyInstaller 打包（桌面端内嵌管道）：可执行文件本身就是入口

    调用方提供 ``config_path`` 时显式透传 ``--config``，保证子进程使用同一份配置。
    """
    if getattr(sys, "frozen", False):
        launcher = [sys.executable or "python3"]
    else:
        launcher = [python or _default_python(), "-m", "dlsite_tracker"]
    if config_path is not None:
        launcher += ["--config", str(config_path)]
    return launcher


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append(log_file: Path, line: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def process_alive(pid: int) -> bool:
    """进程存活探测（跨平台；不发送任何信号）。

    Windows 下 ``os.kill(pid, 0)`` 会直接终止进程，因此改用 OpenProcess 查询。
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _process_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _process_alive_windows(pid: int) -> bool:
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class ChainLock:
    """目录锁（等价于原 bash 的 mkdir 锁 + pid 存活判定）。"""

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir

    def acquire(self) -> Optional[int]:
        """获得锁返回 None；被存活进程占用返回其 PID；无法获取返回 -1。"""
        try:
            self.lock_dir.mkdir(parents=True)
        except FileExistsError:
            old_pid = self._read_pid()
            if old_pid > 0 and process_alive(old_pid):
                return old_pid
            # 陈旧锁（进程已被强杀）：清理后重试一次
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            try:
                self.lock_dir.mkdir(parents=True)
            except OSError:
                return -1
        except OSError:
            return -1
        try:
            (self.lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            return -1
        return None

    def release(self) -> None:
        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def _read_pid(self) -> int:
        try:
            raw = (self.lock_dir / "pid").read_text(encoding="utf-8").strip()
            return int(raw or 0)
        except (OSError, ValueError):
            return 0


def write_state(state_file: Path, phase: str, detail: str, years: str) -> None:
    """原子写入进度状态（应用横幅读取；格式与 bash 版完全一致）。"""
    write_task_progress(state_file, phase, detail=detail, years=years)


def run_step(log_file: Path, name: str, command: Sequence[str]) -> int:
    """执行一步并把输出追加到日志；退出码 3 视为跳过（不计失败）。"""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as handle:
        code = subprocess.run(
            list(command), stdout=handle, stderr=subprocess.STDOUT
        ).returncode
    if code == 0:
        _append(log_file, f"[ok] {name}")
    elif code == 3:
        _append(log_file, f"[skip] {name}（已有导入在运行）")
    else:
        _append(log_file, f"[warn] {name} 失败（退出码 {code}），继续后续步骤")
    return code


def run_raw(log_file: Path, command: Sequence[str]) -> int:
    """原样执行并写日志（不追加 [ok]/[warn] 行）。"""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as handle:
        return subprocess.run(
            list(command), stdout=handle, stderr=subprocess.STDOUT
        ).returncode


def _make_runner(python: str, config_path: Optional[Path] = None) -> StepRunner:
    launcher = _self_launcher(python, config_path)

    def runner(log_file: Path, name: str, cli_args: Sequence[str]) -> int:
        return run_step(log_file, name, [*launcher, *cli_args])

    return runner


def _make_raw_runner(python: str, config_path: Optional[Path] = None) -> RawRunner:
    launcher = _self_launcher(python, config_path)

    def runner(log_file: Path, cli_args: Sequence[str]) -> int:
        return run_raw(log_file, [*launcher, *cli_args])

    return runner


def _run_chain(
    paths: JobPaths,
    *,
    years_label: str,
    lock_name: str,
    log_name: str,
    busy_message: str,
    start_message: str,
    end_message: str,
    done_detail: str,
    failed_detail: str,
    steps: Sequence[_Step],
    runner: StepRunner,
) -> int:
    log_file = paths.data_dir / log_name
    state_file = paths.out_dir / "update-progress.json"
    lock = ChainLock(paths.data_dir / lock_name)
    holder = lock.acquire()
    if holder is not None:
        if holder > 0:
            _append(log_file, f"===== {_timestamp()} {busy_message.format(pid=holder)} =====")
        return 3
    try:
        failed = 0
        _append(log_file, f"===== {_timestamp()} {start_message} =====")
        for phase, detail, name, cli_args in steps:
            write_state(state_file, phase, detail, years_label)
            code = runner(log_file, name, cli_args)
            if code not in (0, 3):
                failed = 1
        write_state(
            state_file,
            "done" if failed == 0 else "failed",
            done_detail if failed == 0 else failed_detail,
            years_label,
        )
        _append(log_file, f"===== {_timestamp()} {end_message.format(failed)} =====")
        return 0 if failed == 0 else 1
    except KeyboardInterrupt:
        _append(log_file, f"===== {_timestamp()} 收到中断（锁已释放） =====")
        return 130
    finally:
        lock.release()


def run_daily(
    paths: JobPaths, python: Optional[str] = None, runner: Optional[StepRunner] = None
) -> int:
    """每日完整维护链（launchd 23:30 / 应用「完整维护」按钮）。"""
    return _run_chain(
        paths,
        years_label="daily",
        lock_name="daily.lock",
        log_name="daily.log",
        busy_message="跳过：每日任务已在运行（PID {pid}）",
        start_message="每日任务开始",
        end_message="每日任务结束（FAILED={}）",
        done_detail="热榜与数据已更新",
        failed_detail="部分步骤失败；详见 data/daily.log",
        steps=DAILY_STEPS,
        runner=runner or _make_runner(python or _default_python(), paths.config_path),
    )


def run_quick(
    paths: JobPaths, python: Optional[str] = None, runner: Optional[StepRunner] = None
) -> int:
    """快版热榜更新链（应用「立即更新热榜（快）」按钮）。"""
    return _run_chain(
        paths,
        years_label="quick",
        lock_name="quick-update.lock",
        log_name="quick-update.log",
        busy_message="跳过：快版热榜更新已在运行（PID {pid}）",
        start_message="快版热榜更新开始",
        end_message="快版热榜更新结束（FAILED={}）",
        done_detail="热榜已更新（快版）",
        failed_detail="部分步骤失败；详见 data/quick-update.log",
        steps=QUICK_STEPS,
        runner=runner or _make_runner(python or _default_python(), paths.config_path),
    )


def run_covers(
    paths: JobPaths, python: Optional[str] = None, runner: Optional[StepRunner] = None
) -> int:
    """封面补齐链（首次初始化完成后由应用自动接续；也可手动执行）。"""
    return _run_chain(
        paths,
        years_label="covers",
        lock_name="covers.lock",
        log_name="covers.log",
        busy_message="跳过：封面补齐已在运行（PID {pid}）",
        start_message="封面补齐开始",
        end_message="封面补齐结束（FAILED={}）",
        done_detail="封面已补齐",
        failed_detail="部分步骤失败；详见 data/covers.log",
        steps=COVERS_STEPS,
        runner=runner or _make_runner(python or _default_python(), paths.config_path),
    )


_USAGE = "用法：python3 -m dlsite_tracker task update-all [1-30|all|since:YYYY|deeper:N]"


def _parse_scope(years: str) -> str:
    """校验范围参数并返回横幅文案；非法时抛 ValueError。"""
    if years == "all":
        return "全部"
    if years.startswith("since:"):
        value = years[len("since:") :]
        if not value.isdigit():
            raise ValueError(_USAGE)
        since = int(value)
        if since < 2005 or since > 2100:
            raise ValueError("since: 年份需在 2005–2100 之间")
        return f"自 {since} 年至今"
    if years.startswith("deeper:"):
        value = years[len("deeper:") :]
        if not value.isdigit():
            raise ValueError(_USAGE)
        deep = int(value)
        if deep < 2 or deep > 30:
            raise ValueError("续深目标年数需在 2–30 之间")
        return f"续深至最近 {deep} 年（跳过已覆盖段）"
    if not years.isdigit():
        raise ValueError(_USAGE)
    count = int(years)
    if count < 1 or count > 30:
        raise ValueError("年数需在 1–30 之间（更大范围请用 since:YYYY）")
    return f"最近 {count} 年"


def _import_summary(out_dir: Path) -> str:
    """完成时的汇总文案（读取导入进度；缺失时回退）。"""
    try:
        job = json.loads((out_dir / "import-progress.json").read_text(encoding="utf-8"))
        return "新增入库 {0} 部 · 排除非游戏 {1} · 忽略低销旧作 {2}".format(
            job.get("enriched", 0), job.get("excluded", 0), job.get("skipped", 0)
        )
    except (OSError, ValueError):
        return "数据已更新"


def run_update_all(
    paths: JobPaths,
    years: str = "1",
    python: Optional[str] = None,
    runner: Optional[RawRunner] = None,
) -> int:
    """一键更新链：导入（断点续传）→ 销量 → 封面 → 导出。

    ``years``：``1-30`` / ``all`` / ``since:YYYY`` / ``deeper:N``；非法时抛 ValueError
    （由 CLI 输出用法并以退出码 2 结束）。
    """
    scope = _parse_scope(years)
    log_file = paths.data_dir / "update.log"
    state_file = paths.out_dir / "update-progress.json"
    raw = runner or _make_raw_runner(python or _default_python(), paths.config_path)
    lock = ChainLock(paths.data_dir / "update.lock")
    holder = lock.acquire()
    if holder is not None:
        if holder > 0:
            _append(log_file, f"===== {_timestamp()} 跳过：已有更新在运行（PID {holder}） =====")
            write_state(state_file, "busy", f"已有更新在运行（PID {holder}）；请稍后再试", years)
        else:
            write_state(state_file, "busy", "无法获取更新锁", years)
        return 3
    try:
        _append(log_file, f"===== {_timestamp()} 一键更新开始（{scope}） =====")
        write_state(state_file, "import", f"导入 {scope}（断点续传）", years)
        if years.startswith("deeper:"):
            import_args: Sequence[str] = (
                "import-recent",
                "--years",
                years[len("deeper:") :],
                "--continue-deeper",
            )
        else:
            import_args = ("import-recent", "--years", years)
        code = raw(log_file, import_args)
        if code == 3:
            _append(log_file, "[跳过] 导入锁被占用（另一导入在运行）")
            write_state(state_file, "busy", "已有导入在运行；本次未执行。可稍后重试", years)
            return 3
        if code == 130:
            _append(log_file, "[中断] 导入被中断；断点已保存")
            write_state(state_file, "failed", "导入被中断；断点已保存（重跑可继续）", years)
            return 130
        if code != 0:
            _append(log_file, f"[错误] 导入失败（退出码 {code}）")
            write_state(state_file, "failed", f"导入失败（退出码 {code}）；详见 data/update.log", years)
            return code
        tail_steps = (
            ("sales", "刷新在榜作品销量（近 7 天上榜，每件每天最多一次）", ("sales", "--hot-days", "7"), "销量刷新失败"),
            ("images", "补齐封面（按配置限额）", ("images",), "封面下载失败"),
            ("export", "导出 out/works.json", ("export",), "导出失败"),
        )
        for phase, detail, cli_args, fail_detail in tail_steps:
            write_state(state_file, phase, detail, years)
            if raw(log_file, cli_args) != 0:
                _append(log_file, f"[错误] {fail_detail}")
                write_state(state_file, "failed", f"{fail_detail}；详见 data/update.log", years)
                return 1
        write_state(state_file, "done", _import_summary(paths.out_dir), years)
        _append(log_file, f"===== {_timestamp()} 一键更新结束（{scope}） =====")
        return 0
    except KeyboardInterrupt:
        _append(log_file, f"===== {_timestamp()} 收到中断（锁已释放） =====")
        write_state(state_file, "failed", "更新被中断；详见 data/update.log", years)
        return 130
    finally:
        lock.release()
