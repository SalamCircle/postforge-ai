import datetime as dt
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import pro_images, content_studio as studio, publish

SOURCE="https://aws.amazon.com/training/"
URL="https://d1.awsstatic.com/training/example.jpg"
CONFIRM="I HAVE IMAGE REUSE PERMISSION"

def picture():
    out=io.BytesIO()
    Image.new("RGB",(400,240),"navy").save(out,format="JPEG")
    return out.getvalue()

class ProImageTests(unittest.TestCase):
    def test_stage_permission_hosts_hash_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def never(url): self.fail("Invalid input must not fetch")
            for url,source,confirm in [(URL,SOURCE,"no"),("https://127.0.0.1/a",SOURCE,CONFIRM),("https://d1.awsstatic.com.evil.example/a",SOURCE,CONFIRM),(URL,"https://evil.example/",CONFIRM)]:
                with self.assertRaises(ValueError):
                    pro_images.stage(root,url,source,confirm,never)
            meta=pro_images.stage(root,URL,SOURCE,CONFIRM,lambda url:picture())
            saved=pro_images.load(root,meta)
            self.assertTrue(saved.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(pro_images.stage(root,URL,SOURCE,CONFIRM,lambda url:picture()),meta)
            pro_images.asset_path(root,meta["sha256"]).write_bytes(b"tampered")
            with self.assertRaises(ValueError): pro_images.load(root,meta)
    def test_exact_image_approval_and_publish_dry_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            date=studio.today().isoformat()
            draft={"id":"image-test","date":date,"title":"AWS","topic":"Cloud","text":"Read more "+SOURCE,"sources":[SOURCE],"image_candidates":[{"url":URL,"source":SOURCE}]}
            studio.save_draft(root,draft)
            old=studio.digest(draft)
            studio.approve(root,draft["id"],old)
            draft["approved_image"]=pro_images.stage(root,URL,SOURCE,CONFIRM,lambda url:picture())
            studio.save_draft(root,draft,edit=True)
            self.assertEqual(studio.review(root,draft["id"])["status"],"draft")
            with self.assertRaises(ValueError): studio.export(root,draft["id"],old)
            digest=studio.digest(draft)
            studio.approve(root,draft["id"],digest)
            result=studio.export(root,draft["id"],digest)
            path=root/"queue"/result["queue"]
            with patch.object(publish,"ROOT",root), patch.object(publish,"request",side_effect=AssertionError("No LinkedIn call")),patch.dict("os.environ",{"LIVE_PUBLISH":"false","TIMED_ONLY":"false"}):
                publish.publish_one(path,date)
                self.assertFalse((root/"state").exists())
                pro_images.asset_path(root,draft["approved_image"]["sha256"]).write_bytes(b"changed")
                with self.assertRaises(ValueError): publish.publish_one(path,date)
    def test_conflicting_image_and_unlinked_candidate_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            meta=pro_images.stage(root,URL,SOURCE,CONFIRM,lambda url:picture())
            date=studio.today().isoformat()
            with self.assertRaises(ValueError):
                publish.validate({"date":date,"text":SOURCE,"approved_image":meta,"visual":{"title":"X","points":["A","B"]}},date)
            with self.assertRaises(ValueError):
                studio.validate_draft({"id":"test","date":date,"title":"T","topic":"T","text":SOURCE,"sources":[SOURCE],"approved_image":meta})
