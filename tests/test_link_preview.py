import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import publish

URL = "https://github.com/SalamCircle/postforge-ai"
POSTER = "https://raw.githubusercontent.com/SalamCircle/postforge-ai/main/docs/assets/postforge-ai-followup.jpg"


class LinkPreviewTests(unittest.TestCase):
    def test_validation_blocks_unapproved_redirect_targets(self):
        item = {"date": "2026-11-24", "text": f"Progress update {URL}",
                "link_preview": {"source": URL, "poster_url": POSTER,
                                 "title": "PostForge AI", "description": "Open-source automation"}}
        self.assertEqual(publish.validate(item, "2026-11-24"), item)
        wrong = json.loads(json.dumps(item))
        wrong["link_preview"]["source"] = "https://somewhere-else.example"
        with self.assertRaises(ValueError):
            publish.validate(wrong, "2026-11-24")
        wrong = json.loads(json.dumps(item))
        wrong["visual"] = {"title": "another image", "points": ["one", "two"]}
        with self.assertRaises(ValueError):
            publish.validate(wrong, "2026-11-24")

    def test_article_preview_upload_click_destination_and_no_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "queue").mkdir()
            (root / "state").mkdir()
            day = "2026-11-24"
            path = root / "queue" / (day + "-postforge-followup.json")
            path.write_text(json.dumps({
                "date": day, "text": f"Verified progress: {URL}",
                "link_preview": {
                    "source": URL, "poster_url": POSTER,
                    "title": "PostForge AI", "description": "Open-source publisher"
                }
            }))
            requests = []
            def fake_request(url, token, payload=None, raw=None, method=None, raw_mime="image/png"):
                requests.append((url, payload, raw, method, raw_mime))
                if url.endswith("/userinfo"):
                    return 200, {}, {"sub": "example-member"}
                if "initializeUpload" in url:
                    return 200, {}, {"value": {
                        "image": "urn:li:image:example",
                        "uploadUrl": "https://www.linkedin.com/dms-uploads/example"
                    }}
                if url.endswith("/rest/posts"):
                    return 201, {"X-RestLi-Id": "urn:li:share:example"}, {}
                return 201, {}, {}
            def fake_record(path, value):
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(value))
            with patch.object(publish, "ROOT", root), \
                 patch.object(publish, "fetch_approved_poster", return_value=bytes.fromhex("ffd8ff0000000000")), \
                 patch.object(publish, "request", side_effect=fake_request), \
                 patch.object(publish, "record", side_effect=fake_record), \
                 patch.dict("os.environ", {"LIVE_PUBLISH": "true", "LINKEDIN_ACCESS_TOKEN": "mock"}):
                publish.publish_one(path, day)
                publish.publish_one(path, day)
            actual_posts = [p for p in requests if p[0].endswith("/rest/posts")]
            self.assertEqual(len(actual_posts), 1)
            article = actual_posts[0][1]["content"]["article"]
            self.assertEqual(article["source"], URL)
            self.assertEqual(article["thumbnail"], "urn:li:image:example")
            self.assertEqual(sum(p[3] == "PUT" for p in requests), 1)
            self.assertTrue(any(p[3] == "PUT" and p[4] == "image/jpeg" for p in requests))
            self.assertTrue(any(p[3] == "PUT" and p[0].startswith("https://www.linkedin.com/") for p in requests))
            receipt = json.loads(next((root / "state").glob("*.json")).read_text())
            self.assertEqual(receipt["status"], "published")
            self.assertEqual(receipt["format"], "linked_article")
            self.assertEqual((root / "state" / "media" / (receipt["published_media"]["sha256"]+".jpg")).read_bytes(), bytes.fromhex("ffd8ff0000000000"))
