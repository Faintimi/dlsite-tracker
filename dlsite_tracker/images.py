"""封面下载：``image_thumb`` → ``out/covers/<workno>.<ext>``（礼貌节流、并发、连接复用）。

约束：
- 仅下载白名单类型（默认游戏）且已富化、带 ``image_url`` 的作品；已存在同名文件则跳过（幂等）；
- ``cfg.images_workers`` > 1 时多线程下载：每个 worker 线程持有独立 Fetcher
  （各自节流与 keep-alive 连接池），聚合速率 = workers 
  ÷ 间隔（默认 4 × 0.25s ≈ 16 张/秒，2026-09-22 经维护者批准）；
- 每次批量数量受 ``limit`` 限制；失败不中断整体流程，计入统计与日志（网络错误由 Fetcher 负责重试）。
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from .export import COVER_EXTENSIONS, find_cover
from .http import Fetcher, HttpError
from .store import Store

LOG = logging.getLogger("dlsite_tracker.images")

MAX_IMAGE_BYTES = 2_000_000


def extension_from_url(url: str) -> str:
    """从 URL 路径推断扩展名（jpeg→jpg；未知/缺失→jpg）。"""
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if suffix == "jpeg":
        return "jpg"
    return suffix if suffix in COVER_EXTENSIONS else "jpg"


def _cover_rows(cfg, store: Store):
    """按白名单取出「已富化且带图」的作品行（新作品优先）。"""
    work_types: List[str] = list(getattr(cfg, "default_work_types", []) or [])
    sql = (
        "SELECT workno, image_url FROM works "
        "WHERE enriched_at IS NOT NULL AND image_url IS NOT NULL AND image_url != '' "
    )
    args: List[Any] = []
    if work_types:
        placeholders = ",".join("?" for _ in work_types)
        sql += f"AND work_type IN ({placeholders}) "
        args.extend(work_types)
    sql += "ORDER BY updated_at DESC, workno"
    return store.conn.execute(sql, args).fetchall()


def list_missing_covers(cfg, store: Store) -> List[Tuple[str, str]]:
    """列出「已富化且缺封面文件」的 (workno, image_url)（新作品优先）。"""
    return [
        (row["workno"], row["image_url"])
        for row in _cover_rows(cfg, store)
        if not find_cover(cfg.out_dir, row["workno"])
    ]


def _download_one(fetcher, cfg, workno: str, url: str) -> str:
    """下载单张封面；返回 downloaded / skipped / failed（不抛网络异常）。"""
    if find_cover(cfg.out_dir, workno):
        return "skipped"
    covers_dir = cfg.out_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    target = covers_dir / f"{workno}.{extension_from_url(url)}"
    try:
        data = fetcher.get_bytes(url, kind="image", max_bytes=MAX_IMAGE_BYTES)
    except HttpError as exc:
        LOG.warning("封面下载失败：%s（%s）", workno, exc)
        return "failed"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return "downloaded"


def _worker_factory(cfg, shared: Fetcher) -> Callable[[], Fetcher]:
    """为每个工作线程生成独立 Fetcher（各自节流 + keep-alive；计数共享）。"""
    lock = threading.Lock()

    def make() -> Fetcher:
        return Fetcher.from_config(cfg, counters=shared.counters, counter_lock=lock)

    return make


def download_entries(
    cfg,
    fetcher: Fetcher,
    entries: List[Tuple[str, str]],
    workers: int | None = None,
    worker_factory: Callable[[], Any] | None = None,
    observer: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, int]:
    """下载给定 (workno, url) 列表；workers>1 时并发（每线程独立 Fetcher）。

    observer：每张完成后回调 ``(已处理数, 总数)``（供调用方写进度 / 周期快照导出）。
    """
    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = list(entries)
    if not entries:
        return results
    if not cfg.images_enabled:
        LOG.info("封面下载已禁用（config [images] enabled=false）")
        return results
    workers = int(workers if workers is not None else getattr(cfg, "images_workers", 1) or 1)
    total = len(entries)
    if workers <= 1:
        for index, (workno, url) in enumerate(entries, start=1):
            results[_download_one(fetcher, cfg, workno, url)] += 1
            if observer is not None:
                observer(index, total)
        return results
    factory = worker_factory or _worker_factory(cfg, fetcher)
    local = threading.local()

    def run(workno: str, url: str) -> str:
        worker = getattr(local, "fetcher", None)
        if worker is None:
            worker = factory()
            local.fetcher = worker
        return _download_one(worker, cfg, workno, url)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run, workno, url) for workno, url in entries]
        for index, future in enumerate(futures, start=1):
            results[future.result()] += 1
            if observer is not None:
                observer(index, total)
    return results


COVER_EXPORT_EVERY = 100  # 封面周期导出频率（每 N 张；补封面过程中应用可边下载边看到）


def download_covers(
    cfg,
    fetcher: Fetcher,
    store: Store,
    limit: int,
    worknos: Optional[Sequence[str]] = None,
    observer: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, int]:
    """兼容入口：列缺口（skipped 含已存在计数）→ 按 limit 限量 → 并发下载。

    worknos（P19.2）：仅补齐清单内作品的封面（现导入定向补图）。
    observer：透传给 download_entries（每张回调一次，供周期写进度 / 快照导出）。
    """
    if not cfg.images_enabled:
        LOG.info("封面下载已禁用（config [images] enabled=false）")
        return {"downloaded": 0, "skipped": 0, "failed": 0}
    rows = _cover_rows(cfg, store)
    if worknos is not None:
        allowed = {str(workno) for workno in worknos}
        rows = [row for row in rows if row["workno"] in allowed]
    missing = [
        (row["workno"], row["image_url"])
        for row in rows
        if not find_cover(cfg.out_dir, row["workno"])
    ]
    pre_existing = len(rows) - len(missing)
    if limit is not None and limit >= 0:
        missing = missing[:limit]
    result = download_entries(cfg, fetcher, missing, observer=observer)
    result["skipped"] += pre_existing
    return result
