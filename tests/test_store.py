"""存储模块测试（离线）。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from dlsite_tracker.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "t.sqlite")
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_upsert_work_and_genres(self):
        self.store.upsert_work({"workno": "RJ1", "site": "maniax", "product_name": "A", "price": 100})
        self.store.replace_genres("RJ1", [{"id": "71", "name": "断面図"}])
        stats = self.store.stats()
        self.assertEqual(stats["works"], 1)
        self.assertEqual(stats["enriched"], 1)
        self.assertEqual(stats["genres"], 1)

        self.store.upsert_work({"workno": "RJ1", "site": "maniax", "price": 200})
        self.assertEqual(self.store.stats()["works"], 1)
        row = self.store.conn.execute("SELECT price, product_name FROM works WHERE workno='RJ1'").fetchone()
        self.assertEqual(row[0], 200)
        self.assertEqual(row[1], "A")  # 未提供的字段保持不变

    def test_sales_stub_and_history(self):
        self.store.record_sales_many("maniax", {"RJ2": 123}, source="ranking:day:game")
        stats = self.store.stats()
        self.assertEqual(stats["works"], 0)  # P18：销量占位行不计入「作品总数」
        self.assertEqual(stats["rows"], 1)
        self.assertEqual(stats["with_sales"], 1)
        history = self.store.conn.execute(
            "SELECT sales, source FROM sales_history WHERE workno='RJ2'"
        ).fetchone()
        self.assertEqual(history[0], 123)
        self.assertEqual(history[1], "ranking:day:game")

        # 后续富化不应清掉销量
        self.store.upsert_work({"workno": "RJ2", "site": "maniax", "product_name": "B"})
        row = self.store.conn.execute("SELECT sales, product_name FROM works WHERE workno='RJ2'").fetchone()
        self.assertEqual(row[0], 123)
        self.assertEqual(row[1], "B")
        self.assertEqual(self.store.stats()["works"], 1)

    def test_options_roundtrip(self):
        self.store.upsert_work({"workno": "RJ9", "site": "maniax", "product_name": "O"})
        self.store.record_sales_many(
            "maniax", {}, source="info-ajax", options={"RJ9": "JPN#SND#MS2#MV2"}
        )
        row = self.store.conn.execute(
            "SELECT options FROM works WHERE workno='RJ9'"
        ).fetchone()
        self.assertEqual(row[0], "JPN#SND#MS2#MV2")
        # 后续富化不应清掉 options
        self.store.upsert_work({"workno": "RJ9", "site": "maniax", "price": 100})
        row = self.store.conn.execute(
            "SELECT options FROM works WHERE workno='RJ9'"
        ).fetchone()
        self.assertEqual(row[0], "JPN#SND#MS2#MV2")

    def test_genre_ranks_snapshot_replace_and_info(self):
        """P19：分类名次快照按分类整批替换；名次/分类元信息可回读。"""
        self.store.replace_genre_ranks("016", {"RJ01000200": 1, "RJ01000201": 2})
        self.assertEqual(self.store.genre_positions("RJ01000200"), {"016": 1})
        self.store.save_genre_info("016", "ファンタジー", 7190)
        row = self.store.conn.execute(
            "SELECT name, count FROM genre_info WHERE genre_id='016'"
        ).fetchone()
        self.assertEqual((row[0], row[1]), ("ファンタジー", 7190))
        # 整批替换：掉出前 N 的作品不再保留旧名次
        self.store.replace_genre_ranks("016", {"RJ01000201": 1})
        self.assertEqual(self.store.genre_positions("RJ01000200"), {})
        self.assertEqual(self.store.genre_positions("RJ01000201"), {"016": 1})

    def test_remove_genre(self):
        """P34：移除分类——只删该分类的名次与元信息，其他分类与作品不受影响。"""
        self.store.save_genre_info("016", "奇幻", 7190)
        self.store.replace_genre_ranks("016", {"W1": 1, "W2": 320})
        self.store.save_genre_info("526", "沉迷快乐", 1249)
        ranks, info = self.store.remove_genre("016")
        self.assertEqual((ranks, info), (2, 1))
        self.assertEqual(self.store.genre_depth("016"), 0)
        self.assertEqual([item["id"] for item in self.store.genre_summaries()], ["526"])
        # 重复移除：无变更
        self.assertEqual(self.store.remove_genre("016"), (0, 0))

    def test_genre_ranks_range_replace_keeps_deep(self):
        """P19.1：范围替换——每日刷新不抹掉更深的「载入更多」名次。"""
        self.store.replace_genre_ranks("526", {"A1": 1, "B1": 250, "C1": 300})
        # 每日 1..2 页：只替换 [1, 200]
        self.store.replace_genre_ranks("526", {"D1": 5}, start=1, end=200)
        rows = dict(
            self.store.conn.execute(
                "SELECT workno, position FROM genre_ranks WHERE genre_id='526'"
            ).fetchall()
        )
        self.assertEqual(rows, {"B1": 250, "C1": 300, "D1": 5})
        # 续抓一页（201..300）：范围内整段替换——B1/C1 掉出该范围被清
        self.store.replace_genre_ranks("526", {"E1": 210}, start=201, end=300)
        rows = dict(
            self.store.conn.execute(
                "SELECT workno, position FROM genre_ranks WHERE genre_id='526'"
            ).fetchall()
        )
        self.assertEqual(rows, {"D1": 5, "E1": 210})
        # 自然末页（end=None）：整段清理 start 之后
        self.store.replace_genre_ranks("526", {"B1": 250}, start=201, end=None)
        rows = dict(
            self.store.conn.execute(
                "SELECT workno, position FROM genre_ranks WHERE genre_id='526'"
            ).fetchall()
        )
        self.assertEqual(rows, {"B1": 250, "D1": 5})

    def test_genre_ranks_range_replace_moves_work(self):
        """P20 修复：作品名次从范围外移入（页面每天变化）不应触发主键冲突。"""
        self.store.replace_genre_ranks("526", {"A1": 150, "B1": 3})
        self.store.replace_genre_ranks("526", {"A1": 50}, start=1, end=100)
        rows = dict(
            self.store.conn.execute(
                "SELECT workno, position FROM genre_ranks WHERE genre_id='526'"
            ).fetchall()
        )
        self.assertEqual(rows, {"A1": 50})

    def test_genre_catalog_summaries_and_depth(self):
        self.store.save_genre_catalog([("016", "ファンタジー"), ("526", "快楽堕ち")])
        self.assertEqual(
            self.store.list_genre_catalog(),
            [{"id": "016", "name": "ファンタジー"}, {"id": "526", "name": "快楽堕ち"}],
        )
        # 同 id 更新名称不新增行
        self.store.save_genre_catalog([("016", "奇幻")])
        catalog = self.store.list_genre_catalog()
        self.assertEqual(len(catalog), 2)
        self.assertEqual(catalog[0]["name"], "奇幻")
        self.store.replace_genre_ranks("016", {"W1": 1, "W2": 320})
        self.store.save_genre_info("016", "奇幻", 7190)
        self.assertEqual(self.store.genre_depth("016"), 320)
        self.assertEqual(self.store.genre_depth("999"), 0)
        summary = self.store.genre_summaries()
        self.assertEqual(summary[0]["id"], "016")
        self.assertEqual((summary[0]["count"], summary[0]["depth"]), (7190, 320))
        self.store.record_ranks("maniax", "trend", {"W1": 1, "W2": 900})
        self.assertEqual(self.store.rank_trend_depth(), 900)
        row = self.store.conn.execute(
            "SELECT rank_trend_current FROM works WHERE workno='W2'"
        ).fetchone()
        self.assertEqual(row[0], 900)
        # P20：深度收缩时清理越界旧名次
        self.assertEqual(self.store.clear_rank_trend_beyond(500), 1)
        row = self.store.conn.execute(
            "SELECT rank_trend_current FROM works WHERE workno='W2'"
        ).fetchone()
        self.assertIsNone(row[0])
        self.assertEqual(self.store.rank_trend_depth(), 1)

    def test_pending_exact_source_skips_enriched(self):
        self.store.add_pending_many(["P1", "P2"], source="genre-rank:maniax:526")
        self.store.add_pending_many(["P3"], source="genre-rank:maniax:5260")
        self.store.upsert_work({"workno": "P2", "site": "maniax", "product_name": "B"})
        batch = self.store.pending_batch_exact_source(10, "genre-rank:maniax:526")
        self.assertEqual([row[0] for row in batch], ["P1"])
        batch_all = self.store.pending_batch_exact_source(
            10, "genre-rank:maniax:526", skip_enriched=False
        )
        self.assertEqual(sorted(row[0] for row in batch_all), ["P1", "P2"])

    def test_pending_batch_hot_skip_enriched(self):
        """P20：热榜富化只收未入库新作。"""
        self.store.add_pending_many(["H1", "H2"], source="trend:maniax")
        self.store.mark_hot("maniax", ["H1", "H2"])
        self.store.upsert_work({"workno": "H1", "site": "maniax", "product_name": "A"})
        batch = self.store.pending_batch_hot(10, window_days=7, skip_enriched=True)
        self.assertEqual([row[0] for row in batch], ["H2"])
        batch_all = self.store.pending_batch_hot(10, window_days=7)
        self.assertEqual([row[0] for row in batch_all], ["H2", "H1"])

    def test_works_for_sales_sync_hot(self):
        """P20：销量只维持在榜作品，且每件每天最多一次。"""
        self.store.upsert_work({"workno": "S1", "site": "maniax", "product_name": "A"})
        self.store.upsert_work({"workno": "S2", "site": "maniax", "product_name": "B"})
        self.store.record_sales_many("maniax", {"S1": 10}, source="test")
        self.store.mark_hot("maniax", ["S1"])
        # S1 刚同步过（<1 天）→ 跳过；S2 未上榜 → 永不入选
        self.assertEqual(self.store.works_for_sales_sync_hot(7), [])
        # 放开最小间隔 → 只剩在榜的 S1
        self.assertEqual(self.store.works_for_sales_sync_hot(7, min_age_days=0), ["S1"])

    def test_save_genre_info_prefers_catalog_chinese_name(self):
        """P20.1：分类目录已有中文名时，genre_info 展示名以中文为准。"""
        self.store.save_genre_catalog([("016", "奇幻")])
        self.store.save_genre_info("016", "ファンタジー", 7190)
        row = self.store.conn.execute(
            "SELECT name FROM genre_info WHERE genre_id='016'"
        ).fetchone()
        self.assertEqual(row[0], "奇幻")
        # 无目录条目时保留原样
        self.store.save_genre_info("999", "テスト", 1)
        row = self.store.conn.execute(
            "SELECT name FROM genre_info WHERE genre_id='999'"
        ).fetchone()
        self.assertEqual(row[0], "テスト")

    def test_record_ranks(self):
        self.store.record_ranks("maniax", "day", {"RJ5": 1, "RJ6": 3})
        self.store.record_ranks("maniax", "week", {"RJ5": 2})
        self.store.record_ranks("maniax", "month", {"RJ5": 11})
        self.store.record_ranks("maniax", "year", {"RJ5": 1})  # 未知 term 跳过
        row = self.store.conn.execute(
            "SELECT rank_day_current, rank_week_current, rank_month_current, "
            "rank_day, rank_current_seen_at FROM works WHERE workno='RJ5'"
        ).fetchone()
        self.assertEqual((row[0], row[1], row[2]), (1, 2, 11))
        self.assertIsNone(row[3])  # 历史快照列不受影响
        self.assertRegex(row[4], r"^\d{4}-\d{2}-\d{2}T")
        row6 = self.store.conn.execute(
            "SELECT rank_day_current FROM works WHERE workno='RJ6'"
        ).fetchone()
        self.assertEqual(row6[0], 3)

        # 后续富化不应清掉当前名次
        self.store.upsert_work({"workno": "RJ5", "site": "maniax", "product_name": "C"})
        row = self.store.conn.execute(
            "SELECT rank_day_current FROM works WHERE workno='RJ5'"
        ).fetchone()
        self.assertEqual(row[0], 1)

    def test_hot_marks_and_pending_batch(self):
        self.store.add_pending_many(["RJ7", "RJ8"], source="sitemap:maniax")
        self.store.mark_hot("maniax", ["RJ7"])
        hot = self.store.pending_batch_hot(10, window_days=7)
        self.assertEqual([row[0] for row in hot], ["RJ7"])
        self.assertEqual({row[0] for row in self.store.pending_batch(10)}, {"RJ7", "RJ8"})

        # 新作品优先于已富化作品（均已过窗口检查）
        self.store.mark_hot("maniax", ["RJ8"])
        self.store.upsert_work({"workno": "RJ8", "site": "maniax", "product_name": "D"})
        hot = self.store.pending_batch_hot(10, window_days=7)
        self.assertEqual([row[0] for row in hot], ["RJ7", "RJ8"])

        # 窗口外的旧标记不再返回
        with self.store.conn:
            self.store.conn.execute(
                "UPDATE works SET hot_seen_at='2000-01-01T00:00:00+09:00'"
            )
        self.assertEqual(self.store.pending_batch_hot(10, window_days=7), [])

    def test_enqueue_refresh_and_source_batch(self):
        self.store.upsert_work({"workno": "RJ9", "site": "maniax", "product_name": "E"})
        self.store.upsert_work({"workno": "RJ10", "site": "maniax", "product_name": "F"})
        self.store.record_sales_many("maniax", {"RJ11": 5}, source="ranking:maniax:day:game")
        added = self.store.enqueue_refresh("refresh:zh_CN")
        self.assertEqual(added, 2)
        batch = self.store.pending_batch_by_source(10, "refresh:")
        self.assertEqual([row[0] for row in batch], ["RJ10", "RJ9"])  # 按作品号排序
        # 幂等：重复登记不产生重复行
        self.store.enqueue_refresh("refresh:zh_CN")
        self.assertEqual(len(self.store.pending_batch_by_source(10, "refresh:")), 2)

    def test_excluded_list_and_delete(self):
        self.store.upsert_work(
            {"workno": "RJ20", "site": "maniax", "product_name": "漫画", "work_type": "MNG"}
        )
        self.store.upsert_work(
            {"workno": "RJ21", "site": "maniax", "product_name": "游戏", "work_type": "RPG"}
        )
        self.store.add_pending_many(["RJ20", "RJ21"], source="sitemap:maniax")
        self.assertEqual(self.store.list_non_games(["RPG", "SLN"]), [("RJ20", "MNG")])
        self.store.add_excluded("RJ20", "MNG")
        self.assertEqual([row[0] for row in self.store.pending_batch(10)], ["RJ21"])
        self.store.delete_work("RJ20")
        stats = self.store.stats()
        self.assertEqual(stats["works"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_sales_deltas_window(self):
        now = datetime.now().astimezone()
        old = (now - timedelta(days=3)).isoformat(timespec="seconds")
        fresh = now.isoformat(timespec="seconds")
        for when, sales in ((old, 100), (fresh, 340)):
            self.store.conn.execute(
                "INSERT OR REPLACE INTO sales_history(workno,sales,seen_at,source) "
                "VALUES('RJ1',?,?,'t')",
                (sales, when),
            )
        self.store.conn.commit()

        deltas = self.store.sales_deltas(7)
        self.assertEqual(deltas["RJ1"], {"delta": 240, "days": 3})

    def test_sales_deltas_skips_insufficient_history(self):
        now = datetime.now().astimezone()
        stale = (now - timedelta(days=30)).isoformat(timespec="seconds")
        fresh = now.isoformat(timespec="seconds")
        rows = (
            ("RJ2", 10, stale, "t"),  # 窗口外
            ("RJ2", 20, fresh, "t"),  # 窗口内仅一条 → 跳过
            ("RJ3", 5, fresh, "t"),   # 单条 → 跳过
            ("RJ4", 5, fresh, "s1"),  # 同一时刻多来源 → 跨度为零 → 跳过
            ("RJ4", 5, fresh, "s2"),
        )
        for workno, sales, when, source in rows:
            self.store.conn.execute(
                "INSERT OR REPLACE INTO sales_history(workno,sales,seen_at,source) "
                "VALUES(?,?,?,?)",
                (workno, sales, when, source),
            )
        self.store.conn.commit()

        self.assertEqual(self.store.sales_deltas(7), {})

    def test_import_job_lifecycle(self):
        self.assertIsNone(self.store.get_import_job())
        self.store.save_import_job(
            years="1", phase="enrich", boundary_old=100, boundary_modern=200,
            fresh_old=110, fresh_modern=210, min_sales=2000, fresh_days=90,
        )
        job = self.store.get_import_job()
        self.assertEqual(
            (job["years"], job["phase"], job["enriched"], job["min_sales"], job["fresh_days"]),
            ("1", "enrich", 0, 2000, 90),
        )
        self.store.update_import_job(phase="done", enriched=5, skipped=2, note="已完成", unknown="x")
        job = self.store.get_import_job()
        self.assertEqual(
            (job["phase"], job["enriched"], job["skipped"], job["note"]),
            ("done", 5, 2, "已完成"),
        )
        self.store.save_import_job(
            years="3", phase="enrich", boundary_old=0, boundary_modern=50,
            fresh_old=0, fresh_modern=50, min_sales=0, fresh_days=0,
        )
        job = self.store.get_import_job()
        self.assertEqual((job["years"], job["enriched"], job["skipped"]), ("3", 0, 0))  # 重建清零
        self.store.delete_import_job()
        self.assertIsNone(self.store.get_import_job())

    def test_import_candidates_boundary_and_order(self):
        self.store.add_pending_many(
            ["RJ420000", "RJ441000", "RJ01480000", "RJ01500000", "RJ01700000", "RJ01490000"],
            source="backfill:maniax",
        )
        self.store.add_excluded("RJ01500000", "MNG")  # 已排除的非游戏不再入选
        self.store.record_sales_many("maniax", {"RJ01490000": 900}, source="ranking:maniax:day:game")
        picked = self.store.import_candidates(10, 440000, 1480000)
        # 销量已知优先 → 编号新到旧（现代系列在前）；旧系列低于边界的不入选
        self.assertEqual([row[0] for row in picked], ["RJ01490000", "RJ01700000", "RJ01480000", "RJ441000"])
        self.assertEqual(self.store.import_remaining(440000, 1480000), 4)
        # 「新作窗」计数（供试算展示）
        self.assertEqual(self.store.import_fresh_remaining(441001, 1700000), 1)
        self.assertEqual(self.store.get_work_sales("RJ01490000"), 900)
        self.assertIsNone(self.store.get_work_sales("RJ01480000"))

    def test_sales_sync_selection_and_wishlist(self):
        self.store.upsert_work({"workno": "RJ30", "site": "maniax", "product_name": "A"})
        self.store.upsert_work({"workno": "RJ31", "site": "maniax", "product_name": "B"})
        self.store.record_sales_many("maniax", {"RJ31": 10}, source="ranking:maniax:day:game")
        self.assertEqual(self.store.works_for_sales_sync(), ["RJ30"])  # 只补缺销量的
        self.store.record_sales_many(
            "maniax", {"RJ30": 20}, source="info-ajax", wishlist={"RJ30": 7}
        )
        row = self.store.conn.execute(
            "SELECT sales, wishlist_count FROM works WHERE workno='RJ30'"
        ).fetchone()
        self.assertEqual((row[0], row[1]), (20, 7))
        self.assertEqual(self.store.works_for_sales_sync(), [])  # 都同步过
        # stale_days=0（--all）包含全部；stale_days=2 因刚同步过不会命中
        self.assertEqual(self.store.works_for_sales_sync(stale_days=0), ["RJ30", "RJ31"])
        self.assertEqual(self.store.works_for_sales_sync(stale_days=2), [])

    def test_pending_lifecycle(self):
        self.store.add_pending_many(["RJ3", "RJ4"], source="sitemap:maniax")
        self.assertEqual(self.store.pending_count(), 2)
        batch = self.store.pending_batch(1)
        self.assertEqual(len(batch), 1)
        workno, source, attempts = batch[0]
        self.assertEqual(attempts, 0)
        self.store.finish_pending(workno)
        self.assertEqual(self.store.pending_count(), 1)

        self.store.fail_pending("RJ4")
        self.store.fail_pending("RJ4")
        self.assertEqual(self.store.pending_count(), 1)
        self.store.fail_pending("RJ4")  # 第 3 次失败后移除
        self.assertEqual(self.store.pending_count(), 0)

    def test_meta_and_runs(self):
        self.store.set_meta("last_seen_workno:maniax", "RJ9")
        self.assertEqual(self.store.get_meta("last_seen_workno:maniax"), "RJ9")
        run_id = self.store.start_run("update")
        self.store.finish_run(run_id, True, "ok")
        stats = self.store.stats()
        self.assertEqual(stats["last_seen"], {"maniax": "RJ9"})
        self.assertEqual(stats["runs"][0][3], "update")

    def test_import_job_source_walk_columns_and_rebuild_reset(self):
        """P18：任务携带来源与遍历游标；重建（换来源）时游标清零。"""
        self.store.save_import_job(
            years="3", phase="enrich", boundary_old=100, boundary_modern=200,
            fresh_old=110, fresh_modern=210, min_sales=0, fresh_days=0, source="catalog",
        )
        job = self.store.get_import_job()
        self.assertEqual(job["source"], "catalog")
        self.assertEqual((job["walk_done"], job["cursor_page"]), (0, 0))
        self.store.update_import_job(cursor_page=7, walk_done=1)
        job = self.store.get_import_job()
        self.assertEqual((job["walk_done"], job["cursor_page"]), (1, 7))
        self.store.save_import_job(
            years="3", phase="enrich", boundary_old=100, boundary_modern=200,
            fresh_old=110, fresh_modern=210, min_sales=0, fresh_days=0, source="numbers",
        )
        job = self.store.get_import_job()
        self.assertEqual((job["source"], job["walk_done"], job["cursor_page"]), ("numbers", 0, 0))

    def test_import_job_migration_adds_catalog_columns(self):
        """旧库（无 P18 列）经 migrate 自动补列，且能写入目录任务。"""
        import sqlite3 as _sqlite3
        path = Path(self._tmp.name) / "old.sqlite"
        conn = _sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE import_job ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), years TEXT NOT NULL, "
            "phase TEXT NOT NULL, boundary_old INTEGER NOT NULL DEFAULT 0, "
            "boundary_modern INTEGER NOT NULL DEFAULT 0, "
            "fresh_old INTEGER NOT NULL DEFAULT 0, fresh_modern INTEGER NOT NULL DEFAULT 0, "
            "min_sales INTEGER NOT NULL DEFAULT 0, fresh_days INTEGER NOT NULL DEFAULT 0, "
            "started_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "enriched INTEGER NOT NULL DEFAULT 0, excluded INTEGER NOT NULL DEFAULT 0, "
            "skipped INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, "
            "note TEXT NOT NULL DEFAULT '')"
        )
        conn.commit()
        conn.close()
        store = Store(path)
        store.migrate()
        try:
            columns = {row[1] for row in store.conn.execute("PRAGMA table_info(import_job)")}
            self.assertLessEqual({"source", "walk_done", "cursor_page"}, columns)
            store.save_import_job(
                years="1", phase="enrich", boundary_old=0, boundary_modern=0,
                fresh_old=0, fresh_modern=0, min_sales=0, fresh_days=0, source="catalog",
            )
            job = store.get_import_job()
            self.assertEqual((job["source"], job["walk_done"]), ("catalog", 0))
        finally:
            store.close()

    def test_catalog_pending_filters_and_known_filter(self):
        """P18：目录登记不改写 refresh 队列；候选按 catalog 前缀过滤；filter_known 生效。"""
        self.store.upsert_work({"workno": "RJ01000100", "site": "maniax", "product_name": "A"})
        self.store.add_catalog_pending(["RJ01000100", "RJ01000101"], source="catalog:maniax:game")
        self.store.enqueue_refresh("refresh:zh_CN")  # RJ01000100 改标为刷新队列
        self.store.add_catalog_pending(["RJ01000100", "RJ01000101"], source="catalog:maniax:game")
        sources = dict(self.store.conn.execute("SELECT workno, source FROM pending").fetchall())
        self.assertEqual(sources["RJ01000100"], "refresh:zh_CN")  # refresh 不被目录登记覆盖
        self.assertEqual(sources["RJ01000101"], "catalog:maniax:game")
        self.store.add_pending_many(["RJ01000102"], source="sitemap:maniax")
        candidates = self.store.import_candidates(10, 0, 0, source_prefix="catalog:")
        self.assertEqual([row[0] for row in candidates], ["RJ01000101"])
        self.assertEqual(self.store.import_remaining(0, 0, source_prefix="catalog:"), 1)
        self.assertEqual(self.store.import_remaining(0, 0), 3)
        self.store.add_excluded("RJ01000103", "MNG")
        self.assertEqual(
            self.store.filter_known_worknos(
                ["RJ01000100", "RJ01000101", "RJ01000103", "RJ01000104"]
            ),
            ["RJ01000101", "RJ01000104"],
        )


if __name__ == "__main__":
    unittest.main()
