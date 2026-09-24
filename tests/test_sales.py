"""销量批查测试（离线）。"""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from dlsite_tracker.sales import (
    BATCH_SIZE,
    fetch_sales,
    parse_options,
    parse_product_info,
    parse_sales,
    save_sales,
    sync_sales,
)
from dlsite_tracker.store import Store
from dlsite_tracker.cli import cmd_sales


class FakeApiFetcher:
    """按 URL 里的 product_id 列表返回销量；sales: workno → (dl_count, wishlist)。"""

    def __init__(self, sales=None, options=None, ratings=None):
        self.sales = sales or {}
        self.options = options or {}
        self.ratings = ratings or {}
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        ids = url.split("product_id=")[1].split("&")[0].split(",")
        result = {}
        for workno in ids:
            item = {}
            if workno in self.sales:
                dl, wishlist = self.sales[workno]
                item.update({"dl_count": dl, "wishlist_count": wishlist})
            if workno in self.options:
                item["options"] = self.options[workno]
            if workno in self.ratings:
                item.update(self.ratings[workno])
            if item:
                result[workno] = item
        return result

    def summary(self):
        return f"{len(self.calls)} requests"


class ParseSalesTest(unittest.TestCase):
    def test_parse(self):
        values = parse_sales(
            {
                "RJ1": {"dl_count": 10, "wishlist_count": 3},
                "RJ2": {"dl_count": 5},
                "RJ3": {"other": 1},
                "RJ4": None,
            }
        )
        self.assertEqual(values["RJ1"], (10, 3))
        self.assertEqual(values["RJ2"], (5, None))
        self.assertNotIn("RJ3", values)
        self.assertNotIn("RJ4", values)
        self.assertEqual(parse_sales(None), {})

    def test_chunking(self):
        ids = [f"RJ{i:06d}" for i in range(BATCH_SIZE + 3)]
        fetcher = FakeApiFetcher({workno: (7, 1) for workno in ids})
        values = fetch_sales(fetcher, "maniax", ids)
        self.assertEqual(len(values), BATCH_SIZE + 3)
        self.assertEqual(len(fetcher.calls), 2)  # 40 + 3 → 分两片
        self.assertIn(f"product_id={ids[0]},{ids[1]}", fetcher.calls[0])


class ParseOptionsTest(unittest.TestCase):
    def test_normalize_hash(self):
        self.assertEqual(parse_options("SND#MS2#JPN#TRI"), "SND#MS2#JPN#TRI")

    def test_normalize_work_attributes(self):
        raw = "RG64737,adl,male,SLN,JPN,SND,MS2,MV2,REV,TRI,302,155,073"
        self.assertEqual(parse_options(raw), "JPN#SND#MS2#MV2#REV#TRI")

    def test_unknown_and_duplicates(self):
        self.assertEqual(parse_options("XPTO#MS2#MS2#073"), "MS2")
        self.assertEqual(parse_options(None), "")

    def test_parse_product_info_carries_options(self):
        infos = parse_product_info(
            {"RJ1": {"dl_count": 1, "options": "AIP#SND#MS2"}, "RJ2": {"options": None}}
        )
        self.assertEqual(infos["RJ1"]["options"], "AIP#SND#MS2")
        self.assertEqual(infos["RJ2"]["options"], "")

    def test_parse_product_info_carries_precise_rating(self):
        infos = parse_product_info({
            "RJ1": {"rate_average_2dp": 4.83, "rate_count": 29},
            "RJ2": {"rate_average_2dp": 5.5, "rate_count": None},
            "RJ3": {"rate_average_2dp": "4.70"},
            "RJ4": {"rate_average_2dp": 0, "rate_count": 0},
        })
        self.assertEqual(infos["RJ1"]["rating_precise"], 4.83)
        self.assertEqual(infos["RJ1"]["rating_count"], 29)
        self.assertIsNone(infos["RJ2"]["rating_precise"])
        self.assertEqual(infos["RJ3"]["rating_precise"], 4.7)
        self.assertIsNone(infos["RJ4"]["rating_precise"])


class SalesSyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "t.sqlite")
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_save_and_sync(self):
        save_sales(
            self.store, "maniax", {"RJ1": (100, 9)}, options={"RJ1": "JPN#SND#MS2"}
        )
        row = self.store.conn.execute(
            "SELECT sales, wishlist_count, options FROM works WHERE workno='RJ1'"
        ).fetchone()
        self.assertEqual((row[0], row[1]), (100, 9))
        self.assertEqual(row[2], "JPN#SND#MS2")
        source = self.store.conn.execute(
            "SELECT source FROM sales_history WHERE workno='RJ1'"
        ).fetchone()[0]
        self.assertEqual(source, "info-ajax")

        fetcher = FakeApiFetcher({"RJ1": (120, 10)}, options={"RJ1": "SND#MS2#MV2"})
        cfg = types.SimpleNamespace(sites=["maniax"])
        result = sync_sales(fetcher, self.store, cfg, ["RJ1", "RJ9"])
        self.assertEqual(result, {"queried": 2, "updated": 1, "missing": 1})
        self.assertEqual(self.store.get_work_sales("RJ1"), 120)
        options = self.store.conn.execute(
            "SELECT options FROM works WHERE workno='RJ1'"
        ).fetchone()[0]
        self.assertEqual(options, "SND#MS2#MV2")

    def test_precise_rating_survives_later_enrich_and_marks_missing(self):
        self.store.upsert_work({"workno": "RJ1", "site": "maniax", "rating_star": 5.0})
        self.store.upsert_work({"workno": "RJ2", "site": "maniax", "rating_star": 4.5})
        self.assertEqual(self.store.works_missing_precise_rating(), ["RJ1", "RJ2"])
        fetcher = FakeApiFetcher(ratings={
            "RJ1": {"rate_average_2dp": 4.83, "rate_count": 31},
            "RJ2": {"rate_average_2dp": None, "rate_count": 0},
        })
        sync_sales(fetcher, self.store, types.SimpleNamespace(sites=["maniax"]), ["RJ1", "RJ2"])
        self.assertEqual(self.store.works_missing_precise_rating(), [])
        self.store.conn.execute(
            "UPDATE works SET rating_precise_checked_at='2020-01-01T00:00:00+00:00' "
            "WHERE workno='RJ2'"
        )
        self.store.conn.commit()
        self.assertEqual(self.store.works_missing_precise_rating(), ["RJ2"])
        row = self.store.conn.execute(
            "SELECT rating_star,rating_precise,rating_count,rating_precise_checked_at "
            "FROM works WHERE workno='RJ1'"
        ).fetchone()
        self.assertEqual((row[0], row[1], row[2]), (5.0, 4.83, 31))
        self.assertIsNotNone(row[3])
        self.store.upsert_work({"workno": "RJ1", "site": "maniax", "price": 100})
        self.assertEqual(self.store.conn.execute(
            "SELECT rating_precise FROM works WHERE workno='RJ1'"
        ).fetchone()[0], 4.83)

    def test_normal_sales_command_backfills_existing_precise_ratings_once(self):
        self.store.upsert_work({"workno": "RJ1", "site": "maniax", "rating_star": 5.0})
        self.store.upsert_work({"workno": "RJ2", "site": "maniax", "rating_star": 4.5})
        fetcher = FakeApiFetcher(ratings={
            "RJ1": {"rate_average_2dp": 4.83, "rate_count": 31},
            "RJ2": {"rate_average_2dp": 4.37, "rate_count": 9},
        })
        cfg = types.SimpleNamespace(
            data_dir=Path(self._tmp.name), out_dir=Path(self._tmp.name) / "out", sites=["maniax"]
        )
        args = types.SimpleNamespace(
            hot_days=7, min_age_days=None, limit=None, all=False, stale_days=None
        )
        with mock.patch("dlsite_tracker.cli._fetcher", return_value=fetcher), \
             mock.patch("dlsite_tracker.cli._open_store", side_effect=lambda _: Store(self.store.path)):
            self.assertEqual(cmd_sales(cfg, args), 0)
            self.assertEqual(cmd_sales(cfg, args), 0)
        self.assertEqual(len(fetcher.calls), 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT rating_precise FROM works WHERE workno='RJ1'"
        ).fetchone()[0], 4.83)


if __name__ == "__main__":
    unittest.main()
