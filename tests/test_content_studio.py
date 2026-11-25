import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import content_studio as studio, publish

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.date = (studio.today() + dt.timedelta(days=1)).isoformat()
        self.draft = {"id":"first-post","date":self.date,"title":"First post","topic":"Security","text":"A unique reviewed security article.","sources":["https://example.com/source"],"series":"security-series"}

    def test_batch_plan_is_drafts_only(self):
        second = dict(self.draft,id="second-post",text="Different second post")
        with self.assertRaises(ValueError):
            studio.import_plan(self.root,[self.draft,dict(self.draft,id="duplicate")])
        self.assertEqual(studio.drafts(self.root),[])
        result = studio.import_plan(self.root,[self.draft,second])
        self.assertEqual(result["queued"],0)
        self.assertEqual(len(studio.drafts(self.root)),2)
        self.assertFalse((self.root/"queue").exists())
        with self.assertRaises(ValueError):
            studio.import_plan(self.root,[dict(self.draft,id="new-id")])

    def test_approval_and_export(self):
        r = studio.save_draft(self.root, self.draft)
        self.assertEqual(r["status"], "draft")
        with self.assertRaises(ValueError):
            studio.export(self.root, "first-post", r["digest"])
        studio.approve(self.root, "first-post", r["digest"])
        self.assertEqual(studio.review(self.root,"first-post")["status"],"approved")
        result = studio.export(self.root,"first-post",r["digest"])
        self.assertEqual(studio.load(self.root/"queue"/result["queue"]),studio.payload(self.draft))
        self.assertEqual(studio.review(self.root,"first-post")["status"],"queued")
        with self.assertRaises(ValueError):
            studio.export(self.root,"first-post",r["digest"])

    def test_revision_invalidates_approval(self):
        r = studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        modified = dict(self.draft,text="Revised text")
        studio.save_draft(self.root,modified,edit=True)
        self.assertEqual(studio.review(self.root,"first-post")["status"],"draft")
        with self.assertRaises(ValueError):
            studio.export(self.root,"first-post",r["digest"])

    def test_existing_receipt_and_duplicate(self):
        r = studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        studio.write(self.root/"state"/"old.json",{"fingerprint":publish.fingerprint(self.draft["text"]),"status":"published","post_id":"example"})
        self.assertEqual(studio.review(self.root,"first-post")["status"],"published")
        with self.assertRaises(ValueError):
            studio.export(self.root,"first-post",r["digest"])

    def test_conflicting_queue_and_claim(self):
        r = studio.save_draft(self.root,self.draft)
        studio.write(self.root/"queue"/(self.date+"-other.json"),studio.payload(self.draft))
        self.assertEqual(studio.review(self.root,"first-post")["status"],"queue-conflict")
        studio.write(self.root/"state"/"claim.json",{"fingerprint":publish.fingerprint(self.draft["text"]),"status":"claimed"})
        self.assertEqual(studio.review(self.root,"first-post")["status"],"review-claim")
        with self.assertRaises(ValueError):
            studio.approve(self.root,"first-post",r["digest"])

    def test_brand_calendar_brief_and_series(self):
        brand = {"name":"Example","audience":"Students","voice":"Plain English","goals":["Educate"],"pillars":["Security"],"avoid":["Unverified claims"]}
        studio.set_brand(self.root,brand)
        studio.save_draft(self.root,self.draft)
        studio.save_draft(self.root,dict(self.draft,id="second-post",text="Different text"))
        self.assertEqual(studio.review(self.root,"first-post")["same_topic"],["second-post"])
        b = studio.brief(self.root)
        self.assertEqual(b["brand"],brand)
        self.assertEqual(len(b["calendar"]),2)
        self.assertEqual(b["topics"][0]["series"],"security-series")
        self.assertEqual(b["topics"][0]["sources"],self.draft["sources"])

    def test_invalid_inputs_and_past_date(self):
        for item in (dict(self.draft,id="../escape"),dict(self.draft,text=""),dict(self.draft,date="2026-02-30"),dict(self.draft,token="bad")):
            with self.assertRaises(ValueError):
                studio.save_draft(self.root,item)
        old = dict(self.draft,date="2000-01-01")
        r = studio.save_draft(self.root,old)
        studio.approve(self.root,"first-post",r["digest"])
        with self.assertRaises(ValueError):
            studio.export(self.root,"first-post",r["digest"])

    def test_archive_and_reuse(self):
        r = studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        self.assertEqual(studio.archive(self.root,"first-post",r["digest"])["status"],"archived")
        with self.assertRaises(ValueError):
            studio.export(self.root,"first-post",r["digest"])
        with self.assertRaises(ValueError):
            studio.reuse(self.root,"first-post")
        studio.write(self.root/"state"/"published.json",{"fingerprint":publish.fingerprint(self.draft["text"]),"status":"published"})
        self.assertEqual(studio.reuse(self.root,"first-post")["original"],self.draft)
        self.assertEqual(studio.report(self.root)["published_receipts"],1)

    def test_overdue_and_legacy_queue(self):
        studio.write(self.root/"queue"/"2000-01-01-old.json",{"date":"2000-01-01","text":"Missed post"})
        studio.write(self.root/"queue"/(self.date+"-legacy.json"),{"date":self.date,"text":"Existing V1 queue"})
        self.assertEqual(studio.report(self.root)["overdue_queue_files"],["2000-01-01-old.json"])
        self.assertEqual(studio.calendar(self.root,self.date,1)[0]["status"],"queued")

    def test_real_publisher_dry_run(self):
        r = studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        result = studio.export(self.root,"first-post",r["digest"])
        with patch.object(publish,"ROOT",self.root), patch.dict("os.environ",{"LIVE_PUBLISH":"false","LINKEDIN_ACCESS_TOKEN":""}), patch.object(publish,"request",side_effect=AssertionError("Unexpected API request")):
            publish.publish_one(self.root/"queue"/result["queue"],self.date)
        self.assertFalse((self.root/"state").exists())

    def test_no_network_or_secret_access_in_export(self):
        with patch.object(publish,"request",side_effect=AssertionError("Unexpected API request")):
            r = studio.save_draft(self.root,self.draft)
            studio.approve(self.root,"first-post",r["digest"])
            studio.export(self.root,"first-post",r["digest"])
        self.assertFalse((self.root/"state").exists())


    def test_reschedule_unclaimed_queue_requires_fresh_approval(self):
        r = studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        entry = studio.export(self.root,"first-post",r["digest"])["queue"]
        later=(studio.today()+dt.timedelta(days=2)).isoformat()+"T09:10"
        with self.assertRaises(ValueError):
            studio.schedule(self.root,"first-post","2000-01-01T09:10","UTC",r["digest"],reschedule=True)
        self.assertTrue((self.root/"queue"/entry).exists())
        updated=studio.schedule(self.root,"first-post",later,"UTC",r["digest"],reschedule=True)
        self.assertEqual(updated["status"],"draft")
        self.assertFalse((self.root/"queue"/entry).exists())
        self.assertFalse(studio.approval_valid(self.root,studio.read_draft(self.root,"first-post")))
        self.assertEqual(studio.read_draft(self.root,"first-post")["scheduled_at"],later+":00+00:00")

    def test_publish_now_exact_queue_and_receipt(self):
        from scripts import publish_reviewed
        r=studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        entry=studio.export(self.root,"first-post",r["digest"])["queue"]
        head="a"*40
        request={"action":"publish-now","id":"first-post","digest":r["digest"],"confirmation":"PUBLISH NOW","head":head}
        def git(*args):
            return head if args[0]=="rev-parse" else ""
        def sent(path,day,*,reviewed_now):
            self.assertTrue(reviewed_now)
            self.assertEqual(path.name,entry)
            self.assertEqual(day,self.date)
            studio.write(self.root/"state"/(publish.fingerprint(self.draft["text"])+".json"),{"status":"published","post_id":"fixture","queue":entry,"fingerprint":publish.fingerprint(self.draft["text"])})
        with patch.object(publish_reviewed.mobile_action,"git",side_effect=git), patch.dict("os.environ",{"LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fixture"}), patch.object(publish,"publish_one",side_effect=sent) as send:
            for bad in (dict(request,confirmation=""),dict(request,digest="bad"),dict(request,head="b"*40)):
                with self.assertRaises(ValueError):
                    publish_reviewed.publish_reviewed(self.root,bad)
            send.assert_not_called()
            with patch.dict("os.environ",{"LIVE_PUBLISH":"false"}):
                with self.assertRaises(ValueError):
                    publish_reviewed.publish_reviewed(self.root,request)
            send.assert_not_called()
            publish_reviewed.publish_reviewed(self.root,request)
            with self.assertRaises(ValueError):
                publish_reviewed.publish_reviewed(self.root,request)
            send.assert_called_once()
        with self.assertRaises(ValueError):
            studio.schedule(self.root,"first-post",(studio.today()+dt.timedelta(days=2)).isoformat()+"T09:10","UTC",r["digest"],reschedule=True)

    def test_reviewed_now_dry_run_never_calls_network(self):
        r=studio.save_draft(self.root,self.draft)
        studio.approve(self.root,"first-post",r["digest"])
        result=studio.export(self.root,"first-post",r["digest"])
        with patch.object(publish,"ROOT",self.root),patch.dict("os.environ",{"LIVE_PUBLISH":"false","LINKEDIN_ACCESS_TOKEN":""}),patch.object(publish,"request",side_effect=AssertionError("Unexpected network")):
            publish.publish_one(self.root/"queue"/result["queue"],self.date,reviewed_now=True)
        self.assertFalse((self.root/"state").exists())

    def test_delete_only_unqueued_drafts_and_bulk_validation(self):
        r=studio.save_draft(self.root,self.draft)
        second=dict(self.draft,id="second-post",text="Different text")
        q=studio.save_draft(self.root,second)
        studio.approve(self.root,"second-post",q["digest"])
        studio.export(self.root,"second-post",q["digest"])
        with self.assertRaises(ValueError):
            studio.delete_plan(self.root,[{"id":"first-post","digest":r["digest"]},{"id":"second-post","digest":q["digest"]}])
        self.assertEqual(len(studio.drafts(self.root)),2)
        with self.assertRaises(ValueError):
            studio.delete_draft(self.root,"first-post","stale")
        studio.approve(self.root,"first-post",r["digest"])
        studio.archive(self.root,"first-post",r["digest"])
        studio.delete_plan(self.root,[{"id":"first-post","digest":r["digest"]}])
        self.assertFalse(studio.draft_path(self.root,"first-post").exists())
        self.assertFalse(studio.approval_path(self.root,"first-post").exists())
        self.assertTrue(studio.draft_path(self.root,"second-post").exists())

if __name__ == "__main__":
    unittest.main()
