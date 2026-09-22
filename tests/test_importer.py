"""渐进导入测试（离线）。"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path

from dlsite_tracker import cli
from dlsite_tracker.enrich import PRODUCT_API_URL
from dlsite_tracker.http import HttpError
from dlsite_tracker.importer import (
    ANCHORS,
    SERIES_MODERN,
    SERIES_OLD,
    acquire_import_lock,
    boundaries_for_days,
    boundaries_for_years,
    estimate_date,
    estimate_number,
    estimate_page_for_date,
    release_import_lock,
    run_import,
    save_coverage,
    workno_number,
    workno_series,
    years_label,
)
from dlsite_tracker.store import Store


def item(
    workno: str,
    work_type: str = "SLN",
    name: str = "测试",
    regist_date: str = "2026-01-01 00:00:00",
) -> dict:
    return {
        "workno": workno,
        "site_id": "maniax",
        "work_name": name,
        "work_type": work_type,
        "genres": [{"id": "1", "name": "测试分类"}],
        "regist_date": regist_date,
    }


def api_url(workno: str) -> str:
    return PRODUCT_API_URL.format(site="maniax", workno=workno, locale="zh_CN")


class FakeApiFetcher:
    def __init__(self, payloads, sales=None):
        self.payloads = payloads
        self.sales = sales or {}  # workno → dl_count 或 (dl_count, wishlist)
        self.image_fetches = []
        self.json_calls = []

    def get_json(self, url):
        self.json_calls.append(url)
        if "/product/info/ajax?" in url:
            ids = url.split("product_id=")[1].split("&")[0].split(",")
            result = {}
            for workno in ids:
                if workno not in self.sales:
                    continue
                value = self.sales[workno]
                if isinstance(value, dict):  # P13：完整信息（类型/上架日等）
                    result[workno] = dict(value)
                else:
                    dl, wishlist = value if isinstance(value, tuple) else (value, 0)
                    result[workno] = {"dl_count": dl, "wishlist_count": wishlist}
            return result
        if url not in self.payloads:
            raise AssertionError(f"意外请求：{url}")
        return self.payloads[url]

    def get_bytes(self, url, kind="image", max_bytes=None):
        self.image_fetches.append(url)
        return b"\xff\xd8\xff\xe0fake-cover"


def filler_worknos(start: int, count: int) -> list:
    """生成「窗口外」填充作品号（RJ+8 位、数字 1,30xxxxx → 远早于最近一年边界）。"""
    return [f"RJ{start + index:08d}" for index in range(count)]


def catalog_page(*worknos: str, sales=None, fillers: int = 0, filler_start: int = 1_300_001) -> str:
    """拼一个「作品一覧」页 HTML：真实条目（可带卡面销量）+ 填充条目（凑够一页）。"""
    sales = sales or {}
    entries = list(worknos) + filler_worknos(filler_start, fillers)
    chunks = []
    for workno in entries:
        counter = ""
        if workno in sales:
            counter = f'<dd class="_dl_count_{workno}">{sales[workno]:,}</dd>'
        chunks.append(
            f'<li data-list_item_product_id="{workno}">'
            f'<a href="https://www.dlsite.com/maniax/work/=/product_id/{workno}.html">x</a>'
            f"{counter}</li>"
        )
    return "<ul>" + "".join(chunks) + "</ul>"


class FakeCatalogFetcher(FakeApiFetcher):
    """在 FakeApiFetcher 之上提供目录页 get_text（P18 run_catalog_walk 用）。"""

    def __init__(self, payloads, sales=None, pages=None, fail_pages=None):
        super().__init__(payloads, sales=sales)
        self.pages = pages or {}
        self.fail_pages = set(fail_pages or ())
        self.text_fetches = []

    def get_text(self, url, kind="page", max_bytes=None):
        self.text_fetches.append(url)
        page = int(url.rsplit("/", 1)[-1])
        if page in self.fail_pages:
            raise HttpError(f"HTTP 500：{url}")
        if page not in self.pages:
            raise HttpError(f"HTTP 404：{url}")
        return self.pages[page]


def make_cfg(
    out_dir: Path,
    min_sales: int = 0,
    fresh_days: int = 0,
    cover_trigger: int = 0,
    cover_batch: int = 0,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        data_dir=out_dir.parent,
        out_dir=out_dir,
        sites=["maniax"],
        locale="zh_CN",
        default_work_types=["RPG", "SLN"],
        hot_window_days=7,
        import_min_sales=min_sales,
        import_fresh_days=fresh_days,
        import_cover_trigger=cover_trigger,
        import_cover_batch=cover_batch,
        images_enabled=True,
    )


class WorknoTest(unittest.TestCase):
    def test_series_and_number(self):
        self.assertEqual(workno_series("RJ441526"), "old")
        self.assertEqual(workno_series("RJ01024693"), "modern")
        self.assertIsNone(workno_series("RJ123"))
        self.assertEqual(workno_number("RJ441526"), 441526)
        self.assertEqual(workno_number("RJ01024693"), 1024693)
        self.assertIsNone(workno_number("RJABC"))


class EstimateTest(unittest.TestCase):
    def test_interpolation_and_extrapolation(self):
        anchors = [(1000, "2020-01-01"), (2000, "2020-01-31")]
        self.assertEqual(estimate_number(datetime(2020, 1, 1), anchors), 1000)
        self.assertEqual(estimate_number(datetime(2020, 1, 31), anchors), 2000)
        middle = estimate_number(datetime(2020, 1, 16), anchors)
        self.assertTrue(1400 <= middle <= 1600)
        self.assertGreater(estimate_number(datetime(2020, 2, 10), anchors), 2000)
        self.assertLess(estimate_number(datetime(2019, 12, 1), anchors), 1000)

    def test_boundaries_for_years(self):
        now = datetime(2026, 9, 21, 12, 0, 0)
        old_1y, modern_1y = boundaries_for_years("1", now=now)
        self.assertGreater(old_1y, 441526)  # 最近一年内旧系列已停用
        self.assertTrue(1460000 <= modern_1y <= 1500000)
        _, modern_3y = boundaries_for_years("3", now=now)
        self.assertTrue(1020000 <= modern_3y <= 1120000)
        self.assertEqual(boundaries_for_years("all"), (0, 0))
        with self.assertRaises(ValueError):
            boundaries_for_years("0")

    def test_boundaries_for_years_since_and_count(self):
        """P22：since:YYYY 按该年 1 月 1 日划线；年数支持任意正整数（如 5/7）。"""
        now = datetime(2026, 9, 21, 12, 0, 0)
        days = (now - datetime(2018, 1, 1)).days
        self.assertEqual(
            boundaries_for_years("since:2018", now=now),
            boundaries_for_days(days, now=now),
        )
        self.assertEqual(
            boundaries_for_years("5", now=now),
            boundaries_for_days(365 * 5, now=now),
        )
        self.assertEqual(years_label("since:2018"), "自 2018 年 1 月")
        self.assertEqual(years_label(7), "最近 7 年")
        self.assertEqual(years_label("all"), "全部")
        with self.assertRaises(ValueError):
            boundaries_for_years("since:20xx")
        with self.assertRaises(ValueError):
            boundaries_for_years("since:2099", now=now)
        with self.assertRaises(ValueError):
            boundaries_for_years("since:1999", now=now)

    def test_estimate_date_inverts_estimate_number(self):
        """P23：编号→日期（逆插值）应与正插值自洽。"""
        for date_text in ("2018-01-01", "2021-06-15"):
            target = datetime.strptime(date_text, "%Y-%m-%d")
            number = estimate_number(target, ANCHORS[SERIES_OLD])
            back = estimate_date(number, ANCHORS[SERIES_OLD])
            self.assertLessEqual(abs((back - target).days), 3)
        for date_text in ("2024-01-01", "2026-01-01"):
            target = datetime.strptime(date_text, "%Y-%m-%d")
            number = estimate_number(target, ANCHORS[SERIES_MODERN])
            back = estimate_date(number, ANCHORS[SERIES_MODERN])
            self.assertLessEqual(abs((back - target).days), 3)

    def test_estimate_page_for_date_calibration(self):
        """P23：页↔日期校准点与三年前档位估算。"""
        now = datetime(2026, 9, 22)
        self.assertEqual(estimate_page_for_date(datetime(2023, 10, 1), now=now), 100)
        self.assertEqual(estimate_page_for_date(datetime(2006, 7, 1), now=now), 359)
        self.assertEqual(estimate_page_for_date(now, now=now), 1)
        page_3y = estimate_page_for_date(datetime(2023, 9, 22), now=now)
        self.assertTrue(95 <= page_3y <= 110)


class ImportRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = Store(self.tmp / "t.sqlite")
        self.store.migrate()
        (self.tmp / "out").mkdir()
        self.cfg = make_cfg(self.tmp / "out")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _payloads(self, *worknos, work_type="SLN"):
        return {api_url(workno): [item(workno, work_type)] for workno in worknos}

    def _progress(self) -> dict:
        path = self.tmp / "out" / "import-progress.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_import_lock_exclusive(self):
        cfg = types.SimpleNamespace(data_dir=self.tmp)
        first = acquire_import_lock(cfg)
        self.assertIsNotNone(first)
        self.assertIsNone(acquire_import_lock(cfg))  # 已占用 → 拒绝
        release_import_lock(first)
        again = acquire_import_lock(cfg)
        self.assertIsNotNone(again)
        release_import_lock(again)

    def test_cli_lock_skip_returns_code_3(self):
        """锁被占用时 import-recent 返回退出码 3（update-all.sh 依赖该约定）。"""
        cfg = types.SimpleNamespace(data_dir=self.tmp, out_dir=self.tmp / "out")
        held = acquire_import_lock(cfg)
        try:
            args = types.SimpleNamespace(
                status=False,
                cancel=False,
                dry_run=False,
                auto=False,
                years="1",
                restart=False,
                limit=None,
                pause=False,
            )
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_import_recent(cfg, args)
            self.assertEqual(code, 3)
            self.assertIn("已有导入进程在运行", buffer.getvalue())
        finally:
            release_import_lock(held)

    def test_cancel_stops_running_process_before_delete(self):
        """P22.2：--cancel 先向运行中的导入进程发 SIGINT（防幽灵），再删任务定义。"""
        import signal as signal_module
        from unittest import mock

        cfg = types.SimpleNamespace(data_dir=self.tmp, out_dir=self.tmp / "out")
        db = Store(self.tmp / "dlsite.sqlite")  # 与 cmd_import_recent 打开的是同一文件
        db.migrate()
        try:
            db.save_import_job(
                years="7",
                phase="enrich",
                boundary_old=1,
                boundary_modern=2,
                fresh_old=1,
                fresh_modern=2,
                min_sales=0,
                fresh_days=0,
                source="catalog",
            )
            progress = self.tmp / "out" / "import-progress.json"
            progress.write_text(json.dumps({"running": True, "pid": 424242}), encoding="utf-8")
            args = types.SimpleNamespace(pause=False, status=False, cancel=True, dry_run=False)

            kill0_calls = 0

            def fake_kill(pid, sig):
                nonlocal kill0_calls
                if sig == 0:
                    kill0_calls += 1
                    if kill0_calls == 1:
                        return None  # 首次探测：还活着
                    raise ProcessLookupError()
                return None  # SIGINT / SIGTERM 等照发

            with mock.patch("dlsite_tracker.cli.os.kill", side_effect=fake_kill) as killer:
                code = cli.cmd_import_recent(cfg, args)
            self.assertEqual(code, 0)
            self.assertIn(
                (424242, signal_module.SIGINT), [call.args for call in killer.call_args_list]
            )
            self.assertIsNone(db.get_import_job())
            self.assertFalse(progress.exists())
            self.assertFalse((self.tmp / "import.pause").exists())  # 标志已清理
        finally:
            db.close()

    def test_run_import_tops_up_covers(self):
        """封面自愈（P12.1）：每累计富化 cover_trigger 件顺带补一批封面；结束再收尾。"""
        worknos = ["RJ01480300", "RJ01480301"]
        self.store.add_pending_many(worknos, source="backfill:maniax")
        payloads = {
            api_url(workno): [
                dict(item(workno), image_thumb=f"https://img.dlsite.jp/{workno}.jpg")
            ]
            for workno in worknos
        }
        fetcher = FakeApiFetcher(payloads, sales={workno: 10 for workno in worknos})
        cfg = make_cfg(self.tmp / "out", cover_trigger=2, cover_batch=5)
        result = run_import(fetcher, self.store, cfg, "all", source="numbers")
        self.assertEqual(result["status"], "done")
        covers = sorted(path.name for path in (self.tmp / "out" / "covers").iterdir())
        self.assertEqual(covers, ["RJ01480300.jpg", "RJ01480301.jpg"])
        self.assertEqual(len(fetcher.image_fetches), 2)  # 每张只取一次

    def test_run_import_batch_preclassifies(self):
        """P13 批量预分类：非游戏与「真实日期过窗且低销」的旧作不逐件抓详情。"""
        self.store.add_pending_many(
            ["RJ01480400", "RJ01700400", "RJ01700401"], source="backfill:maniax"
        )
        # RJ01480400：work_type=MNG（非游戏）——批量实查即排除，不请求 product.json
        # RJ01700400：编号看似新作，但真实上架 2025-01（过窗）且销量 100 → 预筛跳过
        # RJ01700401：新作（2026-09-15，销量 10）→ 富化入库
        # payloads 只给 401 的详情地址：若代码对 400/401 发起详情请求，Fake 会直接报错
        fetcher = FakeApiFetcher(
            {
                api_url("RJ01700401"): [
                    item("RJ01700401", "SLN", regist_date="2026-09-15 00:00:00")
                ]
            },
            sales={
                "RJ01480400": {
                    "dl_count": 5000,
                    "wishlist_count": 10,
                    "work_type": "MNG",
                    "regist_date": "2026-09-01 00:00:00",
                },
                "RJ01700400": {
                    "dl_count": 100,
                    "wishlist_count": 5,
                    "work_type": "SLN",
                    "regist_date": "2025-01-01 00:00:00",
                },
                "RJ01700401": {
                    "dl_count": 10,
                    "wishlist_count": 1,
                    "work_type": "SLN",
                    "regist_date": "2026-09-15 00:00:00",
                },
            },
        )
        cfg = make_cfg(self.tmp / "out", min_sales=2000, fresh_days=90)
        result = run_import(fetcher, self.store, cfg, "all", source="numbers")
        self.assertEqual(
            result["session"], {"enriched": 1, "excluded": 1, "skipped": 1, "failed": 0}
        )
        kept = [
            row[0]
            for row in self.store.conn.execute(
                "SELECT workno FROM works WHERE enriched_at IS NOT NULL"
            ).fetchall()
        ]
        self.assertEqual(kept, ["RJ01700401"])
        row = self.store.conn.execute(
            "SELECT work_type FROM excluded WHERE workno=?", ("RJ01480400",)
        ).fetchone()
        self.assertEqual(row[0], "MNG")  # 类型来自批量实查
        self.assertEqual(self.store.pending_count(), 0)

    def test_run_import_drains_covers_at_end(self):
        """P13.1 收尾清零：导入结束后分批循环补封面直到缺口为空。"""
        worknos = ["RJ01480500", "RJ01480501", "RJ01480502"]
        self.store.add_pending_many(worknos, source="backfill:maniax")
        payloads = {
            api_url(workno): [
                dict(item(workno), image_thumb=f"https://img.dlsite.jp/{workno}.jpg")
            ]
            for workno in worknos
        }
        fetcher = FakeApiFetcher(payloads, sales={workno: 10 for workno in worknos})
        cfg = make_cfg(self.tmp / "out", cover_trigger=1000, cover_batch=1)
        result = run_import(fetcher, self.store, cfg, "all", source="numbers")
        self.assertEqual(result["status"], "done")
        covers = sorted(path.name for path in (self.tmp / "out" / "covers").iterdir())
        self.assertEqual(len(covers), 3)  # 收尾把 3 张全部补齐
        exported = json.loads((self.tmp / "out" / "works.json").read_text(encoding="utf-8"))
        self.assertEqual(exported["count"], 3)  # P15：完成自动导出
        self.assertEqual(len(fetcher.image_fetches), 3)

    def test_cli_pause_paths(self):
        """P15：--pause 无进行中任务→提示；running 但进程不存在→提示且不报错。"""
        cfg = types.SimpleNamespace(data_dir=self.tmp, out_dir=self.tmp / "out")
        args = types.SimpleNamespace(
            status=False,
            cancel=False,
            dry_run=False,
            auto=False,
            years=None,
            restart=False,
            limit=None,
            pause=True,
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cli.cmd_import_recent(cfg, args), 0)
        self.assertIn("没有进行中的导入", buffer.getvalue())
        (self.tmp / "out" / "import-progress.json").write_text(
            json.dumps({"running": True, "pid": 999999}), encoding="utf-8"
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cli.cmd_import_recent(cfg, args), 0)
        self.assertIn("进程已不存在", buffer.getvalue())

    def test_run_import_drains_and_excludes_non_games(self):
        self.store.add_pending_many(["RJ01480000", "RJ01480001"], source="backfill:maniax")
        fetcher = FakeApiFetcher(
            {
                api_url("RJ01480000"): [item("RJ01480000", "SLN")],
                api_url("RJ01480001"): [item("RJ01480001", "MNG")],
            },
            sales={"RJ01480000": 30, "RJ01480001": 40},
        )
        result = run_import(fetcher, self.store, self.cfg, "all", source="numbers")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["session"], {"enriched": 1, "excluded": 1, "skipped": 0, "failed": 0})
        self.assertEqual(self.store.stats()["works"], 1)  # 非游戏已从库中删除
        self.assertEqual(self.store.stats()["pending"], 0)
        self.assertEqual(self.store.get_work_sales("RJ01480000"), 30)  # P11 实查销量已入库
        excluded = self.store.conn.execute("SELECT COUNT(*) FROM excluded").fetchone()[0]
        self.assertEqual(excluded, 1)
        progress = self._progress()
        self.assertEqual(progress["phase"], "done")
        self.assertEqual(progress["enriched"], 1)
        self.assertEqual(progress["excluded"], 1)
        self.assertEqual(progress["remaining"], 0)

    def test_run_import_gate_uses_live_sales(self):
        # A：旧作、实查销量 100 < 2000 → 富化前跳过（不发富化请求）
        # B：旧作、实查销量 3000 ≥ 2000 → 富化并保留
        # C：新作（编号 ≥ fresh 边界）→ 直接富化（不看销量）
        # D：编号算新、实查销量不足、且实际发售很旧 → 富化后复核忽略
        self.store.add_pending_many(
            ["RJ01480000", "RJ01480100", "RJ01700100", "RJ01700101"],
            source="backfill:maniax",
        )
        fetcher = FakeApiFetcher(
            {
                api_url("RJ01480100"): [
                    item("RJ01480100", "SLN", regist_date="2025-01-01 00:00:00")
                ],
                api_url("RJ01700100"): [
                    item("RJ01700100", "SLN", regist_date="2026-09-01 00:00:00")
                ],
                api_url("RJ01700101"): [
                    item("RJ01700101", "SLN", regist_date="2026-01-01 00:00:00")
                ],
            },
            sales={"RJ01480000": 100, "RJ01480100": 3000, "RJ01700100": 5, "RJ01700101": 100},
        )
        cfg = make_cfg(self.tmp / "out", min_sales=2000, fresh_days=90)
        result = run_import(fetcher, self.store, cfg, "all", source="numbers")
        self.assertEqual(result["status"], "done")
        self.assertEqual(
            result["session"], {"enriched": 2, "excluded": 0, "skipped": 2, "failed": 0}
        )
        self.assertEqual(self.store.pending_count(), 0)  # A 在富化前已被移出候选
        kept = [
            row[0]
            for row in self.store.conn.execute(
                "SELECT workno FROM works WHERE enriched_at IS NOT NULL ORDER BY workno"
            ).fetchall()
        ]
        self.assertEqual(kept, ["RJ01480100", "RJ01700100"])  # D 已被复核忽略删除
        self.assertIsNone(self.store.get_work_sales("RJ01480000"))  # 被跳过的不写入库
        self.assertEqual(self.store.get_work_sales("RJ01480100"), 3000)
        progress = self._progress()
        self.assertEqual(progress["skipped"], 2)
        self.assertEqual(progress["min_sales"], 2000)
        self.assertEqual(progress["fresh_days"], 90)

    def test_run_import_resumes_with_limit(self):
        worknos = ["RJ01480100", "RJ01480101", "RJ01480102"]
        self.store.add_pending_many(worknos, source="backfill:maniax")
        fetcher = FakeApiFetcher(self._payloads(*worknos), sales={w: 10 for w in worknos})
        first = run_import(fetcher, self.store, self.cfg, "all", limit=1, source="numbers")
        self.assertEqual(first["status"], "paused")
        self.assertEqual(first["session"]["enriched"], 1)
        self.assertEqual(first["remaining"], 2)
        progress = self._progress()
        self.assertFalse(progress["running"])
        self.assertEqual(progress["enriched"], 1)
        self.assertEqual(progress["remaining"], 2)
        second = run_import(fetcher, self.store, self.cfg, "all", limit=1)
        self.assertEqual(second["session"]["enriched"], 1)
        self.assertEqual(second["job"]["enriched"], 2)  # 计数跨会话累计
        # 不传 years：直接沿用现有任务把剩余作品跑完（断点续传）
        third = run_import(fetcher, self.store, self.cfg, None)
        self.assertEqual(third["status"], "done")
        self.assertEqual(third["remaining"], 0)
        self.assertEqual(self.store.stats()["enriched"], 3)
        self.assertEqual(self.store.get_import_job()["enriched"], 3)

    def test_range_conflict_requires_restart(self):
        self.store.add_pending_many(["RJ01480200", "RJ01480201"], source="backfill:maniax")
        fetcher = FakeApiFetcher(
            self._payloads("RJ01480200", "RJ01480201"),
            sales={"RJ01480200": 10, "RJ01480201": 10},
        )
        run_import(fetcher, self.store, self.cfg, "3", limit=1, source="numbers")
        with self.assertRaises(ValueError):
            run_import(fetcher, self.store, self.cfg, "1")
        # --restart 后按新范围重建（已入库作品保留）
        result = run_import(fetcher, self.store, self.cfg, "1", restart=True, source="numbers")
        self.assertIn(result["status"], {"done", "paused"})
        self.assertEqual(self.store.get_import_job()["years"], "1")


class CatalogImportTest(unittest.TestCase):
    """P18：目录遍历候选源（离线仿真：翻页 → 登记 → 预筛 → 富化）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = Store(self.tmp / "t.sqlite")
        self.store.migrate()
        (self.tmp / "out").mkdir()
        self.cfg = make_cfg(self.tmp / "out")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _progress(self) -> dict:
        path = self.tmp / "out" / "import-progress.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_catalog_walk_registers_enriches_and_stops(self):
        a, b = "RJ01720001", "RJ01720002"
        pages = {
            1: catalog_page(a, sales={a: 10}, fillers=99),
            2: catalog_page(b, sales={b: 20}, fillers=99),
            3: catalog_page(fillers=100),
            4: catalog_page(fillers=100),
        }
        fetcher = FakeCatalogFetcher(
            {api_url(a): [item(a)], api_url(b): [item(b)]},
            sales={a: 10, b: 20},
            pages=pages,
        )
        result = run_import(fetcher, self.store, self.cfg, "1")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["session"]["enriched"], 2)
        kept = [
            row[0]
            for row in self.store.conn.execute(
                "SELECT workno FROM works WHERE enriched_at IS NOT NULL ORDER BY workno"
            ).fetchall()
        ]
        self.assertEqual(kept, [a, b])
        job = self.store.get_import_job()
        self.assertEqual(job["source"], "catalog")
        self.assertEqual((job["walk_done"], job["cursor_page"]), (1, 4))
        progress = self._progress()
        self.assertEqual(progress["source"], "catalog")
        self.assertTrue(progress["walk_done"])
        self.assertEqual(progress["cursor_page"], 4)
        self.assertEqual(len(fetcher.text_fetches), 4)  # 翻页 1–4；第 3、4 页全在窗口外 → 停

    def test_walk_stops_when_job_cancelled_externally(self):
        """P22.2：遍历期间任务被外部取消（幽灵检测）→ 立即停止，不再空转。"""
        pages = {
            1: catalog_page("RJ01720001", sales={"RJ01720001": 10}, fillers=99),
            2: catalog_page("RJ01720002", sales={"RJ01720002": 10}, fillers=99),
            3: catalog_page(fillers=100),
        }
        store = self.store

        class CancellingFetcher(FakeCatalogFetcher):
            def get_text(self, url, kind="page", max_bytes=None):
                text = super().get_text(url, kind=kind, max_bytes=max_bytes)
                if len(self.text_fetches) >= 2:  # 第 2 页抓完后模拟外部取消
                    store.delete_import_job()
                return text

        fetcher = CancellingFetcher({}, sales={}, pages=pages)
        result = run_import(fetcher, self.store, self.cfg, "1")
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(self.store.get_import_job())
        self.assertEqual(len(fetcher.text_fetches), 2)  # 第 3 页不再请求

    def test_walk_pauses_on_flag_file(self):
        """P22.3：暂停以标志文件 data/import.pause 为准（后台进程忽略 SIGINT 的兜底）。"""
        pages = {
            1: catalog_page("RJ01720001", sales={"RJ01720001": 10}, fillers=99),
            2: catalog_page("RJ01720002", sales={"RJ01720002": 10}, fillers=99),
            3: catalog_page(fillers=100),
        }
        flag_dir = self.tmp

        class PausingFetcher(FakeCatalogFetcher):
            def get_text(self, url, kind="page", max_bytes=None):
                text = super().get_text(url, kind=kind, max_bytes=max_bytes)
                if len(self.text_fetches) == 1:  # 第 1 页后模拟用户点「暂停」
                    (flag_dir / "import.pause").write_text("pause\n", encoding="utf-8")
                return text

        fetcher = PausingFetcher({}, sales={}, pages=pages)
        result = run_import(fetcher, self.store, self.cfg, "1")
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(len(fetcher.text_fetches), 1)  # 第 2 页不再请求（标志生效）
        self.assertIsNotNone(self.store.get_import_job())  # 暂停保留任务（可续传）

    def test_walk_starts_from_preset_page(self):
        """P23：续深预设 cursor_page → 遍历直接从更深的页开始，并记录覆盖点。"""
        pages = {
            # 填充号用窗口外的小编号（RJ00050000 → 现代系列 50000 < 7 年边界）
            102: catalog_page(fillers=100, filler_start=50_000),
            103: catalog_page(fillers=100, filler_start=50_000),
        }
        fetcher = FakeCatalogFetcher({}, sales={}, pages=pages)
        result = run_import(fetcher, self.store, self.cfg, "7", start_page=101)
        self.assertEqual(result["status"], "done")
        fetched = [url.rsplit("/", 1)[-1] for url in fetcher.text_fetches]
        self.assertEqual(fetched, ["102", "103"])  # 第 1 页不再请求
        coverage = json.loads((self.tmp / "out" / "import-coverage.json").read_text())
        self.assertEqual(coverage["page"], 103)

    def test_save_coverage_keeps_deeper(self):
        """P23：覆盖记录只在更深时覆写；更浅的完成不动它。"""
        deep = {"years": "7", "boundary_old": 73999, "boundary_modern": 356098}
        shallow = {"years": "3", "boundary_old": 471077, "boundary_modern": 1084802}
        save_coverage(self.cfg, deep, 230)
        record = json.loads((self.tmp / "out" / "import-coverage.json").read_text())
        self.assertEqual(record["boundary_old"], 73999)
        self.assertEqual(record["page"], 230)
        self.assertIsNotNone(record["covered_years"])
        save_coverage(self.cfg, shallow, 104)
        record = json.loads((self.tmp / "out" / "import-coverage.json").read_text())
        self.assertEqual(record["boundary_old"], 73999)  # 保留更深的那条

    def test_continue_deeper_start_page(self):
        """P23：续深起始页 = 记录页号 − 3（留余量）；目标不比已覆盖深则报错。"""
        path = self.tmp / "out" / "import-coverage.json"
        path.write_text(
            json.dumps(
                {
                    "boundary_old": 471077,
                    "boundary_modern": 1084802,
                    "page": 104,
                    "covered_years": 3.0,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(cli._continue_deeper_start_page(self.cfg, 7), 101)
        with self.assertRaises(ValueError):
            cli._continue_deeper_start_page(self.cfg, 3)
        # 无页号 → 用边界日期估算（三年前≈第 100 页）
        path.write_text(
            json.dumps(
                {
                    "boundary_old": 471077,
                    "boundary_modern": 1084802,
                    "page": None,
                    "covered_years": 3.0,
                }
            ),
            encoding="utf-8",
        )
        start = cli._continue_deeper_start_page(self.cfg, 7)
        self.assertTrue(90 <= start <= 110)

    def test_enrich_interleaves_with_walk(self):
        """P24：边登记边入库——首批候选的实查发生在后续目录页请求之前。"""
        works = [f"RJ017200{n:02d}" for n in range(1, 7)]
        pages = {
            page: catalog_page(work, sales={work: 10}, fillers=99)
            for page, work in enumerate(works, start=1)
        }
        pages[7] = catalog_page(fillers=100)
        pages[8] = catalog_page(fillers=100)

        class RecordingFetcher(FakeCatalogFetcher):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.events = []

            def get_text(self, url, kind="page", max_bytes=None):
                self.events.append(("page", int(url.rsplit("/", 1)[-1])))
                return super().get_text(url, kind=kind, max_bytes=max_bytes)

            def get_json(self, url):
                self.events.append(("api", url))
                return super().get_json(url)

        payloads = {api_url(work): [item(work)] for work in works}
        fetcher = RecordingFetcher(
            payloads, sales={work: 10 for work in works}, pages=pages
        )
        result = run_import(fetcher, self.store, self.cfg, "1")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["session"]["enriched"], 6)
        first_api = next(i for i, event in enumerate(fetcher.events) if event[0] == "api")
        page6 = next(i for i, event in enumerate(fetcher.events) if event == ("page", 6))
        self.assertLess(first_api, page6)  # 第 6 页抓取前，首批已实查/入库

    def test_catalog_prefilter_skips_without_api_call(self):
        _, modern_1y = boundaries_for_years("1")
        _, skip_modern = boundaries_for_days(90 + 60)
        old = f"RJ{(modern_1y + skip_modern) // 2:08d}"  # 窗口内、但早于预筛边界
        fresh = f"RJ{skip_modern + 5_000:08d}"  # 不小于预筛边界 → 走实查
        pages = {
            1: catalog_page(old, fresh, sales={old: 100, fresh: 5}, fillers=98),
            2: catalog_page(fillers=100),
            3: catalog_page(fillers=100),
        }
        fetcher = FakeCatalogFetcher(
            {api_url(fresh): [item(fresh, regist_date="2026-09-15 00:00:00")]},
            sales={
                old: 100,
                fresh: {
                    "dl_count": 5,
                    "wishlist_count": 1,
                    "work_type": "SLN",
                    "regist_date": "2026-09-15 00:00:00",
                },
            },
            pages=pages,
        )
        cfg = make_cfg(self.tmp / "out", min_sales=2000, fresh_days=90)
        result = run_import(fetcher, self.store, cfg, "1")
        self.assertEqual(result["status"], "done")
        self.assertEqual(
            result["session"], {"enriched": 1, "excluded": 0, "skipped": 1, "failed": 0}
        )
        self.assertNotIn(old, " ".join(fetcher.json_calls))  # 预筛命中：零请求跳过
        self.assertTrue(any(fresh in url for url in fetcher.json_calls))
        kept = [
            row[0]
            for row in self.store.conn.execute(
                "SELECT workno FROM works WHERE enriched_at IS NOT NULL"
            ).fetchall()
        ]
        self.assertEqual(kept, [fresh])

    def test_catalog_walk_resume_after_transient_error(self):
        a, b = "RJ01720011", "RJ01720012"
        pages = {
            1: catalog_page(a, sales={a: 10}, fillers=99),
            2: catalog_page(b, sales={b: 10}, fillers=99),
            3: catalog_page(fillers=100),
        }
        payloads = {api_url(a): [item(a)], api_url(b): [item(b)]}
        sales = {a: 10, b: 10}
        first = FakeCatalogFetcher(payloads, sales=sales, pages=pages, fail_pages={2})
        result1 = run_import(first, self.store, self.cfg, "1")
        self.assertEqual(result1["session"]["enriched"], 1)  # 中断前只处理了第 1 页
        job = self.store.get_import_job()
        self.assertEqual((job["walk_done"], job["cursor_page"]), (0, 1))
        second = FakeCatalogFetcher(payloads, sales=sales, pages=pages)
        result2 = run_import(second, self.store, self.cfg, None)
        self.assertEqual(result2["status"], "done")
        self.assertEqual(result2["session"]["enriched"], 1)  # 只补第 2 页
        self.assertFalse(any(url.endswith("/page/1") for url in second.text_fetches))
        job = self.store.get_import_job()
        self.assertEqual((job["walk_done"], job["cursor_page"]), (1, 3))


if __name__ == "__main__":
    unittest.main()
