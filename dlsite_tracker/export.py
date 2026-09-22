"""导出阶段：生成 out/works.json 与 out/works.csv（仅标准库）。

导出字段约定：
- JSON：``{schema_version, generated_at, count, works, genres, genre_catalog, trend}``
  （schema v2 / P19.1：每件作品含 ``genre_pos`` 分类人气名次；附分类人气/目录/人气序元信息；
  应用接受数组或含 works 的对象）
- CSV：同字段表格版，UTF-8 带 BOM（Excel 直接打开不乱码）
- ``image_path``：相对 out/ 的路径（``covers/<file>``）；文件不存在时为空串
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .store import Store

LOG = logging.getLogger("dlsite_tracker.export")

SCHEMA_VERSION = 2  # v2（P19.1）：genre_pos / genres / genre_catalog / trend / rank_trend_current

# 导出/查询共用的列集合（供 export 与 serve 复用）
WORK_SELECT = """
SELECT w.workno, w.site, w.product_name, w.maker_name, w.maker_id, w.work_type, w.work_type_string,
       w.price, w.rating_star, w.sales, w.official_price, w.discount_rate,
       w.rating_count, w.rank_day, w.rank_week, w.rank_month,
       w.rank_day_date, w.rank_week_date, w.rank_month_date,
       w.rank_day_current, w.rank_week_current, w.rank_month_current,
       w.rank_trend_current,
       w.rank_current_seen_at,
       w.regist_date, w.sales_seen_at, w.genres_json, w.options
