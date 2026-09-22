"""命令行入口。

已实现：init / update / rankings / enrich / backfill / clean-non-games / import-recent /
status / export / images / serve
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import List, Optional

from .config import Config, add_to_config_list, split_list
from .discovery import backfill as run_backfill
from .discovery import (
    discover_from_sitemap,
    fetch_genre_rankings,
    fetch_listings,
    fetch_rankings,
    fetch_trend_rankings,
)
from .enrich import enrich_pending
from .export import COVER_EXTENSIONS, fetch_records, write_export
from .http import Fetcher, HttpError, RobotsChanged
from .images import download_covers
from .importer import (
    SOURCE_CATALOG,
    SOURCE_NUMBERS,
    acquire_import_lock,
    boundary_cutoff_date,
    boundaries_for_days,
    boundaries_for_years,
    estimate_page_for_date,
    release_import_lock,
    run_import,
    years_label,
)
from .sales import BATCH_SIZE as SALES_BATCH_SIZE
from .sales import fetch_product_info, save_sales
from .serve import run_server
from .store import Store

LOG = logging.getLogger("dlsite_tracker")


def _open_store(cfg: Config) -> Store:
    store = Store(cfg.data_dir / "dlsite.sqlite")
    store.migrate()
    return store


def _fetcher(cfg: Config) -> Fetcher:
    fetcher = Fetcher.from_config(cfg)
    fetcher.verify_robots()
    return fetcher


def _parse_years_arg(value: str) -> str:
    """--years 参数校验（P22）：1–30 年数、all、或 since:YYYY（2005–2100）。"""
    text = str(value).strip()
    lowered = text.lower()
    if lowered == "all":
        return "all"
    if lowered.startswith("since:"):
        try:
            year = int(text.split(":", 1)[1])
        except ValueError:
            raise argparse.ArgumentTypeError("since: 后需要年份，如 since:2018")
        if year < 2005 or year > 2100:
            raise argparse.ArgumentTypeError("since: 年份需在 2005–2100 之间")
        return f"since:{year}"
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("--years 需要年数（1–30）、all 或 since:YYYY")
    if number < 1 or number > 30:
        raise argparse.ArgumentTypeError("年数需在 1–30 之间（更大范围请用 since:YYYY）")
    return str(number)


def _pages_hint(years: str) -> str:
    """目录遍历页数粗估（实测密度 ≈33 页/年；all=359 页）。"""
    text = str(years).strip().lower()
    if text == "all":
        return "359 页"
    if text.startswith("since:"):
        try:
            year = int(text.split(":", 1)[1])
        except ValueError:
            return ""
        count = max(1, time.localtime().tm_year - year)
    else:
        try:
            count = int(text)
        except ValueError:
            return ""
    return f"约 {count * 33} 页"


def _continue_deeper_start_page(cfg: Config, target_years: float) -> int:
    """续深模式起始页（P23）：读已覆盖记录，跳过已导入的年代段。

    - 有页号（真实遍历记录）→ 直接用它（留 3 页安全余量，宁重不漏）
    - 无页号（如编号来源导入）→ 用边界日期 + 页↔日期实测校准点估算
    - 无记录 → 从第 1 页正常开始；目标不比已覆盖更深时直接报错
    """
    path = cfg.out_dir / "import-coverage.json"
    if not path.is_file():
        print("[导入] 尚无已覆盖记录（未完成过目录遍历导入）；本次从第 1 页正常开始")
        return 1
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("[导入] 已覆盖记录无法解析；本次从第 1 页正常开始")
        return 1
    covered_years = float(record.get("covered_years") or 0)
    if covered_years and target_years <= covered_years + 0.25:
        raise ValueError(
            f"目标「最近 {target_years:g} 年」不比已覆盖的 ≈{covered_years:.1f} 年更深；"
            "如需重扫，请去掉续深模式再来一次"
        )
    page = record.get("page")
    if page is None:
        try:
            cutoff = boundary_cutoff_date(
                int(record["boundary_old"]), int(record["boundary_modern"])
            )
            page = estimate_page_for_date(cutoff)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            page = None
    if page is None:
        print("[导入] 无法估算已覆盖位置；本次从第 1 页正常开始")
        return 1
    start = max(1, int(page) - 3)
    print(
        f"[导入] 续深模式：已覆盖 ≈{covered_years:.1f} 年（约第 {int(page)} 页），"
        f"从第 {start + 1} 页继续往更早抓"
    )
    return start


def cmd_init(cfg: Config) -> int:
    for directory in (cfg.data_dir, cfg.out_dir, cfg.out_dir / "covers"):
        directory.mkdir(parents=True, exist_ok=True)
    store = _open_store(cfg)
    store.close()
    print(f"数据目录：{cfg.data_dir}")
    print(f"输出目录：{cfg.out_dir}")
    print(f"数据库：  {cfg.data_dir / 'dlsite.sqlite'}")
    return 0


def cmd_status(cfg: Config) -> int:
    store = _open_store(cfg)
    try:
        stats = store.stats()
        job = store.get_import_job()
        prefix = None
        if job is not None and str(job.get("source") or SOURCE_NUMBERS) == SOURCE_CATALOG:
            prefix = f"{SOURCE_CATALOG}:"
        remaining = (
            store.import_remaining(
                int(job["boundary_old"]), int(job["boundary_modern"]), source_prefix=prefix
            )
            if job
            else 0
        )
    finally:
        store.close()
    print(f"作品总数：  {stats['works']}（数据行 {stats['rows']}）")
    print(f"已富化：    {stats['enriched']}")
    print(f"含销量：    {stats['with_sales']}")
    print(f"待富化队列：{stats['pending']}")
    print(f"分类记录：  {stats['genres']}")
    if job is not None:
        job_source = str(job.get("source") or SOURCE_NUMBERS)
        print(
            f"导入任务：  {years_label(job['years'])} · 来源 {job_source} · "
            f"已入库 {job['enriched']} · "
            f"排除非游戏 {job['excluded']} · 忽略低销旧作 {job['skipped']} · "
            f"失败 {job['failed']} · 剩余 {remaining}"
        )
    for site, value in sorted(stats["last_seen"].items()):
        print(f"增量基准 [{site}]：{value}")
    if stats["runs"]:
        print("\n最近运行：")
        for run_id, started, _finished, command, ok, note in stats["runs"]:
            state = "进行中" if ok is None else ("成功" if ok else "失败")
            print(f"  #{run_id} {started} {command} [{state}] {note or ''}")
    return 0


def cmd_update(cfg: Config, args: argparse.Namespace) -> int:
    store = _open_store(cfg)
    run_id = store.start_run("update")
    notes: List[str] = []
    full = bool(args.full)
    try:
        fetcher = _fetcher(cfg)
        if full and not args.skip_sitemap:
            added = discover_from_sitemap(fetcher, store, cfg)
            notes.append(f"sitemap +{added}")
            print(f"[发现] sitemap 新增 {added} 个作品")
        elif not full:
            print("[发现] 热榜模式：跳过 sitemap 增量（--full 可启用全量模式）")
        if not args.skip_rankings:
            result = fetch_rankings(fetcher, store, cfg)
            notes.append(f"榜单 {result['views']} 视图/{result['sales']} 销量")
            print(f"[榜单] {result['views']} 个视图，记录销量 {result['sales']} 条")
            if args.skip_genre:
                notes.append("分类人气 跳过")
                print("[分类人气] 跳过（--skip-genre：快版不抓分类页）")
            else:
                genre = fetch_genre_rankings(
                    fetcher,
                    store,
                    cfg,
                    genres=split_list(args.genres) if args.genres else None,
                    pages=args.genre_pages
                    if args.genre_pages is not None
                    else cfg.genre_daily_pages,
                )
                notes.append(
                    f"分类人气 {genre['genres']} 分类/{genre['views']} 页/{genre['positions']} 名次"
                )
                print(
                    f"[分类人气] {genre['genres']} 个分类 × {genre['views']} 页，"
                    f"记录名次 {genre['positions']} 条"
                )
            trend_pages = args.trend_pages if args.trend_pages is not None else cfg.trend_pages
            if trend_pages > 0:
                trend = fetch_trend_rankings(fetcher, store, cfg, pages=trend_pages)
                notes.append(f"人气序 {trend['pages']} 页/{trend['positions']} 名次")
                print(
                    f"[人气序] {trend['pages']} 页，记录名次 {trend['positions']} 条"
                    + (f"（清理越界旧名次 {trend['cleared']} 条）" if trend["cleared"] else "")
                )
        if not args.skip_listings:
            result = fetch_listings(fetcher, store, cfg)
            notes.append(f"列表 {result['views']} 视图/{result['sales']} 销量")
            print(f"[列表] {result['views']} 个视图，记录销量 {result['sales']} 条")
        limit = args.enrich_limit if args.enrich_limit is not None else cfg.enrich_batch
        result = enrich_pending(fetcher, store, cfg, limit, hot_only=not full)
        mode = "全量" if full else "热榜"
        notes.append(f"富化({mode}) ok={result['ok']} fail={result['fail']}")
        print(
            f"[富化·{mode}] 成功 {result['ok']}，失败 {result['fail']}，"
            f"队列剩余 {store.pending_count()}"
        )
        print(f"[请求统计] {fetcher.summary()}")
        store.finish_run(run_id, True, "；".join(notes))
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_rankings(cfg: Config, args: argparse.Namespace) -> int:
    store = _open_store(cfg)
    run_id = store.start_run("rankings")
    try:
        fetcher = _fetcher(cfg)
        result = fetch_rankings(
            fetcher,
            store,
            cfg,
            terms=split_list(args.terms) if args.terms else None,
            categories=split_list(args.categories) if args.categories else None,
        )
        genre = fetch_genre_rankings(
            fetcher,
            store,
            cfg,
            genres=split_list(args.genres) if args.genres else None,
            pages=args.genre_pages,
        )
        note = (
            f"{result['views']} 视图，销量 {result['sales']} 条；"
            f"分类人气 {genre['genres']} 分类/{genre['views']} 页"
        )
        print(f"[榜单] {result['views']} 视图，销量 {result['sales']} 条")
        print(
            f"[分类人气] {genre['genres']} 个分类 × {genre['views']} 页，"
            f"记录名次 {genre['positions']} 条"
        )
        trend_pages = args.trend_pages if args.trend_pages is not None else cfg.trend_pages
        if trend_pages > 0:
            trend = fetch_trend_rankings(fetcher, store, cfg, pages=trend_pages)
            note += f"；人气序 {trend['pages']} 页/{trend['positions']} 名次"
            print(
                f"[人气序] {trend['pages']} 页，记录名次 {trend['positions']} 条"
                + (f"（清理越界旧名次 {trend['cleared']} 条）" if trend["cleared"] else "")
            )
        store.finish_run(run_id, True, note)
        print(f"[请求统计] {fetcher.summary()}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_fetch_genre(cfg: Config, args: argparse.Namespace) -> int:
    """现导入/载入更多：抓取指定分类的人气列表并落库（P19.2）。

    - 默认抓前 genre_rank_pages 页（现导入）；--more 从已抓深度之后续抓一页；
    - 抓到的作品登记入队（供随后 `enrich --source` 定向富化入库）；
    - 本次名次涉及的作品号写入 data/genre-worknos.txt（供 images 定向补封面）。
    """
    store = _open_store(cfg)
    run_id = store.start_run("fetch-genre")
    genre_id = str(args.genre).strip()
    try:
        fetcher = _fetcher(cfg)
        if args.more:
            depth = store.genre_depth(genre_id)
            if depth > 0:
                start_page = depth // 100 + 1
                pages = 1
            else:
                start_page = 1
                pages = args.pages or cfg.genre_rank_pages
        else:
            start_page = 1
            pages = args.pages or cfg.genre_rank_pages
        result = fetch_genre_rankings(
            fetcher, store, cfg, genres=[genre_id], pages=pages, start_page=start_page
        )
        detail = result["details"][0] if result["details"] else {}
        name = detail.get("name")
        # P20.1：优先用库里已存的展示名（若目录有中文名，save_genre_info 已落中文）
        row = store.conn.execute(
            "SELECT name FROM genre_info WHERE genre_id=?", (genre_id,)
        ).fetchone()
        if row and row[0]:
            name = row[0]
        elif not name:
            name = "未知"
        depth = detail.get("depth", store.genre_depth(genre_id))
        count = detail.get("count")
        worknos = detail.get("worknos", [])
        out_path = (
            Path(args.worknos_out)
            if args.worknos_out
            else (cfg.data_dir / "genre-worknos.txt")
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "\n".join(worknos) + ("\n" if worknos else ""), encoding="utf-8"
        )
        note = f"{genre_id} 名次 {result['positions']} 条（深度 {depth}"
        note += f" / 在售 {count}）" if count else "）"
        store.finish_run(run_id, True, note)
        print(f"[分类人气] {genre_id} 名称 {name}")
        print(
            f"[分类人气] 本次 {result['views']} 页，名次 {result['positions']} 条；"
            f"深度 {depth}" + (f" / 在售 {count}" if count else "")
        )
        print(f"[分类人气] 作品号清单：{out_path}")
        print(f"[请求统计] {fetcher.summary()}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_watch_genre(cfg: Config, args: argparse.Namespace) -> int:
    """把分类加入每日刷新列表（写入配置 genre_rank_ids；P19.2）。"""
    genre_id = str(args.genre).strip()
    try:
        changed, value = add_to_config_list(cfg.path, "discovery", "genre_rank_ids", genre_id)
    except OSError as exc:
        LOG.error("配置写入失败：%s", exc)
        return 1
    if changed:
        print(f"[分类人气] 已加入每日刷新：{genre_id}（genre_rank_ids = {value}）")
    else:
        print(f"[分类人气] {genre_id} 已在每日刷新列表中")
    return 0


def cmd_enrich(cfg: Config, args: argparse.Namespace) -> int:
    store = _open_store(cfg)
    run_id = store.start_run("enrich")
    try:
        fetcher = _fetcher(cfg)
        if args.refresh:
            added = store.enqueue_refresh(f"refresh:{cfg.locale}")
            print(f"[刷新] 重新登记已富化作品 {added} 个（locale={cfg.locale}）")
        limit = args.limit if args.limit is not None else cfg.enrich_batch
        if args.source:
            result = enrich_pending(fetcher, store, cfg, limit, source=args.source)
        elif args.refresh:
            result = enrich_pending(fetcher, store, cfg, limit, source_prefix="refresh:")
        else:
            result = enrich_pending(fetcher, store, cfg, limit, hot_only=not args.all)
        if args.source:
            mode = "定向"
        elif args.refresh:
            mode = "刷新"
        else:
            mode = "全量" if args.all else "热榜"
        note = f"{mode} ok={result['ok']} fail={result['fail']}，队列剩余 {store.pending_count()}"
        store.finish_run(run_id, True, note)
        print(f"[富化] {note}")
        print(f"[请求统计] {fetcher.summary()}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_backfill(cfg: Config, args: argparse.Namespace) -> int:
    store = _open_store(cfg)
    run_id = store.start_run("backfill")
    try:
        fetcher = _fetcher(cfg)
        added = run_backfill(
            fetcher, store, cfg, last_shards=args.last_shards, all_shards=bool(args.all)
        )
        scope = "全部" if args.all else f"最近 {args.last_shards} 个"
        note = f"登记{scope}分片，入队 {added}；富化请另跑 enrich"
        store.finish_run(run_id, True, note)
        print(f"[回填] {note}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_export(cfg: Config, args: argparse.Namespace) -> int:
    store = _open_store(cfg)
    run_id = store.start_run("export")
    try:
        work_types = split_list(args.work_types) if args.work_types else (cfg.default_work_types or None)
        records = fetch_records(store, cfg.out_dir, work_types=work_types)
        watched = set(split_list(cfg.genre_rank_ids))
        genres = store.genre_summaries()
        for item in genres:
            item["watched"] = item["id"] in watched
        trend_seen = store.get_meta(f"trend_seen:{cfg.sites[0]}") if cfg.sites else None
        paths = write_export(
            cfg.out_dir,
            records,
            genres=genres,
            genre_catalog=store.list_genre_catalog(),
            trend={"depth": store.rank_trend_depth(), "seen_at": trend_seen},
        )
        covered = sum(1 for record in records if record["image_path"])
        note = f"{len(records)} 条（含封面 {covered}）"
        store.finish_run(run_id, True, note)
        print(f"[导出] {note}")
        print(f"  JSON：{paths['json']}")
        print(f"  CSV： {paths['csv']}")
        return 0
    except OSError as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("导出失败：%s", exc)
        return 1
    finally:
        store.close()


def cmd_images(cfg: Config, args: argparse.Namespace) -> int:
    if not cfg.images_enabled:
        print("[封面] 已在配置中禁用（[images] enabled=false）")
        return 0
    store = _open_store(cfg)
    run_id = store.start_run("images")
    try:
        fetcher = _fetcher(cfg)
        limit = args.limit if args.limit is not None else cfg.images_max
        worknos = None
        if args.worknos_file:
            try:
                worknos = [
                    line.strip()
                    for line in Path(args.worknos_file).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except OSError as exc:
                store.finish_run(run_id, False, str(exc))
                LOG.error("作品号清单读取失败：%s", exc)
                return 1
        result = download_covers(cfg, fetcher, store, limit, worknos=worknos)
        note = f"下载 {result['downloaded']} / 跳过 {result['skipped']} / 失败 {result['failed']}"
        store.finish_run(run_id, True, note)
        print(f"[封面] {note}")
        print(f"[请求统计] {fetcher.summary()}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def cmd_serve(cfg: Config, args: argparse.Namespace) -> int:
    if args.host:
        cfg.serve_host = args.host
    if args.port is not None:
        cfg.serve_port = args.port
    return run_server(cfg)


def cmd_clean_non_games(cfg: Config, args: argparse.Namespace) -> int:
    """一次性清理：删除库中非白名单类型的作品（含封面），并记入排除清单。"""
    store = _open_store(cfg)
    run_id = store.start_run("clean-non-games")
    keep = list(cfg.default_work_types or [])
    try:
        if not keep:
            note = "白名单为空（[scope] default_work_types），未执行"
            store.finish_run(run_id, True, note)
            print(f"[清理] {note}")
            return 0
        rows = store.list_non_games(keep)
        removed_covers = 0
        for workno, work_type in rows:
            store.add_excluded(workno, work_type)
            for ext in COVER_EXTENSIONS:
                cover = cfg.out_dir / "covers" / f"{workno}.{ext}"
                if cover.is_file():
                    cover.unlink()
                    removed_covers += 1
            store.delete_work(workno)
        note = f"清理非游戏 {len(rows)} 条（封面 {removed_covers} 张）"
        store.finish_run(run_id, True, note)
        print(f"[清理] {note}")
        return 0
    except OSError as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("清理失败：%s", exc)
        return 1
    finally:
        store.close()


def _pause_import(cfg: Config) -> int:
    """暂停正在进行的导入：写暂停标志（可靠）+ SIGINT（尽力）。

    P22.3：经 bash 后台（&）启动的 python 会忽略 SIGINT（实测验证）——因此暂停以
    `data/import.pause` 标志文件为准（导入循环每翻一页/每件作品都会检查它）。
    """
    progress_path = cfg.out_dir / "import-progress.json"
    info = {}
    if progress_path.is_file():
        try:
            info = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
    pid = int(info.get("pid") or 0)
    running = bool(info.get("running"))
    if pid <= 0:
        pid_file = cfg.data_dir / "import.pid"
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip() or 0)
            except (OSError, ValueError):
                pid = 0
    if not running:
        print("[导入] 当前没有进行中的导入（无需暂停）")
        return 0
    if pid > 0 and not _pid_alive(pid):
        print("[导入] 进程已不存在（可能刚结束）；用 --status 查看")
        return 0
    flag = cfg.data_dir / "import.pause"
    try:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("pause\n", encoding="utf-8")
    except OSError as exc:
        print(f"[导入] 无法写入暂停标志：{exc}")
        return 1
    if pid > 0:
        try:
            os.kill(pid, signal.SIGINT)  # 尽力：前台进程即时响应；后台进程忽略则靠标志
        except (ProcessLookupError, PermissionError):
            pass
    print("[导入] 已请求暂停；断点自动保存，再开即续传")
    return 0


def _pid_alive(pid: int) -> bool:
    """进程存活探测（信号 0）。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stop_running_import(cfg: Config, wait_seconds: float = 10.0) -> None:
    """P22.2/22.3：取消任务前把仍在运行的导入进程停稳。

    手段按可靠性递进：①暂停标志（data/import.pause，循环每页/每件检查——后台进程
    忽略 SIGINT 时的可靠途径）；②SIGINT；③SIGTERM；④SIGKILL（对取消而言可接受，
    每件作品都已即时落盘）。完成后清掉标志文件。
    """
    progress_path = cfg.out_dir / "import-progress.json"
    info: dict = {}
    if progress_path.is_file():
        try:
            info = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
    pid = int(info.get("pid") or 0)
    running = bool(info.get("running"))
    flag = cfg.data_dir / "import.pause"
    if running and pid > 0 and pid != os.getpid():
        try:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("stop\n", encoding="utf-8")
        except OSError:
            pass
        for sig, label, wait in (
            (signal.SIGINT, "SIGINT", wait_seconds),
            (signal.SIGTERM, "SIGTERM", 3.0),
            (signal.SIGKILL, "SIGKILL", 2.0),
        ):
            if not _pid_alive(pid):
                break
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            print(f"[导入] 已发送 {label}（PID {pid}）")
            deadline = time.time() + wait
            while time.time() < deadline and _pid_alive(pid):
                time.sleep(0.2)
        print(
            "[导入] 导入进程已退出"
            if not _pid_alive(pid)
            else "[导入] 提示：进程仍未退出；任务定义仍将删除"
        )
    try:
        flag.unlink()
    except OSError:
        pass


