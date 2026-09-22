"""发现阶段：sitemap 增量、榜单、列表页、历史回填（仅标准库）。

合规要点：
- 只访问 robots 允许的页面：sitemap、/ranking/、/works/type/（列表页；P18 起含
  站内翻页——robots 仅禁 `/*/fsr/=/*/per_page/*/page/`，该路径分页不受限，≥10s/页）；
- 榜单分页已实测无效（page/2 与 page/1 完全重叠），因此不做分页；
- 分类人气列表（P19）：`/works/type/…/genre/<id>` 页（实测可翻页，page≥2 需
  `show_type/3`）。原先的「分类榜」（ranking/…/genre/<id>）经复核无效——genre
  参数被站点忽略、各分类返回同一份数据，已由分类人气列表替代。
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from .config import split_list
from .http import Fetcher, HttpError
from .store import Store

LOG = logging.getLogger("dlsite_tracker.discovery")

SITEMAP_INDEX_URL = "https://www.dlsite.com/modpub/sitemap-xml/indexes/{site}_index.xml"
RANKING_URL = (
    "https://www.dlsite.com/{site}/ranking/{term}/=/date/30d/category/{category}"
    "?locale=zh_CN"  # P20.1：中文渲染——顺带解析的「分类导航」即官方中文分类名
)
GENRE_LIST_URL = (
    "https://www.dlsite.com/{site}/works/type/=/work_type_category/{work_type}"
    "/genre/{genre}/per_page/{per_page}/page/{page}/show_type/3"
)
TREND_URL = (
    "https://www.dlsite.com/{site}/works/type/=/work_type_category/{work_type}"
    "/order%5B0%5D/trend/per_page/{per_page}/page/{page}"
)
LISTING_URL = "https://www.dlsite.com/{site}/works/type/=/work_type_category/{work_type}"
CATALOG_URL = (
    "https://www.dlsite.com/{site}/works/type/=/work_type_category/{work_type}"
    "/order%5B0%5D/release_d/per_page/{per_page}/page/{page}"
)

WORKNO_RE = re.compile(r"product_id/(RJ\d+)\.html")
CATALOG_ITEM_RE = re.compile(r'data-list_item_product_id="(RJ\d+)"')
SALES_RE = re.compile(r'_dl_count_(RJ\d+)">([\d,]+)')
GENRE_NAME_RE = re.compile(r"「(.+?)」作品一覧")
GENRE_COUNT_RE = re.compile(r"([\d,]+)件販売中")
GENRE_NAV_RE = re.compile(
    r'href="[^"]*fsr/=/genre/(\d+)/from/work\.genre"[^>]*>\s*([^<]+?)\s*<'
)
SHARD_RE = re.compile(r"/work_(\d+)\.xml$")

SITEMAP_MAX_BYTES = 64_000_000


def extract_worknos(html: str) -> List[str]:
    """按出现顺序提取作品号（去重，保留首次出现位置 = 榜单名次序）。"""
    seen = set()
    ordered: List[str] = []
    for match in WORKNO_RE.finditer(html):
        workno = match.group(1)
        if workno not in seen:
            seen.add(workno)
            ordered.append(workno)
    return ordered


def extract_sales(html: str) -> Dict[str, int]:
    """提取 `_dl_count_` 销量（如 12,464 → 12464）。"""
    sales: Dict[str, int] = {}
    for match in SALES_RE.finditer(html):
        try:
            sales[match.group(1)] = int(match.group(2).replace(",", ""))
        except ValueError:
            continue
    return sales


def extract_catalog_items(html: str) -> List[str]:
    """提取「作品一覧」页的列表项作品号（按页面顺序去重；P18 目录遍历用）。

    以列表容器条目属性 `data-list_item_product_id` 为锚——页面侧栏/推荐位的
    普通 product_id 链接不会被误收（实测每页恰为 per_page 件）。
    """
    seen = set()
    ordered: List[str] = []
    for match in CATALOG_ITEM_RE.finditer(html):
        workno = match.group(1)
        if workno not in seen:
            seen.add(workno)
            ordered.append(workno)
    return ordered


def catalog_page_url(site: str, work_type: str, page: int, per_page: int = 100) -> str:
    """「作品一覧」翻页 URL（发售日新→旧；站点自身分页即此形态，robots 未禁）。"""
    return CATALOG_URL.format(site=site, work_type=work_type, per_page=per_page, page=page)


def parse_sitemap_index(xml_text: str) -> List[str]:
    """解析 sitemap 索引，返回按编号升序排列的 work_*.xml 分片 URL。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"sitemap 索引解析失败：{exc}") from exc
    shards = [
        element.text.strip()
        for element in root.iter()
        if element.tag.endswith("loc") and element.text and SHARD_RE.search(element.text.strip())
    ]
    shards.sort(key=lambda url: int(SHARD_RE.search(url).group(1)))  # type: ignore[union-attr]
    return shards


