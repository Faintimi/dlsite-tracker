"""HTTP 层本机回环测试（离线；用 127.0.0.1 临时服务器验证 keep-alive / 重定向 / 重试）。"""

from __future__ import annotations

import http.server
import threading
import unittest

from dlsite_tracker.http import Fetcher, HttpError


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    lock = threading.Lock()
    connections = 0
    requests = 0
    retry_hits = 0

    def log_message(self, *args):  # 静默
        pass

    def setup(self):
        super().setup()
        with Handler.lock:
            Handler.connections += 1

    def _send(self, status: int, body: bytes = b"", extra=None):
        self.send_response(status)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        with Handler.lock:
            Handler.requests += 1
        if self.path == "/img":
            self._send(200, b"hello-image")
        elif self.path == "/redirect":
            self._send(302, extra={"Location": "/img"})
        elif self.path == "/retry":
            with Handler.lock:
                Handler.retry_hits += 1
                first = Handler.retry_hits == 1
            if first:
                self._send(429, extra={"Retry-After": "0"})
            else:
                self._send(200, b"ok-after-retry")
        else:
            self._send(404)


def make_fetcher() -> Fetcher:
    return Fetcher(
        user_agent="test",
        page_delay=0.01,
        api_delay=0.01,
        image_delay=0.01,
        timeout=5,
        max_retries=1,
    )


class LocalServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.connections = 0
        Handler.requests = 0
        Handler.retry_hits = 0

    def test_keep_alive_reuses_connection(self):
        fetcher = make_fetcher()
        try:
            first = fetcher.get_bytes(self.base + "/img", kind="image")
            second = fetcher.get_bytes(self.base + "/img", kind="image")
        finally:
            fetcher.close()
        self.assertEqual(first, b"hello-image")
        self.assertEqual(second, b"hello-image")
        self.assertEqual(Handler.requests, 2)
        self.assertEqual(Handler.connections, 1)  # 两条请求复用同一条连接

    def test_redirect_followed(self):
        fetcher = make_fetcher()
        try:
            data = fetcher.get_bytes(self.base + "/redirect", kind="page")
        finally:
            fetcher.close()
        self.assertEqual(data, b"hello-image")

    def test_retry_after_429(self):
        fetcher = make_fetcher()
        try:
            data = fetcher.get_bytes(self.base + "/retry", kind="api")
        finally:
            fetcher.close()
        self.assertEqual(data, b"ok-after-retry")
        self.assertEqual(Handler.retry_hits, 2)

    def test_404_raises(self):
        fetcher = make_fetcher()
        try:
            with self.assertRaises(HttpError):
                fetcher.get_bytes(self.base + "/missing", kind="page")
        finally:
            fetcher.close()


if __name__ == "__main__":
    unittest.main()