def cmd_import_recent(cfg: Config, args: argparse.Namespace) -> int:
    """渐进导入：把「最近 N 年」的作品批量富化入库（断点续传）。"""
    store = _open_store(cfg)
    source = getattr(args, "source", None)
    try:
        if args.pause:
            return _pause_import(cfg)
        if args.status:
            job = store.get_import_job()
            if job is None:
                print(
                    "[导入] 无导入任务；用 import-recent --years N|all|since:YYYY 开始"
                    "（N=1–30 年；先用 --dry-run 可试算候选数量）"
                )
                return 0
            job_source = str(job.get("source") or SOURCE_NUMBERS)
            prefix = f"{SOURCE_CATALOG}:" if job_source == SOURCE_CATALOG else None
            remaining = store.import_remaining(
                int(job["boundary_old"]), int(job["boundary_modern"]), source_prefix=prefix
            )
            print(
                f"[导入] 任务：{years_label(job['years'])} · 来源 {job_source} · "
                f"阶段 {job['phase']} · "
                f"已入库 {job['enriched']} · 排除非游戏 {job['excluded']} · "
                f"忽略低销旧作 {job['skipped']} · 失败 {job['failed']} · 剩余 {remaining}"
            )
            if job_source == SOURCE_CATALOG and not int(job.get("walk_done") or 0):
                print(
                    f"[导入] 目录遍历：已翻到第 {int(job.get('cursor_page') or 0)} 页"
                    "（100 件/页，≥10s/页；断点自动保存）"
                )
            print(
                f"[导入] 边界：旧系列 ≥ {job['boundary_old']}；"
                f"现代系列 ≥ {job['boundary_modern']}"
            )
            print(
                f"[导入] 门槛：最近 {job['fresh_days']} 天新作全收；"
                f"更早先批量实查销量 ≥ {job['min_sales']}（0 = 关闭过滤）"
            )
            if job.get("note"):
                print(f"[导入] 备注：{job['note']}")
            print(f"[导入] 进度文件：{cfg.out_dir / 'import-progress.json'}")
            return 0

        if args.cancel:
            _stop_running_import(cfg)  # P22.2：先停住运行中的进程，再删任务（防幽灵进程）
            store.delete_import_job()
            progress_path = cfg.out_dir / "import-progress.json"
            if progress_path.is_file():
                progress_path.unlink()
            print("[导入] 已取消任务（已入库作品保留；重新运行 --years 可再次开始）")
            return 0

        if args.dry_run:
            job = store.get_import_job()
            years = args.years or (str(job["years"]) if job else "1")
            source_kind = source or (
                str(job.get("source") or SOURCE_NUMBERS)
                if job is not None
                else SOURCE_CATALOG
            )
            if source_kind == SOURCE_CATALOG and not (
                job is not None
                and str(job["years"]) == str(years)
                and int(job.get("walk_done") or 0)
            ):
                hint = _pages_hint(str(years))
                detail = f"（100 件/页、≥10s/页{hint and '；按实测密度约 ' + hint}）"
                print(
                    f"[导入] 试算（{years_label(years)}，来源=游戏目录遍历）："
                    f"逐页枚举游戏目录{detail}"
                )
                if cfg.import_min_sales > 0:
                    print(
                        "[导入] 候选 = 目录内未入库游戏；随后仅对「新作窗」或「卡面销量 ≥ "
                        f"{cfg.import_min_sales}」的游戏批量实查；老且低销零请求跳过"
                    )
                else:
                    print("[导入] 门槛未启用：目录内全部未入库游戏将逐件富化（每件 ≈1.2 秒）")
                print("[导入] 断点续传，可分段/过夜跑")
                return 0
            if job is not None and str(job["years"]) == str(years):
                boundary_old, boundary_modern = int(job["boundary_old"]), int(job["boundary_modern"])
                fresh_old, fresh_modern = int(job["fresh_old"]), int(job["fresh_modern"])
                min_sales, fresh_days = int(job["min_sales"]), int(job["fresh_days"])
            else:
                boundary_old, boundary_modern = boundaries_for_years(str(years))
                min_sales = cfg.import_min_sales
                fresh_days = cfg.import_fresh_days
                if min_sales > 0 and fresh_days > 0:
                    fresh_old, fresh_modern = boundaries_for_days(fresh_days)
                else:
                    min_sales = fresh_days = 0
                    fresh_old, fresh_modern = boundary_old, boundary_modern
            count = store.import_remaining(boundary_old, boundary_modern)
            print(
                f"[导入] 试算（{years_label(years)}）：候选 {count} 条；"
                f"边界 旧系列 ≥ {boundary_old} / 现代系列 ≥ {boundary_modern}"
            )
            if min_sales > 0:
                fresh_count = store.import_fresh_remaining(fresh_old, fresh_modern)
                batches = (count + SALES_BATCH_SIZE - 1) // SALES_BATCH_SIZE
                minutes = batches * 1.2 / 60
                print(
                    f"[导入] 批量预筛（P13）：按 {SALES_BATCH_SIZE} 件/请求实查（销量+类型+上架日）"
                    f"≈{batches} 次请求，约 {minutes:.0f} 分钟；"
                    f"非游戏与低销旧作（dl_count < {min_sales}）不逐件抓详情"
                )
                print(
                    f"[导入] 其中最近 {fresh_days} 天新作约 {fresh_count} 条全收；"
                    f"更早的约 {count - fresh_count} 条按门槛筛选"
                )
                print("[导入] 富化耗时取决于达标作品数（每件 ≈1.2 秒）")
            else:
                print("[导入] 过滤：未启用（全部候选直接富化）")
                print(f"[导入] 按约 1.2 秒/件估算：≈ {count * 1.2 / 3600:.1f} 小时")
            print("[导入] 断点续传，可分段/过夜跑")
            return 0

        if args.auto:
            job = store.get_import_job()
            if job is not None:
                if job["phase"] == "done":
                    print("[导入] 任务已完成；跳过（重新导入请手动加 --years ... --restart）")
                    return 0
                years = str(job["years"])
            elif cfg.import_years > 0:
                years = str(cfg.import_years)
            else:
                print("[导入] 无进行中的任务（且 [import] years = 0）；跳过")
                return 0
        else:
            years = args.years

        start_page: Optional[int] = None
        if getattr(args, "continue_deeper", False):
            try:
                target_years = float(str(years))
            except ValueError:
                print("[导入] 续深模式只支持年数目标（如 --years 7）")
                return 2
            try:
                start_page = _continue_deeper_start_page(cfg, target_years)
            except ValueError as exc:
                print(f"[导入] {exc}")
                return 2

        lock = acquire_import_lock(cfg)
        if lock is None:
            print("[导入] 已有导入进程在运行；本次跳过（避免并发重复请求；退出码 3）")
            return 3
        try:
            fetcher = _fetcher(cfg)
            run_id = store.start_run("import-recent")
            started = time.monotonic()
            try:
                result = run_import(
                    fetcher,
                    store,
                    cfg,
                    years,
                    restart=bool(args.restart),
                    limit=args.limit,
                    source=source,
                    start_page=start_page,
                )
            except KeyboardInterrupt:
                store.finish_run(run_id, True, "中断（断点已保存）")
                print("[导入] 已中断；重跑同一命令即可从断点继续")
                return 130
            except ValueError as exc:
                store.finish_run(run_id, False, str(exc))
                LOG.error("%s", exc)
                return 1
            elapsed = time.monotonic() - started
            session = result["session"]
            job = result["job"] or {}
            note = (
                f"入库 {session['enriched']} / 排除 {session['excluded']} / "
                f"忽略 {session['skipped']} / 失败 {session['failed']}；剩余 {result['remaining']}"
            )
            store.finish_run(run_id, True, note)
            print(
                f"[导入] 本次：入库 {session['enriched']} · 排除非游戏 {session['excluded']} "
                f"· 忽略低销旧作 {session['skipped']} · 失败 {session['failed']}"
            )
            print(
                f"[导入] 累计：入库 {job.get('enriched', 0)} · 排除 {job.get('excluded', 0)} · "
                f"忽略 {job.get('skipped', 0)}；剩余 {result['remaining']} 条"
                f"（状态：{result['status']}）· 用时 {elapsed / 60:.1f} 分钟"
            )
            print(f"[导入] 进度文件：{cfg.out_dir / 'import-progress.json'}")
            print(f"[请求统计] {fetcher.summary()}")
            if result["status"] == "done":
                auto_covers = int(getattr(cfg, "import_cover_trigger", 0) or 0) > 0
                print(
                    "[导入] 全部完成！"
                    + (
                        "封面缺口已在收尾阶段自动补齐。"
                        if auto_covers
                        else "（封面自愈已关闭；可随时跑 images 命令补封面）"
                    )
                )
            return 130 if result["status"] == "interrupted" else 0
        finally:
            release_import_lock(lock)
    finally:
        store.close()