def genre_list_url(site: str, work_type: str, genre: str, page: int, per_page: int = 100) -> str:
    """分类人气列表页 URL（P19；默认排序 = 人気順；page≥2 必须带 show_type/3）。"""
    return GENRE_LIST_URL.format(
        site=site, work_type=work_type, genre=genre, per_page=per_page, page=page
    )


def extract_genre_name(html: str) -> Optional[str]:
    """从分类页标题解析分类名（「NAME のゲーム」作品一覧 → NAME）。"""
    match = GENRE_NAME_RE.search(html)
    if not match:
        return None
    name = match.group(1).strip()
    if name.endswith("のゲーム"):
        name = name[: -len("のゲーム")]
    return name


def extract_genre_count(html: str) -> Optional[int]:
    """解析分类页自报的在售件数（如 1,248件販売中 → 1248）。"""
    match = GENRE_COUNT_RE.search(html)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def trend_page_url(site: str, work_type: str, page: int, per_page: int = 100) -> str:
    """全站人气序（人気順）目录页 URL（P19.4；默认排序即 trend，显式参数同序）。"""
    return TREND_URL.format(site=site, work_type=work_type, per_page=per_page, page=page)


def extract_genre_catalog(html: str) -> List[Dict[str, str]]:
    """解析站点分类导航（排行页侧栏，实测 198 项）：[{id, name}]（按页面顺序去重）。

    链接形态：`/maniax/fsr/=/genre/<id>/from/work.genre`（id 带前导零，如 016）。
    """
    seen = set()
    items: List[Dict[str, str]] = []
    for match in GENRE_NAV_RE.finditer(html):
        genre_id = match.group(1).strip()
        name = re.sub(r"\s+", " ", match.group(2)).strip()
        if not genre_id or not name or genre_id in seen:
            continue
        seen.add(genre_id)
        items.append({"id": genre_id, "name": name})
    return items


def list_sitemap_shards(fetcher: Fetcher, site: str) -> List[str]:
    xml_text = fetcher.get_text(
        SITEMAP_INDEX_URL.format(site=site), kind="page", max_bytes=2_000_000
    )
    return parse_sitemap_index(xml_text)


def discover_from_sitemap(fetcher: Fetcher, store: Store, cfg) -> int:
    """增量发现：从最新分片向前扫描，命中已见作品号即停止。

    通常每次仅需 1 个分片；若上次运行间隔较久（存在跨分片缺口），
    会继续向前补扫，数量受 cfg.sitemap_max_shards 限制。
    """
    total_new = 0
    for site in cfg.sites:
        meta_key = f"last_seen_workno:{site}"
        last_seen = store.get_meta(meta_key)
        shards = list_sitemap_shards(fetcher, site)
        if not shards:
            LOG.warning("[%s] sitemap 索引中没有 work_*.xml 分片", site)
            continue
        scanned = 0
        for url in reversed(shards):
            if scanned >= cfg.sitemap_max_shards:
                break
            scanned += 1
            text = fetcher.get_text(url, kind="page", max_bytes=SITEMAP_MAX_BYTES)
            worknos = extract_worknos(text)
            if not worknos:
                LOG.warning("分片解析为空（可能结构变化）：%s", url)
                break
            new = [w for w in worknos if last_seen is None or w > last_seen]
            if not new:
                break
            store.add_pending_many(new, source=f"sitemap:{site}")
            total_new += len(new)
            gap = last_seen is not None and min(worknos) > last_seen
            last_seen = max(worknos)
            store.set_meta(meta_key, last_seen)
            if not gap:
                break
    return total_new


def _store_view(
    store: Store, site: str, worknos: List[str], sales: Dict[str, int], source: str
) -> None:
    store.add_pending_many(worknos, source=source)
    store.mark_hot(site, worknos)  # 出现在榜单/列表中 = 热榜候选（P6）
    if sales:
        store.record_sales_many(site, sales, source=source)


