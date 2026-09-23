"""SQLite 存储（仅标准库）。

本模块负责建表、迁移与全部读写。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA_STATEMENTS: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS works (
        workno            TEXT PRIMARY KEY,
        site              TEXT,
        product_name      TEXT,
        maker_id          TEXT,
        maker_name        TEXT,
        work_category     TEXT,
        work_type         TEXT,
        work_type_string  TEXT,
        age_category      INTEGER,
        sex_category      INTEGER,
        price             INTEGER,
        official_price    INTEGER,
        discount_rate     INTEGER,
        is_timesale       INTEGER,
        timesale_price    INTEGER,
        timesale_end_date TEXT,
        rating_star       REAL,
        rating_count      INTEGER,
        rank_day          INTEGER,
        rank_day_date     TEXT,
        rank_week         INTEGER,
        rank_week_date    TEXT,
        rank_month        INTEGER,
        rank_month_date   TEXT,
        rank_day_current  INTEGER,
        rank_week_current INTEGER,
        rank_month_current INTEGER,
        rank_trend_current INTEGER,
        rank_current_seen_at TEXT,
        hot_seen_at       TEXT,
        regist_date       TEXT,
        update_date       TEXT,
        series_name       TEXT,
        is_bl             INTEGER,
        is_tl             INTEGER,
        genres_json       TEXT,
        image_url         TEXT,
        sales             INTEGER,
        sales_seen_at     TEXT,
        wishlist_count    INTEGER,
        options           TEXT,
        enriched_at       TEXT,
        updated_at        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS work_genres (
        workno   TEXT NOT NULL,
        genre_id TEXT NOT NULL,
        name     TEXT NOT NULL,
        PRIMARY KEY (workno, genre_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_work_genres_name ON work_genres(name)",
    """
    CREATE TABLE IF NOT EXISTS sales_history (
        workno  TEXT NOT NULL,
        sales   INTEGER NOT NULL,
        seen_at TEXT NOT NULL,
        source  TEXT NOT NULL,
        PRIMARY KEY (workno, seen_at, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pending (
        workno        TEXT PRIMARY KEY,
        source        TEXT NOT NULL,
        discovered_at TEXT NOT NULL,
        attempts      INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS excluded (
        workno      TEXT PRIMARY KEY,
        work_type   TEXT,
        excluded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS genre_info (
        genre_id TEXT PRIMARY KEY,
        name     TEXT NOT NULL,
        count    INTEGER,
        seen_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS genre_ranks (
        workno   TEXT NOT NULL,
        genre_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        seen_at  TEXT NOT NULL,
        PRIMARY KEY (workno, genre_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS genre_catalog (
        genre_id TEXT PRIMARY KEY,
        name     TEXT NOT NULL,
        seen_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_job (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        years           TEXT NOT NULL,
        source          TEXT NOT NULL DEFAULT 'numbers',
        walk_done       INTEGER NOT NULL DEFAULT 0,
        cursor_page     INTEGER NOT NULL DEFAULT 0,
        phase           TEXT NOT NULL,
        boundary_old    INTEGER NOT NULL DEFAULT 0,
        boundary_modern INTEGER NOT NULL DEFAULT 0,
        fresh_old       INTEGER NOT NULL DEFAULT 0,
        fresh_modern    INTEGER NOT NULL DEFAULT 0,
        min_sales       INTEGER NOT NULL DEFAULT 0,
        fresh_days      INTEGER NOT NULL DEFAULT 0,
        started_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        enriched        INTEGER NOT NULL DEFAULT 0,
        excluded        INTEGER NOT NULL DEFAULT 0,
        skipped         INTEGER NOT NULL DEFAULT 0,
        failed          INTEGER NOT NULL DEFAULT 0,
        note            TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        command     TEXT NOT NULL,
        ok          INTEGER,
        note        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
]

WORK_COLUMNS: List[str] = [
    "workno", "site", "product_name", "maker_id", "maker_name", "work_category",
    "work_type", "work_type_string", "age_category", "sex_category", "price",
    "official_price", "discount_rate", "is_timesale", "timesale_price",
    "timesale_end_date", "rating_star", "rating_count", "rank_day",
    "rank_day_date", "rank_week", "rank_week_date", "rank_month",
    "rank_month_date", "rank_day_current", "rank_week_current",
    "rank_month_current", "rank_trend_current", "rank_current_seen_at", "hot_seen_at",
    "regist_date", "update_date", "series_name", "is_bl",
    "is_tl", "genres_json", "image_url", "sales", "sales_seen_at",
    "wishlist_count", "options", "enriched_at", "updated_at",
]

# 榜单 term → 当前榜位列；rank_day/week/month（无 _current）为富化写入的历史快照
RANK_COLUMNS: Dict[str, str] = {
    "day": "rank_day_current",
    "week": "rank_week_current",
    "month": "rank_month_current",
    "trend": "rank_trend_current",  # P19.4：全站人气序（人気順）
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def migrate(self) -> None:
        with self.conn:
            for statement in SCHEMA_STATEMENTS:
                self.conn.execute(statement)
            self._ensure_columns()

    def _ensure_columns(self) -> None:
        """旧库补列（幂等）：P5 榜位列、P16 options 徽章、P18 导入来源/遍历游标。"""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(works)")}
        for column, column_type in (
            ("rank_day_current", "INTEGER"),
            ("rank_week_current", "INTEGER"),
            ("rank_month_current", "INTEGER"),
            ("rank_trend_current", "INTEGER"),
            ("rank_current_seen_at", "TEXT"),
            ("hot_seen_at", "TEXT"),
            ("wishlist_count", "INTEGER"),
            ("options", "TEXT"),
        ):
            if column not in existing:
                self.conn.execute(f"ALTER TABLE works ADD COLUMN {column} {column_type}")
        job_existing = {row[1] for row in self.conn.execute("PRAGMA table_info(import_job)")}
        for column, column_type in (
            ("source", "TEXT"),
            ("walk_done", "INTEGER DEFAULT 0"),
            ("cursor_page", "INTEGER DEFAULT 0"),
        ):
            if column not in job_existing:
                self.conn.execute(f"ALTER TABLE import_job ADD COLUMN {column} {column_type}")

    def close(self) -> None:
        self.conn.close()

    # ---- meta ---------------------------------------------------------
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    # ---- runs ---------------------------------------------------------
    def start_run(self, command: str) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO runs(started_at,command) VALUES(?,?)", (_now(), command)
            )
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, ok: bool, note: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET finished_at=?, ok=?, note=? WHERE id=?",
                (_now(), 1 if ok else 0, note, run_id),
            )

    # ---- pending 队列 ---------------------------------------------------
    def add_pending_many(self, worknos: Sequence[str], source: str) -> int:
        rows = [(workno, source, _now()) for workno in worknos]
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO pending(workno,source,discovered_at) VALUES(?,?,?)",
                rows,
            )
        return len(rows)

    def pending_batch(self, limit: int) -> List[Tuple[str, str, int]]:
        cursor = self.conn.execute(
            "SELECT p.workno, p.source, p.attempts FROM pending p "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "WHERE e.workno IS NULL "
            "ORDER BY p.discovered_at LIMIT ?",
            (limit,),
        )
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def pending_batch_hot(
        self, limit: int, window_days: int = 7, skip_enriched: bool = False
    ) -> List[Tuple[str, str, int]]:
        """热榜待富化：仅取近 window_days 天出现在榜单/列表中的作品（按登记时间）。

        skip_enriched=True（P20 默认路径）：跳过已富化作品——热榜富化只负责把
        “新上榜、尚未入库”的作品带进来；已入库作品的数据保鲜交给榜单/销量等专用步。
        """
        cutoff = (
            datetime.now().astimezone() - timedelta(days=max(window_days, 0))
        ).isoformat(timespec="seconds")
        sql = (
            "SELECT p.workno, p.source, p.attempts FROM pending p "
            "JOIN works w ON w.workno = p.workno "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "WHERE w.hot_seen_at IS NOT NULL AND w.hot_seen_at >= ? "
            "AND e.workno IS NULL "
        )
        if skip_enriched:
            sql += "AND w.enriched_at IS NULL "
        sql += "ORDER BY (w.enriched_at IS NOT NULL), p.discovered_at LIMIT ?"
        cursor = self.conn.execute(sql, (cutoff, limit))
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def pending_batch_by_source(self, limit: int, prefix: str) -> List[Tuple[str, str, int]]:
        """按来源前缀取队列（如 refresh:，用于换语言/数据刷新等定向处理，P8）。"""
        cursor = self.conn.execute(
            "SELECT p.workno, p.source, p.attempts FROM pending p "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "WHERE p.source LIKE ? AND e.workno IS NULL "
            "ORDER BY p.workno LIMIT ?",
            (f"{prefix}%", limit),
        )
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def pending_batch_exact_source(
        self, limit: int, source: str, skip_enriched: bool = True
    ) -> List[Tuple[str, str, int]]:
        """按「来源完整匹配」取队列（P19.2：现导入按分类定向富化）。

        skip_enriched=True 时跳过已富化作品——只把新作品带入库，
        老作品的保鲜交给常驻流程（热榜/销量/刷新）。
        """
        sql = (
            "SELECT p.workno, p.source, p.attempts FROM pending p "
            "LEFT JOIN works w ON w.workno = p.workno "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "WHERE p.source = ? AND e.workno IS NULL "
        )
        if skip_enriched:
            sql += "AND w.enriched_at IS NULL "
        sql += "ORDER BY p.discovered_at LIMIT ?"
        cursor = self.conn.execute(sql, (str(source), limit))
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def enqueue_refresh(self, source: str) -> int:
        """将已富化作品重新登记进队列（换语言/刷新数据），返回登记数量。

        已在队列中的行会被改为该来源（如 refresh:zh_CN），保证刷新批次能优先处理到。
        """
        now = _now()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO pending(workno, source, discovered_at) "
                "SELECT workno, ?, ? FROM works WHERE enriched_at IS NOT NULL "
                "ON CONFLICT(workno) DO UPDATE SET source=excluded.source, "
                "discovered_at=excluded.discovered_at",
                (source, now),
            )
        return int(cursor.rowcount or 0)

    def filter_known_worknos(self, worknos: Sequence[str]) -> List[str]:
        """过滤掉「已富化」与「已排除」的作品号（P18 目录遍历登记前调用；分批查询）。"""
        result = list(worknos)
        if not result:
            return []
        known = set()
        for start in range(0, len(result), 400):
            chunk = result[start : start + 400]
            marks = ",".join("?" for _ in chunk)
            rows = self.conn.execute(
                f"SELECT workno FROM works WHERE enriched_at IS NOT NULL "
                f"AND workno IN ({marks})",
                chunk,
            )
            known.update(row[0] for row in rows)
            rows = self.conn.execute(
                f"SELECT workno FROM excluded WHERE workno IN ({marks})", chunk
            )
            known.update(row[0] for row in rows)
        return [workno for workno in result if workno not in known]

    def add_catalog_pending(self, worknos: Sequence[str], source: str) -> int:
        """目录遍历登记（P18）：新登记，或把既有行改标为目录来源。

        与 add_pending_many 的差别：既有行会迁移到目录来源——保证目录任务
        （候选查询按 `source_prefix='catalog:'` 过滤）能取到它们；但 `refresh:%`
        （换语言等定向队列）保持原来源，不被覆盖。
        """
        rows = [(workno, source, _now()) for workno in worknos]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                "INSERT INTO pending(workno, source, discovered_at) VALUES(?,?,?) "
                "ON CONFLICT(workno) DO UPDATE SET source=excluded.source "
                "WHERE pending.source NOT LIKE 'refresh:%'",
                rows,
            )
        return len(rows)

    # ---- 排除清单（非游戏等）---------------------------------------------
    def add_excluded(self, workno: str, work_type: Optional[str]) -> None:
        """记入排除清单（防止未来重复富化）；work_type 可为 None。"""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO excluded(workno, work_type, excluded_at) "
                "VALUES(?,?,?)",
                (workno, work_type, _now()),
            )

    def delete_work(self, workno: str) -> None:
        """从库中彻底删除作品（含分类与销量历史、队列登记）；封面由调用方处理。"""
        with self.conn:
            self.conn.execute("DELETE FROM works WHERE workno=?", (workno,))
            self.conn.execute("DELETE FROM work_genres WHERE workno=?", (workno,))
            self.conn.execute("DELETE FROM sales_history WHERE workno=?", (workno,))
            self.conn.execute("DELETE FROM pending WHERE workno=?", (workno,))

    def list_non_games(self, work_types: Sequence[str]) -> List[Tuple[str, Optional[str]]]:
        """已富化但不在白名单内的作品（workno, work_type）；白名单为空时返回空。"""
        if not work_types:
            return []
        placeholders = ",".join("?" for _ in work_types)
        rows = self.conn.execute(
            f"SELECT workno, work_type FROM works WHERE enriched_at IS NOT NULL "
            f"AND (work_type IS NULL OR work_type NOT IN ({placeholders}))",
            list(work_types),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def pending_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM pending").fetchone()[0])

    def finish_pending(self, workno: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM pending WHERE workno=?", (workno,))

    def fail_pending(self, workno: str, max_attempts: int = 3) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE pending SET attempts=attempts+1 WHERE workno=?", (workno,)
            )
            self.conn.execute(
                "DELETE FROM pending WHERE workno=? AND attempts>=?", (workno, max_attempts)
            )

    # ---- 渐进导入（P10）--------------------------------------------------
    def get_import_job(self) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM import_job WHERE id=1").fetchone()
        return dict(row) if row else None

    def save_import_job(
        self,
        *,
        years: str,
        phase: str,
        boundary_old: int,
        boundary_modern: int,
        fresh_old: int,
        fresh_modern: int,
        min_sales: int,
        fresh_days: int,
        source: str = "numbers",
        start_page: int = 0,
    ) -> None:
        """新建/重建导入任务（单行；计数清零；质量门槛一并快照）。

        start_page（P23）：起始页游标——续深模式从已覆盖位置继续时预设。
        """
        now = _now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO import_job(id, years, source, phase, boundary_old, "
                "boundary_modern, fresh_old, fresh_modern, min_sales, fresh_days, "
                "walk_done, cursor_page, started_at, updated_at) "
                "VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET years=excluded.years, "
                "source=excluded.source, phase=excluded.phase, "
                "boundary_old=excluded.boundary_old, boundary_modern=excluded.boundary_modern, "
                "fresh_old=excluded.fresh_old, fresh_modern=excluded.fresh_modern, "
                "min_sales=excluded.min_sales, fresh_days=excluded.fresh_days, "
                "started_at=excluded.started_at, updated_at=excluded.updated_at, "
                "enriched=0, excluded=0, skipped=0, failed=0, note='', "
                "walk_done=0, cursor_page=excluded.cursor_page",
                (
                    str(years),
                    str(source),
                    phase,
                    int(boundary_old),
                    int(boundary_modern),
                    int(fresh_old),
                    int(fresh_modern),
                    int(min_sales),
                    int(fresh_days),
                    int(start_page),
                    now,
                    now,
                ),
            )

    def update_import_job(self, **fields: Any) -> None:
        """部分更新任务字段（phase / 计数 / note / 遍历游标 walk_done·cursor_page）。"""
        allowed = {
            "phase", "enriched", "excluded", "skipped", "failed", "note",
            "walk_done", "cursor_page",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.conn:
            self.conn.execute(
                f"UPDATE import_job SET {assignments}, updated_at=? WHERE id=1",
                [*updates.values(), _now()],
            )

    def delete_import_job(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM import_job WHERE id=1")

    def _import_where(
        self, boundary_old: int, boundary_modern: int
    ) -> Tuple[str, List[Any]]:
        """导入候选边界子句（P11）：编号在范围内且未被排除。

        销量门槛（min_sales/fresh_days）不在这里预过滤——由导入流程运行时
        用 info/ajax 批量实查判定（旧作品达标才富化）。
        """
        clause = (
            "e.workno IS NULL AND ("
            "(LENGTH(p.workno)=8 AND CAST(SUBSTR(p.workno,3) AS INTEGER) >= ?) "
            "OR (LENGTH(p.workno)=10 AND CAST(SUBSTR(p.workno,3) AS INTEGER) >= ?))"
        )
        return clause, [boundary_old, boundary_modern]

    def import_candidates(
        self,
        limit: int,
        boundary_old: int,
        boundary_modern: int,
        source_prefix: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """导入候选作品（销量已知优先 → 编号新到旧）；source_prefix 限定来源（P18）。"""
        clause, args = self._import_where(boundary_old, boundary_modern)
        if source_prefix:
            clause += " AND p.source LIKE ?"
            args = [*args, f"{source_prefix}%"]
        cursor = self.conn.execute(
            "SELECT p.workno, p.source FROM pending p "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "LEFT JOIN works w ON w.workno = p.workno "
            f"WHERE {clause} "
            "ORDER BY (w.sales IS NULL), w.sales DESC, LENGTH(p.workno) DESC, p.workno DESC "
            "LIMIT ?",
            [*args, limit],
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def import_remaining(
        self, boundary_old: int, boundary_modern: int, source_prefix: Optional[str] = None
    ) -> int:
        """当前边界下尚未处理的候选数量（source_prefix 限定来源，P18）。"""
        clause, args = self._import_where(boundary_old, boundary_modern)
        if source_prefix:
            clause += " AND p.source LIKE ?"
            args = [*args, f"{source_prefix}%"]
        row = self.conn.execute(
            "SELECT COUNT(*) FROM pending p "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            f"WHERE {clause}",
            args,
        ).fetchone()
        return int(row[0])

    def import_fresh_remaining(self, fresh_old: int, fresh_modern: int) -> int:
        """边界内「新作窗」数量（供试算展示，不参与实际选择）。"""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM pending p "
            "LEFT JOIN excluded e ON e.workno = p.workno "
            "WHERE e.workno IS NULL AND ("
            "(LENGTH(p.workno)=8 AND CAST(SUBSTR(p.workno,3) AS INTEGER) >= ?) "
            "OR (LENGTH(p.workno)=10 AND CAST(SUBSTR(p.workno,3) AS INTEGER) >= ?))",
            (fresh_old, fresh_modern),
        ).fetchone()
        return int(row[0])

    def get_work_sales(self, workno: str) -> Optional[int]:
        """读取库内已知销量（未知返回 None）。"""
        row = self.conn.execute(
            "SELECT sales FROM works WHERE workno=?", (workno,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    # ---- works --------------------------------------------------------
    def upsert_work(self, row: Dict[str, Any]) -> None:
        row = dict(row)
        row["enriched_at"] = _now()
        row.setdefault("updated_at", _now())
        columns = [name for name in WORK_COLUMNS if name in row]
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{name}=excluded.{name}" for name in columns if name != "workno")
        sql = (
            f"INSERT INTO works({','.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT(workno) DO UPDATE SET {updates}"
        )
        with self.conn:
            self.conn.execute(sql, [row[name] for name in columns])

    def replace_genres(self, workno: str, genres: Sequence[Dict[str, str]]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM work_genres WHERE workno=?", (workno,))
            self.conn.executemany(
                "INSERT OR REPLACE INTO work_genres(workno,genre_id,name) VALUES(?,?,?)",
                [(workno, genre["id"], genre["name"]) for genre in genres],
            )

    # ---- 分类人气名次（P19）-----------------------------------------------
    def save_genre_info(self, genre_id: str, name: str, count: Optional[int]) -> None:
        """记录分类元信息（名称/在售件数，来自分类人气页）。

        P20.1：若分类目录（排行页中文导航，存于 `genre_catalog`）已有该 id 的中文名，
        展示名以中文为准（站点分类页本身只有日文名）。
        """
        display = str(name)
        row = self.conn.execute(
            "SELECT name FROM genre_catalog WHERE genre_id=?", (str(genre_id),)
        ).fetchone()
        if row and row[0]:
            display = str(row[0])
        with self.conn:
            self.conn.execute(
                "INSERT INTO genre_info(genre_id,name,count,seen_at) VALUES(?,?,?,?) "
                "ON CONFLICT(genre_id) DO UPDATE SET name=excluded.name, "
                "count=excluded.count, seen_at=excluded.seen_at",
                (str(genre_id), display, count, _now()),
            )

    def replace_genre_ranks(
        self,
        genre_id: str,
        positions: Dict[str, int],
        *,
        start: int = 1,
        end: Optional[int] = None,
    ) -> None:
        """替换某分类的名次快照（P19；P19.1 起支持「范围替换」以保护深页）。

        - end=None：整批替换（删除 ≥start 的旧名次）——抓到自然末页/空页时的形态；
        - end=N：仅替换 [start, N]，范围外（更深）的名次保留——每日只抓前 N 页、
          或「载入更多」只抓一页时，不会抹掉此前手动加深的名次。
        """
        now = _now()
        with self.conn:
            if end is None:
                self.conn.execute(
                    "DELETE FROM genre_ranks WHERE genre_id=? AND position>=?",
                    (str(genre_id), int(start)),
                )
            else:
                self.conn.execute(
                    "DELETE FROM genre_ranks WHERE genre_id=? AND position>=? AND position<=?",
                    (str(genre_id), int(start), int(end)),
                )
            self.conn.executemany(
                "INSERT INTO genre_ranks(workno,genre_id,position,seen_at) VALUES(?,?,?,?) "
                "ON CONFLICT(workno,genre_id) DO UPDATE SET position=excluded.position, "
                "seen_at=excluded.seen_at",
                [
                    (workno, str(genre_id), int(position), now)
                    for workno, position in positions.items()
                ],
            )

    def genre_positions(self, workno: str) -> Dict[str, int]:
        """某作品在各分类的人气名次（{genre_id: position}；无记录返回空）。"""
        rows = self.conn.execute(
            "SELECT genre_id, position FROM genre_ranks WHERE workno=?", (workno,)
        ).fetchall()
        return {row[0]: int(row[1]) for row in rows}

    def save_genre_catalog(self, items: Sequence[Tuple[str, str]]) -> int:
        """保存站点分类目录（排行页导航解析：id → 名称）——P19.3 搜索/现导入用。"""
        now = _now()
        rows = [
            (str(genre_id).strip(), str(name).strip(), now)
            for genre_id, name in items
            if str(genre_id).strip() and str(name).strip()
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                "INSERT INTO genre_catalog(genre_id,name,seen_at) VALUES(?,?,?) "
                "ON CONFLICT(genre_id) DO UPDATE SET name=excluded.name, seen_at=excluded.seen_at",
                rows,
            )
        return len(rows)

    def list_genre_catalog(self) -> List[Dict[str, Any]]:
        """分类目录（按站点导航顺序）。"""
        rows = self.conn.execute(
            "SELECT genre_id, name FROM genre_catalog ORDER BY rowid"
        ).fetchall()
        return [{"id": row[0], "name": row[1]} for row in rows]

    def genre_depth(self, genre_id: str) -> int:
        """某分类已抓到的名次深度（最大名次；未抓过返回 0）。"""
        row = self.conn.execute(
            "SELECT COALESCE(MAX(position),0) FROM genre_ranks WHERE genre_id=?",
            (str(genre_id),),
        ).fetchone()
        return int(row[0])

    def genre_summaries(self) -> List[Dict[str, Any]]:
        """有数据的分类摘要（名称/在售件数/数据日期/已抓深度）——供导出给应用。"""
        rows = self.conn.execute(
            "SELECT gi.genre_id, gi.name, gi.count, gi.seen_at, "
            "(SELECT COALESCE(MAX(r.position),0) FROM genre_ranks r "
            " WHERE r.genre_id=gi.genre_id) AS depth "
            "FROM genre_info gi ORDER BY gi.rowid"
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "count": row[2],
                "seen_at": row[3],
                "depth": int(row[4]),
            }
            for row in rows
        ]

    def remove_genre(self, genre_id: str) -> Tuple[int, int]:
        """移除某分类的名次与元信息（P34；已入库作品与其他分类不受影响）。

        返回 (删除的名次条数, 是否删除元信息〔0/1〕)。
        """
        gid = str(genre_id)
        with self.conn:
            ranks = self.conn.execute(
                "DELETE FROM genre_ranks WHERE genre_id=?", (gid,)
            ).rowcount
            info = self.conn.execute(
                "DELETE FROM genre_info WHERE genre_id=?", (gid,)
            ).rowcount
        return int(ranks), int(info)

    def rank_trend_depth(self) -> int:
        """全站人气序的已记录深度（最大名次；未抓过返回 0）。"""
        row = self.conn.execute(
            "SELECT COALESCE(MAX(rank_trend_current),0) FROM works"
        ).fetchone()
        return int(row[0])

    def clear_rank_trend_beyond(self, position: int) -> int:
        """清理全站人气序中超出本次抓取深度的陈旧名次（P20：深度收缩时同步收缩）。"""
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE works SET rank_trend_current=NULL WHERE rank_trend_current > ?",
                (int(position),),
            )
        return int(cursor.rowcount or 0)

    def record_sales_many(
        self, site: str, sales: Dict[str, int], source: str,
        wishlist: Optional[Dict[str, int]] = None,
        options: Optional[Dict[str, str]] = None,
    ) -> None:
        seen_at = _now()
        with self.conn:
            for workno, value in sales.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO works(workno,site,updated_at) VALUES(?,?,?)",
                    (workno, site, seen_at),
                )
                self.conn.execute(
                    "UPDATE works SET sales=?, sales_seen_at=?, updated_at=? WHERE workno=?",
                    (value, seen_at, seen_at, workno),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO sales_history(workno,sales,seen_at,source) "
                    "VALUES(?,?,?,?)",
                    (workno, value, seen_at, source),
                )
            for workno, count in (wishlist or {}).items():
                self.conn.execute(
                    "UPDATE works SET wishlist_count=?, updated_at=? WHERE workno=?",
                    (count, seen_at, workno),
                )
            # P16：options 徽章 token（SND=音声あり / MS2=音楽あり / MV2=動画あり …）
            for workno, tokens in (options or {}).items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO works(workno,site,updated_at) VALUES(?,?,?)",
                    (workno, site, seen_at),
                )
                self.conn.execute(
                    "UPDATE works SET options=?, updated_at=? WHERE workno=?",
                    (tokens, seen_at, workno),
                )

    def works_for_sales_sync(
        self, stale_days: Optional[int] = None, limit: Optional[int] = None
    ) -> List[str]:
        """待同步销量的已富化作品（P11）。

        stale_days=None：仅缺销量/从未同步的；stale_days=N：另含 N 天前同步过的。
        """
        clauses = ["enriched_at IS NOT NULL"]
        args: List[Any] = []
        if stale_days is None:
            clauses.append("(sales IS NULL OR sales_seen_at IS NULL)")
        elif int(stale_days) > 0:
            cutoff = (
                datetime.now().astimezone() - timedelta(days=int(stale_days))
            ).isoformat(timespec="seconds")
            clauses.append("(sales IS NULL OR sales_seen_at IS NULL OR sales_seen_at < ?)")
            args.append(cutoff)
        # stale_days == 0：全部已富化作品（--all）
        sql = (
            "SELECT workno FROM works WHERE " + " AND ".join(clauses)
            + " ORDER BY (sales IS NULL) DESC, workno"
        )
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        return [row[0] for row in self.conn.execute(sql, args).fetchall()]

    def works_for_sales_sync_hot(
        self, hot_days: int = 7, min_age_days: float = 1.0, limit: Optional[int] = None
    ) -> List[str]:
        """在榜作品销量刷新（P20 做减法）：近 hot_days 天上过榜、且距上次同步
        ≥ min_age_days 的已富化作品——每件每天最多刷新一次；不在榜作品不再自动刷新。"""
        now = datetime.now().astimezone()
        cutoff_hot = (now - timedelta(days=max(int(hot_days), 0))).isoformat(
            timespec="seconds"
        )
        sql = (
            "SELECT workno FROM works WHERE enriched_at IS NOT NULL "
            "AND hot_seen_at IS NOT NULL AND hot_seen_at >= ? "
        )
        args: List[Any] = [cutoff_hot]
        if float(min_age_days) > 0:
            # 每件每天最多刷新一次（0 = 不限制间隔，直接用 0 做比较会撞同秒边界）
            cutoff_fresh = (now - timedelta(days=float(min_age_days))).isoformat(
                timespec="seconds"
            )
            sql += "AND (sales_seen_at IS NULL OR sales_seen_at < ?) "
            args.append(cutoff_fresh)
        sql += "ORDER BY (sales IS NULL) DESC, workno"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        return [row[0] for row in self.conn.execute(sql, args).fetchall()]

    def record_ranks(self, site: str, term: str, ranks: Dict[str, int]) -> int:
        """记录当前榜名次（term: day/week/month/trend，1 = 最热）；返回写入条数。

        写入 rank_*_current 与 rank_current_seen_at（观察时间）。
        未知 term 或空数据直接跳过；作品行不存在时先建占位行（与销量一致）。
        注意：rank_day/week/month（无 `_current`）为富化写入的历史名次快照，勿混用。
        """
        column = RANK_COLUMNS.get(term)
        if not column or not ranks:
            return 0
        now = _now()
        with self.conn:
            for workno, position in ranks.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO works(workno,site,updated_at) VALUES(?,?,?)",
                    (workno, site, now),
                )
                self.conn.execute(
                    f"UPDATE works SET {column}=?, rank_current_seen_at=?, updated_at=? "
                    "WHERE workno=?",
                    (int(position), now, now, workno),
                )
        return len(ranks)

    def mark_hot(self, site: str, worknos: Sequence[str]) -> int:
        """标记作品出现在当日榜单/列表视图（`hot_seen_at`），供热榜富化优先（P6）。"""
        if not worknos:
            return 0
        now = _now()
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO works(workno,site,updated_at) VALUES(?,?,?)",
                [(workno, site, now) for workno in worknos],
            )
            self.conn.executemany(
                "UPDATE works SET hot_seen_at=?, updated_at=? WHERE workno=?",
                [(now, now, workno) for workno in worknos],
            )
        return len(worknos)

    # ---- 统计 ----------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        def scalar(sql: str) -> int:
            return int(self.conn.execute(sql).fetchone()[0])

        last_seen: Dict[str, str] = {}
        for key, value in self.conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE 'last_seen_workno:%'"
        ).fetchall():
            last_seen[key.split(":", 1)[1]] = value

        runs = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT id, started_at, finished_at, command, ok, note "
                "FROM runs ORDER BY id DESC LIMIT 5"
            ).fetchall()
        ]
        return {
            # P18：目录遍历会为未富化作品建「销量占位行」——作品总数取已富化口径
            "works": scalar("SELECT COUNT(*) FROM works WHERE enriched_at IS NOT NULL"),
            "rows": scalar("SELECT COUNT(*) FROM works"),
            "enriched": scalar("SELECT COUNT(*) FROM works WHERE enriched_at IS NOT NULL"),
            "with_sales": scalar("SELECT COUNT(*) FROM works WHERE sales IS NOT NULL"),
            "pending": self.pending_count(),
            "genres": scalar("SELECT COUNT(*) FROM work_genres"),
            "last_seen": last_seen,
            "runs": runs,
        }