def cmd_sales(cfg: Config, args: argparse.Namespace) -> int:
    """批量补/刷新销量与收藏数（info/ajax 批查，80 件/请求；P16 起顺带写入徽章 token）。"""
    store = _open_store(cfg)
    run_id = store.start_run("sales")
    try:
        fetcher = _fetcher(cfg)
        if args.hot_days is not None:
            # P20 做减法：只维持在榜作品（近 N 天上过榜、每件每天最多一次）
            min_age = 1.0 if args.min_age_days is None else float(args.min_age_days)
            worknos = store.works_for_sales_sync_hot(
                hot_days=args.hot_days, min_age_days=min_age, limit=args.limit
            )
            mode = f"在榜（近 {args.hot_days} 天）"
        else:
            stale_days = 0 if args.all else args.stale_days
            worknos = store.works_for_sales_sync(stale_days=stale_days, limit=args.limit)
            if args.all:
                mode = "全库"
            elif stale_days:
                mode = f"近 {stale_days} 天"
            else:
                mode = "缺销量"
        total = len(worknos)
        if total == 0:
            note = f"{mode}：没有需要同步的作品"
            store.finish_run(run_id, True, note)
            print(f"[销量] {note}")
            return 0
        site = cfg.sites[0] if cfg.sites else "maniax"
        chunk = 400
        done = updated = missing = 0
        for start in range(0, total, chunk):
            part = worknos[start : start + chunk]
            infos = fetch_product_info(fetcher, site, part)
            values = {
                workno: (info["dl_count"], info["wishlist_count"])
                for workno, info in infos.items()
                if info["dl_count"] is not None or info["wishlist_count"] is not None
            }
            options = {
                workno: info["options"] for workno, info in infos.items() if info["options"]
            }
            save_sales(store, site, values, options=options)
            done += len(part)
            updated += len(values)
            missing += len(part) - len(values)
            print(f"[销量] {done}/{total}（更新 {updated} · 缺失 {missing}）", flush=True)
        note = f"{mode} {total} 件：更新 {updated} · 缺失 {missing}"
        store.finish_run(run_id, True, note)
        print(f"[销量] {note}")
        print(f"[请求统计] {fetcher.summary()}")
        return 0
    except (HttpError, RobotsChanged, ValueError) as exc:
        store.finish_run(run_id, False, str(exc))
        LOG.error("%s", exc)
        return 1
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlsite_tracker",
        description="同人游戏雷达 · DLsite 数据管道（本机运行、零第三方依赖；详见 README.md）",
    )
    parser.add_argument("--config", default="config.ini", help="配置文件路径（默认 config.ini）")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="初始化数据目录与数据库")
    sub.add_parser("status", help="查看数据量与最近运行记录")

    update = sub.add_parser("update", help="每日更新：默认热榜模式（榜单/列表 + 热榜富化）")
    update.add_argument("--full", action="store_true", help="全量模式：含 sitemap 增量 + 富化全队列")
    update.add_argument("--enrich-limit", type=int, default=None, help="本轮富化上限（默认取配置）")
    update.add_argument("--skip-sitemap", action="store_true", help="跳过 sitemap 增量发现")
    update.add_argument("--skip-rankings", action="store_true", help="跳过榜单抓取")
    update.add_argument("--skip-genre", action="store_true", help="跳过分类人气页（快版：榜单/列表/人气序照常）")
    update.add_argument("--skip-listings", action="store_true", help="跳过列表页抓取")
    update.add_argument("--genres", default=None, help="分类人气列表：分类 id（逗号分隔；默认取配置）")
    update.add_argument(
        "--genre-pages", type=int, default=None, help="每个分类抓取页数（每日默认取配置 genre_daily_pages）"
    )
    update.add_argument(
        "--trend-pages", type=int, default=None, help="全站人气序抓取页数（默认取配置；0=关闭）"
    )

    rankings = sub.add_parser("rankings", help="只抓榜单与销量")
    rankings.add_argument("--terms", default=None, help="逗号分隔，如 day,week")
    rankings.add_argument("--categories", default=None, help="逗号分隔，如 game")
    rankings.add_argument("--genres", default=None, help="分类人气列表：分类 id（逗号分隔；默认取配置）")
    rankings.add_argument("--genre-pages", type=int, default=None)
    rankings.add_argument(
        "--trend-pages", type=int, default=None, help="全站人气序抓取页数（默认取配置；0=关闭）"
    )

    enrich = sub.add_parser("enrich", help="只跑富化队列（默认仅热榜作品）")
    enrich.add_argument("--all", action="store_true", help="不限于热榜：按登记顺序处理全队列")
    enrich.add_argument("--refresh", action="store_true", help="先重新登记已富化作品（换语言/刷新），再处理刷新队列")
    enrich.add_argument("--limit", type=int, default=None, help="本轮上限（默认取配置）")
    enrich.add_argument(
        "--source",
        default=None,
        help="定向处理某个完整来源的队列（如 genre-rank:maniax:526；自动跳过已富化）",
    )

    fetch_genre = sub.add_parser("fetch-genre", help="现导入/载入更多：抓取指定分类的人气列表")
    fetch_genre.add_argument("genre", help="分类 id（带前导零按站点习惯，如 016）")
    fetch_genre.add_argument("--more", action="store_true", help="从已抓深度之后续抓一页（载入更多）")
    fetch_genre.add_argument("--pages", type=int, default=None, help="抓取页数（默认取配置 genre_rank_pages）")
    fetch_genre.add_argument(
        "--worknos-out", default=None, help="作品号清单输出路径（默认 data/genre-worknos.txt）"
    )

    watch = sub.add_parser("watch-genre", help="把分类加入每日刷新列表（写入配置）")
    watch.add_argument("genre", help="分类 id")

    backfill = sub.add_parser("backfill", help="sitemap 历史登记（仅入队，不富化）")
    backfill.add_argument("--all", action="store_true", help="登记全部分片（首次全量；游标可续跑）")
    backfill.add_argument("--last-shards", type=int, default=3, help="从最新分片向前登记的数量")

    sub.add_parser(
        "clean-non-games", help="清理库中非游戏作品（按 default_work_types 白名单，含封面）"
    )

    sales = sub.add_parser("sales", help="批量补/刷新销量与收藏数（info/ajax，80 件/请求）")
    sales.add_argument("--all", action="store_true", help="刷新全部已富化作品（默认只补缺销量的）")
    sales.add_argument("--stale-days", type=int, default=None, help="另含 N 天前同步过的作品")
    sales.add_argument(
        "--hot-days",
        type=int,
        default=None,
        help="P20：只维持在榜作品——刷新近 N 天上过榜的已富化作品（每件每天最多一次）",
    )
    sales.add_argument(
        "--min-age-days",
        type=float,
        default=None,
        help="在榜刷新最小间隔天数（默认 1.0＝每件每天最多一次；0 = 不限制）",
    )
    sales.add_argument("--limit", type=int, default=None, help="本轮上限")

    importer = sub.add_parser(
        "import-recent",
        help="渐进导入指定范围的作品（年数 N / all / since:YYYY；断点续传）",
    )
    importer.add_argument(
        "--years",
        type=_parse_years_arg,
        default=None,
        metavar="N|all|since:YYYY",
        help="导入范围：年数 N（1–30）、all、或 since:YYYY（自该年 1 月 1 日至今）；默认沿用现有任务",
    )
    importer.add_argument(
        "--restart", action="store_true", help="重建任务（计数清零；已入库作品保留）"
    )
    importer.add_argument(
        "--limit", type=int, default=None, help="本次最多处理的作品数（默认不限）"
    )
    importer.add_argument("--status", action="store_true", help="只查看任务进度")
    importer.add_argument(
        "--auto", action="store_true", help="每日调度用：有任务则续传；无任务且配置 years>0 则开始"
    )
    importer.add_argument("--cancel", action="store_true", help="取消任务（已入库作品保留）")
    importer.add_argument("--pause", action="store_true", help="暂停正在进行的导入（优雅中断，断点保留）")
    importer.add_argument(
        "--dry-run", action="store_true", help="只试算候选数量，不发任何请求"
    )
    importer.add_argument(
        "--continue-deeper",
        action="store_true",
        help="续深模式：从上次已覆盖的最深位置继续往更早抓（跳过重扫；--years 记目标总深度）",
    )
    importer.add_argument(
        "--source",
        choices=["catalog", "numbers"],
        default=None,
        help="候选来源：catalog=游戏目录遍历（默认）；numbers=编号扫描（审计用）",
    )

    export = sub.add_parser("export", help="导出 out/works.json 与 out/works.csv")
    export.add_argument("--work-types", default=None, help="逗号分隔的作品形式过滤（默认取配置 default_work_types）")

    images = sub.add_parser("images", help="下载封面缩略图到 out/covers/")
    images.add_argument("--limit", type=int, default=None, help="本轮下载上限（默认取配置）")
    images.add_argument(
        "--worknos-file", default=None, help="仅补齐清单内作品（每行一个作品号；P19.2 现导入用）"
    )

    serve = sub.add_parser("serve", help="启动本地只读 API（仅 127.0.0.1）")
    serve.add_argument("--host", default=None, help="仅允许回环地址（127.0.0.1/localhost）")
    serve.add_argument("--port", type=int, default=None)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    try:
        cfg = Config.load(args.config)
    except (FileNotFoundError, ValueError) as exc:
        LOG.error("配置错误：%s", exc)
        return 1
    if args.command == "init":
        return cmd_init(cfg)
    if args.command == "status":
        return cmd_status(cfg)
    if args.command == "update":
        return cmd_update(cfg, args)
    if args.command == "rankings":
        return cmd_rankings(cfg, args)
    if args.command == "fetch-genre":
        return cmd_fetch_genre(cfg, args)
    if args.command == "watch-genre":
        return cmd_watch_genre(cfg, args)
    if args.command == "enrich":
        return cmd_enrich(cfg, args)
    if args.command == "backfill":
        return cmd_backfill(cfg, args)
    if args.command == "clean-non-games":
        return cmd_clean_non_games(cfg, args)
    if args.command == "sales":
        return cmd_sales(cfg, args)
    if args.command == "import-recent":
        return cmd_import_recent(cfg, args)
    if args.command == "export":
        return cmd_export(cfg, args)
    if args.command == "images":
        return cmd_images(cfg, args)
    if args.command == "serve":
        return cmd_serve(cfg, args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