FROM works w
"""

CSV_COLUMNS = [
    "id", "title", "maker", "category", "form", "sales", "rating", "price",
    "image_path", "url", "official_price", "discount_rate", "rating_count",
    "rank_day", "rank_week", "rank_month",
    "rank_day_date", "rank_week_date", "rank_month_date",
    "rank_day_current", "rank_week_current", "rank_month_current",
    "rank_trend_current", "rank_current_seen_at",
    "work_type", "regist_date", "sales_seen_at",
    "maker_id", "voice", "music", "video",
]

COVER_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")


def find_cover(out_dir: Path, workno: str) -> str:
    """返回相对 out/ 的封面路径（如 ``covers/RJ1.jpg``）；不存在返回空串。"""
    covers = out_dir / "covers"
    for ext in COVER_EXTENSIONS:
        candidate = covers / f"{workno}.{ext}"
        if candidate.is_file():
            return f"covers/{candidate.name}"
    return ""


def load_genre_map(
    conn: sqlite3.Connection, worknos: Optional[Sequence[str]] = None
) -> Dict[str, List[str]]:
    """workno → 分类名列表（保持写入顺序）。"""
    if worknos is not None:
        worknos = list(worknos)
        if not worknos:
            return {}
        placeholders = ",".join("?" for _ in worknos)
        sql = (
            "SELECT workno, name FROM work_genres "
            f"WHERE workno IN ({placeholders}) ORDER BY rowid"
        )
        rows = conn.execute(sql, worknos).fetchall()
    else:
        rows = conn.execute("SELECT workno, name FROM work_genres ORDER BY rowid").fetchall()
    mapping: Dict[str, List[str]] = {}
    for workno, name in rows:
        mapping.setdefault(workno, []).append(name)
    return mapping


def load_genre_positions(conn: sqlite3.Connection) -> Dict[str, Dict[str, int]]:
    """workno → {分类 id: 人气名次}（P19.1，供导出 ``genre_pos``）。"""
    mapping: Dict[str, Dict[str, int]] = {}
    rows = conn.execute(
        "SELECT workno, genre_id, position FROM genre_ranks ORDER BY position"
    ).fetchall()
    for workno, genre_id, position in rows:
        mapping.setdefault(workno, {})[genre_id] = int(position)
    return mapping


def _genre_names_from_snapshot(row: Any) -> List[str]:
    raw = row["genres_json"]
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    names = [
        str(item.get("name") or "").strip()
        for item in items
        if isinstance(item, dict)
    ]
    return [name for name in names if name]


def build_record(
    row: Any,
    genre_names: Sequence[str],
    cover_rel: str,
    genre_pos: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """数据库行 → 应用契约记录（额外字段应用会忽略，供分析使用）。

    P16：voice/music/video 取自 options 徽章 token（SND=音声あり / MS2=音楽あり /
    MV2=動画あり）；maker_id 供应用跳转 DLsite 制作者主页。
    P19.1：``genre_pos`` = 分类内人气名次（{分类 id: 名次}）；
    ``rank_trend_current`` = 全站人气序名次（NULL = 未入前 N）。
    """
    site = row["site"] or "maniax"
    workno = row["workno"]
    tokens = set((row["options"] or "").split("#"))
    record: Dict[str, Any] = {
        "id": workno,
        "title": row["product_name"] or "",
        "maker": row["maker_name"] or "",
        "category": " | ".join(genre_names),
        "form": row["work_type_string"] or "",
        "sales": row["sales"],
        "rating": row["rating_star"],
        "price": row["price"],
        "image_path": cover_rel,
        "url": f"https://www.dlsite.com/{site}/work/=/product_id/{workno}.html",
        "official_price": row["official_price"],
        "discount_rate": row["discount_rate"],
        "rating_count": row["rating_count"],
        "rank_day": row["rank_day"],
        "rank_week": row["rank_week"],
        "rank_month": row["rank_month"],
        "rank_day_date": row["rank_day_date"],
        "rank_week_date": row["rank_week_date"],
        "rank_month_date": row["rank_month_date"],
        "rank_day_current": row["rank_day_current"],
        "rank_week_current": row["rank_week_current"],
        "rank_month_current": row["rank_month_current"],
        "rank_trend_current": row["rank_trend_current"],
        "rank_current_seen_at": row["rank_current_seen_at"],
        "work_type": row["work_type"],
        "regist_date": row["regist_date"],
        "sales_seen_at": row["sales_seen_at"],
        "maker_id": row["maker_id"] or "",
        "voice": "SND" in tokens,
        "music": "MS2" in tokens,
        "video": "MV2" in tokens,
    }
    if genre_pos:
        record["genre_pos"] = {str(key): int(value) for key, value in genre_pos.items()}
    return record


def fetch_records(
    store: Store,
    out_dir: Path,
    work_types: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """读取已富化作品并生成导出记录（按作品号稳定排序）。"""
    clauses = ["w.enriched_at IS NOT NULL", "w.product_name IS NOT NULL"]
    args: List[Any] = []
    if work_types:
        placeholders = ",".join("?" for _ in work_types)
        clauses.append(f"w.work_type IN ({placeholders})")
        args.extend(work_types)
    sql = f"{WORK_SELECT} WHERE {' AND '.join(clauses)} ORDER BY w.workno"
    rows = store.conn.execute(sql, args).fetchall()
    genre_map = load_genre_map(store.conn)
    position_map = load_genre_positions(store.conn)
    records: List[Dict[str, Any]] = []
    for row in rows:
        names = genre_map.get(row["workno"]) or _genre_names_from_snapshot(row)
        records.append(
            build_record(
                row,
                names,
                find_cover(out_dir, row["workno"]),
                position_map.get(row["workno"]),
            )
        )
    return records


def _render_csv(records: Sequence[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return "\ufeff" + buffer.getvalue()  # BOM：Windows Excel 兼容


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_export(
    out_dir: Path,
    records: Sequence[Dict[str, Any]],
    *,
    genres: Optional[Sequence[Dict[str, Any]]] = None,
    genre_catalog: Optional[Sequence[Dict[str, str]]] = None,
    trend: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """原子写入 works.json 与 works.csv；返回两个文件路径。

    P19.1：附加元信息——``genres``（有数据的分类：名称/件数/深度/数据日期/是否每日刷新）、
    ``genre_catalog``（站点全量分类目录）、``trend``（全站人气序覆盖情况）。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(records),
        "genres": list(genres or []),
        "genre_catalog": list(genre_catalog or []),
        "trend": dict(trend or {"depth": 0, "seen_at": None}),
        "works": list(records),
    }
    json_path = out_dir / "works.json"
    csv_path = out_dir / "works.csv"
    _atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    _atomic_write_text(csv_path, _render_csv(records))
    return {"json": str(json_path), "csv": str(csv_path)}
