"""销量批查测试（离线）。"""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path

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


class FakeApiFetcher:
    """按 URL 里的 product_id 列表返回销量；sales: workno → (dl_count, wishlist)。"""

    def __init__(self, sales=None, options=None):
        self.sales = sales or {}
        self.options = options or {}
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
            if item:
                result[workno] = item
        return result


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


if __name__ == "__main__":
    unittest.main()
