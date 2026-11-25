import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pro_recovery as recovery, pro_assistant as pro, content_studio as studio

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.request={"topic":"Cloud training","instructions":"Find official material","date":"2030-01-02"}
    def test_durable_request_and_same_run_replay_refused(self):
        record=recovery.start(self.root,"123",self.request,"publish")
        self.assertEqual(studio.load(recovery.path(self.root,"123"))["status"],"started")
        with self.assertRaises(ValueError):
            recovery.start(self.root,"123",self.request,"publish")
        recovery.update(self.root,record,status="failed",message=pro.safe_reason(ValueError("secret fixture")))
        saved=studio.load(recovery.path(self.root,"123"))
        self.assertEqual(saved["request"],self.request)
        self.assertNotIn("secret fixture",json.dumps(saved))
        self.assertEqual(saved["draft_ids"],[])
        for bad in ("../123","0","abc"):
            with self.assertRaises(ValueError): recovery.path(self.root,bad)
    def test_expired_plan_preserves_text_without_automatic_schedule(self):
        now=dt.datetime(2030,1,2,10,tzinfo=dt.timezone.utc)
        old={"id":"a","date":"2030-01-02","scheduled_at":"2030-01-02T09:00:00+00:00","text":"Original content"}
        future={"id":"b","date":"2030-01-03","scheduled_at":"2030-01-03T09:00:00+00:00","text":"Future content"}
        self.assertTrue(recovery.review_expired([old,future],now))
        self.assertNotIn("scheduled_at",old)
        self.assertEqual(old["text"],"Original content")
        self.assertIn("scheduled_at",future)
        self.assertFalse(recovery.review_expired([old,future],now))
    def test_requested_visual_validated_before_publication(self):
        d={"visual":{"title":"Cloud learning","points":["Official sources","Learn cloud skills"]}}
        recovery.validate_visuals([d])
        with patch.object(studio.publish,"render",return_value=b"invalid"):
            with self.assertRaisesRegex(ValueError,"visual could not"):
                recovery.validate_visuals([d])
    def test_failed_generation_records_safe_error_without_publication(self):
        env={"GITHUB_RUN_ID":"123","PRO_REQUEST":json.dumps(dict(self.request,head="a"*40)),
             "PRO_CONFIRMATION":"GENERATE DRAFT ONLY"}
        with patch.dict("os.environ",env),patch.object(studio,"ROOT",self.root),patch.object(pro.mobile_action,"git",side_effect=lambda *a:"a"*40 if a[0]=="rev-parse" else ""),patch.object(pro.mobile_action,"commit_workspace") as commit,patch.object(pro,"generate_plan",side_effect=ValueError("AI selected an unknown research source")),patch.object(pro,"publish_generated") as send:
            with self.assertRaises(ValueError):pro.main()
            self.assertEqual(commit.call_count,2)
            send.assert_not_called()
        record=studio.load(recovery.path(self.root,"123"))
        self.assertEqual(record["status"],"failed")
        self.assertEqual(record["message"],"AI selected an unknown research source")
        self.assertFalse((self.root/"queue").exists())
    def test_expired_auto_queue_downgrades_to_unapproved_draft(self):
        today=studio.today().isoformat()
        request=dict(self.request,date=today,scheduled_at=today+"T00:00:00+00:00",head="a"*40,automation="queue")
        draft={"id":"ai-expired","date":today,"scheduled_at":request["scheduled_at"],"title":"Cloud","topic":"Cloud","text":"Research example"}
        with patch.dict("os.environ",{"GITHUB_RUN_ID":"124","PRO_REQUEST":json.dumps(request),"PRO_CONFIRMATION":"RESEARCH AND QUEUE"}),patch.object(studio,"ROOT",self.root),patch.object(pro.mobile_action,"git",side_effect=lambda *a:"a"*40 if a[0]=="rev-parse" else ""),patch.object(pro.mobile_action,"commit_workspace"),patch.object(pro,"generate_plan",return_value=[draft]),patch.object(pro,"publish_generated") as send:
            pro.main()
            send.assert_not_called()
        record=studio.load(recovery.path(self.root,"124"))
        self.assertEqual(record["status"],"needs-review")
        self.assertEqual(record["draft_ids"],["ai-expired"])
        self.assertEqual(studio.status(self.root,studio.read_draft(self.root,"ai-expired")),"draft")
        self.assertFalse((self.root/"queue").exists())
    def test_uncertain_publication_is_not_marked_retryable(self):
        today=studio.today().isoformat()
        request=dict(self.request,date=today,head="a"*40,automation="publish")
        draft={"id":"ai-example","date":today,"title":"Cloud","topic":"Cloud","text":"Research example"}
        env={"GITHUB_RUN_ID":"125","PRO_REQUEST":json.dumps(request),"PRO_CONFIRMATION":"RESEARCH AND PUBLISH","LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fixture"}
        with patch.dict("os.environ",env),patch.object(studio,"ROOT",self.root),patch.object(pro.mobile_action,"git",side_effect=lambda *a:"a"*40 if a[0]=="rev-parse" else ""),patch.object(pro.mobile_action,"commit_workspace"),patch.object(pro,"generate_plan",return_value=[draft]),patch.object(pro,"publish_generated",side_effect=RuntimeError("uncertain")) as send:
            with self.assertRaises(RuntimeError):pro.main()
            send.assert_called_once()
        record=studio.load(recovery.path(self.root,"125"))
        self.assertEqual(record["status"],"publication-pending")
        self.assertEqual(record["draft_ids"],["ai-example"])
        self.assertFalse((self.root/"queue").exists())
