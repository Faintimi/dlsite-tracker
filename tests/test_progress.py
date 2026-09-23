"""progress.py 的统一进度写入测试（离线）。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from dlsite_tracker.progress import write_task_progress


class WriteTaskProgressTest(unittest.TestCase):
    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_base_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "update-progress.json"
            write_task_progress(path, "rankings", detail="富化 50/400", years="quick")
            payload = self._read(path)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["phase"], "rankings")
            self.assertEqual(payload["detail"], "富化 50/400")
            self.assertEqual(payload["years"], "quick")
            self.assertEqual(payload["pid"], os.getpid())
            self.assertIsInstance(payload["updated_ts"], int)
            self.assertFalse((path.parent / "update-progress.json.tmp").exists())

    def test_optional_fields_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            write_task_progress(path, "enrich", schema_version=2, extra={"running": True})
            payload = self._read(path)
            self.assertNotIn("detail", payload)
            self.assertNotIn("years", payload)
            self.assertEqual(payload["schema_version"], 2)
            self.assertTrue(payload["running"])

    def test_extra_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            write_task_progress(
                path,
                "enrich",
                years="1",
                extra={"enriched": 12, "remaining": 88, "note": "本轮结束"},
            )
            payload = self._read(path)
            self.assertEqual(payload["enriched"], 12)
            self.assertEqual(payload["remaining"], 88)
            self.assertEqual(payload["note"], "本轮结束")
            self.assertEqual(payload["years"], "1")
