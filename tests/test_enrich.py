"""富化模块测试（离线，使用夹具数据）。"""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path

from dlsite_tracker.enrich import PRODUCT_API_URL, enrich_pending, parse_product
from dlsite_tracker.store import Store

ITEM = {
    "workno": "RJ12345678",
    "site_id": "maniax",
    "work_name": "测试作品",
    "maker_id": 123,
    "maker_name": "测试社团",
    "work_category": "doujin",
    "work_type": "SLN",
    "work_type_string": "シミュレーション",
    "age_category": 3,
    "sex_category": 1,
    "price": 1540,
    "official_price": 2200,
    "discount_rate": 30,
    "is_timesale_work": False,
    "timesale_price": 1500,
    "timesale_end_date": "2026-10-15 00:00:00",
    "rate_average_star": 50,
    "rate_count_detail": {"5": 308, "4": 75, "3": 31, "2": 8, "1": 8},
    "rank_day": 1,
    "rank_week": 4,
    "rank_month": 14,
    "regist_date": "2026-06-24 00:00:00",
    "update_date": "2026-07-07 15:41:08",
    "series_name": None,
    "is_bl": False,
    "is_tl": True,
    "work_attributes": "RG123,male,SLN,JPN,SND,MS2,TRI,073,071",
    "genres": [{"id": 71, "name": "断面図"}, {"id": "101", "name": "和風"}],
    "image_thumb": "//img.dlsite.jp/resize/images2/work/doujin/RJ12345000/RJ12345678_img_main_240x240.jpg",
}


class ParseProductTest(unittest.TestCase):
    def test_core_fields(self):
        parsed = parse_product([ITEM], "RJ12345678")
        self.assertIsNotNone(parsed)
        row, genres = parsed  # type: ignore[misc]
        self.assertEqual(row["rating_star"], 5.0)
        self.assertEqual(row["rating_count"], 430)
        self.assertEqual(row["price"], 1540)
        self.assertEqual(row["discount_rate"], 30)
        self.assertEqual(row["is_tl"], 1)
        self.assertEqual(row["is_bl"], 0)
        self.assertTrue(row["image_url"].startswith("https://img.dlsite.jp/"))
        self.assertEqual([genre["id"] for genre in genres], ["71", "101"])
        self.assertEqual(row["options"], "JPN#SND#MS2#TRI")

    def test_picks_requested_workno(self):
        other = dict(ITEM, workno="RJ99999999", work_name="别的作品")
        parsed = parse_product([other, ITEM], "RJ12345678")
        self.assertIsNotNone(parsed)
        row, _ = parsed  # type: ignore[misc]
        self.assertEqual(row["workno"], "RJ12345678")

    def test_options_absent_when_no_attributes(self):
        item = dict(ITEM)
        item.pop("work_attributes")
        parsed = parse_product([item], "RJ12345678")
        self.assertIsNotNone(parsed)
        row, _ = parsed  # type: ignore[misc]
        self.assertNotIn("options", row)

    def test_missing_rating_fields(self):
        item = dict(ITEM)
        item.pop("rate_average_star")
        item.pop("rate_count_detail")
        parsed = parse_product([item], "RJ12345678")
        self.assertIsNotNone(parsed)
        row, _ = parsed  # type: ignore[misc]
        self.assertIsNone(row["rating_star"])
        self.assertIsNone(row["rating_count"])

    def test_empty_payload(self):
        self.assertIsNone(parse_product([], "RJ1"))
        self.assertIsNone(parse_product(None, "RJ1"))


class FakeApiFetcher:
    def __init__(self, payloads, sales=None):
        self.payloads = payloads
        self.sales = sales or {}

    def get_json(self, url):
        if "/product/info/ajax?" in url:
            ids = url.split("product_id=")[1].split("&")[0].split(",")
            return {
                workno: {"dl_count": self.sales[workno], "wishlist_count": 0}
                for workno in ids
                if workno in self.sales
            }
        return self.payloads[url]


