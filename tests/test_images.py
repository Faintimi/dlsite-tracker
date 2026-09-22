"""封面下载测试（离线）。"""

from __future__ import annotations

import tempfile
import threading
import types
import unittest
from pathlib import Path

from dlsite_tracker.images import download_covers, download_entries, extension_from_url
from dlsite_tracker.store import Store


class FakeFetcher:
    def __init__(self, payload: bytes = b"img"):
        self.payload = payload
        self.calls = []

    def get_bytes(self, url, kind="page", max_bytes=8_000_000):
        self.calls.append(url)
        return self.payload


class Factory:
    """模拟生产中的 worker 工厂（每线程一个独立 Fetcher）。"""

    def __init__(self):
        self.fetchers = []
        self.lock = threading.Lock()

    def __call__(self):
        fetcher = FakeFetcher()
        with self.lock:
            self.fetchers.append(fetcher)
        return fetcher


class ImagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.out = self.base / "out"
        self.store = Store(self.base / "t.sqlite")
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _add(self, workno="RJ1", url="https://img.dlsite.jp/resize/x/RJ1_img_main_240x240.jpg"):
        self.store.upsert_work(
            {"workno": workno, "site": "maniax", "product_name": "t", "image_url": url}
        )

    def test_work_type_filter(self):
        self.store.upsert_work(
            {"workno": "RJ1", "site": "maniax", "product_name": "游戏", "work_type": "RPG",
             "image_url": "https://img.dlsite.jp/resize/x/RJ1_img_main_240x240.jpg"}
        )
        self.store.upsert_work(
            {"workno": "RJ2", "site": "maniax", "product_name": "漫画", "work_type": "MNG",
             "image_url": "https://img.dlsite.jp/resize/x/RJ2_img_main_240x240.jpg"}
        )
        cfg = types.SimpleNamespace(
            out_dir=self.out, images_enabled=True, images_max=10,
            default_work_types=["RPG", "SLN"],
        )
        fetcher = FakeFetcher(b"data")
        result = download_covers(cfg, fetcher, self.store, limit=10)
        self.assertEqual(result["downloaded"], 1)
        self.assertTrue((self.out / "covers" / "RJ1.jpg").is_file())
        self.assertFalse((self.out / "covers" / "RJ2.jpg").is_file())

    def test_download_then_skip(self):
        self._add()
        cfg = types.SimpleNamespace(out_dir=self.out, images_enabled=True, images_max=10)
        fetcher = FakeFetcher(b"data")
        result = download_covers(cfg, fetcher, self.store, limit=10)
        self.assertEqual(result, {"downloaded": 1, "skipped": 0, "failed": 0})
        self.assertEqual((self.out / "covers" / "RJ1.jpg").read_bytes(), b"data")

        second = download_covers(cfg, fetcher, self.store, limit=10)
        self.assertEqual(second, {"downloaded": 0, "skipped": 1, "failed": 0})
        self.assertEqual(len(fetcher.calls), 1)

    def test_parallel_downloads_all(self):
        cfg = types.SimpleNamespace(
            out_dir=self.out, images_enabled=True, default_work_types=[], images_workers=4
        )
        entries = [(f"RJ01701{i:03d}", f"https://img.dlsite.jp/{i}.jpg") for i in range(12)]
        factory = Factory()
        result = download_entries(cfg, FakeFetcher(), entries, worker_factory=factory)
        self.assertEqual(result, {"downloaded": 12, "skipped": 0, "failed": 0})
        self.assertEqual(len(list((self.out / "covers").iterdir())), 12)
        self.assertTrue(1 <= len(factory.fetchers) <= 4)  # 并发使用但不超过 workers

    def test_extension_mapping(self):
        self.assertEqual(extension_from_url("https://a/b.webp"), "webp")
        self.assertEqual(extension_from_url("https://a/b.jpeg"), "jpg")
        self.assertEqual(extension_from_url("https://a/b"), "jpg")

    def test_disabled(self):
        self._add()
        cfg = types.SimpleNamespace(out_dir=self.out, images_enabled=False, images_max=10)
        fetcher = FakeFetcher()
        result = download_covers(cfg, fetcher, self.store, limit=10)
        self.assertEqual(result["downloaded"], 0)
        self.assertEqual(fetcher.calls, [])


if __name__ == "__main__":
    unittest.main()
