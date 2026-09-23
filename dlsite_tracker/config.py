"""配置加载（INI 格式；仅标准库）。

用法：``Config.load("config.ini")``；模板见仓库根目录 config.example.ini。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# 硬性下限（默认节流不得调低）
FLOORS: List[Tuple[str, str, float]] = [
    ("http", "page_delay_seconds", 5.0),
    ("http", "api_delay_seconds", 1.0),
    ("http", "image_delay_seconds", 0.2),
]

DEFAULTS = {
    "general": {"data_dir": "data", "out_dir": "out", "timezone": "Asia/Tokyo"},
    "scope": {"sites": "maniax", "default_work_types": "RPG, SLN, ADV, ACN, STG, PZL, QIZ, TBL, DNV, ETC, TYP"},
    "http": {
        "page_delay_seconds": "10.0",
        "api_delay_seconds": "1.0",
        "image_delay_seconds": "0.25",
        "timeout_seconds": "25",
        "max_retries": "4",
        "user_agent": "dlsite-tracker/0.1 (local personal data pipeline)",
    },
    "discovery": {
        "sitemap_max_shards_per_run": "3",
        "rank_terms": "day, week, month",
        "rank_categories": "game",
        "genre_rank_ids": "016,502,048,510,526,317,046,004,536,432,533,509,519,431,012",
        "genre_rank_pages": "2",
        "genre_daily_pages": "1",
        "trend_pages": "5",
        "list_work_types": "game",
    },
    "enrich": {"batch_size_per_run": "400", "store_raw": "false", "hot_window_days": "7", "locale": "zh_CN"},
    "import": {"years": "0", "fresh_days": "90", "min_sales": "2000", "cover_trigger": "1000", "cover_batch": "300"},
    "images": {"enabled": "true", "max_per_run": "300", "workers": "4"},
    "serve": {"host": "127.0.0.1", "port": "8765"},
}


def split_list(value: str) -> List[str]:
    """逗号分隔 → 去空列表（兼容中文逗号）。"""
    return [part.strip() for part in (value or "").replace("，", ",").split(",") if part.strip()]


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    path: Path
    base_dir: Path
    data_dir: Path
    out_dir: Path
    timezone: str
    sites: List[str]
    default_work_types: List[str]
    page_delay: float
    api_delay: float
    image_delay: float
    timeout: float
    max_retries: int
    user_agent: str
    sitemap_max_shards: int
    rank_terms: List[str]
    rank_categories: List[str]
    genre_rank_ids: str
    genre_rank_pages: int
    genre_daily_pages: int
    trend_pages: int
    list_work_types: List[str]
    enrich_batch: int
    hot_window_days: int
    import_years: int
    import_fresh_days: int
    import_min_sales: int
    import_cover_trigger: int
    import_cover_batch: int
    locale: str
    store_raw: bool
    images_enabled: bool
    images_max: int
    images_workers: int
    serve_host: str
    serve_port: int

    @classmethod
    def load(cls, path="config.ini") -> "Config":
        path = Path(path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"未找到配置文件 {path}；请先执行：cp config.example.ini config.ini"
            )
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")

        def get(section: str, key: str) -> str:
            return parser.get(section, key, fallback=DEFAULTS[section][key])

        delays = {}
        for section, key, floor in FLOORS:
            value = float(get(section, key))
            if value < floor:
                raise ValueError(
                    f"[{section}] {key}={value} 低于硬性下限 {floor}；"
                    "默认节流不得调低（如确需调整请先人工评审）"
                )
            delays[key] = value

        base = path.resolve().parent
        data_dir = Path(get("general", "data_dir")).expanduser()
        out_dir = Path(get("general", "out_dir")).expanduser()
        if not data_dir.is_absolute():
            data_dir = (base / data_dir).resolve()
        if not out_dir.is_absolute():
            out_dir = (base / out_dir).resolve()

        return cls(
            path=path,
            base_dir=base,
            data_dir=data_dir,
            out_dir=out_dir,
            timezone=get("general", "timezone"),
            sites=split_list(get("scope", "sites")),
            default_work_types=split_list(get("scope", "default_work_types")),
            page_delay=delays["page_delay_seconds"],
            api_delay=delays["api_delay_seconds"],
            image_delay=delays["image_delay_seconds"],
            timeout=float(get("http", "timeout_seconds")),
            max_retries=int(get("http", "max_retries")),
            user_agent=get("http", "user_agent"),
            sitemap_max_shards=int(get("discovery", "sitemap_max_shards_per_run")),
            rank_terms=split_list(get("discovery", "rank_terms")),
            rank_categories=split_list(get("discovery", "rank_categories")),
            genre_rank_ids=get("discovery", "genre_rank_ids"),
            genre_rank_pages=int(get("discovery", "genre_rank_pages")),
            genre_daily_pages=int(get("discovery", "genre_daily_pages")),
            trend_pages=int(get("discovery", "trend_pages")),
            list_work_types=split_list(get("discovery", "list_work_types")),
            enrich_batch=int(get("enrich", "batch_size_per_run")),
            hot_window_days=int(get("enrich", "hot_window_days")),
            import_years=int(get("import", "years")),
            import_fresh_days=int(get("import", "fresh_days")),
            import_min_sales=int(get("import", "min_sales")),
            import_cover_trigger=int(get("import", "cover_trigger")),
            import_cover_batch=int(get("import", "cover_batch")),
            locale=get("enrich", "locale"),
            store_raw=parse_bool(get("enrich", "store_raw")),
            images_enabled=parse_bool(get("images", "enabled")),
            images_max=int(get("images", "max_per_run")),
            images_workers=int(get("images", "workers")),
            serve_host=get("serve", "host"),
            serve_port=int(get("serve", "port")),
        )


def add_to_config_list(path: Path, section: str, key: str, item: str) -> Tuple[bool, str]:
    """把 item 追加进 INI 的逗号列表（行级编辑，保留注释与既有顺序）。

    返回 (是否发生变更, 变更后的完整列表文本)。
    - 键已存在：去重后追加；
    - 键不存在但节存在：插入节头之后；
    - 节不存在：追加到文件末尾。
    """
    path = Path(path).expanduser()
    item = str(item).strip()
    lines = path.read_text(encoding="utf-8").splitlines()
    header = f"[{section}]"
    section_start = -1
    insert_at = -1  # 键不存在时的插入位置（节内第一条内容行之前）
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section_start >= 0:
                break  # 已越过目标节，查找结束
            if stripped == header:
                section_start = index
            continue
        if section_start >= 0 and "=" in stripped and not stripped.startswith(("#", ";")):
            name, _, value = stripped.partition("=")
            if name.strip() == key:
                items = [
                    part.strip()
                    for part in value.replace("，", ",").split(",")
                    if part.strip()
                ]
                if item in items:
                    return False, ",".join(items)
                items.append(item)
                text_value = ",".join(items)
                lines[index] = f"{key} = {text_value}"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True, text_value
            if insert_at < 0:
                insert_at = index
    if section_start >= 0:
        position = insert_at if insert_at >= 0 else section_start + 1
        lines.insert(position, f"{key} = {item}")
    else:
        lines.extend(["", header, f"{key} = {item}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, item


def remove_from_config_list(path: Path, section: str, key: str, item: str) -> Tuple[bool, str]:
    """从 INI 的逗号列表中移除 item（P34；行级编辑，保留注释与既有顺序）。

    返回 (是否发生变更, 变更后的完整列表文本)。
    - 节/键不存在、或 item 不在列表中：返回 (False, 当前列表文本或 "")；
    - 移除后列表为空：写回 `key =`（空值）。
    """
    path = Path(path).expanduser()
    item = str(item).strip()
    lines = path.read_text(encoding="utf-8").splitlines()
    header = f"[{section}]"
    section_start = -1
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section_start >= 0:
                break  # 已越过目标节，查找结束
            if stripped == header:
                section_start = index
            continue
        if section_start >= 0 and "=" in stripped and not stripped.startswith(("#", ";")):
            name, _, value = stripped.partition("=")
            if name.strip() == key:
                items = [
                    part.strip()
                    for part in value.replace("，", ",").split(",")
                    if part.strip()
                ]
                if item not in items:
                    return False, ",".join(items)
                items.remove(item)
                text_value = ",".join(items)
                lines[index] = f"{key} = {text_value}".rstrip()
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True, text_value
    return False, ""