class EnrichPendingTest(unittest.TestCase):
    def test_drains_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                store.add_pending_many(["RJ12345678"], source="ranking:maniax:day:game")
                cfg = types.SimpleNamespace(sites=["maniax"], enrich_batch=10, locale="zh_CN")
                url = PRODUCT_API_URL.format(site="maniax", workno="RJ12345678", locale="zh_CN")
                fetcher = FakeApiFetcher({url: [ITEM]}, sales={"RJ12345678": 42})
                result = enrich_pending(fetcher, store, cfg, limit=10)  # type: ignore[arg-type]
                self.assertEqual(result, {"ok": 1, "fail": 0})
                self.assertEqual(store.pending_count(), 0)
                self.assertEqual(store.stats()["enriched"], 1)
                self.assertEqual(store.get_work_sales("RJ12345678"), 42)  # P11 顺带补记
            finally:
                store.close()


    def test_hot_only_skips_cold_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                store.add_pending_many(
                    ["RJ12345678", "RJ00000001"], source="ranking:maniax:day:game"
                )
                store.mark_hot("maniax", ["RJ12345678"])
                cfg = types.SimpleNamespace(
                    sites=["maniax"], enrich_batch=10, hot_window_days=7, locale="zh_CN"
                )
                url = PRODUCT_API_URL.format(site="maniax", workno="RJ12345678", locale="zh_CN")
                fetcher = FakeApiFetcher({url: [ITEM]}, sales={"RJ12345678": 42})
                result = enrich_pending(fetcher, store, cfg, limit=10, hot_only=True)  # type: ignore[arg-type]
                self.assertEqual(result, {"ok": 1, "fail": 0})
                # 冷门作品仍留在队列
                self.assertEqual([row[0] for row in store.pending_batch(10)], ["RJ00000001"])
            finally:
                store.close()

    def test_observer_reports_every_50(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                worknos = [f"RJ{i:08d}" for i in range(1, 51)]
                store.add_pending_many(worknos, source="ranking:maniax:day:game")
                cfg = types.SimpleNamespace(sites=["maniax"], enrich_batch=100, locale="zh_CN")
                payloads = {}
                sales = {}
                for workno in worknos:
                    url = PRODUCT_API_URL.format(site="maniax", workno=workno, locale="zh_CN")
                    payloads[url] = [dict(ITEM, workno=workno)]
                    sales[workno] = 10
                fetcher = FakeApiFetcher(payloads, sales=sales)
                seen: list = []
                result = enrich_pending(
                    fetcher,
                    store,
                    cfg,  # type: ignore[arg-type]
                    limit=100,
                    observer=lambda order, total: seen.append((order, total)),
                )
                self.assertEqual(result, {"ok": 50, "fail": 0})
                self.assertEqual(seen, [(50, 50)])
            finally:
                store.close()

    def test_hot_only_skips_enriched_works(self):
        """P20：热榜富化只收未入库新作（已富化不再重复刷新）。"""
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                store.add_pending_many(["RJ12345678"], source="ranking:maniax:day:game")
                store.mark_hot("maniax", ["RJ12345678"])
                store.upsert_work(
                    {"workno": "RJ12345678", "site": "maniax", "product_name": "已入库"}
                )
                cfg = types.SimpleNamespace(
                    sites=["maniax"], enrich_batch=10, hot_window_days=7, locale="zh_CN"
                )
                fetcher = FakeApiFetcher({}, sales={})
                result = enrich_pending(fetcher, store, cfg, limit=10, hot_only=True)  # type: ignore[arg-type]
                self.assertEqual(result, {"ok": 0, "fail": 0})
                self.assertEqual(store.pending_count(), 1)
            finally:
                store.close()

    def test_refresh_prefix_processes_only_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                store.add_pending_many(
                    ["RJ12345678", "RJ00000002"], source="sitemap:maniax"
                )
                store.upsert_work({"workno": "RJ12345678", "site": "maniax", "product_name": "旧"})
                store.enqueue_refresh("refresh:zh_CN")
                cfg = types.SimpleNamespace(sites=["maniax"], enrich_batch=10, locale="zh_CN")
                url = PRODUCT_API_URL.format(site="maniax", workno="RJ12345678", locale="zh_CN")
                fetcher = FakeApiFetcher({url: [ITEM]}, sales={"RJ12345678": 42})
                result = enrich_pending(  # type: ignore[arg-type]
                    fetcher, store, cfg, limit=10, source_prefix="refresh:"
                )
                self.assertEqual(result, {"ok": 1, "fail": 0})
                # 普通 sitemap 队列项不受影响
                self.assertEqual([row[0] for row in store.pending_batch(10)], ["RJ00000002"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
