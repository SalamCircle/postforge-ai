import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts import pro_assistant as pro, content_studio as studio

class ProAssistantTests(unittest.TestCase):
    def test_grounded_draft_and_fixed_endpoints(self):
        url="https://aws.amazon.com/training/digital/"
        calls=[]
        def transport(endpoint,key,payload):
            calls.append((endpoint,key,payload))
            if endpoint==pro.SEARCH:
                return {"results":[{"url":url,"title":"AWS training","content":"Some digital training is free."},{"url":"https://notaws.example/","title":"Ignore","content":"Untrusted"}]}
            return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore free AWS digital training.","sources":[url]})}}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            d=pro.generate(root,{"topic":"AWS courses","instructions":"Find free training","domains":["aws.amazon.com"],"date":"2030-01-02","scheduled_at":"2030-01-02T09:10:00+00:00"}, "search-fixture","model-fixture","test-model",transport,dt.datetime(2026,11,24,tzinfo=dt.timezone.utc))
            self.assertEqual(d["scheduled_at"],"2030-01-02T09:10:00+00:00")
            self.assertEqual(d["sources"],[url])
            self.assertIn(url,d["text"])
            self.assertNotIn("notaws",json.dumps(calls[-1][2]))
            self.assertNotIn("search-fixture",json.dumps(calls[-1][2]))
            self.assertEqual([x[0] for x in calls],[pro.SEARCH,pro.MODEL])
            self.assertEqual(list(root.iterdir()),[])
            self.assertNotIn("visual",d)
    def test_reject_hallucinated_link_and_missing_sources(self):
        url="https://aws.amazon.com/training/"
        for output in [{"title":"T","text":"Hello","sources":["https://invented.example/"]},{"title":"T","text":"Go to https://invented.example/","sources":[url]},{"title":"T","text":"Hello","sources":[]}]:
            def transport(endpoint,key,payload):
                if endpoint==pro.SEARCH:return {"results":[{"url":url,"content":"Training"}]}
                return {"choices":[{"message":{"content":json.dumps(output)}}]}
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(ValueError):
                    pro.generate(Path(temp),{"topic":"AWS","instructions":"Find training","date":"2030-01-02"},"a","b","fixture",transport)
                self.assertEqual(list(Path(temp).iterdir()),[])
    def test_invalid_request_fails_before_network(self):
        def never(*args):self.fail("No network request expected")
        for req in [{"topic":"AWS","instructions":"Find training","date":"2000-01-01"},{"topic":"AWS","instructions":"Find training","date":"2030-01-02","domains":["https://aws.amazon.com"]},{"topic":"AWS","instructions":"Find training","date":"2030-01-02","publish":True}]:
            with self.assertRaises(ValueError):
                pro.generate(Path("."),req,"a","b","fixture",never)

    def test_batch_followup_and_source_images(self):
        url="https://aws.amazon.com/training/"
        image="https://d1.awsstatic.com/training/example.jpg"
        calls=[]
        def transport(endpoint,key,payload):
            calls.append((endpoint,payload))
            if endpoint==pro.SEARCH:
                return {"results":[{"url":url,"content":"Free training","images":[{"url":image},{"url":"https://unrelated.example/image.jpg"}]}]}
            context=json.loads(payload["messages"][1]["content"])
            return {"choices":[{"message":{"content":json.dumps({"title":context["topic"],"text":"New evidence about "+context["topic"],"sources":[url]})}}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            first={"id":"prior","date":"2030-01-01","title":"Previous post","topic":"Cloud","text":"Previous content"}
            studio.save_draft(root,first)
            item={"topic":"AWS","instructions":"Find training","date":"2030-01-02","domains":["aws.amazon.com"],"find_images":True,"reference_id":"prior"}
            drafts=pro.generate_plan(root,{"requests":[item,dict(item,topic="Cloud security",date="2030-01-03")]}, "a","b","fixture",transport)
            self.assertEqual(len(drafts),2)
            self.assertTrue(calls[0][1]["include_images"])
            self.assertEqual(drafts[0]["image_candidates"],[{"url":image,"source":url}])
            self.assertIn("Previous content",calls[1][1]["messages"][1]["content"])
            self.assertNotIn("image_candidates",studio.payload(drafts[0]))
            studio.import_plan(root,drafts)
            self.assertEqual(len(studio.drafts(root)),3)
            self.assertFalse((root/"queue").exists())
            self.assertEqual(studio.read_draft(root,"prior"),first)
            with self.assertRaises(ValueError):
                pro.generate_plan(root,{"requests":[item]*4},"a","b","fixture",transport)

    def test_groq_runtime_matches_successful_transport(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        key="gsk_fixture_only"
        body={"model":"openai/gpt-oss-20b","messages":[{"role":"user","content":"Example"}],"response_format":{"type":"json_object"}}
        expected={"choices":[{"message":{"content":"{}"}}]}
        def runner(args,**kwargs):
            self.assertNotIn(key," ".join(args))
            self.assertEqual(kwargs["input"],"Authorization: Bearer "+key+"\n")
            self.assertIn(pro.MODEL,args)
            self.assertNotIn("--location",args)
            payload=json.loads(Path(args[args.index("--data-binary")+1][1:]).read_text())
            self.assertEqual(payload["response_format"]["type"],"json_schema")
            self.assertEqual(payload["reasoning_format"],"hidden")
            Path(args[args.index("--output")+1]).write_text(json.dumps(expected))
            return SimpleNamespace(returncode=0,stdout="200")
        with patch.object(pro.subprocess,"run",side_effect=runner) as run:
            self.assertEqual(pro.call(pro.MODEL,key,body),expected)
            run.assert_called_once()
        self.assertEqual(body["response_format"]["type"],"json_object")
        with patch.object(pro.subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout="403")) as run:
            with self.assertRaisesRegex(ValueError,"HTTP 403"):
                pro.call(pro.MODEL,key,body)
            run.assert_called_once()
        with patch.object(pro.subprocess,"run") as run:
            with self.assertRaises(ValueError):
                pro.call(pro.MODEL,"gsk_invalid\nheader",body)
            run.assert_not_called()

    def test_verified_inline_links_survive_and_missing_sources_are_appended(self):
        url="https://aws.amazon.com/training/"
        other="https://skillbuilder.aws/learn"
        for caption in ("Learn here: "+url, "Learn here ("+url+").", "Learn here: "+url+", then practise."):
            with self.subTest(caption=caption):
                def transport(endpoint,key,payload):
                    if endpoint==pro.SEARCH:
                        return {"results":[{"url":url,"content":"AWS training"},{"url":other,"content":"AWS courses"}]}
                    return {"choices":[{"message":{"content":json.dumps({"title":"Free cloud learning","text":caption,"sources":[url,other]})}}]}
                with tempfile.TemporaryDirectory() as temp:
                    root=Path(temp)
                    draft=pro.generate(root,{"topic":"AWS","instructions":"Include a real course link","date":"2030-01-02","domains":["aws.amazon.com","skillbuilder.aws"]},"a","b","fixture",transport)
                    self.assertEqual(draft["text"].count(url),1)
                    self.assertEqual(draft["text"].count(other),1)
                    studio.import_plan(root,[draft])
                    self.assertEqual(studio.status(root,draft),"draft")
                    self.assertFalse((root/"queue").exists())

    def test_inline_link_must_match_whole_researched_url(self):
        url="https://aws.amazon.com/training/"
        other="https://skillbuilder.aws/learn"
        for bad in (url+"invented",url+"?redirect=evil","https://aws.amazon.com.evil.example/training/","https://aws.amazon.com@evil.example/training/","www.evil.example","http://aws.amazon.com/training/"):
            with self.subTest(bad=bad),self.assertRaisesRegex(ValueError,"unverified inline links"):
                pro.grounded_caption("Visit "+bad,[url],{url})
        caption,sources=pro.grounded_caption("Visit "+other,[url],{url,other})
        self.assertEqual(sources,[url,other])
        self.assertEqual(caption.count(other),1)
        self.assertEqual(caption.count(url),1)

    def test_automation_consent_and_no_implicit_publication(self):
        from unittest.mock import patch
        today=studio.today().isoformat()
        with self.assertRaises(ValueError):
            pro.automation_mode({"automation":"publish","date":today},"GENERATE DRAFT ONLY")
        with self.assertRaises(ValueError):
            pro.automation_mode({"automation":"queue","date":today},"RESEARCH AND QUEUE")
        with self.assertRaises(ValueError):
            pro.automation_mode({"automation":"publish","date":today,"scheduled_at":"2030-01-01T09:00:00Z"},"RESEARCH AND PUBLISH")
        self.assertEqual(pro.automation_mode({"date":today},"GENERATE DRAFT ONLY"),"review")
        self.assertEqual(pro.automation_mode({"automation":"publish","date":today},"RESEARCH AND PUBLISH"),"publish")
        for mode in ("review","queue","publish"):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                future=(studio.today()+dt.timedelta(days=2)).isoformat()
                d={"id":"ai-example","title":"Cloud course","topic":"Cloud","date":future if mode=="queue" else today,"text":"Explore cloud learning."}
                if mode=="queue":d["scheduled_at"]=future+"T09:10:00+00:00"
                with patch.object(studio.publish,"publish_one") as send:
                    pro.save_generated(root,[d],mode)
                    send.assert_not_called()
                self.assertEqual(studio.status(root,d),{"review":"draft","queue":"queued","publish":"approved"}[mode])
                self.assertEqual(bool(studio.queued(root)),mode=="queue")
                if mode!="review":self.assertEqual(studio.load(studio.approval_path(root,d["id"]))["automation_mode"],mode)

    def test_immediate_publication_receipt_and_failure_no_queue(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            d={"id":"ai-example","title":"Cloud course","topic":"Cloud","date":studio.today().isoformat(),"text":"Explore cloud learning."}
            pro.save_generated(root,[d],"publish")
            with patch.object(pro.mobile_action,"git",return_value=""),patch.dict("os.environ",{"LIVE_PUBLISH":"false","LINKEDIN_ACCESS_TOKEN":""}),patch.object(studio.publish,"publish_one") as send:
                with self.assertRaises(ValueError):pro.publish_generated(root,d)
                send.assert_not_called()
            def sent(path,day,*,reviewed_now):
                self.assertTrue(reviewed_now)
                self.assertEqual(studio.load(path),studio.payload(d))
                studio.write(root/"state"/(studio.publish.fingerprint(d["text"])+".json"),{"status":"published","post_id":"fixture","queue":path.name,"fingerprint":studio.publish.fingerprint(d["text"])})
            with patch.object(pro.mobile_action,"git",return_value=""),patch.dict("os.environ",{"LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fixture"}),patch.object(studio.publish,"publish_one",side_effect=RuntimeError("fixture failure")):
                with self.assertRaises(RuntimeError):pro.publish_generated(root,d)
            self.assertEqual(studio.queued(root),[])
            with patch.object(pro.mobile_action,"git",return_value=""),patch.dict("os.environ",{"LIVE_PUBLISH":"true","LINKEDIN_ACCESS_TOKEN":"fixture"}),patch.object(studio.publish,"publish_one",side_effect=sent) as send:
                pro.publish_generated(root,d)
                with self.assertRaises(ValueError):pro.publish_generated(root,d)
                send.assert_called_once()

    def test_visual_request_renders_original_png(self):
        url="https://aws.amazon.com/training/"
        def transport(endpoint,key,payload):
            if endpoint==pro.SEARCH:return {"results":[{"url":url,"content":"AWS training"}]}
            return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore AWS training.","sources":[url]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            d=pro.generate(Path(tmp),{"topic":"AWS training","instructions":"Find a course and add visual","date":"2030-01-02","domains":["aws.amazon.com"]},"a","b","fixture",transport)
            self.assertIn("visual",d)
            png=studio.publish.render(d["visual"])
            self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_source_ids_resolve_original_urls_without_model_copying(self):
        url="https://aws.amazon.com/training/?course=cloud%20skills"
        other="https://skillbuilder.aws/learn"
        def transport(endpoint,key,payload):
            if endpoint==pro.SEARCH:
                return {"results":[{"url":url,"content":"Training"},{"url":"https://unknown.example/","content":"Ignore"},{"url":other,"content":"Learning"}]}
            context=json.loads(payload["messages"][1]["content"])
            self.assertEqual([r["id"] for r in context["sources"]],["S1","S2"])
            self.assertEqual(context["sources"][0]["url"],url)
            return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore the courses.","sources":["S2","S1","S1"]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            d=pro.generate(Path(tmp),{"topic":"Cloud","instructions":"Include links and add visual","date":"2030-01-02","domains":["aws.amazon.com","skillbuilder.aws"]},"a","b","fixture",transport)
            self.assertEqual(d["sources"],[other,url])
            self.assertEqual(d["text"].count(url),1)
            self.assertIn("visual",d)
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_unknown_source_ids_and_insufficient_evidence_fail_closed(self):
        results=[{"id":"S1","url":"https://aws.amazon.com/training/"}]
        for refs in (["S2"],["S1","S9"],["https://aws.amazon.com/training/?invented"],[1],[],["S1"]*6):
            with self.subTest(refs=refs),self.assertRaises(ValueError):
                pro.resolve_sources(refs,results)
        self.assertEqual(pro.resolve_sources(["S1",results[0]["url"]],results),[results[0]["url"]])

    def test_recovery_refreshes_insufficient_evidence_without_broadening_domains(self):
        first="https://aws.amazon.com/training/"
        fresh="https://aws.amazon.com/training/digital/"
        calls=[]
        def transport(endpoint,key,payload):
            calls.append((endpoint,payload))
            if endpoint==pro.SEARCH:
                self.assertEqual(payload["include_domains"],["aws.amazon.com"])
                url=fresh if len(calls)>1 else first
                return {"results":[{"url":url,"content":"Training is available."},{"url":"https://outside.example/","content":"Not permitted"}]}
            context=json.loads(payload["messages"][1]["content"])
            if len(calls)==2:
                return {"choices":[{"message":{"content":json.dumps({"title":"Cloud","text":"Insufficient evidence","sources":[]})}}]}
            self.assertEqual(context["sources"][0]["url"],fresh)
            self.assertNotIn("outside.example",json.dumps(context))
            return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore AWS training.","sources":["S1"]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            d=pro.generate(Path(tmp),{"topic":"AWS training","instructions":"Find a course and add visual","date":"2030-01-02","domains":["aws.amazon.com"]},"a","b","fixture",transport)
            self.assertEqual(d["sources"],[fresh])
            self.assertIn(fresh,d["text"])
            self.assertIn("visual",d)
            self.assertEqual([x[0] for x in calls],[pro.SEARCH,pro.MODEL,pro.SEARCH,pro.MODEL])
            self.assertEqual(calls[2][1]["query"],"AWS training")
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_malformed_response_corrected_once_without_extra_search(self):
        url="https://aws.amazon.com/training/"
        calls=[]
        def transport(endpoint,key,payload):
            calls.append(endpoint)
            if endpoint==pro.SEARCH:return {"results":[{"url":url,"content":"Training is available."}]}
            content="not json" if len(calls)==2 else json.dumps({"title":"Cloud learning","text":"Explore AWS training.","sources":["S1"]})
            return {"choices":[{"message":{"content":content}}]}
        with tempfile.TemporaryDirectory() as tmp:
            d=pro.generate(Path(tmp),{"topic":"AWS","instructions":"Find training","date":"2030-01-02"},"a","b","fixture",transport)
            self.assertEqual(d["sources"],[url])
            self.assertEqual(calls,[pro.SEARCH,pro.MODEL,pro.MODEL])

    def test_no_evidence_and_provider_failures_do_not_loop(self):
        item={"topic":"AWS","instructions":"Find training","date":"2030-01-02"}
        calls=[]
        def empty(endpoint,key,payload):
            calls.append(endpoint)
            return {"results":[]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"No matching source"):
                pro.generate(Path(tmp),item,"a","b","fixture",empty)
            self.assertEqual(calls,[pro.SEARCH,pro.SEARCH])
            for code in (403,429,503):
                calls.clear()
                def failed(endpoint,key,payload):
                    calls.append(endpoint)
                    if endpoint==pro.SEARCH:return {"results":[{"url":"https://aws.amazon.com/training/","content":"Training"}]}
                    raise ValueError("Groq request failed (HTTP "+str(code)+"); no retry")
                with self.assertRaisesRegex(ValueError,"HTTP "+str(code)):
                    pro.generate(Path(tmp),item,"a","b","fixture",failed)
                self.assertEqual(calls,[pro.SEARCH,pro.MODEL])
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_recovery_budget_shared_across_plan_and_failed_plan_writes_nothing(self):
        item={"topic":"AWS","instructions":"Find training","date":"2030-01-02"}
        calls=[]
        def transport(endpoint,key,payload):
            calls.append(endpoint)
            if endpoint==pro.SEARCH:return {"results":[{"url":"https://aws.amazon.com/training/","content":"Training"}]}
            valid=calls.count(pro.MODEL)==2
            return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore training.","sources":["S1"] if valid else ["S9"]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"unknown research source"):
                pro.generate_plan(Path(tmp),{"requests":[item,dict(item,topic="Cloud security")]},"a","b","fixture",transport)
            self.assertEqual(calls,[pro.SEARCH,pro.MODEL,pro.MODEL,pro.SEARCH,pro.MODEL])
            self.assertEqual(list(Path(tmp).iterdir()),[])
