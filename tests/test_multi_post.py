import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import publish

class MultiPostTests(unittest.TestCase):
    def test_multiple_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            day = "2026-01-01"
            (root / "queue").mkdir()
            (root / "state").mkdir()
            for suffix, content in [("01","First post"),("02","Second post"),("03","FIRST POST!")]:
                (root / "queue" / f"{day}-{suffix}.json").write_text(json.dumps({"date":day,"text":content}))
            def record(path, value):
                path.write_text(json.dumps(value))
            def request(url, token, payload=None, **kwargs):
                if url.endswith("userinfo"):
                    return 200, {}, {"sub":"test"}
                return 201, {"X-RestLi-Id":"urn:li:share:test"}, {}
            with patch.object(publish,"ROOT",root), patch.object(publish,"record",side_effect=record), patch.object(publish,"request",side_effect=request) as api, patch.dict("os.environ",{"LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fake"}):
                for path in publish.queue_paths(day):
                    publish.publish_one(path,day)
                for path in publish.queue_paths(day):
                    publish.publish_one(path,day)
                self.assertEqual(sum(call.args[0].endswith("ugcPosts") for call in api.call_args_list),2)
                self.assertEqual(len(list((root / "state").glob("*.json"))),2)
