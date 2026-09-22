"""发现模块测试（离线，使用夹具数据）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dlsite_tracker.config import Config
from dlsite_tracker.discovery import (
    RANKING_URL,
    backfill,
    catalog_page_url,
    discover_from_sitemap,
    extract_catalog_items,
    extract_genre_catalog,
    extract_genre_count,
    extract_genre_name,
    extract_sales,
    extract_worknos,
    fetch_genre_rankings,
    fetch_rankings,
    fetch_trend_rankings,
    genre_list_url,
    parse_sitemap_index,
    trend_page_url,
)
from dlsite_tracker.http import HttpError
from dlsite_tracker.store import Store

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.dlsite.com/modpub/sitemap-xml/nodes/20260921/maniax/pages.xml</loc></sitemap>
  <sitemap><loc>https://www.dlsite.com/modpub/sitemap-xml/nodes/20260921/maniax/work_0.xml</loc></sitemap>
  <sitemap><loc>https://www.dlsite.com/modpub/sitemap-xml/nodes/20260921/maniax/work_1.xml</loc></sitemap>
</sitemapindex>"""

INDEX_URL = "https://www.dlsite.com/modpub/sitemap-xml/indexes/maniax_index.xml"
SHARD_0_URL = "https://www.dlsite.com/modpub/sitemap-xml/nodes/20260921/maniax/work_0.xml"
SHARD_1_URL = "https://www.dlsite.com/modpub/sitemap-xml/nodes/20260921/maniax/work_1.xml"


def _shard(*worknos: str) -> str:
    entries = "".join(
        f"<url><loc>https://www.dlsite.com/maniax/work/=/product_id/{workno}.html</loc>"
        f"<lastmod>2026-09-21T00:00:00+09:00</lastmod></url>"
        for workno in worknos
    )
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'


SHARD_0 = _shard("RJ000001")
SHARD_1 = _shard("RJ000004", "RJ000005")

RANKING_HTML = """
<a href="https://www.dlsite.com/maniax/work/=/product_id/RJ000002.html">B</a>
<span class="_dl_count_RJ000002">12,345</span>
<a href="https://www.dlsite.com/maniax/work/reviewlist/=/product_id/RJ000002.html">review</a>
<a href="https://www.dlsite.com/maniax/work/=/product_id/RJ000001.html">A</a>
<span class="_dl_count_RJ000001">2,000</span>
<a href="/maniax/fsr/=/genre/071/from/work.genre">g71</a>
<a href="/maniax/fsr/=/genre/004/from/work.genre">g04</a>
<a href="/maniax/fsr/=/genre/071/from/work.genre">g71 重复</a>
"""

GENRE_HTML = """
<a href="https://www.dlsite.com/maniax/work/=/product_id/RJ000009.html">G</a>
<span class="_dl_count_RJ000009">7,777</span>
"""


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.fetched = []

    def get_text(self, url, kind="page", max_bytes=8_000_000):
        self.fetched.append(url)
        if url not in self.pages:
            raise HttpError(f"HTTP 404：{url}")
        return self.pages[url]


def _config(base: Path) -> Config:
    path = base / "config.ini"
    path.write_text("[scope]\nsites = maniax\n", encoding="utf-8")
    return Config.load(path)


class ParseTest(unittest.TestCase):
    def test_extract_worknos_order_and_dedupe(self):
        self.assertEqual(extract_worknos(RANKING_HTML), ["RJ000002", "RJ000001"])

    def test_extract_sales(self):
        self.assertEqual(
            extract_sales(RANKING_HTML), {"RJ000002": 12345, "RJ000001": 2000}
        )

    def test_parse_sitemap_index_sorted_and_filtered(self):
        shards = parse_sitemap_index(SITEMAP_INDEX)
        self.assertEqual(shards, [SHARD_0_URL, SHARD_1_URL])

    def test_extract_genre_name_and_count(self):
        html = '<title>「快楽堕ちのゲーム」作品一覧 | DLsite 同人 - R18</title><p>1,248件販売中！</p>'
        self.assertEqual(extract_genre_name(html), "快楽堕ち")
        self.assertEqual(extract_genre_count(html), 1248)

    def test_genre_list_url_shape(self):
        url = genre_list_url("maniax", "game", "526", 2)
        self.assertIn("/works/type/=/work_type_category/game/genre/526", url)
        self.assertTrue(url.endswith("/per_page/100/page/2/show_type/3"))

    def test_extract_genre_catalog_dedupe_and_order(self):
        items = extract_genre_catalog(RANKING_HTML)
        self.assertEqual(
            items,
            [{"id": "071", "name": "g71"}, {"id": "004", "name": "g04"}],
        )

    def test_trend_page_url_shape(self):
        url = trend_page_url("maniax", "game", 2)
        self.assertIn("/order%5B0%5D/trend/", url)
        self.assertTrue(url.endswith("/per_page/100/page/2"))


