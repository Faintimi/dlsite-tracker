"""富化阶段：调用站点自有 JSON 接口补齐字段（仅标准库）。

字段映射与语义见 README；销量不在此处获取（来自发现阶段的榜单/列表页）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .http import Fetcher, HttpError
from .sales import parse_options, sync_sales
from .store import Store

LOG = logging.getLogger("dlsite_tracker.enrich")

PRODUCT_API_URL = (
    "https://www.dlsite.com/{site}/api/=/product.json?workno={workno}&locale={locale}"
)

_SOURCE_SITE_PREFIXES = {"ranking", "listing", "sitemap", "backfill"}


def _site_for(source: str, workno: str, store: Store, cfg) -> str:
    """从来源推断站点（如 ranking:maniax:day:game → maniax）；未知来源回退数据库/配置。"""
    parts = source.split(":")
    if len(parts) >= 2 and parts[0] in _SOURCE_SITE_PREFIXES:
        return parts[1]
    row = store.conn.execute("SELECT site FROM works WHERE workno=?", (workno,)).fetchone()
    if row and row[0]:
        return str(row[0])
    return cfg.sites[0] if cfg.sites else "maniax"
FAIL_LIMIT_BEFORE_ABORT = 5


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if bool(value) else 0


def parse_product(
    items: Any, workno: str
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, str]]]]:
    """从 product.json 响应中提取目标作品，返回 (行数据, 分类列表)。"""
    if not isinstance(items, list) or not items:
        return None
    picked = next(
        (item for item in items if isinstance(item, dict) and item.get("workno") == workno),
        None,
    )
    if picked is None:
        picked = next((item for item in items if isinstance(item, dict)), None)
    if picked is None:
        return None

    star = _as_float(picked.get("rate_average_star"))
    rating = round(star / 10.0, 2) if star is not None else None

    detail = picked.get("rate_count_detail")
    rating_count: Optional[int] = None
    if isinstance(detail, dict):
        total = 0
        seen = False
        for value in detail.values():
            number = _as_int(value)
            if number is not None:
                total += number
                seen = True
        rating_count = total if seen else None

    genres: List[Dict[str, str]] = []
    for genre in picked.get("genres") or []:
        if isinstance(genre, dict) and genre.get("id") is not None:
            genres.append({"id": str(genre["id"]), "name": str(genre.get("name") or "").strip()})

    image = picked.get("image_thumb") or picked.get("image_main") or ""
    if isinstance(image, str) and image.startswith("//"):
        image = "https:" + image

    # P16：work_attributes 与 info/ajax options 同源（SND/MS2/MV2 徽章 + 语言 token）
    options = parse_options(picked.get("work_attributes"))

    maker_id = picked.get("maker_id")

    row: Dict[str, Any] = {
        "workno": picked.get("workno") or workno,
        "site": picked.get("site_id") or "maniax",
        "product_name": picked.get("work_name"),
        "maker_id": str(maker_id) if maker_id is not None else None,
        "maker_name": picked.get("maker_name"),
        "work_category": picked.get("work_category"),
        "work_type": picked.get("work_type"),
        "work_type_string": picked.get("work_type_string"),
        "age_category": _as_int(picked.get("age_category")),
        "sex_category": _as_int(picked.get("sex_category")),
        "price": _as_int(picked.get("price")),
        "official_price": _as_int(picked.get("official_price")),
        "discount_rate": _as_int(picked.get("discount_rate")),
        "is_timesale": _bool_int(picked.get("is_timesale_work")),
        "timesale_price": _as_int(picked.get("timesale_price")),
        "timesale_end_date": picked.get("timesale_end_date"),
        "rating_star": rating,
        "rating_count": rating_count,
        "rank_day": _as_int(picked.get("rank_day")),
        "rank_day_date": picked.get("rank_day_date"),
        "rank_week": _as_int(picked.get("rank_week")),
        "rank_week_date": picked.get("rank_week_date"),
        "rank_month": _as_int(picked.get("rank_month")),
        "rank_month_date": picked.get("rank_month_date"),
        "regist_date": picked.get("regist_date"),
        "update_date": picked.get("update_date"),
        "series_name": picked.get("series_name"),
        "is_bl": _bool_int(picked.get("is_bl")),
        "is_tl": _bool_int(picked.get("is_tl")),
        "genres_json": json.dumps(genres, ensure_ascii=False),
        "image_url": image or None,
    }
    if options:
        row["options"] = options
    return row, genres


def enrich_one(
    fetcher: Fetcher, store: Store, cfg, workno: str, source: str
) -> Optional[Dict[str, Any]]:
    """富化单件作品（一次 API 请求）。

    成功：写入作品与分类、移出队列，返回作品行；失败：累计 attempts，返回 None。
    """
    site = _site_for(source, workno, store, cfg)
    url = PRODUCT_API_URL.format(
        site=site, workno=workno, locale=getattr(cfg, "locale", "zh_CN")
    )
    try:
        payload = fetcher.get_json(url)
    except HttpError as exc:
        store.fail_pending(workno)
        LOG.warning("富化失败：%s（%s）", workno, exc)
        return None
    parsed = parse_product(payload, workno)
    if parsed is None:
        store.fail_pending(workno)
        LOG.warning("富化无有效数据：%s", workno)
        return None
    row, genres = parsed
    store.upsert_work(row)
    store.replace_genres(workno, genres)
    store.finish_pending(workno)
    return row


def enrich_pending(
    fetcher: Fetcher,
    store: Store,
    cfg,
    limit: int,
    hot_only: bool = False,
    source_prefix: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, int]:
    """处理待富化队列（每作品一次 API 请求，失败计入 attempts，连续失败会中止）。

    - hot_only=True：仅处理近 `hot_window_days` 天出现在榜单/列表中的作品（热榜模式；
      P20 起跳过已富化——热榜只负责把未入库的新上榜作品带进来）
    - source_prefix：仅处理指定来源前缀的队列项（如 refresh: 语言/数据刷新，P8）
    - source：仅处理「来源完整匹配」的队列项（P19.2 现导入定向富化；自动跳过已富化）
    """
    if source:
        batch = store.pending_batch_exact_source(limit, source)
    elif source_prefix:
        batch = store.pending_batch_by_source(limit, source_prefix)
    elif hot_only:
        batch = store.pending_batch_hot(
            limit,
            window_days=int(getattr(cfg, "hot_window_days", 7)),
            skip_enriched=True,
        )
    else:
        batch = store.pending_batch(limit)
    ok = fail = 0
    consecutive = 0
    enriched_worknos: List[str] = []
    for order, (workno, item_source, _attempts) in enumerate(batch, start=1):
        row = enrich_one(fetcher, store, cfg, workno, item_source)
        if row is None:
            fail += 1
            consecutive += 1
            if consecutive >= FAIL_LIMIT_BEFORE_ABORT:
                LOG.error("连续失败达到 %d 次，中止本轮富化", consecutive)
                break
        else:
            ok += 1
            consecutive = 0
            enriched_worknos.append(workno)
        if order % 50 == 0:
            LOG.info("富化进行中：%d/%d（成功 %d 失败 %d）", order, len(batch), ok, fail)
    if enriched_worknos:
        # P11：顺带批量补记销量/收藏（info/ajax，40 件/请求；失败不影响富化结果）
        try:
            result = sync_sales(fetcher, store, cfg, enriched_worknos)
            LOG.info(
                "销量补记：%d 件（更新 %d，缺失 %d）",
                result["queried"],
                result["updated"],
                result["missing"],
            )
        except (HttpError, ValueError) as exc:
            LOG.warning("销量补记失败（不影响富化结果）：%s", exc)
    return {"ok": ok, "fail": fail}
