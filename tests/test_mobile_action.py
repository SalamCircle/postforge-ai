import json
import datetime as dt
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import mobile_action, content_studio, publish

class MobileActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.remote = Path(self.tmp.name) / "remote.git"
        subprocess.run(["git","init","--bare",str(self.remote)],check=True,capture_output=True)
        self.root.mkdir()
        self.git("init","-b","main")
        self.git("config","user.name","Test")
        self.git("config","user.email","test@example.invalid")
        (self.root/"README.md").write_text("Test workspace")
        self.git("add","README.md")
        self.git("commit","-m","Initial")
        self.git("remote","add","origin",str(self.remote))
        self.git("push","-u","origin","main")
        self.head=self.git("rev-parse","HEAD").strip()
        self.draft={"id":"mobile-example","date":"2030-01-02","title":"Example","topic":"AI","text":"A reviewed example"}

    def git(self,*args):
        return subprocess.run(["git",*args],cwd=self.root,check=True,capture_output=True,text=True).stdout

    def test_mobile_commit_and_stale_head(self):
        data={"action":"draft","draft":self.draft,"head":self.head}
        with patch.object(mobile_action,"ROOT",self.root):
            mobile_action.apply(dict(data))
            self.assertEqual(content_studio.read_draft(self.root,"mobile-example"),self.draft)
            self.assertEqual(self.git("status","--porcelain"),"")
            with self.assertRaises(ValueError):
                mobile_action.apply(dict(data))
            self.assertFalse((self.root/"queue").exists())

    def test_disallowed_action_and_path(self):
        with patch.object(mobile_action,"ROOT",self.root):
            with self.assertRaises(ValueError):
                mobile_action.apply({"action":"publish","head":self.head})
            def unexpected(root,data):
                (root/"README.md").write_text("Unexpected change")
            with patch.object(mobile_action.dashboard,"action",unexpected):
                with self.assertRaises(ValueError):
                    mobile_action.apply({"action":"draft","head":self.head})
            self.assertEqual(self.git("rev-parse","HEAD").strip(),self.head)

    def test_complete_mobile_lifecycle_preserves_existing_publisher_data(self):
        # The actual production action handler runs against a disposable Git
        # checkout and local bare remote, never the real publishing queue.
        today = content_studio.today()
        future = (today + dt.timedelta(days=2)).isoformat()
        draft = dict(self.draft, date=future, text="Private acceptance draft — never publish")
        protected = {
            "queue/" + today.isoformat() + "-existing.json": json.dumps({"date":today.isoformat(),"text":"Existing planned post"}),
            "state/existing.json": json.dumps({"status":"published","fingerprint":publish.fingerprint("Earlier post"),"queue":"earlier.json","post_id":"urn:li:share:123"}),
            "scripts/publish.py": "existing publisher sentinel",
            ".github/workflows/publish.yml": "existing workflow sentinel",
        }
        for name, content in protected.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.git("add", ".")
        self.git("commit", "-m", "Existing publishing configuration and data")
        self.git("push", "origin", "main")
        name = draft["id"]
        def apply(action, **kwargs):
            before = self.git("rev-parse", "HEAD").strip()
            mobile_action.apply(dict(action=action, head=before, **kwargs))
            self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.git("ls-remote","origin","refs/heads/main").split()[0])
            self.assertEqual(self.git("status","--porcelain"), "")
            for file, content in protected.items():
                self.assertEqual((self.root/file).read_text(), content)
        def review():
            return content_studio.review(self.root, name)
        def checked(action, confirmation):
            apply(action, id=name, digest=review()["digest"], confirmation=confirmation)
        with patch.object(mobile_action,"ROOT",self.root), patch.object(publish,"ROOT",self.root), patch.object(publish,"request",side_effect=AssertionError("Network publication forbidden")), patch.dict("os.environ",{"LIVE_PUBLISH":"false","LINKEDIN_ACCESS_TOKEN":""}):
            apply("brand",brand={"name":"Fixture","audience":"Test","voice":"Clear","goals":["Learn"],"pillars":["AI"],"avoid":["Spam"]})
            apply("draft",draft=draft)
            self.assertEqual(review()["status"],"draft")
            old = review()["digest"]
            checked("approve","APPROVE")
            self.assertEqual(review()["status"],"approved")
            apply("revise",id=name,digest=old,draft=dict(draft,text="Revised private acceptance draft"))
            self.assertEqual(review()["status"],"draft")
            with self.assertRaises(ValueError):
                apply("approve",id=name,digest=old,confirmation="APPROVE")
            apply("schedule",id=name,digest=review()["digest"],local_time=future+"T09:00",timezone="Europe/London")
            self.assertIn("scheduled_at",review()["draft"])
            checked("approve","APPROVE")
            checked("export","QUEUE")
            self.assertEqual(review()["status"],"queued")
            q = self.root/"queue"/content_studio.queue_name(review()["draft"])
            self.assertTrue(q.is_file())
            publish.publish_one(q,future)
            self.assertFalse((self.root/"state"/(publish.fingerprint(review()["draft"]["text"])+".json")).exists())
            checked("cancel","CANCEL")
            self.assertFalse(q.exists())
            self.assertEqual(review()["status"],"draft")
            checked("archive","ARCHIVE")
            self.assertEqual(review()["status"],"archived")
            apply("import",drafts=[dict(draft,id="imported-example",text="Unique imported draft")])
            self.assertEqual(content_studio.review(self.root,"imported-example")["status"],"draft")
            self.assertEqual(sorted(p.name for p in (self.root/"queue").glob("*.json")),[today.isoformat()+"-existing.json"])
            self.assertEqual(sorted(p.name for p in (self.root/"state").glob("*.json")),["existing.json"])
