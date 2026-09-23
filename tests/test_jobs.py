"""jobs.py 的离线测试：锁 / 状态 / 步骤执行 / 链编排（不触网、不起真实管道）。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dlsite_tracker import jobs


def _paths(tmp: str) -> jobs.JobPaths:
    return jobs.JobPaths(data_dir=Path(tmp) / "data", out_dir=Path(tmp) / "out")


class ProcessAliveTests(unittest.TestCase):
    def test_self_is_alive(self) -> None:
        self.assertTrue(jobs.process_alive(os.getpid()))

    def test_bogus_pid_is_dead(self) -> None:
        self.assertFalse(jobs.process_alive(999_999_999))

    def test_invalid_pids(self) -> None:
        self.assertFalse(jobs.process_alive(0))
        self.assertFalse(jobs.process_alive(-1))


class ChainLockTests(unittest.TestCase):
    def test_acquire_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = jobs.ChainLock(Path(tmp) / "x.lock")
            self.assertIsNone(lock.acquire())
            self.assertEqual((Path(tmp) / "x.lock" / "pid").read_text().strip(), str(os.getpid()))
            lock.release()
            self.assertFalse((Path(tmp) / "x.lock").exists())

    def test_busy_when_holder_alive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp) / "x.lock"
            lock_dir.mkdir()
            (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
            self.assertEqual(jobs.ChainLock(lock_dir).acquire(), os.getpid())

    def test_stale_lock_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp) / "x.lock"
            lock_dir.mkdir()
            (lock_dir / "pid").write_text("999999999", encoding="utf-8")
            lock = jobs.ChainLock(lock_dir)
            self.assertIsNone(lock.acquire())
            self.assertEqual((lock_dir / "pid").read_text().strip(), str(os.getpid()))


class PipelineLockTests(unittest.TestCase):
    def test_shared_lock_blocks_other_update_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            lock = jobs.PipelineLock(paths.data_dir / "pipeline.lock")
            self.assertIsNone(lock.acquire())
            try:
                self.assertEqual(jobs.run_quick(paths, runner=lambda *args: 0), 3)
                self.assertEqual(jobs.run_bootstrap(paths, runner=lambda *args: 0), 3)
                self.assertEqual(jobs.run_update_all(paths, runner=lambda *args: 0), 3)
            finally:
                lock.release()
            self.assertEqual(jobs.run_quick(paths, runner=lambda *args: 0), 0)


class WriteStateTests(unittest.TestCase):
    def test_payload_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "out" / "update-progress.json"
            jobs.write_state(state, "rankings", "测试详情", "quick")
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["phase"], "rankings")
            self.assertEqual(payload["detail"], "测试详情")
            self.assertEqual(payload["years"], "quick")
            self.assertEqual(payload["pid"], os.getpid())
            self.assertIsInstance(payload["updated_ts"], int)
            self.assertFalse((Path(tmp) / "out" / "update-progress.json.tmp").exists())


class SelfLauncherTests(unittest.TestCase):
    """_self_launcher：源码运行 / PyInstaller 打包两种形态；--config 透传。"""

    def test_source_run(self) -> None:
        self.assertEqual(
            jobs._self_launcher("/usr/bin/python3"),
            ["/usr/bin/python3", "-m", "dlsite_tracker"],
        )

    def test_source_run_with_config(self) -> None:
        config = Path("/tmp/x/config.ini")
        self.assertEqual(
            jobs._self_launcher("/usr/bin/python3", config),
            ["/usr/bin/python3", "-m", "dlsite_tracker", "--config", str(config)],
        )

    def test_frozen_uses_self_executable(self) -> None:
        config = Path("/opt/cfg.ini")
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys, "executable", "/opt/radar-pipeline"
        ):
            self.assertEqual(
                jobs._self_launcher(None, config),
                ["/opt/radar-pipeline", "--config", str(config)],
            )


class RunStepTests(unittest.TestCase):
    """run_step：默认执行器（子进程 + 日志行）。"""

    def _run(self, code: int) -> tuple:
        tmp = tempfile.mkdtemp()
        log = Path(tmp) / "a.log"
        result = jobs.run_step(log, "步骤", [sys.executable, "-c", f"import sys; sys.exit({code})"])
        return result, log.read_text(encoding="utf-8")

    def test_ok(self) -> None:
        code, log = self._run(0)
        self.assertEqual(code, 0)
        self.assertIn("[ok] 步骤", log)

    def test_skip_code_3(self) -> None:
        code, log = self._run(3)
        self.assertEqual(code, 3)
        self.assertIn("[skip] 步骤（已有导入在运行）", log)

    def test_warn_other_code(self) -> None:
        code, log = self._run(5)
        self.assertEqual(code, 5)
        self.assertIn("[warn] 步骤 失败（退出码 5），继续后续步骤", log)


class DailyChainTests(unittest.TestCase):
    def test_daily_ok(self) -> None:
        calls: list = []

        def runner(log_file: Path, name: str, cli_args) -> int:
            calls.append((name, list(cli_args)))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_daily(paths, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(
                [args for _, args in calls],
                [
                    ["update", "--progress-label", "daily"],
                    ["sales", "--hot-days", "7"],
                    ["images", "--progress-label", "daily"],
                    ["export"],
                    ["import-recent", "--auto"],
                ],
            )
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "done")
            self.assertEqual(state["years"], "daily")
            log = (paths.data_dir / "daily.log").read_text(encoding="utf-8")
            self.assertIn("每日任务开始", log)
            self.assertIn("每日任务结束（FAILED=0）", log)
            self.assertTrue((paths.data_dir / "pipeline.lock").exists())

    def test_daily_failure_marks_failed(self) -> None:
        codes = iter([0, 5, 0, 0, 0])

        def runner(log_file: Path, name: str, cli_args) -> int:
            return next(codes)

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_daily(paths, runner=runner)
            self.assertEqual(code, 1)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "failed")
            log = (paths.data_dir / "daily.log").read_text(encoding="utf-8")
            self.assertIn("每日任务结束（FAILED=1）", log)

    def test_daily_skip_counts_as_ok(self) -> None:
        codes = iter([3, 0, 0, 0, 0])

        def runner(log_file: Path, name: str, cli_args) -> int:
            return next(codes)

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_daily(paths, runner=runner)
            self.assertEqual(code, 0)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "done")

    def test_daily_busy_when_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            lock = jobs.PipelineLock(paths.data_dir / "pipeline.lock")
            self.assertIsNone(lock.acquire())
            try:
                code = jobs.run_daily(paths, runner=lambda *a: 0)
                self.assertEqual(code, 3)
                log = (paths.data_dir / "daily.log").read_text(encoding="utf-8")
                self.assertIn("跳过：每日任务已在运行", log)
            finally:
                lock.release()


class QuickChainTests(unittest.TestCase):
    def test_quick_steps_and_skip_genre(self) -> None:
        calls: list = []

        def runner(log_file: Path, name: str, cli_args) -> int:
            calls.append(list(cli_args))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_quick(paths, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(
                calls,
                [
                    ["update", "--skip-genre", "--progress-label", "quick"],
                    ["sales", "--hot-days", "7"],
                    ["images", "--progress-label", "quick"],
                    ["export"],
                ],
            )
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["years"], "quick")
            log = (paths.data_dir / "quick-update.log").read_text(encoding="utf-8")
            self.assertIn("快版热榜更新开始", log)
            self.assertIn("快版热榜更新结束（FAILED=0）", log)


class BootstrapChainTests(unittest.TestCase):
    def test_bootstrap_always_finishes_covers_before_export(self) -> None:
        calls: list = []

        def runner(log_file: Path, name: str, cli_args) -> int:
            calls.append(list(cli_args))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_bootstrap(paths, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(
                calls,
                [
                    ["init"],
                    ["update", "--skip-genre", "--progress-label", "bootstrap"],
                    ["sales", "--hot-days", "7"],
                    ["images", "--progress-label", "bootstrap"],
                    ["export"],
                ],
            )
            state = json.loads(
                (paths.out_dir / "update-progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["phase"], "done")
            self.assertEqual(state["years"], "bootstrap")
            log = (paths.data_dir / "bootstrap.log").read_text(encoding="utf-8")
            self.assertIn("首次初始化开始", log)
            self.assertIn("首次初始化结束（FAILED=0）", log)

    def test_failed_init_stops_before_network_work(self) -> None:
        calls: list = []

        def runner(log_file: Path, name: str, cli_args) -> int:
            calls.append(list(cli_args))
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            self.assertEqual(jobs.run_bootstrap(paths, runner=runner), 1)
            self.assertEqual(calls, [["init"]])
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "failed")


class CoversChainTests(unittest.TestCase):
    def test_covers_steps(self) -> None:
        calls: list = []

        def runner(log_file: Path, name: str, cli_args) -> int:
            calls.append(list(cli_args))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_covers(paths, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(
                calls, [["images", "--progress-label", "covers"], ["export"]]
            )
            state = json.loads(
                (paths.out_dir / "update-progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["years"], "covers")
            log = (paths.data_dir / "covers.log").read_text(encoding="utf-8")
            self.assertIn("封面补齐开始", log)


class UpdateAllTests(unittest.TestCase):
    def test_validation_errors(self) -> None:
        cases = (
            ("99", "年数需在 1–30"),
            ("0", "年数需在 1–30"),
            ("abc", "用法"),
            ("since:1900", "2005–2100"),
            ("since:abc", "用法"),
            ("deeper:1", "2–30"),
            ("deeper:99", "2–30"),
            ("deeper:abc", "用法"),
        )
        for years, expected in cases:
            with self.subTest(years=years):
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(ValueError) as ctx:
                        jobs.run_update_all(_paths(tmp), years=years, runner=lambda *a: 0)
                    self.assertIn(expected, str(ctx.exception))

    def test_success_flow(self) -> None:
        calls: list = []

        def runner(log_file: Path, cli_args) -> int:
            calls.append(list(cli_args))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="2", runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(
                calls,
                [["import-recent", "--years", "2"], ["sales", "--hot-days", "7"], ["images"], ["export"]],
            )
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "done")
            self.assertEqual(state["detail"], "数据已更新")  # 无导入进度文件时的回退文案
            log = (paths.data_dir / "update.log").read_text(encoding="utf-8")
            self.assertIn("一键更新开始（最近 2 年）", log)
            self.assertIn("一键更新结束（最近 2 年）", log)
            self.assertTrue((paths.data_dir / "pipeline.lock").exists())

    def test_deeper_flow(self) -> None:
        calls: list = []

        def runner(log_file: Path, cli_args) -> int:
            calls.append(list(cli_args))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="deeper:5", runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(calls[0], ["import-recent", "--years", "5", "--continue-deeper"])
            log = (paths.data_dir / "update.log").read_text(encoding="utf-8")
            self.assertIn("续深至最近 5 年（跳过已覆盖段）", log)

    def test_import_summary_used_when_available(self) -> None:
        def runner(log_file: Path, cli_args) -> int:
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            paths.out_dir.mkdir(parents=True)
            (paths.out_dir / "import-progress.json").write_text(
                json.dumps({"enriched": 12, "excluded": 3, "skipped": 5}), encoding="utf-8"
            )
            jobs.run_update_all(paths, years="2", runner=runner)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["detail"], "新增入库 12 部 · 排除非游戏 3 · 忽略低销旧作 5")

    def test_import_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="2", runner=lambda *a: 3)
            self.assertEqual(code, 3)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "busy")
            log = (paths.data_dir / "update.log").read_text(encoding="utf-8")
            self.assertIn("[跳过] 导入锁被占用", log)

    def test_import_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="2", runner=lambda *a: 130)
            self.assertEqual(code, 130)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "failed")
            log = (paths.data_dir / "update.log").read_text(encoding="utf-8")
            self.assertIn("[中断] 导入被中断；断点已保存", log)

    def test_import_error_code_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="2", runner=lambda *a: 4)
            self.assertEqual(code, 4)
            log = (paths.data_dir / "update.log").read_text(encoding="utf-8")
            self.assertIn("[错误] 导入失败（退出码 4）", log)

    def test_sales_failure_marks_failed(self) -> None:
        codes = iter([0, 5, 0, 0])

        def runner(log_file: Path, cli_args) -> int:
            return next(codes)

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(tmp)
            code = jobs.run_update_all(paths, years="2", runner=runner)
            self.assertEqual(code, 1)
            state = json.loads((paths.out_dir / "update-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "failed")
            self.assertIn("销量刷新失败", state["detail"])


if __name__ == "__main__":
    unittest.main()
