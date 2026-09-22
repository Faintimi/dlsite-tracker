"""本地只读 API（仅回环地址；仅 GET；SQLite 只读连接）。

最小安全设计：
- 绑定固定回环地址 ``127.0.0.1``（配置里的非回环地址会被拒绝）；
- 数据库连接使用 ``mode=ro`` URI，物理上无法写入；
- 排序字段白名单 + 参数化 SQL + 结果条数上限（MAX_LIMIT）；
- 无鉴权接口也仅暴露公开商品数据，不含任何本地文件内容。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .export import (
    SCHEMA_VERSION,
    WORK_SELECT,
    _genre_names_from_snapshot,
    build_record,
    find_cover,
    load_genre_map,
)

LOG = logging.getLogger("dlsite_tracker.serve")

MAX_LIMIT = 500
SORTABLE = {
    "workno", "price", "rating_star", "sales",
    "rank_day", "rank_week", "rank_month", "regist_date", "updated_at",
    "rank_day_current", "rank_week_current", "rank_month_current",
}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_works(
    db_path: Path,
    out_dir: Path,
    *,
    workno: Optional[str] = None,
    work_type: Optional[str] = None,
    genre: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    min_sales: Optional[float] = None,
    sort: str = "rank_day_current",
    order: str = "asc",
    limit: Any = 100,
    offset: Any = 0,
) -> List[Dict[str, Any]]:
    """按条件查询作品（只读）。排序字段走白名单，其余一律参数化。"""
    sort_column = sort if sort in SORTABLE else "workno"
    direction = "DESC" if str(order).lower() == "desc" else "ASC"
    try:
        limit_value = max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        limit_value = 100
    try:
        offset_value = max(0, int(offset))
    except (TypeError, ValueError):
        offset_value = 0

    clauses = ["w.enriched_at IS NOT NULL", "w.product_name IS NOT NULL"]
    args: List[Any] = []
    if workno:
        clauses.append("w.workno = ?")
        args.append(workno)
    if work_type:
        clauses.append("w.work_type = ?")
        args.append(work_type)
    if genre:
        clauses.append(
            "EXISTS (SELECT 1 FROM work_genres g WHERE g.workno = w.workno "
            "AND (g.name = ? OR g.genre_id = ?))"
        )
        args.extend([genre, genre])
    for column, operator, value in (
        ("price", ">=", min_price),
        ("price", "<=", max_price),
        ("rating_star", ">=", min_rating),
        ("sales", ">=", min_sales),
    ):
        if value is not None:
            clauses.append(f"w.{column} {operator} ?")
            args.append(value)

    sql = (
        f"{WORK_SELECT} WHERE {' AND '.join(clauses)} "
        f"ORDER BY (w.{sort_column} IS NULL), w.{sort_column} {direction} "
        "LIMIT ? OFFSET ?"
    )
    args.extend([limit_value, offset_value])

    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, args).fetchall()
        genre_map = load_genre_map(conn, [row["workno"] for row in rows])
    finally:
        conn.close()
    return [
        build_record(
            row,
            genre_map.get(row["workno"]) or _genre_names_from_snapshot(row),
            find_cover(out_dir, row["workno"]),
        )
        for row in rows
    ]


def _stats(db_path: Path) -> Dict[str, Any]:
    conn = _connect(db_path)
    try:
        def scalar(sql: str) -> int:
            try:
                return int(conn.execute(sql).fetchone()[0])
            except sqlite3.OperationalError:
                return 0

        return {
            "works": scalar("SELECT COUNT(*) FROM works"),
            "enriched": scalar("SELECT COUNT(*) FROM works WHERE enriched_at IS NOT NULL"),
            "with_sales": scalar("SELECT COUNT(*) FROM works WHERE sales IS NOT NULL"),
            "pending": scalar("SELECT COUNT(*) FROM pending"),
            "schema_version": SCHEMA_VERSION,
        }
    finally:
        conn.close()


def _to_filters(params: Dict[str, List[str]]) -> Dict[str, Any]:
    def first(name: str) -> Optional[str]:
        values = params.get(name)
        return values[0] if values else None

    def number(name: str) -> Optional[float]:
        raw = first(name)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    return {
        "work_type": first("work_type") or None,
        "genre": first("genre") or None,
        "min_price": number("min_price"),
        "max_price": number("max_price"),
        "min_rating": number("min_rating"),
        "min_sales": number("min_sales"),
        "sort": first("sort") or "rank_day_current",
        "order": first("order") or "asc",
        "limit": first("limit") or 100,
        "offset": first("offset") or 0,
    }


def make_handler(cfg) -> type:
    """构造请求处理器（闭包捕获路径；便于测试）。"""
    db_path = Path(cfg.data_dir) / "dlsite.sqlite"
    out_dir = Path(cfg.out_dir)

    class Handler(BaseHTTPRequestHandler):
        server_version = "dlsite-tracker/1.0"

        def do_GET(self) -> None:  # noqa: N802 - http.server 约定
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/health":
                    stats = _stats(db_path)
                    self._json(200, {"ok": True, "schema_version": SCHEMA_VERSION, "works": stats["enriched"]})
                elif parsed.path == "/stats":
                    self._json(200, _stats(db_path))
                elif parsed.path == "/works":
                    records = query_works(db_path, out_dir, **_to_filters(parse_qs(parsed.query)))
                    self._json(200, {"count": len(records), "works": records})
                elif parsed.path.startswith("/works/"):
                    workno = parsed.path.split("/", 2)[2].strip().upper()
                    records = query_works(db_path, out_dir, workno=workno, limit=1)
                    if records:
                        self._json(200, records[0])
                    else:
                        self._json(404, {"error": "not found"})
                else:
                    self._json(404, {"error": "not found"})
            except Exception as exc:  # 服务器边界：异常转为 500，避免进程退出
                LOG.error("请求处理失败：%s", exc)
                self._json(500, {"error": "internal error"})

        def _json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:  # 精简日志
            LOG.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def run_server(cfg) -> int:
    import dataclasses  # noqa: F401 - 保持最小依赖，仅本函数使用

    host = str(cfg.serve_host or "127.0.0.1").strip().lower()
    if host not in LOOPBACK_HOSTS:
        LOG.error("为保持最小暴露面，仅允许监听回环地址（当前配置：%s）", cfg.serve_host)
        return 1
    db_path = Path(cfg.data_dir) / "dlsite.sqlite"
    if not db_path.exists():
        LOG.error("数据库不存在：%s（请先运行 init / update）", db_path)
        return 1
    server = ThreadingHTTPServer(("127.0.0.1", int(cfg.serve_port)), make_handler(cfg))
    LOG.info("本地只读 API 已启动：http://127.0.0.1:%d（Ctrl+C 停止）", int(cfg.serve_port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
