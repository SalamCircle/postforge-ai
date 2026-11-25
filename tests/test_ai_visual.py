import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import ai_visual as ai, pro_images, pro_assistant as pro, content_studio as studio, smart_visual

ENV={"PRO_IMAGE_ENABLED":"true","PRO_IMAGE_FREE_ONLY":ai.ACK,
     "CLOUDFLARE_ACCOUNT_ID":"a"*32,"CLOUDFLARE_IMAGE_TOKEN":"fixture_"+"x"*24}
SOURCE="https://example.com/training"

class AIVisualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def draft(self):
        d={"id":"ai-test","date":studio.today().isoformat(),"topic":"Cloud learning","title":"Learn cloud skills","text":"Read the source.\n"+SOURCE,"sources":[SOURCE]}
        smart_visual.apply(self.root,d,"ai-photo")
        return d
    def image(self,size=(512,512)):
        stream=io.BytesIO()
        Image.new("RGB",size,"navy").save(stream,format="JPEG")
        return stream.getvalue()
    def test_default_disabled_and_explicit_gate(self):
        for env in ({},dict(ENV,PRO_IMAGE_ENABLED="false"),dict(ENV,PRO_IMAGE_FREE_ONLY=""),dict(ENV,CLOUDFLARE_ACCOUNT_ID="other")):
            d=self.draft()
            with patch.object(ai,"fetch") as network:
                self.assertEqual(ai.apply(self.root,d,"ai-photo",env=env,transport=network),"disabled")
                network.assert_not_called()
            self.assertIn("visual",d)
            self.assertNotIn("ai_image",d)
    def test_valid_generated_image_normalized_disclosed_and_queued(self):
        d=self.draft()
        with patch.object(ai,"fetch",return_value=self.image()) as network:
            self.assertEqual(ai.apply(self.root,d,"ai-illustration",env=ENV,transport=network),"generated")
            network.assert_called_once()
            self.assertNotIn(SOURCE,network.call_args.args[2])
            self.assertNotIn(d["text"],network.call_args.args[2])
        self.assertNotIn("visual",d)
        self.assertIn("AI-generated conceptual illustration",d["text"])
        png=pro_images.load_generated(self.root,d["ai_image"])
        self.assertTrue(png.startswith(b"\x89PNG"))
        studio.validate_draft(d)
        studio.import_plan(self.root,[d])
        studio.approve(self.root,d["id"],studio.digest(d))
        studio.export(self.root,d["id"],studio.digest(d))
        item=studio.queued(self.root)[0][1]
        self.assertEqual(item["ai_image"],d["ai_image"])
        # Exact bytes are validated by the existing publisher in dry-run mode.
        with patch.object(studio.publish,"ROOT",self.root),patch.dict("os.environ",{"LIVE_PUBLISH":"false"}),patch.object(studio.publish,"request") as request:
            studio.publish.publish_one(self.root/"queue"/studio.queue_name(d),d["date"],reviewed_now=True)
            request.assert_not_called()
        pro_images.asset_path(self.root,d["ai_image"]["sha256"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"bytes changed"):
            pro_images.load_generated(self.root,d["ai_image"])
    def test_error_and_small_or_malformed_images_fall_back(self):
        for value in (b"bad",self.image((32,32)),None):
            d=self.draft()
            with patch.object(ai,"fetch",return_value=value) as network:
                self.assertEqual(ai.apply(self.root,d,"ai-poster",env=ENV,transport=network),"fallback")
                network.assert_called_once()
            self.assertIn("visual",d)
            self.assertNotIn("ai_image",d)
        d=self.draft()
        with patch.object(ai,"fetch",side_effect=urllib.error.HTTPError("https://api.cloudflare.com",429,"quota",{},None)) as network:
            self.assertEqual(ai.apply(self.root,d,"ai-photo",env=ENV,transport=network),"fallback")
            network.assert_called_once()
        self.assertFalse((self.root/"studio"/"assets").exists())
    def test_invalid_metadata_or_missing_disclosure_cannot_publish(self):
        d=self.draft()
        ai.apply(self.root,d,"ai-photo",env=ENV,transport=lambda *_:self.image())
        invalid=dict(d,text="No disclosure")
        with self.assertRaisesRegex(ValueError,"disclosure"):
            studio.validate_draft(invalid)
        with self.assertRaisesRegex(ValueError,"one image format"):
            studio.validate_draft(dict(d,visual={"title":"Other","points":["One","Two"]}))
    def test_plan_has_one_provider_attempt_and_preserves_other_fallback(self):
        first=self.draft()
        second=dict(self.draft(),id="ai-test-2",title="Another topic",text="Other research "+SOURCE)
        request={"head":"a"*40,"automation":"review","requests":[{"visual_mode":"ai-photo"},{"visual_mode":"ai-poster"}]}
        env={"GITHUB_RUN_ID":"345","PRO_REQUEST":json.dumps(request),"PRO_CONFIRMATION":"GENERATE DRAFT ONLY"}
        with patch.dict("os.environ",env),patch.object(studio,"ROOT",self.root),patch.object(pro.mobile_action,"git",side_effect=lambda *a:"a"*40 if a[0]=="rev-parse" else ""),patch.object(pro.mobile_action,"commit_workspace"),patch.object(pro,"generate_plan",return_value=[first,second]),patch.object(ai,"apply",return_value="fallback") as apply,patch.object(pro,"publish_generated") as send:
            pro.main()
            apply.assert_called_once()
            send.assert_not_called()
        self.assertEqual(len(studio.drafts(self.root)),2)
        self.assertFalse((self.root/"queue").exists())

class AIVisualTransportTests(unittest.TestCase):
    def test_malformed_provider_utf8_falls_back_without_retry(self):
        import tempfile
        from unittest.mock import patch
        from pathlib import Path
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return b"\xff"
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            draft={"id":"ai-test-transport","date":studio.today().isoformat(),"topic":"Cloud","title":"Cloud learning","text":"Read more. "+SOURCE,"sources":[SOURCE]}
            smart_visual.apply(root,draft,"ai-photo")
            with patch.object(ai.urllib.request,"build_opener") as opener:
                opener.return_value.open.return_value=Response()
                self.assertEqual(ai.apply(root,draft,"ai-photo",env=ENV),"fallback")
                opener.return_value.open.assert_called_once()
            self.assertIn("visual",draft)
            self.assertNotIn("ai_image",draft)