def fetch_rankings(
    fetcher: Fetcher,
    store: Store,
    cfg,
    terms: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
) -> Dict[str, int]:
    """抓取 term × category 总榜（含名次写入；顺带存档分类目录）；返回视图/销量/目录数。"""
    views = sales_total = 0
    catalog_total = 0
    for site in cfg.sites:
        catalog_saved = False
        use_terms = list(terms) if terms else list(cfg.rank_terms)
        use_categories = list(categories) if categories else list(cfg.rank_categories)
        for term in use_terms:
            for category in use_categories:
                url = RANKING_URL.format(site=site, term=term, category=category)
                html = fetcher.get_text(url, kind="page")
                if not catalog_saved:
                    # P19.3：排行页侧栏含全量分类导航（198 项）——顺带存档供应用搜索/现导入
                    catalog = extract_genre_catalog(html)
                    if catalog:
                        catalog_total = max(
                            catalog_total,
                            store.save_genre_catalog(
                                [(item["id"], item["name"]) for item in catalog]
                            ),
                        )
                        catalog_saved = True
                worknos = extract_worknos(html)
                sales = extract_sales(html)
                if not worknos:
                    LOG.warning("榜单解析为空（可能页面结构变化）：%s", url)
                    continue
                _store_view(store, site, worknos, sales, source=f"ranking:{site}:{term}:{category}")
                # 总榜视图：出现顺序即名次（1 = 最热），写入 rank_*_current（P5）
                store.record_ranks(
                    site,
                    term,
                    {workno: index for index, workno in enumerate(worknos, start=1)},
                )
                views += 1
                sales_total += len(sales)
    return {"views": views, "sales": sales_total, "catalog": catalog_total}


def fetch_genre_rankings(
    fetcher: Fetcher,
    store: Store,
    cfg,
    genres: Optional[Sequence[str]] = None,
    pages: Optional[int] = None,
    start_page: int = 1,
) -> Dict[str, Any]:
    """抓取「分类人气列表」（选定分类 × 指定页范围）——名次快照 + 销量 + 热榜候选。

    - 每日调用：start_page=1、pages=配置页数 → 只替换 [1, pages×100] 范围，保留
      此前手动「载入更多」抓到的更深名次；抓到自然末页/空页则整段替换（清理陈旧深页）。
    - 现导入（fetch-genre）：默认同每日；`--more` 时传 start_page=深度页+1、pages=1，
      即从已抓深度之后续抓一页。
    - 返回 {"genres", "views", "positions", "details"}；details 含每分类名称/件数/
      深度/本次作品号等（现导入脚本用）。
    """
    genre_ids = [
        str(item).strip()
        for item in (genres if genres is not None else split_list(cfg.genre_rank_ids))
        if str(item).strip()
    ]
    page_limit = max(int(pages if pages is not None else cfg.genre_rank_pages), 1)
    start_page = max(int(start_page), 1)
    work_type = cfg.list_work_types[0] if getattr(cfg, "list_work_types", None) else "game"
    genres_done = views = positions_total = 0
    details: List[Dict[str, Any]] = []
    for site in cfg.sites:
        for genre_id in genre_ids:
            positions: Dict[str, int] = {}
            ended = False
            done_pages = 0
            name: Optional[str] = None
            count: Optional[int] = None
            page = start_page
            stop = start_page + page_limit - 1
            while page <= stop:
                url = genre_list_url(site, work_type, genre_id, page)
                try:
                    html = fetcher.get_text(url, kind="page")
                except HttpError as exc:
                    if "HTTP 404" in str(exc) and page > 1:
                        ended = True  # 越界页（含「载入更多」越过末页）
                        break
                    raise
                worknos = extract_catalog_items(html)
                if not worknos:
                    if page == 1:
                        LOG.warning("分类人气页解析为空：%s", url)
                    ended = True
                    break
                if page == 1:
                    found = extract_genre_name(html)
                    if found:
                        name = found
                        count = extract_genre_count(html)
                        store.save_genre_info(genre_id, name, count)
                sales = extract_sales(html)
                for index, workno in enumerate(worknos, start=(page - 1) * 100 + 1):
                    positions[workno] = index
                if sales:
                    store.record_sales_many(site, sales, source=f"genre-rank:{site}:{genre_id}")
                views += 1
                done_pages += 1
                if len(worknos) < 100:
                    ended = True  # 末页
                    break
                page += 1
            range_start = (start_page - 1) * 100 + 1
            if positions or (ended and start_page > 1):
                range_end = None if ended else range_start + done_pages * 100 - 1
                store.replace_genre_ranks(
                    genre_id, positions, start=range_start, end=range_end
                )
            if positions:
                store.add_pending_many(list(positions), source=f"genre-rank:{site}:{genre_id}")
                store.mark_hot(site, list(positions))
                positions_total += len(positions)
                genres_done += 1
                depth = store.genre_depth(genre_id)
                details.append(
                    {
                        "id": genre_id,
                        "site": site,
                        "name": name,
                        "count": count,
                        "positions": len(positions),
                        "depth": depth,
                        "ended": ended,
                        "worknos": list(positions),
                    }
                )
                LOG.info(
                    "分类人气 [%s] %s：%d 条名次（深度 %d）",
                    site,
                    genre_id,
                    len(positions),
                    depth,
                )
            elif ended and start_page > 1:
                depth = store.genre_depth(genre_id)
                details.append(
                    {
                        "id": genre_id,
                        "site": site,
                        "name": name,
                        "count": count,
                        "positions": 0,
                        "depth": depth,
                        "ended": True,
                        "worknos": [],
                    }
                )
                LOG.info(
                    "分类人气 [%s] %s：已到末页（清理 %d 之后的名次）",
                    site,
                    genre_id,
                    range_start - 1,
                )
    return {
        "genres": genres_done,
        "views": views,
        "positions": positions_total,
        "details": details,
    }


