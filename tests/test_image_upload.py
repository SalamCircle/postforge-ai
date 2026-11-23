import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import publish

class LiveUploadContractTests(unittest.TestCase):
    def test_image_registration_upload_and_single_public_post(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "queue").mkdir()
            (root / "state").mkdir()
            day = "2026-11-23"
            path = root / "queue" / (day + "-verified-image.json")
            path.write_text(json.dumps({
                "date": day,
                "text": "A unique test message for LinkedIn visual upload.",
                "visual": {"title": "Verify before publishing", "points": ["Review account and content", "Stop uncertain retries"]}
            }))
            requests = []
            def fake_request(url, token, payload=None, raw=None, method=None):
                requests.append((url, payload, raw, method))
                if url.endswith("/userinfo"):
                    return 200, {}, {"sub": "example-member"}
                if "registerUpload" in url:
                    return 200, {}, {
                        "value": {
                            "asset": "urn:li:digitalmediaAsset:example",
                            "uploadMechanism": {
                                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                                    "uploadUrl": "https://www.linkedin.com/dms-uploads/example"
                                }
                            }
                        }
                    }
                if url.endswith("/ugcPosts"):
                    return 201, {"X-RestLi-Id": "urn:li:share:example"}, {}
                return 201, {}, {}
            def fake_record(path, value):
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(value))
            with patch.object(publish, "ROOT", root),                  patch.object(publish, "request", side_effect=fake_request),                  patch.object(publish, "record", side_effect=fake_record),                  patch.dict("os.environ", {"LIVE_PUBLISH": "true", "LINKEDIN_ACCESS_TOKEN": "dummy"}):
                publish.publish_one(path, day)
                publish.publish_one(path, day)
            upload_calls = [item for item in requests if item[3] == "PUT"]
            post_calls = [item for item in requests if item[0].endswith("/ugcPosts")]
            self.assertEqual(len(upload_calls), 1)
            self.assertTrue(upload_calls[0][2].startswith(b"\x89PNG"))
            self.assertEqual(len(post_calls), 1)
            self.assertEqual(post_calls[0][1]["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"], "IMAGE")
            receipt = json.loads(next((root / "state").glob("*.json")).read_text())
            self.assertEqual(receipt["status"], "published")
            self.assertTrue(receipt["visual"])
