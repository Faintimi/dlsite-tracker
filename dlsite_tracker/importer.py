"""渐进导入（P10）：把「最近 N 年」的作品按编号边界批量富化入库，支持断点续传。

原理（实测校准，「渐进导入」）：
- DLsite 作品号有两个接续的系列：
  - 旧系列 RJ+6 位（编号 1 ~ 441,526）：2006-02 ~ 2023-01-25 注册，此后停用；
  - 现代系列 RJ+8 位（RJ01xxxxxxxx，编号 1,000,015 ~ 1,725,817）：2023 起启用，
    编号随注册时间近似线性增长（约 1.5 万 ~ 2 万/月）。
- 「最近 N 年」用「编号边界」界定：按校准锚点线性插值/外推出「N 年前」对应的编号，
  编号不小于边界的作品即候选。比 sitemap 的 lastmod 更准（lastmod 会把老作品的
  改价、翻译等更新也算作“近期”，造成大量无关候选）。
- 候选直接来自 pending 台账（P6 已全量登记 42.7 万作品号），无需再爬 sitemap。
- 断点：任务状态存 `import_job` 表（单行）；每完成一件作品立即推进（移出 pending +
  更新计数）；任何时刻中断（Ctrl+C、关机、断电）后重跑同一命令都会从断点继续，
  不会重复富化、也不会跳过作品。进度同步镜像到 out/import-progress.json 供应用横幅。
- 质量门槛（[import] fresh_days / min_sales，默认 90 天 / 2000，两项都 >0 才启用）：
  最近 fresh_days 天发售的新作一律收录；更早的作品先经 info/ajax **批量实查销量**
  （P11，默认 80 件/请求），仅 dl_count ≥ min_sales 的才富化——未达标的在富化前直接跳过；
  富化后再按真实发售日期复核一次（编号边界是估算值）。
- 批量预分类（P13）：每批 80 件先经 info/ajax 实查（1 次请求），同时取回销量/收藏、
  work_type（非游戏直接排除、不抓详情）与 regist_date（真实上架日，替代编号估算做门槛判定）；
  只有通过预筛的游戏才逐件请求 product.json。
- 富化顺序：销量已知优先（榜单可见）→ 编号新到旧（新作品优先）。
- 封面自愈（P12.1）：导入过程中每累计富化 cover_trigger 件顺带补一批封面（cover_batch）；
  暂停/完成时补尾批；中断不补。配置见 [import] cover_trigger / cover_batch（0 = 关闭）。

校准方法（重新校准用）：从最新分片抽若干位于不同位置的「非热榜」作品，逐一请求
product.json 读取 regist_date，填入 ANCHORS 的（编号, 日期）点即可。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .jobs import PipelineLock, process_alive
from .discovery import catalog_page_url, extract_catalog_items, extract_sales
from .enrich import enrich_one
from .export import export_snapshot
from .http import HttpError
from .images import download_covers, download_entries, list_missing_covers
from .progress import write_task_progress
from .sales import fetch_product_info, save_sales
from .store import Store

LOG = logging.getLogger("dlsite_tracker.importer")

PROGRESS_SCHEMA_VERSION = 2  # P18：新增 source / walk_done / cursor_page 字段


def pause_requested(cfg, pipeline_lock: Optional[PipelineLock] = None) -> bool:
    """P22.3：暂停标志（data/import.pause）。

    经 bash 后台（&）启动的 python 会忽略 SIGINT（实测验证），暂停/取消不能只靠
    信号——导入循环每翻一页、每处理一件都检查该标志，用户点「暂停」立即可靠生效。
    """
    base = getattr(cfg, "data_dir", None) or Path(cfg.out_dir).parent
    data_dir = Path(base)
    if (data_dir / "import.pause").exists():
        return True
    yield_flag = data_dir / "import.yield"
    if pipeline_lock is None or not yield_flag.exists():
        return False
    # 更新链优先：在作品/页面边界让出共享锁，进程与导入参数保持原样，更新后续跑。
    pipeline_lock.release()
    while yield_flag.exists():
        if (data_dir / "import.pause").exists():
            return True
        try:
            holder = int(yield_flag.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            holder = -1
        if holder > 0 and not process_alive(holder):
            yield_flag.unlink(missing_ok=True)
            break
        time.sleep(0.2)
    while pipeline_lock.acquire() is not None:
        if (data_dir / "import.pause").exists():
            return True
        time.sleep(0.2)
    return (data_dir / "import.pause").exists()
BATCH_ROWS = 80  # 每批从队列取多少件（P13：与 info/ajax 批量对齐，80 件/请求）
PRINT_EVERY = 25  # 终端进度打印频率
PROGRESS_EVERY = 10  # 进度文件写入频率（每 N 件；DB 计数仍逐件落盘）
EXPORT_EVERY = 200  # 周期导出频率（每 N 件；应用可边导入边看到新增作品）

SOURCE_CATALOG = "catalog"  # P18：候选来源 = 游戏目录遍历（新任务默认）
SOURCE_NUMBERS = "numbers"  # 旧编号扫描（保留为审计工具：--source numbers）
CATALOG_PAGE_SIZE = 100  # 目录页每页条目数（站点上限 100，per_page>100 返回异常）
CATALOG_MAX_PAGES = 500  # 遍历安全阀（当前游戏目录约 359 页）
CATALOG_END_EMPTY_PAGES = 2  # 连续 N 页整页无「窗口内」条目 → 视为越过窗口边界
WALK_CHUNK_PAGES = 5  # P24：边登记边入库的翻页粒度（每段 N 页后先处理已登记候选）
PREFILTER_MARGIN_DAYS = 60  # 卡面销量预筛的编号↔日期保险带（覆盖锚点估计误差）

SERIES_OLD = "old"  # RJ+6 位（2006-02 ~ 2023-01）
SERIES_MODERN = "modern"  # RJ+8 位（RJ01xxxxxxxx，2023 至今）

# 注册日期校准锚点：编号数字 → 注册日期（2026-09-21 抽样实测）
ANCHORS: Dict[str, List[Tuple[int, str]]] = {
    SERIES_OLD: [
        (419548, "2022-09-20"),
        (430000, "2022-10-23"),
        (441526, "2023-01-25"),
    ],
    SERIES_MODERN: [
        (1146692, "2024-01-26"),
        (1311399, "2024-12-21"),
        (1498016, "2025-11-01"),
        (1719646, "2026-09-13"),
    ],
}


def workno_series(workno: str) -> Optional[str]:
    """由长度判断编号系列（8 = 旧系列 RJ+6 位；10 = 现代系列 RJ+8 位）。"""
    if len(workno) == 8 and workno.startswith("RJ"):
        return SERIES_OLD
    if len(workno) == 10 and workno.startswith("RJ"):
        return SERIES_MODERN
    return None


def workno_number(workno: str) -> Optional[int]:
    """提取编号数字部分（RJ441526 → 441526；RJ01024693 → 1024693）。"""
    digits = workno[2:] if workno.startswith("RJ") else workno
    if not digits.isdigit():
        return None
    return int(digits)


def _age_days(regist_date: Optional[str]) -> Optional[int]:
    """作品已发售天数（无法解析时返回 None）。"""
    if not regist_date:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            released = datetime.strptime(str(regist_date), fmt)
        except ValueError:
            continue
        return (datetime.now() - released).days
    return None


def _is_old(workno: str, fresh_old: int, fresh_modern: int) -> bool:
    """编号是否早于「新作窗」边界（旧作品）。"""
    number = workno_number(workno)
    if number is None:
        return False
    boundary = fresh_old if workno_series(workno) == SERIES_OLD else fresh_modern
    return number < boundary


def workno_in_window(workno: str, boundary_old: int, boundary_modern: int) -> bool:
    """编号是否在导入窗口内（与 store._import_where 同口径）。"""
    number = workno_number(workno)
    series = workno_series(workno)
    if number is None or series is None:
        return False
    boundary = boundary_old if series == SERIES_OLD else boundary_modern
    return number >= boundary


def catalog_source_name(site: str) -> str:
    """目录遍历登记用来源名（候选查询按 `catalog:` 前缀过滤）。"""
    return f"{SOURCE_CATALOG}:{site}:game"


def _download_covers_safe(cfg, fetcher, store: Store, limit: int) -> Dict[str, int]:
    """封面自愈：下载一批封面；失败只记日志，不中断导入。"""
    try:
        return download_covers(cfg, fetcher, store, limit)
    except (HttpError, OSError) as exc:
        LOG.warning("封面自愈失败（不影响导入）：%s", exc)
        return {"downloaded": 0, "skipped": 0, "failed": 0}


def _download_entries_safe(cfg, fetcher, entries) -> Dict[str, int]:
    """按清单批量下载封面（收尾用）；异常只记日志，不中断导入。"""
    try:
        return download_entries(cfg, fetcher, entries)
    except (HttpError, OSError) as exc:
        LOG.warning("封面批量下载失败（不影响导入）：%s", exc)
        return {"downloaded": 0, "skipped": 0, "failed": 0}


def acquire_import_lock(cfg):
    """尝试独占导入锁（data/import.lock）；已被占用时返回 None。

    防止手动导入与每日调度续传并发（两进程会重复请求、计数竞态）。
    Windows 与 POSIX 均使用同一系统文件锁，进程退出时自动释放。
    """
    path = Path(cfg.data_dir) / "import.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = PipelineLock(path)
    return lock if lock.acquire() is None else None


def release_import_lock(handle) -> None:
    if handle is not None:
        handle.release()


def _slope(left: Tuple[datetime, int], right: Tuple[datetime, int]) -> float:
    days = (right[0] - left[0]).days
    return (right[1] - left[1]) / days if days else 0.0


def estimate_date(number: int, anchors: Sequence[Tuple[int, str]]) -> datetime:
    """编号 → 发售日（estimate_number 的逆插值；越界按端点斜率外推）。"""
    points = sorted(
        (datetime.strptime(date, "%Y-%m-%d"), num) for num, date in anchors
    )
    if len(points) < 2:
        raise ValueError("校准锚点至少需要 2 个")
    if number <= points[0][1]:
        slope = _slope(points[0], points[1])
        days = (points[0][1] - number) / slope if slope else 0.0
        return points[0][0] - timedelta(days=days)
    for left, right in zip(points, points[1:]):
        if number <= right[1]:
            slope = _slope(left, right)
            days = (number - left[1]) / slope if slope else 0.0
            return left[0] + timedelta(days=days)
    slope = _slope(points[-2], points[-1])
    days = (number - points[-1][1]) / slope if slope else 0.0
    return points[-1][0] + timedelta(days=days)


# P23：目录页 ↔ 发售日的实测校准点（page, 约发售日）——用于续深起步估算
PAGE_CALIBRATION = (
    (100, "2023-10-01"),  # P18 实测：第 100 页 ≈ 2023-10
    (359, "2006-07-01"),  # P18 实测：末页 ≈ 2006
)


def estimate_page_for_date(target: datetime, now: Optional[datetime] = None) -> int:
    """发售日 → 游戏目录页号估算（续深起步用；调用方自行留安全余量）。

    校准点：第 1 页 ≈ 今天、第 100 页 ≈ 2023-10（实测）、第 359 页 ≈ 2006（实测），
    分段线性；越界按端点斜率外推。返回 ≥1 的页号。
    """
    points = [(_naive(now), 1.0)]
    for page_number, date in PAGE_CALIBRATION:
        points.append((datetime.strptime(date, "%Y-%m-%d"), float(page_number)))
    target = _naive(target)
    if target >= points[0][0]:
        return 1
    for (d1, p1), (d2, p2) in zip(points, points[1:]):
        if target >= d2:
            span = max(1, (d1 - d2).days)
            ratio = (d1 - target).days / span
            return max(1, int(round(p1 + ratio * (p2 - p1))))
    d1, p1 = points[-2]
    d2, p2 = points[-1]
    span = max(1, (d1 - d2).days)
    ratio = (d1 - target).days / span
    return max(1, int(round(p1 + ratio * (p2 - p1))))


def boundary_cutoff_date(
    boundary_old: int, boundary_modern: int, now: Optional[datetime] = None
) -> datetime:
    """导入边界（编号对）→ 大约的截止发售日（现代边界 ≥1,000,015 时才用它反插）。"""
    if int(boundary_modern) >= 1_000_015:
        return estimate_date(int(boundary_modern), ANCHORS[SERIES_MODERN])
    return estimate_date(int(boundary_old), ANCHORS[SERIES_OLD])


COVERAGE_SCHEMA_VERSION = 1


def coverage_path(cfg) -> Path:
    """已覆盖最深位置记录文件（P23；供续深模式跳过重扫）。"""
    return Path(cfg.out_dir) / "import-coverage.json"


def save_coverage(cfg, job: Dict[str, Any], page: Optional[int]) -> None:
    """P23：记录「已覆盖最深位置」。

    仅在本次比已记录更深（boundary_old 更小）时覆写；page 可为 None
    （无真实遍历页号，如编号来源导入——续深时按边界日期估算）。
    """
    try:
        boundary_old = int(job["boundary_old"])
        boundary_modern = int(job["boundary_modern"])
    except (KeyError, TypeError, ValueError):
        return
    path = coverage_path(cfg)
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if int(existing.get("boundary_old") or 10 ** 9) <= boundary_old:
                return  # 已有记录不浅于本次 → 保留更深的那条
        except (OSError, ValueError, TypeError):
            pass
    try:
        cutoff = boundary_cutoff_date(boundary_old, boundary_modern)
    except (ValueError, ZeroDivisionError):
        cutoff = None
    now = datetime.now()
    covered_days = max(0, (now - cutoff).days) if cutoff else None
    payload = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "updated_at": now.astimezone().isoformat(timespec="seconds"),
        "years": str(job.get("years")),
        "boundary_old": boundary_old,
        "boundary_modern": boundary_modern,
        "page": int(page) if page else None,
        "covered_days": covered_days,
        "covered_years": round(covered_days / 365.25, 2) if covered_days else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def estimate_number(cutoff: datetime, anchors: Sequence[Tuple[int, str]]) -> int:
    """由（编号, 注册日期）锚点线性插值/外推 `cutoff` 日期对应的编号。"""
    points: List[Tuple[datetime, int]] = sorted(
        (datetime.strptime(date, "%Y-%m-%d"), number) for number, date in anchors
    )
    if len(points) < 2:
        raise ValueError("校准锚点至少需要 2 个")
    if cutoff <= points[0][0]:
        slope = _slope(points[0], points[1])
        return int(round(points[0][1] - slope * (points[0][0] - cutoff).days))
    for left, right in zip(points, points[1:]):
        if cutoff <= right[0]:
            slope = _slope(left, right)
            return int(round(left[1] + slope * (cutoff - left[0]).days))
    slope = _slope(points[-2], points[-1])
    return int(round(points[-1][1] + slope * (cutoff - points[-1][0]).days))


def _naive(reference: Optional[datetime]) -> datetime:
    value = reference or datetime.now()
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def boundaries_for_days(days: int, now: Optional[datetime] = None) -> Tuple[int, int]:
    """返回「days 天前」对应的（旧系列边界, 现代系列边界）。"""
    cutoff = _naive(now) - timedelta(days=int(days))
    return (
        estimate_number(cutoff, ANCHORS[SERIES_OLD]),
        estimate_number(cutoff, ANCHORS[SERIES_MODERN]),
    )


def boundaries_for_years(years: str, now: Optional[datetime] = None) -> Tuple[int, int]:
    """返回（旧系列边界, 现代系列边界）。

    支持三种形式（P22）：
      - ``"all"`` → (0, 0)（全部作品）
      - 年数（如 ``"5"``）→ 最近 N 年
      - ``"since:YYYY"`` → 自该年 1 月 1 日起至今
    """
    text = str(years).strip()
    if text.lower() == "all":
        return 0, 0
    if text.lower().startswith("since:"):
        try:
            year = int(text.split(":", 1)[1])
        except ValueError:
            raise ValueError(f"since: 需要年份（如 since:2018）：{years}")
        if year < 2005 or year > 2100:
            raise ValueError(f"since: 年份需在 2005–2100 之间：{years}")
        cutoff = datetime(year, 1, 1)
        days = (_naive(now) - cutoff).days
        if days < 1:
            raise ValueError(f"since:{year} 的开始时间在未来（当前 {_naive(now).date()}）")
        return boundaries_for_days(days, now=now)
    years_int = int(text)
    if years_int < 1:
        raise ValueError(f"years 需要 ≥1、all 或 since:YYYY：{years}")
    return boundaries_for_days(365 * years_int, now=now)


def years_label(years) -> str:
    """导入范围值 → 可读标签（P22）：全部 / 自 YYYY 年 1 月 / 最近 N 年。"""
    text = str(years).strip()
    if text.lower() == "all":
        return "全部"
    if text.lower().startswith("since:"):
        return f"自 {text.split(':', 1)[1]} 年 1 月"
    return f"最近 {text} 年"


def resolve_job(
    store: Store,
    cfg,
    years: Optional[str],
    restart: bool,
    source: Optional[str] = None,
    start_page: Optional[int] = None,
) -> Dict[str, Any]:
    """读取现有任务或按 `years`/`source` 新建（质量门槛一并快照）；冲突时给出明确提示。"""
    job = store.get_import_job()
    if restart and years is None and job is not None:
        years = str(job["years"])  # 用原范围重建
    if restart:
        store.delete_import_job()
        job = None
    if job is not None and years is not None and str(years) != str(job["years"]):
        if job["phase"] == "done":
            job = None  # 已完成的任务：允许直接换范围重建
        else:
            raise ValueError(
                f"已有进行中的导入任务（{years_label(job['years'])}）；"
                "如需更换范围请加 --restart（已入库作品会保留）"
            )
    if job is not None and source is not None:
        job_source = str(job.get("source") or SOURCE_NUMBERS)
        if job_source != source:
            if job["phase"] == "done":
                job = None  # 已完成的任务：允许直接换来源重建
            else:
                raise ValueError(
                    f"已有进行中的导入任务（来源 {job_source}）；"
                    "如需切换来源请加 --restart（已入库作品会保留）"
                )
    if job is None:
        if years is None:
            raise ValueError("请指定 --years N|all|since:YYYY 以开始导入（N=1–30 年）")
        boundary_old, boundary_modern = boundaries_for_years(str(years))
        min_sales = int(getattr(cfg, "import_min_sales", 0) or 0)
        fresh_days = int(getattr(cfg, "import_fresh_days", 0) or 0)
        if min_sales > 0 and fresh_days > 0:
            fresh_old, fresh_modern = boundaries_for_days(fresh_days)
        else:  # 过滤关闭：新鲜度子句退化为边界本身（等价于全量导入）
            min_sales = 0
            fresh_days = 0
            fresh_old, fresh_modern = boundary_old, boundary_modern
        store.save_import_job(
            years=str(years),
            phase="enrich",
            boundary_old=boundary_old,
            boundary_modern=boundary_modern,
            fresh_old=fresh_old,
            fresh_modern=fresh_modern,
            min_sales=min_sales,
            fresh_days=fresh_days,
            source=source or SOURCE_CATALOG,
            start_page=int(start_page or 0),
        )
        job = store.get_import_job()
        LOG.info(
            "新建导入任务：最近 %s（来源：%s；边界：旧系列 ≥%d；现代系列 ≥%d；门槛：%s）",
            years,
            source or SOURCE_CATALOG,
            boundary_old,
            boundary_modern,
            (
                f"{fresh_days} 天内新作全收，更早仅收销量 ≥{min_sales}"
                if min_sales > 0
                else "未启用（全量）"
            ),
        )
    return job


def write_progress(
    cfg, job: Optional[Dict[str, Any]], remaining: int, running: bool, note: str = ""
) -> None:
    """把任务进度原子写入 out/import-progress.json（供应用显示横幅）。"""
    if job is None:
        return
    enriched = int(job["enriched"])
    excluded = int(job["excluded"])
    skipped = int(job["skipped"])
    failed = int(job["failed"])
    write_task_progress(
        Path(cfg.out_dir) / "import-progress.json",
        str(job["phase"]),
        years=str(job["years"]),
        schema_version=PROGRESS_SCHEMA_VERSION,
        extra={
            "running": bool(running),
            "source": str(job.get("source") or SOURCE_NUMBERS),
            "walk_done": bool(int(job.get("walk_done") or 0)),
            "cursor_page": int(job.get("cursor_page") or 0),
            "boundaries": {
                "old": int(job["boundary_old"]),
                "modern": int(job["boundary_modern"]),
            },
            "min_sales": int(job["min_sales"]),
            "fresh_days": int(job["fresh_days"]),
            "enriched": enriched,
            "excluded": excluded,
            "skipped": skipped,
            "failed": failed,
            "remaining": int(remaining),
            "total": enriched + excluded + skipped + failed + int(remaining),
            "note": note,
        },
    )


def run_catalog_walk(
    fetcher, store: Store, cfg, job: Dict[str, Any], max_pages: Optional[int] = None,
    pipeline_lock: Optional[PipelineLock] = None,
) -> int:
    """P18 目录遍历：把游戏目录（发售日新→旧）逐页登记进候选队列。

    - 断点续传：游标 `cursor_page` 每页推进（中断安全）；完成后置 `walk_done`。
    - P24：`max_pages` 限定本次最多翻几页（边登记边入库的交错粒度）；未走完时
      不置 `walk_done`，游标已持久化，下一段从断点继续。
    - 停止条件：连续 CATALOG_END_EMPTY_PAGES 页整页无「窗口内」条目（越过边界）、
      或到达末页（条目数 < per_page；超出末页站点返回 404，同样按结束处理）。
    - 登记前过滤已富化/已排除（避免重复富化）；页内卡面销量顺带入库（供预筛）。
    - 返回本次遍历登记的条目数。
    """
    boundary_old = int(job["boundary_old"])
    boundary_modern = int(job["boundary_modern"])
    site = cfg.sites[0] if getattr(cfg, "sites", None) else "maniax"
    source = catalog_source_name(site)
    page = int(job.get("cursor_page") or 0)
    empty_pages = 0
    registered = 0
    walked = 0
    while True:
        if pause_requested(cfg, pipeline_lock):
            raise KeyboardInterrupt  # P22.3：暂停标志生效（后台进程忽略 SIGINT 的兜底）
        page += 1
        try:
            html = fetcher.get_text(
                catalog_page_url(site, "game", page, CATALOG_PAGE_SIZE), kind="page"
            )
        except HttpError as exc:
            if page > 1 and "HTTP 404" in str(exc):
                break  # 超出末页（实测 404）→ 遍历结束
            raise
        items = extract_catalog_items(html)
        if not items:
            if page == 1:
                raise ValueError("目录页解析为空（页面结构可能变化）：第 1 页")
            break  # 空页（防御）：按结束处理
        sales = extract_sales(html)
        in_window = [
            workno
            for workno in items
            if workno_in_window(workno, boundary_old, boundary_modern)
        ]
        fresh = store.filter_known_worknos(in_window)
        if fresh:
            store.add_catalog_pending(fresh, source=source)
            registered += len(fresh)
        known_sales = {workno: sales[workno] for workno in in_window if workno in sales}
        if known_sales:
            store.record_sales_many(site, known_sales, source=source)
        store.update_import_job(cursor_page=page)
        job = store.get_import_job()
        if job is None:
            # P22.2：任务定义被外部取消（幽灵检测）——立即停止，避免无账空转
            print("[导入] 任务定义已被外部取消；停止目录遍历", flush=True)
            return registered
        remaining = store.import_remaining(
            boundary_old, boundary_modern, source_prefix=f"{SOURCE_CATALOG}:"
        )
        write_progress(
            cfg,
            job,
            remaining,
            running=True,
            note=f"目录遍历中（第 {page} 页，累计登记 {registered} 件）",
        )
        print(
            f"[导入] 目录遍历第 {page} 页：窗口内 {len(in_window)} 件"
            f"（新登记 {len(fresh)}）；累计登记 {registered}",
            flush=True,
        )
        walked += 1
        if max_pages is not None and walked >= max_pages:
            return registered  # P24：先回去处理已登记候选；游标已持久化，下段续走
        if in_window:
            empty_pages = 0
        else:
            empty_pages += 1
            if empty_pages >= CATALOG_END_EMPTY_PAGES:
                break
        if len(items) < CATALOG_PAGE_SIZE:
            break  # 末页
        if page >= CATALOG_MAX_PAGES:
            LOG.warning("目录遍历达到安全阀 %d 页，提前停止", CATALOG_MAX_PAGES)
            break
    store.update_import_job(
        walk_done=1, note=f"目录遍历完成（共 {page} 页，登记 {registered} 件）"
    )
    save_coverage(cfg, store.get_import_job() or job, page)  # P23：记录已覆盖最深位置
    return registered


def run_import(
    fetcher,
    store: Store,
    cfg,
    years: Optional[str],
    restart: bool = False,
    limit: Optional[int] = None,
    source: Optional[str] = None,
    start_page: Optional[int] = None,
    pipeline_lock: Optional[PipelineLock] = None,
) -> Dict[str, Any]:
    """执行（或续传）渐进导入；返回本次会话的统计。

    - limit=None：不限量，一直处理到候选清空（或被中断）；
    - P24：目录遍历与富化交错进行（每走 WALK_CHUNK_PAGES 页先处理一批候选，边登记边入库）；
    - 销量门槛（P11）：老作品先实查销量（info/ajax 批量），未达 min_sales 的在富化前跳过；
    - 中断安全：每件作品完成即落盘（pending 移出 + 计数 + 进度文件）。
    """
    job = resolve_job(
        store,
        cfg,
        str(years) if years is not None else None,
        restart,
        source=source,
        start_page=start_page,
    )
    # P22.3：清除遗留的暂停标志（新会话不应立即暂停）
    try:
        base = getattr(cfg, "data_dir", None) or Path(cfg.out_dir).parent
        (Path(base) / "import.pause").unlink()
    except OSError:
        pass
    source_kind = str(job.get("source") or SOURCE_NUMBERS)
    boundary_old = int(job["boundary_old"])
    boundary_modern = int(job["boundary_modern"])
    fresh_old = int(job["fresh_old"])
    fresh_modern = int(job["fresh_modern"])
    min_sales = int(job["min_sales"])
    fresh_days = int(job["fresh_days"])
    gate_on = min_sales > 0 and fresh_days > 0
    skip_boundaries = boundaries_for_days(fresh_days + PREFILTER_MARGIN_DAYS) if gate_on else (0, 0)
    cover_trigger = int(getattr(cfg, "import_cover_trigger", 0) or 0)
    cover_batch = int(getattr(cfg, "import_cover_batch", 300) or 300)
    cover_enabled = (
        cover_trigger > 0 and cover_batch > 0 and bool(getattr(cfg, "images_enabled", True))
    )
    since_cover = 0
    site = cfg.sites[0] if getattr(cfg, "sites", None) else "maniax"
    base = {
        "enriched": int(job["enriched"]),
        "excluded": int(job["excluded"]),
        "skipped": int(job["skipped"]),
        "failed": int(job["failed"]),
    }
    session = {"enriched": 0, "excluded": 0, "skipped": 0, "failed": 0}
    prefix = f"{SOURCE_CATALOG}:" if source_kind == SOURCE_CATALOG else None
    walk_failed = False
    # P24：遍历与富化交错（边登记边入库）——每处理一批前先走一小段目录，
    # 不再等全部遍历完毕才开始入库；walk_pending 在 walk_done 置位后关闭
    walk_pending = (
        source_kind == SOURCE_CATALOG
        and job["phase"] != "done"
        and not int(job.get("walk_done") or 0)
    )

    remaining = store.import_remaining(boundary_old, boundary_modern, source_prefix=prefix)
    walk_ok = source_kind != SOURCE_CATALOG or bool(int(job.get("walk_done") or 0))
    if job["phase"] == "done" or (remaining == 0 and walk_ok):
        store.update_import_job(phase="done", note="已完成")
        write_progress(cfg, store.get_import_job(), 0, running=False, note="已完成")
        return {"status": "done", "session": session, "job": store.get_import_job(), "remaining": 0}

    keep_types = [str(code) for code in (getattr(cfg, "default_work_types", []) or [])]
    write_progress(cfg, job, remaining, running=True, note="")
    interrupted = False
    try:
        while True:
            if pause_requested(cfg, pipeline_lock):
                raise KeyboardInterrupt  # P22.3：暂停标志生效（按批检查）
            processed = sum(session.values())
            if limit is not None and processed >= limit:
                break
            # P24：先走一小段目录（边登记边入库），再处理一批候选
            if walk_pending and not walk_failed:
                try:
                    run_catalog_walk(fetcher, store, cfg, job, max_pages=WALK_CHUNK_PAGES, pipeline_lock=pipeline_lock)
                except HttpError as exc:
                    walk_failed = True
                    LOG.error("目录遍历失败（%s）；先处理已登记候选，重跑可续传", exc)
                    store.update_import_job(note="目录遍历中断（重跑续传）")
                job = store.get_import_job()
                if job is None:
                    # P22.2：遍历期间任务被外部取消 → 结束会话（不再以幽灵状态继续）
                    print("[导入] 任务定义已被外部取消；本次会话结束", flush=True)
                    return {"status": "cancelled", "session": session, "job": None, "remaining": 0}
                walk_ok = bool(int(job.get("walk_done") or 0))
                if walk_ok:
                    walk_pending = False
                remaining = store.import_remaining(
                    boundary_old, boundary_modern, source_prefix=prefix
                )
            take = BATCH_ROWS if limit is None else max(min(BATCH_ROWS, limit - processed), 1)
            batch = store.import_candidates(
                take, boundary_old, boundary_modern, source_prefix=prefix
            )
            if not batch:
                if walk_pending and not walk_failed:
                    continue  # P24：队列暂时空了，但目录还没走完——继续登记下一段
                break
            worknos = [workno for workno, _ in batch]
            sources = dict(batch)
            # P13：整批产品信息实查（info/ajax，80 件/请求）——同时取得
            # 销量/收藏（门槛与入库）、work_type（游戏判别）、regist_date（真实上架日）
            infos: Dict[str, Dict[str, Any]] = {}
            # P18 零请求预筛：目录来源 +「编号已明显过窗」+ 卡面销量低于门槛 → 跳过实查
            prefilter_skipped = set()
            if gate_on and prefix is not None:
                skip_old, skip_modern = skip_boundaries
                for workno in worknos:
                    known = store.get_work_sales(workno)
                    if (
                        known is not None
                        and known < min_sales
                        and _is_old(workno, skip_old, skip_modern)
                    ):
                        prefilter_skipped.add(workno)
            to_query = [workno for workno in worknos if workno not in prefilter_skipped]
            try:
                infos = fetch_product_info(fetcher, site, to_query) if to_query else {}
            except HttpError as exc:
                if gate_on:
                    LOG.error("批量实查失败（%s）；本轮中止，重跑可续传", exc)
                    break
                LOG.warning("批量实查失败，本轮继续富化（销量稍后可用 sales 命令补）：%s", exc)
            for workno in worknos:
                if pause_requested(cfg, pipeline_lock):
                    raise KeyboardInterrupt  # P22.3：暂停标志生效（按件检查）
                info = infos.get(workno) or {}
                dl_count = info.get("dl_count")
                work_type = str(info.get("work_type") or "")
                age_days = _age_days(info.get("regist_date"))
                if workno in prefilter_skipped:
                    # P18 预筛命中：卡面销量低于门槛且编号明显早于新作窗 → 不实查直接跳过
                    store.finish_pending(workno)
                    session["skipped"] += 1
                elif keep_types and work_type and work_type not in keep_types:
                    # P13 预分类：类型已知且非游戏 → 不入库、不抓详情（与 product.json 同码）
                    store.add_excluded(workno, work_type)
                    store.finish_pending(workno)
                    session["excluded"] += 1
                elif (
                    gate_on
                    and (
                        age_days > fresh_days
                        if age_days is not None
                        else _is_old(workno, fresh_old, fresh_modern)
                    )
                    and (dl_count or 0) < min_sales
                ):
                    # 老作品且实查销量未达门槛：不富化（移出候选；日后上热榜仍可被热榜模式补收）
                    store.finish_pending(workno)
                    session["skipped"] += 1
                    LOG.info("销量未达门槛，跳过：%s（dl_count=%s）", workno, dl_count)
                else:
                    if workno in infos:
                        save_sales(
                            store,
                            site,
                            {workno: (dl_count, info.get("wishlist_count"))},
                            options={workno: info["options"]} if info.get("options") else None,
                        )
                    row = enrich_one(fetcher, store, cfg, workno, sources[workno])
                    if row is None:
                        session["failed"] += 1
                    elif keep_types and str(row.get("work_type") or "") not in keep_types:
                        # 非游戏：记入排除清单并删除，避免下次再被候选选中
                        store.add_excluded(workno, row.get("work_type"))
                        store.delete_work(workno)
                        session["excluded"] += 1
                    else:
                        age_days = _age_days(row.get("regist_date"))
                        known_sales = store.get_work_sales(workno)
                        if (
                            gate_on
                            and age_days is not None
                            and age_days > fresh_days
                            and (known_sales or 0) < min_sales
                        ):
                            # 复核：发卖超过 fresh_days 且销量未达门槛 → 忽略（移出库）
                            store.delete_work(workno)
                            session["skipped"] += 1
                            LOG.info(
                                "复核忽略：%s（%s 天，销量 %s）", workno, age_days, known_sales
                            )
                        else:
                            session["enriched"] += 1
                            since_cover += 1
                            if cover_enabled and since_cover >= cover_trigger:
                                since_cover = 0
                                covers = _download_covers_safe(cfg, fetcher, store, cover_batch)
                                if covers["downloaded"] or covers["failed"]:
                                    print(
                                        f"[封面] 顺带补齐 {covers['downloaded']} 张"
                                        f"（失败 {covers['failed']}）",
                                        flush=True,
                                    )
                remaining -= 1
                if remaining < 0:
                    remaining = 0
                job = store.get_import_job()
                if job is None:
                    # P22.2：任务被外部取消 → 停止富化（已入库作品保留）
                    print("[导入] 任务定义已被外部取消；停止富化", flush=True)
                    return {
                        "status": "cancelled",
                        "session": session,
                        "job": None,
                        "remaining": remaining,
                    }
                store.update_import_job(
                    enriched=base["enriched"] + session["enriched"],
                    excluded=base["excluded"] + session["excluded"],
                    skipped=base["skipped"] + session["skipped"],
                    failed=base["failed"] + session["failed"],
                )
                job = store.get_import_job() or job
                processed = sum(session.values())
                if processed % PROGRESS_EVERY == 0:
                    write_progress(cfg, job, remaining, running=True, note="")
                if processed % EXPORT_EVERY == 0:
                    snapshot = export_snapshot(cfg, store, f"导入进行中（已处理 {processed}）")
                    if snapshot:
                        print(f"[导出] 中途快照：{snapshot}", flush=True)
                if processed % PRINT_EVERY == 0:
                    print(
                        f"[导入] 入库 {session['enriched']} · 排除非游戏 {session['excluded']} "
                        f"· 忽略低销旧作 {session['skipped']} · 失败 {session['failed']} "
                        f"· 剩余 {remaining}",
                        flush=True,
                    )
                if limit is not None and processed >= limit:
                    break
    except KeyboardInterrupt:
        interrupted = True

    # 封面收尾（P13.1/P14）：导入结束时把封面缺口补到清零（缺口清单只算一次；分块并发下载）
    if cover_enabled and not interrupted:
        pending_covers = list_missing_covers(cfg, store)
        for start in range(0, len(pending_covers), cover_batch):
            if pipeline_lock is not None and (Path(cfg.data_dir) / "import.yield").exists():
                pause_requested(cfg, pipeline_lock)
            chunk = pending_covers[start : start + cover_batch]
            covers = _download_entries_safe(cfg, fetcher, chunk)
            if covers["downloaded"] or covers["failed"]:
                print(
                    f"[封面] 收尾补齐 {covers['downloaded']} 张（失败 {covers['failed']}）",
                    flush=True,
                )

    remaining = store.import_remaining(boundary_old, boundary_modern)
    if source_kind == SOURCE_CATALOG:
        walk_ok = bool(int((store.get_import_job() or job).get("walk_done") or 0))
    done = remaining == 0 and walk_ok
    if done:
        note = "已完成"
    elif interrupted:
        note = "已中断（重跑同一命令即可续传）"
    elif not walk_ok:
        note = "目录遍历未完成（重跑续传）"
    else:
        note = "本轮结束（可续传）"
    if done:
        # P15：导入完成自动导出（应用闭环；失败不影响导入）
        snapshot = export_snapshot(cfg, store, "导入完成")
        if snapshot:
            print(f"[导出] 导入完成，已自动导出 {snapshot}", flush=True)
    store.update_import_job(phase="done" if done else "enrich", note=note)
    job = store.get_import_job()
    write_progress(cfg, job, remaining, running=False, note=note)
    return {
        "status": "interrupted" if interrupted else ("done" if done else "paused"),
        "session": session,
        "job": job,
        "remaining": remaining,
    }