def fetch_trend_rankings(
    fetcher: Fetcher, store: Store, cfg, pages: Optional[int] = None
) -> Dict[str, int]:
    """官方全站人气序（人気順）目录前 N 页——「人气（官方）」排序与 #名次 数据源（P19.4）。

    - 每页 100 件、≥10s/页；抓到空页/404/不足一页即停；
    - 与榜单同待遇：登记队列 + 热标记 + 顺带记销量；名次写入 rank_trend_current
      （1 = 全站最热；NULL = 未入前 N）；超出本次深度的旧名次会被清理（P20）。
    """
    page_limit = int(cfg.trend_pages if pages is None else pages)
    if page_limit <= 0:
        return {"pages": 0, "positions": 0, "cleared": 0}
    work_type = cfg.list_work_types[0] if getattr(cfg, "list_work_types", None) else "game"
    total_pages = total_positions = total_cleared = 0
    for site in cfg.sites:
        positions: Dict[str, int] = {}
        done = 0
        for page in range(1, page_limit + 1):
            url = trend_page_url(site, work_type, page)
            try:
                html = fetcher.get_text(url, kind="page")
            except HttpError as exc:
                if page > 1 and "HTTP 404" in str(exc):
                    break
                raise
            worknos = extract_catalog_items(html)
            if not worknos:
                if page == 1:
                    LOG.warning("人气序页解析为空：%s", url)
                break
            sales = extract_sales(html)
            _store_view(store, site, worknos, sales, source=f"trend:{site}")
            for index, workno in enumerate(worknos, start=(page - 1) * 100 + 1):
                positions[workno] = index
            done += 1
            if len(worknos) < 100:
                break
        if positions:
            store.record_ranks(site, "trend", positions)
            cleared = store.clear_rank_trend_beyond(max(positions.values()))
            total_cleared += cleared
            store.set_meta(
                f"trend_seen:{site}",
                datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            LOG.info("人气序 [%s]：%d 页，名次 %d 条（清理越界 %d 条）", site, done, len(positions), cleared)
        total_pages += done
        total_positions += len(positions)
    return {"pages": total_pages, "positions": total_positions, "cleared": total_cleared}


def fetch_listings(fetcher: Fetcher, store: Store, cfg) -> Dict[str, int]:
    """抓取列表页第 1 页（最新上架信号 + 销量）。"""
    views = sales_total = 0
    for site in cfg.sites:
        for work_type in cfg.list_work_types:
            url = LISTING_URL.format(site=site, work_type=work_type)
            html = fetcher.get_text(url, kind="page")
            worknos = extract_worknos(html)
            sales = extract_sales(html)
            if not worknos:
                LOG.warning("列表页解析为空（可能页面结构变化）：%s", url)
                continue
            _store_view(store, site, worknos, sales, source=f"listing:{site}:{work_type}")
            views += 1
            sales_total += len(sales)
    return {"views": views, "sales": sales_total}


def backfill(
    fetcher: Fetcher, store: Store, cfg, last_shards: int = 3, all_shards: bool = False
) -> int:
    """历史登记（仅入队）：从最新分片向前；all_shards=True 登记全部（游标可续跑）。"""
    total = 0
    for site in cfg.sites:
        shards = list_sitemap_shards(fetcher, site)
        cursor_key = f"backfill_cursor:{site}"
        cursor = int(store.get_meta(cursor_key) or "0")
        ordered = list(reversed(shards))
        if all_shards:
            selected = ordered[cursor:]
        else:
            selected = ordered[cursor : cursor + max(last_shards, 0)]
        for index, url in enumerate(selected, start=cursor):
            text = fetcher.get_text(url, kind="page", max_bytes=SITEMAP_MAX_BYTES)
            worknos = extract_worknos(text)
            store.add_pending_many(worknos, source=f"backfill:{site}")
            store.set_meta(cursor_key, str(index + 1))
            total += len(worknos)
            LOG.info(
                "[%s] 登记分片 %d/%d（%d 个，累计 %d）",
                site,
                index + 1,
                len(ordered),
                len(worknos),
                total,
            )
    return total
