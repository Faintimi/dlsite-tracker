"""本地只读 API 测试（离线；含一次真实回环 HTTP 测试）。"""

from __future__ import annotations

import json
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from dlsite_tracker.serve import make_handler, query_works
from dlsite_tracker.store import Store


class ServeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.out = self.base / "out"
        (self.out / "covers").mkdir(parents=True)
        self.db = self.base / "dlsite.sqlite"
        self.store = Store(self.db)
        self.store.migrate()
        self.store.upsert_work({
            "workno": "RJ1", "site": "maniax", "product_name": "A", "work_type": "SLN",
            "work_type_string": "模拟", "price": 1000, "rating_star": 4.5, "sales": 100,
            "rank_day": 1,
        })
        self.store.replace_genres("RJ1", [{"id": "1", "name": "X"}])
        self.store.record_ranks("maniax", "day", {"RJ1": 3})
        self.store.upsert_work({
            "workno": "RJ2", "site": "maniax", "product_name": "B", "work_type": "RPG",
            "work_type_string": "RPG", "price": 3000, "rating_star": 3.0, "sales": 5,
            "rank_day": None,
        })
        self.store.upsert_work({
            "workno": "RJ3", "site": "maniax", "product_name": "C", "work_type": "SLN",
            "work_type_string": "模拟", "price": 2000, "rating_star": 4.0, "sales": 50,
            "rank_day": None,
        })
        (self.out / "covers" / "RJ1.png").write_bytes(b"x")
        self.cfg = types.SimpleNamespace(
            data_dir=self.base, out_dir=self.out, serve_host="127.0.0.1", serve_port=0
        )

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_query_filters_and_sort(self):
        rows = query_works(self.db, self.out, work_type="SLN")
        self.assertEqual({r["id"] for r in rows}, {"RJ1", "RJ3"})

        rows = query_works(self.db, self.out, genre="X")
        self.assertEqual([r["id"] for r in rows], ["RJ1"])
        self.assertEqual(rows[0]["image_path"], "covers/RJ1.png")

        rows = query_works(self.db, self.out, min_price=1500, max_price=2500)
        self.assertEqual([r["id"] for r in rows], ["RJ3"])

        rows = query_works(self.db, self.out, min_rating=4.2)
        self.assertEqual([r["id"] for r in rows], ["RJ1"])

        rows = query_works(self.db, self.out, sort="rank_day", order="asc")
        self.assertEqual(rows[0]["id"], "RJ1")  # 有排名的最小值排最前，NULL 排最后

        rows = query_works(self.db, self.out, sort="rank_day_current", order="asc")
        self.assertEqual(rows[0]["id"], "RJ1")
        self.assertEqual(rows[0]["rank_day_current"], 3)

        rows = query_works(self.db, self.out, sort="price", order="desc")
        self.assertEqual([row["id"] for row in rows], ["RJ2", "RJ3", "RJ1"])

        rows = query_works(self.db, self.out, sort="price; DROP TABLE works--", order="desc; DROP TABLE works--")
        self.assertEqual([row["id"] for row in rows], ["RJ1", "RJ2", "RJ3"])
        self.assertEqual(len(query_works(self.db, self.out)), 3)

        self.assertEqual(len(query_works(self.db, self.out, limit=1)), 1)
        self.assertEqual(len(query_works(self.db, self.out, limit=0)), 1)  # 下限钳制为 1

        rows = query_works(self.db, self.out, workno="RJ2")
        self.assertEqual([r["id"] for r in rows], ["RJ2"])

    def test_http_endpoints(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.cfg))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]

        def get(path: str):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))

        try:
            status, payload = get("/health")
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])

            status, payload = get("/works?work_type=SLN")
            self.assertEqual(payload["count"], 2)

            status, payload = get("/works/RJ1")
            self.assertEqual(payload["id"], "RJ1")

            with self.assertRaises(urllib.error.HTTPError) as ctx:
                get("/nope")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
