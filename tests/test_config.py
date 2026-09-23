"""配置模块测试（离线）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dlsite_tracker.config import (
    Config,
    add_to_config_list,
    parse_bool,
    remove_from_config_list,
    split_list,
)


class ConfigTest(unittest.TestCase):
    def _write_config(self, text: str):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "config.ini"
        path.write_text(text, encoding="utf-8")
        return tmp, path

    def test_defaults_and_lists(self):
        tmp, path = self._write_config("[scope]\nsites = maniax, girls\n")
        try:
            cfg = Config.load(path)
            self.assertEqual(cfg.sites, ["maniax", "girls"])
            self.assertEqual(cfg.page_delay, 10.0)
            self.assertEqual(cfg.rank_terms, ["day", "week", "month"])
            self.assertIn("RPG", cfg.default_work_types)  # P9 游戏白名单默认值
            self.assertEqual(cfg.import_years, 0)  # P10 渐进导入默认关闭
            self.assertEqual(cfg.import_fresh_days, 90)  # P10 质量门槛默认值
            self.assertEqual(cfg.import_min_sales, 2000)
            self.assertEqual(cfg.import_cover_trigger, 1000)  # P12.1 封面自愈
            self.assertEqual(cfg.import_cover_batch, 300)
            self.assertEqual(cfg.genre_daily_pages, 1)  # P20 做减法默认
            self.assertEqual(cfg.trend_pages, 5)
            self.assertTrue(cfg.images_enabled)
            self.assertEqual(cfg.serve_host, "127.0.0.1")
        finally:
            tmp.cleanup()

    def test_floor_enforced(self):
        tmp, path = self._write_config("[http]\npage_delay_seconds = 1.0\n")
        try:
            with self.assertRaises(ValueError):
                Config.load(path)
        finally:
            tmp.cleanup()

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            Config.load("/nonexistent/config.ini")

    def test_helpers(self):
        self.assertEqual(split_list("a，b, c"), ["a", "b", "c"])
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool("0"))

    def test_add_to_config_list(self):
        tmp, path = self._write_config(
            "[discovery]\n; 保留注释\nrank_terms = day, week\n"
        )
        try:
            changed, value = add_to_config_list(path, "discovery", "genre_rank_ids", "526")
            self.assertTrue(changed)
            self.assertEqual(value, "526")
            text = path.read_text(encoding="utf-8")
            self.assertIn("; 保留注释", text)
            self.assertLess(text.index("genre_rank_ids"), text.index("rank_terms"))
            # 重复项不重复追加
            changed, _ = add_to_config_list(path, "discovery", "genre_rank_ids", "526")
            self.assertFalse(changed)
            # 已有键：去重后追加
            changed, value = add_to_config_list(path, "discovery", "genre_rank_ids", "016")
            self.assertTrue(changed)
            self.assertEqual(value, "526,016")
            changed, value = add_to_config_list(path, "discovery", "rank_terms", "year")
            self.assertTrue(changed)
            self.assertEqual(value, "day,week,year")
            self.assertIn("rank_terms = day,week,year", path.read_text(encoding="utf-8"))
        finally:
            tmp.cleanup()

    def test_remove_from_config_list(self):
        tmp, path = self._write_config(
            "[discovery]\n; 保留注释\ngenre_rank_ids = 526,016\nrank_terms = day\n"
        )
        try:
            changed, value = remove_from_config_list(
                path, "discovery", "genre_rank_ids", "526"
            )
            self.assertTrue(changed)
            self.assertEqual(value, "016")
            self.assertIn("genre_rank_ids = 016", path.read_text(encoding="utf-8"))
            self.assertIn("; 保留注释", path.read_text(encoding="utf-8"))
            # 不在列表中 → 不变更
            changed, value = remove_from_config_list(
                path, "discovery", "genre_rank_ids", "999"
            )
            self.assertFalse(changed)
            self.assertEqual(value, "016")
            # 移除最后一项 → 空值
            changed, value = remove_from_config_list(
                path, "discovery", "genre_rank_ids", "016"
            )
            self.assertTrue(changed)
            self.assertEqual(value, "")
            self.assertIn("genre_rank_ids =", path.read_text(encoding="utf-8"))
            # 键 / 节不存在 → 不变更
            changed, value = remove_from_config_list(path, "discovery", "missing", "X")
            self.assertFalse(changed)
            self.assertEqual(value, "")
            changed, _ = remove_from_config_list(path, "other", "genre_rank_ids", "X")
            self.assertFalse(changed)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
