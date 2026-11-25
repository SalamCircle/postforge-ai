import unittest
import tempfile
import pathlib
import json
from scripts.v2_manager import plan, schedule_preview, history, queue

class V2Tests(unittest.TestCase):
    def test_draft_only(self):
        for action in ("comment", "reply", "edit", "profile"):
            result = plan(action, "selected target", "Reviewed draft")
            self.assertFalse(result["live_execution"])
            self.assertTrue(result["approval_required"])
        self.assertFalse(plan("delete", "selected target")["live_execution"])
        self.assertFalse(plan("reaction", "selected target", "LIKE")["live_execution"])

    def test_invalid(self):
        for args in [("unknown", "x"), ("comment", "x"), ("delete", ""), ("reaction", "x", "bad")]:
            with self.assertRaises(ValueError):
                plan(*args)

    def test_timezones(self):
        self.assertEqual(schedule_preview("2026-07-01T09:00")["utc"], "2026-07-01T08:00:00+00:00")
        self.assertEqual(schedule_preview("2026-11-24T09:00")["utc"], "2026-11-24T09:00:00+00:00")
        self.assertFalse(schedule_preview("2026-11-24T09:00")["scheduled"])
        for value in ("2026-03-29T01:30", "2026-10-25T01:30"):
            with self.assertRaises(ValueError):
                schedule_preview(value)

    def test_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "state").mkdir()
            (root / "queue").mkdir()
            receipt = root / "state" / "receipt.json"
            receipt.write_text(json.dumps({"status": "published", "post_id": "example", "secret": "hidden"}))
            queued = root / "queue" / "2026-11-24-example.json"
            queued.write_text("{}")
            self.assertEqual(history(root), [{"status": "published", "post_id": "example"}])
            self.assertEqual(queue(root), [queued.name])
            self.assertEqual(queued.read_text(), "{}")