class IncrementalTest(unittest.TestCase):
    def test_first_run_queues_newest_shard_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                fetcher = FakeFetcher({INDEX_URL: SITEMAP_INDEX, SHARD_0_URL: SHARD_0, SHARD_1_URL: SHARD_1})
                added = discover_from_sitemap(fetcher, store, cfg)
                self.assertEqual(added, 2)
                self.assertEqual(store.pending_count(), 2)
                self.assertEqual(store.get_meta("last_seen_workno:maniax"), "RJ000005")
                # 首次运行只请求：索引 + 最新分片
                self.assertEqual(fetcher.fetched, [INDEX_URL, SHARD_1_URL])

                second = FakeFetcher({INDEX_URL: SITEMAP_INDEX, SHARD_0_URL: SHARD_0, SHARD_1_URL: SHARD_1})
                self.assertEqual(discover_from_sitemap(second, store, cfg), 0)
                self.assertEqual(second.fetched, [INDEX_URL, SHARD_1_URL])
            finally:
                store.close()

    def test_gap_fills_previous_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                store.set_meta("last_seen_workno:maniax", "RJ000002")
                fetcher = FakeFetcher({INDEX_URL: SITEMAP_INDEX, SHARD_0_URL: SHARD_0, SHARD_1_URL: SHARD_1})
                added = discover_from_sitemap(fetcher, store, cfg)
                self.assertEqual(added, 2)
                self.assertEqual(
                    fetcher.fetched, [INDEX_URL, SHARD_1_URL, SHARD_0_URL]
                )
                self.assertEqual(store.get_meta("last_seen_workno:maniax"), "RJ000005")
            finally:
                store.close()


