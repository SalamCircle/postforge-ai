import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import pro_assistant as pro, content_studio as studio, pro_images, smart_visual

URL="https://aws.amazon.com/training/"
IMAGE="https://a0.awsstatic.com/cloud.png"

class SmartVisualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.request={"topic":"Cloud learning","instructions":"Include the actual image","date":"2030-01-02"}
    def transport(self,endpoint,key,body):
        if endpoint==pro.SEARCH:
            return {"results":[{"url":URL,"content":"Cloud training","images":[IMAGE]}]}
        return {"choices":[{"message":{"content":json.dumps({"title":"Cloud training","text":"Explore training.","sources":["S1"]})}}]}
    def generated(self,mode):
        return pro.generate(self.root,dict(self.request,visual_mode=mode),"a","b","fixture",self.transport)
    def library(self,source=URL,permission="OWNER_CONFIRMED_REUSABLE_WITHOUT_EXPIRY"):
        buf=io.BytesIO()
        Image.new("RGB",(40,40),"white").save(buf,format="PNG")
        meta=pro_images.stage(self.root,IMAGE,source,"I HAVE IMAGE REUSE PERMISSION",fetch=lambda _:buf.getvalue())
        studio.write(self.root/"studio"/"reusable-images.json",[{"image":meta,"permission":permission,"attribution":"Example rights holder"}],replace=True)
        return meta
    def test_automatic_real_image_request_without_grant_uses_original(self):
        for automation,confirmation in (("publish","RESEARCH AND PUBLISH"),("queue","RESEARCH AND QUEUE")):
            today=studio.today().isoformat()
            req=dict(self.request,date=today,automation=automation,find_images=True)
            if automation=="queue":req["scheduled_at"]=today+"T23:59:00+00:00"
            self.assertEqual(pro.automation_mode(req,confirmation),automation)
            self.assertEqual(req["visual_mode"],"smart")
        d=self.generated("smart")
        self.assertIn("visual",d)
        self.assertNotIn("approved_image",d)
        self.assertTrue(studio.publish.render(d["visual"]).startswith(b"\x89PNG"))
    def test_exact_pre_authorised_asset_and_credit(self):
        meta=self.library()
        for mode in ("smart","source-only"):
            d=self.generated(mode)
            self.assertEqual(d["approved_image"],meta)
            self.assertNotIn("visual",d)
            self.assertIn("Image credit: Example rights holder",d["text"])
            self.assertIn(URL,d["text"])
            self.assertEqual(studio.payload(d)["approved_image"],meta)
        for mode in ("text","original"):
            d=self.generated(mode)
            self.assertNotIn("approved_image",d)
            self.assertEqual("visual" in d,mode=="original")
    def test_unknown_permission_unrelated_source_or_changed_bytes_never_attached(self):
        self.library(permission="UNKNOWN")
        self.assertIn("visual",self.generated("smart"))
        self.library(source="https://aws.amazon.com/other/")
        self.assertIn("visual",self.generated("smart"))
        meta=self.library()
        pro_images.asset_path(self.root,meta["sha256"]).write_bytes(b"changed")
        self.assertIn("visual",self.generated("smart"))
        self.assertNotIn("approved_image",self.generated("source-only"))
    def test_source_only_missing_asset_holds_without_publication(self):
        today=studio.today().isoformat()
        req=dict(self.request,visual_mode="source-only",date=today,head="a"*40,automation="publish")
        d=self.generated("source-only")
        d["date"]=today
        self.assertNotIn("visual",d)
        env={"GITHUB_RUN_ID":"123","PRO_REQUEST":json.dumps(req),"PRO_CONFIRMATION":"RESEARCH AND PUBLISH","LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fixture"}
        with patch.dict("os.environ",env),patch.object(studio,"ROOT",self.root),patch.object(pro.mobile_action,"git",side_effect=lambda *a:"a"*40 if a[0]=="rev-parse" else ""),patch.object(pro.mobile_action,"commit_workspace"),patch.object(pro,"generate_plan",return_value=[d]),patch.object(pro,"publish_generated") as send:
            pro.main()
            send.assert_not_called()
        saved=studio.load(self.root/"studio"/"requests"/"123.json")
        self.assertEqual(saved["status"],"needs-review")
        self.assertIn("No matching authorised",saved["message"])
        self.assertEqual(studio.status(self.root,d),"draft")
        self.assertFalse((self.root/"queue").exists())
    def test_invalid_visual_policy_rejected(self):
        for value in ("invented",[],True):
            with self.assertRaisesRegex(ValueError,"Invalid visual mode"):
                smart_visual.mode_for({"visual_mode":value})
