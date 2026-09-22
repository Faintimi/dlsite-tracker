"""HTTP 客户端：礼貌节流、持久连接（keep-alive）、失败重试、robots 校验（仅标准库）。

设计要点：
- 按 kind（page / api / image）分别维护最小请求间隔，串行执行；
- 持久连接（keep-alive，P14）：按主机复用连接，避免每次请求重复 TLS 握手
  （单张封面实测握手 180–370ms，是主要固定开销）；复用连接被服务器空闲关闭时立即换新连接重试；
- 429 与 5xx 指数退避，优先遵守 Retry-After；3xx 自动跟随（最多 5 跳）；
- 注意：改用 http.client 后不再读取环境代理变量（原 urllib 隐式行为）；如需代理支持请提出；
- 每次网络命令启动时校验 robots.txt 的关键规则，异常即中止；
- 线程模型：同一 Fetcher 不跨线程共享；图片并发由工作线程各自持有克隆 Fetcher
  （各自节流与连接池）；计数可通过 counters / counter_lock 共享。
"""

from __future__ import annotations

import http.client
import json
import logging
import re
import ssl
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

LOG = logging.getLogger("dlsite_tracker.http")

ROBOTS_URL = "https://www.dlsite.com/robots.txt"
REQUIRED_CRAWL_DELAY = 10
REQUIRED_ROBOTS_MARKERS = ("per_page/*/page/",)


class HttpError(RuntimeError):
    """网络请求在重试后仍失败。"""


class RobotsChanged(RuntimeError):
    """robots.txt 与预期不符：中止运行，等待人工确认。"""


class _Retryable(Exception):
    """内部信号：可重试失败（429 / 5xx / 网络错误）。"""

    def __init__(self, message: str, retry_after: Optional[str] = None):
        super().__init__(message)
        self.retry_after = retry_after


class _Fatal(Exception):
    """内部信号：不可重试失败（4xx / 超限 / 重定向异常）。"""


class Fetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        page_delay: float,
        api_delay: float,
        image_delay: float,
        timeout: float,
        max_retries: int,
        counters: Optional[Dict[str, int]] = None,
        counter_lock: Optional[threading.Lock] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self._delays = {"page": page_delay, "api": api_delay, "image": image_delay}
        # -inf = “从未请求过”：首次请求不应等待
        # （不能用 0.0：在 monotonic 基线接近 0 的环境里首请求会白等一个完整间隔）
        self._last: Dict[str, float] = {kind: float("-inf") for kind in self._delays}
        self.counters: Dict[str, int] = (
            counters if counters is not None else {kind: 0 for kind in self._delays}
        )
        self._counter_lock = counter_lock if counter_lock is not None else threading.Lock()
        self._robots_ok = False
        self._conns: Dict[str, http.client.HTTPConnection] = {}

    @classmethod
    def from_config(
        cls,
        cfg,
        counters: Optional[Dict[str, int]] = None,
        counter_lock: Optional[threading.Lock] = None,
    ) -> "Fetcher":
        return cls(
            user_agent=cfg.user_agent,
            page_delay=cfg.page_delay,
            api_delay=cfg.api_delay,
            image_delay=cfg.image_delay,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            counters=counters,
            counter_lock=counter_lock,
        )

    def _throttle(self, kind: str) -> None:
        wait = self._last[kind] + self._delays[kind] - time.monotonic()
        if wait > 0:
            if wait >= 2.0:
                LOG.info("按节流等待 %.1fs（%s 请求间隔）", wait, kind)
            time.sleep(wait)
        self._last[kind] = time.monotonic()

    def _backoff(self, attempt: int, retry_after: Optional[str]) -> None:
        delay: Optional[float] = None
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = None
        if delay is None:
            delay = min(60.0, 5.0 * (2 ** (attempt - 1)))
        LOG.warning("请求失败，第 %d 次重试前等待 %.1fs", attempt, delay)
        time.sleep(delay)

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": "ja,en;q=0.8",
            "Accept-Encoding": "identity",
        }

    def _connection(self, scheme: str, host: str, port: int) -> http.client.HTTPConnection:
        key = f"{scheme}://{host}:{port}"
        conn = self._conns.get(key)
        if conn is None:
            if scheme == "https":
                conn = http.client.HTTPSConnection(
                    host, port, timeout=self.timeout, context=ssl.create_default_context()
                )
            else:
                conn = http.client.HTTPConnection(host, port, timeout=self.timeout)
            self._conns[key] = conn
        return conn

    def _drop_connection(self, scheme: str, host: str, port: int) -> None:
        conn = self._conns.pop(f"{scheme}://{host}:{port}", None)
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass

    def close(self) -> None:
        """关闭所有持久连接（测试/清理用）。"""
        for conn in self._conns.values():
            try:
                conn.close()
            except OSError:
                pass
        self._conns.clear()

    @staticmethod
    def _drain(response) -> None:
        try:
            response.read()
        except (http.client.HTTPException, OSError):
            pass

    def _request(self, url: str, max_bytes: int) -> bytes:
        """单次请求（跟随重定向、复用连接）；失败抛内部信号 _Retryable / _Fatal。"""
        current = url
        redirects = 0
        reused_retry_used = False
        while True:
            parts = urlsplit(current)
            scheme = (parts.scheme or "").lower()
            if scheme not in ("http", "https"):
                raise _Fatal(f"不支持的协议：{current}")
            host = parts.hostname or ""
            port = parts.port or (443 if scheme == "https" else 80)
            path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
            reused = f"{scheme}://{host}:{port}" in self._conns
            conn = self._connection(scheme, host, port)
            try:
                conn.request("GET", path, headers=self._headers())
                response = conn.getresponse()
                status = response.status
                if status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    self._drain(response)
                    self._drop_connection(scheme, host, port)
                    redirects += 1
                    if not location or redirects > 5:
                        raise _Fatal(f"重定向异常：{current}")
                    current = urljoin(current, location)
                    continue
                if status in (429, 500, 502, 503, 504):
                    retry_after = response.getheader("Retry-After")
                    self._drain(response)
                    raise _Retryable(f"HTTP {status}", retry_after)
                if status >= 400:
                    self._drain(response)
                    raise _Fatal(f"HTTP {status}")
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise _Fatal(f"响应超过 {max_bytes} 字节上限")
                return data
            except (_Retryable, _Fatal):
                raise
            except (http.client.HTTPException, OSError, TimeoutError) as exc:
                self._drop_connection(scheme, host, port)
                if reused and not reused_retry_used:
                    # 复用连接可能已被服务器空闲关闭：立即换新连接重试一次（不打扰退避）
                    reused_retry_used = True
                    continue
                raise _Retryable(f"网络错误（{exc}）") from exc

    def get_bytes(self, url: str, kind: str = "page", max_bytes: int = 8_000_000) -> bytes:
        attempt = 0
        while True:
            attempt += 1
            self._throttle(kind)
            with self._counter_lock:
                self.counters[kind] += 1
            LOG.debug("GET[%s] %s", kind, url)
            try:
                return self._request(url, max_bytes)
            except _Retryable as exc:
                if attempt <= self.max_retries:
                    self._backoff(attempt, exc.retry_after)
                    continue
                raise HttpError(f"{exc}：{url}") from exc
            except _Fatal as exc:
                raise HttpError(f"{exc}：{url}") from exc

    def get_text(
        self, url: str, kind: str = "page", max_bytes: int = 8_000_000
    ) -> str:
        return self.get_bytes(url, kind=kind, max_bytes=max_bytes).decode("utf-8", errors="replace")

    def get_json(self, url: str) -> Any:
        text = self.get_text(url, kind="api")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HttpError(f"JSON 解析失败：{url}（{exc}）") from exc

    def verify_robots(self) -> None:
        """校验 robots.txt 的关键规则；进程内只执行一次。"""
        if self._robots_ok:
            return
        text = self.get_text(ROBOTS_URL, kind="page", max_bytes=200_000)
        match = re.search(r"(?im)^\s*Crawl-delay:\s*(\d+)", text)
        if not match or int(match.group(1)) < REQUIRED_CRAWL_DELAY:
            raise RobotsChanged(
                "robots.txt 中 Crawl-delay 缺失或低于 10；已中止（请人工核对 robots.txt）"
            )
        for marker in REQUIRED_ROBOTS_MARKERS:
            if marker not in text:
                raise RobotsChanged(
                    f"robots.txt 关键规则缺失（{marker}）；已中止（请人工核对 robots.txt）"
                )
        self._robots_ok = True
        LOG.info("robots.txt 校验通过（Crawl-delay=%s）", match.group(1))

    def summary(self) -> Dict[str, int]:
        return dict(self.counters)