class RankingsTest(unittest.TestCase):
    def _store(self, tmp: str) -> Store:
        store = Store(Path(tmp) / "t.sqlite")
        store.migrate()
        return store

    def _category_pages(self):
        return {
            RANKING_URL.format(site="maniax", term=term, category="game"): RANKING_HTML
            for term in ("day", "week", "month")
        }

    def test_category_views_write_ranks(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = self._store(tmp)
            try:
                result = fetch_rankings(
                    FakeFetcher(self._category_pages()),
                    store,
                    cfg,
                    terms=["day", "week", "month"],
                    categories=["game"],
                )
                self.assertEqual(result["views"], 3)
                self.assertEqual(result["sales"], 6)
                row = store.conn.execute(
                    "SELECT rank_day_current, rank_week_current, rank_month_current, "
                    "rank_current_seen_at, rank_day "
                    "FROM works WHERE workno='RJ000002'"
                ).fetchone()
                self.assertEqual((row[0], row[1], row[2]), (1, 1, 1))
                self.assertRegex(row[3], r"^\d{4}-\d{2}-\d{2}T")
                self.assertIsNone(row[4])  # 历史快照列不受影响
                row = store.conn.execute(
                    "SELECT rank_day_current, rank_week_current FROM works WHERE workno='RJ000001'"
                ).fetchone()
                self.assertEqual((row[0], row[1]), (2, 2))
                hot = store.conn.execute(
                    "SELECT hot_seen_at FROM works WHERE workno='RJ000002'"
                ).fetchone()
                self.assertRegex(hot[0], r"^\d{4}-\d{2}-\d{2}T")
            finally:
                store.close()

class GenreRankingsTest(unittest.TestCase):
    """P19：分类人气列表（名次快照 + 销量 + 422/短页停止）。"""

    def _store(self, tmp: str) -> Store:
        store = Store(Path(tmp) / "t.sqlite")
        store.migrate()
        return store

    @staticmethod
    def _page(worknos, name="テスト分類", count=1024):
        cells = "".join(
            f'<li data-list_item_product_id="{workno}">'
            f'<span class="_dl_count_{workno}">1,000</span></li>'
            for workno in worknos
        )
        return (
            f'<title>「{name}のゲーム」作品一覧</title>'
            f"<p>{count:,}件販売中！</p>{cells}"
        )

    def test_genre_rankings_positions_snapshot_and_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = self._store(tmp)
            try:
                page1_ids = [f"RJ01{100000 + i:06d}" for i in range(1, 101)]
                page2_ids = ["RJ01100101", "RJ01100102"]
                pages1 = {
                    genre_list_url("maniax", "game", "071", 1): self._page(page1_ids),
                    genre_list_url("maniax", "game", "071", 2): self._page(page2_ids),
                }
                result = fetch_genre_rankings(
                    FakeFetcher(pages1), store, cfg, genres=["071"], pages=2
                )
                self.assertEqual(
                    (result["genres"], result["views"], result["positions"]), (1, 2, 102)
                )
                self.assertEqual(store.genre_positions("RJ01100001"), {"071": 1})
                self.assertEqual(store.genre_positions("RJ01100102"), {"071": 102})
                row = store.conn.execute(
                    "SELECT sales FROM works WHERE workno='RJ01100001'"
                ).fetchone()
                self.assertEqual(row[0], 1000)  # 销量已入库
                self.assertEqual(store.pending_count(), 102)  # 热榜候选登记
                info = store.conn.execute(
                    "SELECT name, count FROM genre_info WHERE genre_id='071'"
                ).fetchone()
                self.assertEqual((info[0], info[1]), ("テスト分類", 1024))
                # 整批替换：掉出前 N 的作品不带旧名次
                new_ids = [f"RJ01{200000 + i:06d}" for i in range(1, 101)]
                pages2 = {
                    genre_list_url("maniax", "game", "071", 1): self._page(new_ids, count=100),
                }
                result2 = fetch_genre_rankings(
                    FakeFetcher(pages2), store, cfg, genres=["071"], pages=2
                )
                self.assertEqual(result2["views"], 1)  # 第 2 页 404 → 停
                self.assertEqual(store.genre_positions("RJ01100001"), {})
                self.assertEqual(store.genre_positions("RJ01200001"), {"071": 1})
            finally:
                store.close()

    def test_genre_rankings_empty_page_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = self._store(tmp)
            try:
                pages = {genre_list_url("maniax", "game", "999", 1): "<html></html>"}
                result = fetch_genre_rankings(
                    FakeFetcher(pages), store, cfg, genres=["999"], pages=1
                )
                self.assertEqual(
                    (result["genres"], result["views"], result["positions"]), (0, 0, 0)
                )
                self.assertEqual(store.genre_positions("RJ01100001"), {})
            finally:
                store.close()

    def test_genre_rankings_more_page_keeps_and_extends(self):
        """P19.1/P19.2：每日抓 1..2 页不抹掉更深名次；--more 从深度之后续抓一页。"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = self._store(tmp)
            try:
                page1 = [f"RJ01{300000 + i:06d}" for i in range(1, 101)]
                page2 = [f"RJ01{400000 + i:06d}" for i in range(1, 101)]
                page3 = [f"RJ01{500000 + i:06d}" for i in range(1, 101)]
                pages = {
                    genre_list_url("maniax", "game", "071", 1): self._page(page1),
                    genre_list_url("maniax", "game", "071", 2): self._page(page2),
                }
                fetch_genre_rankings(FakeFetcher(pages), store, cfg, genres=["071"], pages=2)
                self.assertEqual(store.genre_depth("071"), 200)
                # 载入更多：续抓第 3 页（start_page=3，仅一页）
                pages3 = {genre_list_url("maniax", "game", "071", 3): self._page(page3)}
                result = fetch_genre_rankings(
                    FakeFetcher(pages3), store, cfg, genres=["071"], pages=1, start_page=3
                )
                self.assertEqual(result["positions"], 100)
                self.assertEqual(store.genre_positions("RJ01500001"), {"071": 201})
                self.assertEqual(store.genre_depth("071"), 300)
                # 每日刷新（1..2 页）不应抹掉第 3 页
                fetch_genre_rankings(
                    FakeFetcher(
                        {
                            genre_list_url("maniax", "game", "071", 1): self._page(page1),
                            genre_list_url("maniax", "game", "071", 2): self._page(page2),
                        }
                    ),
                    store,
                    cfg,
                    genres=["071"],
                    pages=2,
                )
                self.assertEqual(store.genre_depth("071"), 300)
                self.assertEqual(store.genre_positions("RJ01500001"), {"071": 201})
                # 越界续抓（下一页 404）→ 清理更深处名次，保留 1..300
                fetch_genre_rankings(
                    FakeFetcher({}), store, cfg, genres=["071"], pages=1, start_page=4
                )
                self.assertEqual(store.genre_depth("071"), 300)
            finally:
                store.close()


class TrendRankingsTest(unittest.TestCase):
    """P19.4：全站人气序（trend）——名次/销量/登记/深度。"""

    def _store(self, tmp: str) -> Store:
        store = Store(Path(tmp) / "t.sqlite")
        store.migrate()
        return store

    @staticmethod
    def _page(worknos):
        cells = "".join(
            f'<li data-list_item_product_id="{workno}">'
            f'<span class="_dl_count_{workno}">5,000</span></li>'
            for workno in worknos
        )
        return f"<html>{cells}</html>"

    @staticmethod
    def _trend_rank(store: Store, workno: str):
        row = store.conn.execute(
            "SELECT rank_trend_current FROM works WHERE workno=?", (workno,)
        ).fetchone()
        return row[0]

    def test_trend_records_ranks_stops_on_short_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = self._store(tmp)
            try:
                page1 = [f"RJ01{600000 + i:06d}" for i in range(1, 101)]
                page2 = [f"RJ01{700000 + i:06d}" for i in range(1, 51)]
                pages = {
                    trend_page_url("maniax", "game", 1): self._page(page1),
                    trend_page_url("maniax", "game", 2): self._page(page2),
                }
                result = fetch_trend_rankings(FakeFetcher(pages), store, cfg, pages=10)
                self.assertEqual(
                    (result["pages"], result["positions"], result["cleared"]), (2, 150, 0)
                )
                self.assertEqual(self._trend_rank(store, "RJ01600001"), 1)
                self.assertEqual(self._trend_rank(store, "RJ01700050"), 150)
                self.assertEqual(store.rank_trend_depth(), 150)
                self.assertEqual(store.pending_count(), 150)
                self.assertIsNotNone(store.get_meta("trend_seen:maniax"))
            finally:
                store.close()


class BackfillTest(unittest.TestCase):
    def test_backfill_all_registers_every_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp))
            store = Store(Path(tmp) / "t.sqlite")
            store.migrate()
            try:
                fetcher = FakeFetcher(
                    {INDEX_URL: SITEMAP_INDEX, SHARD_0_URL: SHARD_0, SHARD_1_URL: SHARD_1}
                )
                added = backfill(fetcher, store, cfg, all_shards=True)
                self.assertEqual(added, 3)
                self.assertEqual(store.pending_count(), 3)
                self.assertEqual(fetcher.fetched, [INDEX_URL, SHARD_1_URL, SHARD_0_URL])
                # 续跑：游标已到头，再次执行不再请求分片
                again = FakeFetcher({INDEX_URL: SITEMAP_INDEX})
                self.assertEqual(backfill(again, store, cfg, all_shards=True), 0)
                self.assertEqual(again.fetched, [INDEX_URL])
            finally:
                store.close()


class CatalogPageTest(unittest.TestCase):
    """P18：游戏目录页（作品一覧）的提取与翻页 URL。"""

    def test_extract_catalog_items_scoped_ordered_dedup(self):
        html = (
            '<a href="https://www.dlsite.com/maniax/work/=/product_id/RJ00000001.html">侧栏</a>'
            '<li data-list_item_product_id="RJ01100002"><a href="x">a</a></li>'
            '<li data-list_item_product_id="RJ01100001">b</li>'
            '<li data-list_item_product_id="RJ01100002">dup</li>'
            '<a href="https://www.dlsite.com/maniax/cart/=/product_id/RJ01100003.html">c</a>'
        )
        self.assertEqual(extract_catalog_items(html), ["RJ01100002", "RJ01100001"])

    def test_catalog_page_url(self):
        url = catalog_page_url("maniax", "game", 3)
        self.assertIn("/works/type/=/work_type_category/game", url)
        self.assertIn("/order%5B0%5D/release_d", url)
        self.assertTrue(url.endswith("/per_page/100/page/3"))


if __name__ == "__main__":
    unittest.main()
