"""批量实查（P11；P13 扩展）：站点自有 JSON 接口 `/{site}/product/info/ajax`。

背景与合规（「批量实查」）：
- 发现途径：详情页 `product-price` Vue 组件（`/vue/js/pc/app.js`）用它渲染「販売数」；
- 返回单件 70+ 字段（P13 探明）：`dl_count`（= 販売数）、`wishlist_count`（收藏）、
  `work_type`（类型码，与 product.json 同源同码——可用于批量预分类）、
  `regist_date`（上架日）、`price`、`rate_*` 等；
- `options`（P16 探明）：`#` 分隔的官方徽章 token（SND=音声あり / MS2=音楽あり /
  MV2=動画あり / TRI=体験版 …），与热榜卡片徽章、product.json `work_attributes` 同源；
- 支持逗号批量（实测 80 件/请求 ≈1.8s；P11.2 起）；接口自带 1 分钟级缓存参数；
- robots 全文核对未被禁；按「站点自有 JSON 接口」档位串行请求（默认 1s 间隔），
  批量=总请求更少。
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .http import Fetcher, HttpError
from .store import Store

LOG = logging.getLogger("dlsite_tracker.sales")

SALES_API_URL = (
    "https://www.dlsite.com/{site}/product/info/ajax?product_id={ids}&cdn_cache_min=1"
)
BATCH_SIZE = 80  # 批量件数（P11.2：40→80，请求数减半；URL 长度 ~1KB 内）

# P16：options token 字典（热榜卡片官方徽章）。对照热榜页 HTML：
# icon_SND=音声あり / icon_MS2=音楽あり / icon_MV2=動画あり / icon_TRI=体験版 /
# icon_AIP=AI一部利用 / icon_GRO=グロテスク表現あり / icon_GEN=全年齢 /
# icon_EVT=同人展联动；其余为语言版本 token（JPN/ENG/CHI_HANS…）。
BADGE_TOKENS = ("SND", "MS2", "MV2", "TRI", "AIP", "GRO", "GEN", "EVT", "REV")
LANGUAGE_TOKENS = ("JPN", "ENG", "CHI", "CHI_HANS", "CHI_HANT", "KO_KR")
KNOWN_OPTION_TOKENS = frozenset(BADGE_TOKENS + LANGUAGE_TOKENS)
_OPTION_SPLIT = re.compile(r"[#,\s]+")

SalesValue = Tuple[int, int]  # (dl_count, wishlist_count)


def parse_options(raw: Any) -> str:
    """规范化 options / work_attributes：仅保留已知 token，保序去重，`#` 连接。

    未知 token（平台、类型码、RG 开头、纯数字、genres 名等）一律丢弃——
    白名单见 KNOWN_OPTION_TOKENS，避免把整串属性塞进数据库。
    """
    if raw is None:
        return ""
    picked: List[str] = []
    for token in _OPTION_SPLIT.split(str(raw)):
        if token in KNOWN_OPTION_TOKENS and token not in picked:
            picked.append(token)
    return "#".join(picked)


def _as_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def parse_precise_rating(value: Any) -> float | None:
    """官方两位小数评分；非法或缺失时不伪造精度。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        rating = float(value)
    except ValueError:
        return None
    return round(rating, 2) if math.isfinite(rating) and 0 < rating <= 5 else None


def parse_sales(payload: Any) -> Dict[str, Tuple[int | None, int | None]]:
    """解析 info/ajax 响应：workno → (dl_count, wishlist_count)（缺字段为 None）。"""
    values: Dict[str, Tuple[int | None, int | None]] = {}
    if not isinstance(payload, dict):
        return values
    for workno, item in payload.items():
        if not isinstance(item, dict):
            continue
        dl = _as_count(item.get("dl_count"))
        wishlist = _as_count(item.get("wishlist_count"))
        if dl is None and wishlist is None:
            continue
        values[str(workno)] = (dl, wishlist)
    return values


def fetch_sales(
    fetcher: Fetcher, site: str, worknos: Sequence[str]
) -> Dict[str, Tuple[int | None, int | None]]:
    """批量拉取销量/收藏（兼容包装：内部走 fetch_product_info）。"""
    infos = fetch_product_info(fetcher, site, worknos)
    return {
        workno: (info["dl_count"], info["wishlist_count"])
        for workno, info in infos.items()
        if info["dl_count"] is not None or info["wishlist_count"] is not None
    }


