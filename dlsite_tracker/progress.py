"""任务进度文件的统一写入（应用横幅读取）。

update / import / covers 等抓取流程共用本模块写各自的进度文件（原子写）：

- 基础字段：``schema_version`` / ``phase`` / ``pid`` / ``updated_at`` / ``updated_ts``
- ``detail`` / ``years`` / ``schema_version`` / ``extra`` 按调用方提供的字段追加，
  不提供则保持旧格式（不写入该字段），确保既有读取方与 bash 脚本兼容。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso() -> str:
    """当前时间（与既有进度文件的 updated_at 格式一致）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write_task_progress(
    path: Path,
    phase: str,
    *,
    detail: Optional[str] = None,
    years: Optional[str] = None,
    schema_version: int = 1,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """原子写入任务进度（tmp 文件 + os.replace）。"""
    payload: Dict[str, Any] = {"schema_version": schema_version, "phase": phase}
    if detail is not None:
        payload["detail"] = detail
    if years is not None:
        payload["years"] = years
    payload["pid"] = os.getpid()
    payload["updated_at"] = now_iso()
    payload["updated_ts"] = int(time.time())
    if extra:
        payload.update(extra)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
