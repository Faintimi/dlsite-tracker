"""导出模块测试（离线）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dlsite_tracker.export import fetch_records, find_cover, write_export
from dlsite_tracker.store import Store


class ExportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.out = self.base / "out"
        (self.out / "covers").mkdir(parents=True)
        self.store = Store(self.base / "t.sqlite")
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _add_work(self, workno: str, **overrides):
        row = {
            "workno": workno,
            "site": "maniax",
            "product_name": f"游戏{workno}",
            "maker_name": "社团",
            "work_type": "SLN",
            "work_type_string": "模拟",
            "price": 1000,
            "rating_star": 4.5,
            "sales": 123,
            "official_price": 1500,
            "discount_rate": 20,
            "rating_count": 10,
            "rank_day": 1,
            "rank_day_date": "2026-09-21",
            "rank_day_current": 5,
            "rank_current_seen_at": "2026-09-21T21:00:00+09:00",
            "regist_date": "2026-01-01",
            "sales_seen_at": "2026-09-21T00:00:00+09:00",
        }
        row.update(overrides)
        self.store.upsert_work(row)

    def test_records_and_files(self):
        self._add_work("RJ1")
        self.store.replace_genres("RJ1", [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}])
        (self.out / "covers" / "RJ1.jpg").write_bytes(b"x")

        records = fetch_records(self.store, self.out)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["id"], "RJ1")
        self.assertEqual(record["title"], "游戏RJ1")
        self.assertEqual(record["category"], "A | B")
        self.assertEqual(record["form"], "模拟")
        self.assertEqual(record["rating"], 4.5)
        self.assertEqual(record["sales"], 123)
        self.assertEqual(record["rank_day_date"], "2026-09-21")
        self.assertEqual(record["rank_day_current"], 5)
        self.assertEqual(record["image_path"], "covers/RJ1.jpg")
        self.assertIn("product_id/RJ1.html", record["url"])

        paths = write_export(self.out, records)
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["works"][0]["id"], "RJ1")

        csv_text = Path(paths["csv"]).read_text(encoding="utf-8")
        self.assertTrue(csv_text.startswith("\ufeff"))
        self.assertIn("id,title,maker,category,form", csv_text.splitlines()[0])
        self.assertIn("rank_day_date", csv_text.splitlines()[0])
        self.assertIn("rank_day_current", csv_text.splitlines()[0])
        self.assertIn("rank_trend_current", csv_text.splitlines()[0])
        self.assertIn("RJ1", csv_text)

    def test_genre_meta_payload_fields(self):
        self._add_work("RJ1")
        self.store.replace_genre_ranks("016", {"RJ1": 7})
        self.store.save_genre_info("016", "ファンタジー", 7190)
        self.store.save_genre_catalog([("016", "ファンタジー"), ("526", "快楽堕ち")])
        self.store.record_ranks("maniax", "trend", {"RJ1": 42})
        records = fetch_records(self.store, self.out)
        self.assertEqual(records[0]["genre_pos"], {"016": 7})
        self.assertEqual(records[0]["rank_trend_current"], 42)
        paths = write_export(
            self.out,
            records,
            genres=self.store.genre_summaries(),
            genre_catalog=self.store.list_genre_catalog(),
            trend={"depth": self.store.rank_trend_depth(), "seen_at": "2026-09-22T12:00:00+08:00"},
        )
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["genres"][0]["id"], "016")
        self.assertEqual(payload["genres"][0]["depth"], 7)
        self.assertEqual(payload["genres"][0]["count"], 7190)
        self.assertEqual(
            payload["genre_catalog"],
            [{"id": "016", "name": "ファンタジー"}, {"id": "526", "name": "快楽堕ち"}],
        )
        self.assertEqual(payload["trend"]["depth"], 42)
        self.assertEqual(payload["trend"]["seen_at"], "2026-09-22T12:00:00+08:00")

    def test_work_type_filter_and_missing_cover(self):
        self._add_work("RJ1")
        self._add_work("RJ2", work_type="RPG")
        records = fetch_records(self.store, self.out, work_types=["SLN"])
        self.assertEqual([r["id"] for r in records], ["RJ1"])
        self.assertEqual(records[0]["image_path"], "")
        self.assertEqual(find_cover(self.out, "RJ2"), "")

    def test_option_badges_and_maker_id(self):
        self._add_work("RJ1", maker_id="RG12345", options="JPN#SND#MS2#MV2#TRI")
        self._add_work("RJ2")
        records = {r["id"]: r for r in fetch_records(self.store, self.out)}
        self.assertEqual(records["RJ1"]["maker_id"], "RG12345")
        self.assertTrue(records["RJ1"]["voice"])
        self.assertTrue(records["RJ1"]["music"])
        self.assertTrue(records["RJ1"]["video"])
        self.assertEqual(records["RJ2"]["maker_id"], "")
        self.assertFalse(records["RJ2"]["voice"])
        self.assertFalse(records["RJ2"]["music"])
        self.assertFalse(records["RJ2"]["video"])

    def test_empty_export(self):
        records = fetch_records(self.store, self.out)
        self.assertEqual(records, [])
        paths = write_export(self.out, records)
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["count"], 0)


if __name__ == "__main__":
    unittest.main()
