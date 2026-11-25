import datetime as dt
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from scripts import content_studio as studio, publish, studio_dashboard as dashboard

class DashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.date = (studio.today() + dt.timedelta(days=2)).isoformat()
        self.draft = {"id":"dashboard-test","date":self.date,"title":"Test","topic":"Security","text":"Example reviewed post"}

    def test_dashboard_actions(self):
        r = dashboard.action(self.root,{"action":"draft","draft":self.draft})
        req = {"id":self.draft["id"],"digest":r["digest"]}
        with self.assertRaises(ValueError):
            dashboard.action(self.root,dict(req,action="approve"))
        dashboard.action(self.root,dict(req,action="approve",confirmation="APPROVE"))
        dashboard.action(self.root,dict(req,action="export",confirmation="QUEUE"))
        self.assertEqual(dashboard.model(self.root)["calendar"][0]["status"],"queued")
        dashboard.action(self.root,dict(req,action="cancel",confirmation="CANCEL"))
        self.assertEqual(studio.review(self.root,self.draft["id"])["status"],"draft")
        self.assertFalse(list((self.root/"queue").glob("*.json")))

    def test_schedule_and_approval(self):
        r=studio.save_draft(self.root,self.draft)
        studio.approve(self.root,self.draft["id"],r["digest"])
        updated=studio.schedule(self.root,self.draft["id"],self.date+"T14:30","Europe/London",r["digest"])
        self.assertEqual(updated["status"],"draft")
        self.assertIn("scheduled_at",updated["draft"])
        with self.assertRaises(ValueError):
            studio.approve(self.root,self.draft["id"],r["digest"])
        for bad in ("2027-03-28T01:30","2027-10-31T01:30"):
            with self.assertRaises(ValueError):
                studio.schedule(self.root,self.draft["id"],bad,"Europe/London",updated["digest"])

    def test_due_window(self):
        scheduled="2027-01-01T14:30:00+00:00"
        item={"date":"2027-01-01","text":"Example","scheduled_at":scheduled}
        publish.validate(item,item["date"])
        start=publish.parse_scheduled(scheduled)
        self.assertFalse(publish.due(item,start-dt.timedelta(seconds=1)))
        self.assertTrue(publish.due(item,start))
        self.assertTrue(publish.due(item,start+dt.timedelta(minutes=29),True))
        self.assertFalse(publish.due(item,start+dt.timedelta(hours=3)))
        self.assertFalse(publish.due({"date":item["date"]},start,True))
        self.assertTrue(publish.due({"date":item["date"]},start))
        with self.assertRaises(ValueError):
            publish.validate(dict(item,scheduled_at="2027-01-02T14:30:00+00:00"),item["date"])

    def test_publisher_skips_future_time_without_api(self):
        item=dict(self.draft,scheduled_at=self.date+"T14:30:00+00:00")
        r=studio.save_draft(self.root,item)
        studio.approve(self.root,item["id"],r["digest"])
        q=studio.export(self.root,item["id"],r["digest"])
        with patch.object(publish,"ROOT",self.root),patch.dict("os.environ",{"LIVE_PUBLISH":"true"}),patch.object(publish,"request",side_effect=AssertionError("Unexpected API call")):
            publish.publish_one(self.root/"queue"/q["queue"],self.date)
        self.assertFalse((self.root/"state").exists())

    def test_http_session_and_origin(self):
        server=HTTPServer(("127.0.0.1",0),dashboard.handler_for(self.root,"test-token","unused"))
        authority="127.0.0.1:"+str(server.server_port)
        server.RequestHandlerClass=dashboard.handler_for(self.root,"test-token",authority)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join,3)
        self.addCleanup(server.shutdown)
        def request(method,path,body=None,headers=None):
            conn=HTTPConnection("127.0.0.1",server.server_port,timeout=3)
            try:
                conn.request(method,path,body,headers or {})
                response=conn.getresponse()
                return response.status,response.read()
            finally:
                conn.close()
        self.assertEqual(request("GET","/")[0],200)
        self.assertEqual(request("GET","/api/model")[0],403)
        self.assertEqual(request("GET","/api/model",headers={"Host":"attacker.invalid","X-Studio-Token":"test-token"})[0],403)
        self.assertEqual(request("GET","/api/model",headers={"X-Studio-Token":"test-token"})[0],200)
        body=json.dumps({"action":"draft","draft":self.draft})
        headers={"Content-Type":"application/json","X-Studio-Token":"test-token","Origin":"https://attacker.invalid"}
        self.assertEqual(request("POST","/api/action",body,headers)[0],403)
        headers["Origin"]="http://"+authority
        self.assertEqual(request("POST","/api/action",body,headers)[0],200)
        self.assertEqual(request("GET","/../../.env")[0],404)
        self.assertEqual(len(studio.drafts(self.root)),1)

if __name__ == "__main__":
    unittest.main()