def parse_product_info(payload: Any) -> Dict[str, Dict[str, Any]]:
    """解析为完整信息（P13/P16）：workno → {dl_count, wishlist_count, work_type,

    regist_date, options, rating_precise, rating_count}。缺失时保留 None/空串。
    """
    infos: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return infos
    for workno, item in payload.items():
        if not isinstance(item, dict):
            continue
        rating_count = _as_count(item.get("rate_count"))
        precise_rating = parse_precise_rating(item.get("rate_average_2dp"))
        infos[str(workno)] = {
            "dl_count": _as_count(item.get("dl_count")),
            "wishlist_count": _as_count(item.get("wishlist_count")),
            "work_type": str(item.get("work_type") or ""),
            "regist_date": str(item.get("regist_date") or ""),
            "options": parse_options(item.get("options")),
            "rating_precise": precise_rating if rating_count != 0 else None,
            "rating_count": rating_count,
        }
    return infos


def fetch_product_info(
    fetcher: Fetcher, site: str, worknos: Sequence[str]
) -> Dict[str, Dict[str, Any]]:
    """批量拉取完整产品信息（P13；按 BATCH_SIZE 分片）。"""
    infos: Dict[str, Dict[str, Any]] = {}
    ids = [str(workno) for workno in worknos]
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        url = SALES_API_URL.format(site=site, ids=",".join(chunk))
        found = parse_product_info(fetcher.get_json(url))
        missing = [workno for workno in chunk if workno not in found]
        if missing:
            LOG.info("产品信息接口未返回 %d 件（可能已下架）：%s …", len(missing), missing[0])
        infos.update(found)
    return infos


def save_sales(
    store: Store,
    site: str,
    values: Dict[str, Tuple[int | None, int | None]],
    source: str = "info-ajax",
    options: Optional[Dict[str, str]] = None,
) -> int:
    """写入销量/收藏快照与 options 徽章 token；返回写入的作品数。"""
    if not values and not options:
        return 0
    sales = {workno: data[0] for workno, data in values.items() if data[0] is not None}
    wishlist = {workno: data[1] for workno, data in values.items() if data[1] is not None}
    picked = {workno: tokens for workno, tokens in (options or {}).items() if tokens}
    if sales or wishlist or picked:
        store.record_sales_many(
            site, sales, source=source, wishlist=wishlist or None, options=picked or None
        )
    return len(values)


def save_product_info(
    store: Store, site: str, infos: Dict[str, Dict[str, Any]],
    source: str = "info-ajax", queried_worknos: Optional[Sequence[str]] = None,
) -> int:
    """统一落库批查字段，避免导入/富化/刷新任一路径丢掉精确评分。"""
    values = {
        workno: (info["dl_count"], info["wishlist_count"])
        for workno, info in infos.items()
        if info["dl_count"] is not None or info["wishlist_count"] is not None
    }
    options = {workno: info["options"] for workno, info in infos.items() if info["options"]}
    updated = save_sales(store, site, values, source=source, options=options)
    ratings = {
        workno: info["rating_precise"] for workno, info in infos.items()
        if info["rating_precise"] is not None
    }
    counts = {
        workno: info["rating_count"] for workno, info in infos.items()
        if info["rating_count"] is not None
    }
    store.record_precise_ratings(site, queried_worknos or list(infos), ratings, counts)
    return updated


def sync_sales(
    fetcher: Fetcher,
    store: Store,
    cfg,
    worknos: Sequence[str],
    source: str = "info-ajax",
) -> Dict[str, int]:
    """拉取并写入（供命令与富化流程复用）；返回 {queried, updated, missing}。"""
    ids = list(worknos)
    if not ids:
        return {"queried": 0, "updated": 0, "missing": 0}
    site = cfg.sites[0] if getattr(cfg, "sites", None) else "maniax"
    infos = fetch_product_info(fetcher, site, ids)
    updated = save_product_info(store, site, infos, source=source, queried_worknos=ids)
    return {"queried": len(ids), "updated": updated, "missing": len(ids) - updated}
