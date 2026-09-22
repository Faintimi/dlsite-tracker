"""HTTP 层测试（离线；不发起任何网络请求）。"""

from __future__ import annotations

import time
import unittest

from dlsite_tracker.http import Fetcher


def make_fetcher(delay: float) -> Fetcher:
    return Fetcher(
        user_agent="test",
        page_delay=delay,
        api_delay=delay,
        image_delay=delay,
        timeout=1,
        max_retries=0,
    )


class ThrottleTest(unittest.TestCase):
    def test_first_request_no_wait(self):
        # 回归：monotonic 基线接近 0 的环境下，首次请求不应等待（P11.1 修复）
        fetcher = make_fetcher(10.0)
        start = time.monotonic()
        fetcher._throttle("page")
        self.assertLess(time.monotonic() - start, 1.0)

    def test_second_request_waits(self):
        fetcher = make_fetcher(0.3)
        fetcher._throttle("page")
        start = time.monotonic()
        fetcher._throttle("page")
        self.assertGreaterEqual(time.monotonic() - start, 0.25)

    def test_kinds_are_independent(self):
        fetcher = make_fetcher(5.0)
        fetcher._throttle("page")
        start = time.monotonic()
        fetcher._throttle("api")
        self.assertLess(time.monotonic() - start, 1.0)


if __name__ == "__main__":
    unittest.main()
