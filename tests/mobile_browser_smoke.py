"""Mobile viewport browser smoke test; all GitHub calls are mocked."""
import base64
import hashlib
import io
from PIL import Image
import functools
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
HEAD, TREE, BLOB = "a"*40, "b"*40, "c"*40
DRAFT = {"id":"mobile-example","date":"2030-01-02","title":"Mobile example","topic":"AI","text":"A safe example draft"}
TOKEN = "github_pat_fixture_only"
EDIT_TOKEN = "github_pat_edit_fixture_only"

def main():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT/"docs"/"mobile"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            chrome = shutil.which("google-chrome") or shutil.which("chromium")
            browser = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
            page = browser.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
            calls = []
            dispatched = []
            completed = set()
            remote_head = HEAD
            ref_unavailable = False
            blobs = {}
            entries = []
            def add(path, content):
                sha = format(len(entries)+100, "040x")
                blobs[sha] = content
                entries.append({"path":path,"type":"blob","mode":"100644","sha":sha,"size":len(content if isinstance(content,bytes) else content.encode())})
            add("README.md","# PostForge AI\n")
            add("scripts/publish.py","# publisher")
            add(".github/workflows/publish.yml","name: PostForge Publisher\nrun: python3 scripts/publish.py")
            add("requirements.txt","")
            add("VERSION","2.0.0-alpha.1")
            add(".postforge-installation.json",json.dumps({"product":"postforge-ai","edition":"v2-core","mobile_protocol":1}))
            for path in ("scripts/content_studio.py","scripts/studio_dashboard.py","scripts/mobile_action.py",".github/workflows/mobile-studio.yml"):
                add(path,"# core")
            add("studio/drafts/mobile-example.json",json.dumps(DRAFT))
            full = "Published example. "*15+"Read this final sentence."
            add("queue/2030-01-03-legacy.json",json.dumps({"date":"2030-01-03","text":full}))
            png=io.BytesIO()
            Image.new("RGB",(32,32),"#0a66c2").save(png,format="PNG")
            media=png.getvalue()
            media_sha=hashlib.sha256(media).hexdigest()
            add("state/media/"+media_sha+".png",media)
            add("state/receipt.json",json.dumps({"date":"2030-01-03","queue":"2030-01-03-legacy.json","status":"published","post_id":"urn:li:share:123","visual":True,"published_media":{"sha256":media_sha,"extension":"png"}}))
            page.on("pageerror", lambda error: print("Browser error:", error))
            page.on("console", lambda message: print("Browser console:", message.text) if message.type == "error" else None)
            def api(route):
                request=route.request
                path=request.url.split("api.github.com",1)[1].split("?",1)[0]
                headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization, accept, x-github-api-version, content-type","access-control-allow-methods":"GET, POST, OPTIONS"}
                if request.method=="OPTIONS":
                    route.fulfill(status=204,headers=headers);return
                if request.all_headers().get("authorization") not in ("Bearer "+TOKEN,"Bearer "+EDIT_TOKEN):
                    route.fulfill(status=401,headers=headers);return
                calls.append((request.method,path))
                if path=="/repos/owner/private": data={"private":True}
                elif path.endswith("/git/ref/heads/main"):
                    if ref_unavailable:
                        route.fulfill(status=503,headers=headers);return
                    data={"object":{"sha":remote_head}}
                elif path.endswith("/git/commits/"+remote_head): data={"tree":{"sha":TREE}}
                elif path.endswith("/git/trees/"+TREE): data={"truncated":False,"tree":entries}
                elif "/git/blobs/" in path and path.split("/")[-1] in blobs: data={"encoding":"base64","content":base64.b64encode(blobs[path.split("/")[-1]] if isinstance(blobs[path.split("/")[-1]],bytes) else blobs[path.split("/")[-1]].encode()).decode()}
                elif path.endswith("/dispatches"):
                    body=json.loads(request.post_data)
                    assert body.get("return_run_details") is True
                    assert request.all_headers().get("x-github-api-version") == "2022-11-28"
                    if body["ref"]!="main" or json.loads(body["inputs"]["payload"])["head"]!=remote_head:
                        route.fulfill(status=400,headers=headers);return
                    if path.endswith("/pro-ai.yml/dispatches"):
                        assert body["inputs"]["confirmation"] == "GENERATE DRAFT ONLY"
                    dispatched.append(json.loads(body["inputs"]["payload"]))
                    data={"workflow_run_id":123}
                elif path.endswith("/actions/runs/123"):
                    action = dispatched[-1]
                    key = len(dispatched)
                    if key not in completed:
                        completed.add(key)
                        if action.get("action") == "approve":
                            add("studio/approvals/"+action["id"]+".json",json.dumps({"digest":action["digest"]}))
                        elif action.get("action") == "export":
                            add("queue/"+DRAFT["date"]+"-studio-"+DRAFT["id"]+".json",json.dumps({"date":DRAFT["date"],"text":DRAFT["text"]}))
                        elif "topic" in action or "requests" in action:
                            for n, item in enumerate(action.get("requests",[action])):
                                draft={"id":f"ai-test-{key}-{n}","date":item["date"],"title":item["topic"],"topic":item["topic"],"text":"Generated research example"}
                                add("studio/drafts/"+draft["id"]+".json",json.dumps(draft))
                    data={"status":"completed","conclusion":"success"}
                else:
                    route.fulfill(status=404,headers=headers);return
                route.fulfill(status=200,headers=headers,content_type="application/json",body=json.dumps(data))
            page.route("https://api.github.com/**",api)
            def settings():
                page.locator('[data-tab="settings"]').click()
                expect(page.locator("#settings")).to_be_visible()
            page.goto("http://127.0.0.1:"+str(server.server_port)+"/")
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(TOKEN)
            page.locator("#enable-write").check()
            page.get_by_role("button",name="Connect",exact=True).click()
            try:
                expect(page.locator("#connection-label")).to_contain_text("reviewed actions enabled")
            except AssertionError:
                print("Connection notice:", page.locator("#notice").inner_text())
                print("Mocked request paths:", calls)
                raise
            expect(page.locator("#connection-label")).to_contain_text("V2 (")
            expect(page.locator("#edition-title")).to_have_text("PostForge AI v2 PRO")
            settings()
            page.locator('#settings [data-go="integrations"]').click()
            expect(page.locator("#integrations")).to_be_visible()
            expect(page.locator("#integration-status")).to_contain_text("Backend not installed")
            expect(page.locator("#setup-progress")).to_contain_text("Private workspace")
            page.locator('#integrations [data-go="chatgpt-centre"]').click()
            expect(page.locator("#chatgpt-centre")).to_be_visible()
            for section in ("chatgpt-centre","research","integrations"):
                link=page.locator("#"+section+" a.chatgpt-connect-link")
                expect(link).to_have_attribute("href","https://chatgpt.com/plugins/github")
                expect(link).to_have_attribute("target","_blank")
                expect(link).to_have_attribute("rel","noopener noreferrer")
            expect(page.locator("#chatgpt-centre a.chatgpt-connect-link")).to_be_visible()
            expect(page.locator("#chatgpt-status")).to_have_text("Not verified on this device")
            assert page.locator('a[href*="developers.openai.com/plugins/"]').count() == 0
            capability_prompt=page.locator("#chatgpt-capability-prompt").input_value()
            assert "owner/private" in capability_prompt and "Do not create files" in capability_prompt
            assert "Only report publication" in page.locator("#chatgpt-receipt-prompt").input_value()
            expect(page.locator("#chatgpt-copy-capability")).to_be_enabled()
            expect(page.locator("#chatgpt-copy-receipt")).to_be_enabled()
            assert "owner/private" in page.locator("#chatgpt-content-prompt").input_value()
            assert "Do not create files, queue, publish" in page.locator("#chatgpt-content-prompt").input_value()
            page.locator("#chatgpt-mode").select_option("publish")
            expect(page.locator("#chatgpt-copy-content")).to_be_disabled()
            expect(page.locator("#chatgpt-content-prompt")).to_have_value("")
            page.locator("#chatgpt-live-consent").check()
            expect(page.locator("#chatgpt-copy-content")).to_be_enabled()
            live_prompt=page.locator("#chatgpt-content-prompt").input_value()
            assert "owner/private" in live_prompt and "queue/YYYY-MM-DD-chatgpt-free-test-unique.json" in live_prompt and "Do not retry an uncertain" in live_prompt
            page.locator("#chatgpt-mode").select_option("draft")
            assert not page.locator("#chatgpt-live-consent").is_checked()
            page.locator("#chatgpt-start").click()
            expect(page.locator("#chatgpt-status")).to_contain_text("Awaiting connection proof")
            prompt=page.locator("#chatgpt-prompt").input_value()
            import re
            nonce=re.search(r"chatgpt-([a-f0-9]{32})\.json",prompt).group(1)
            retry_prompt=page.locator("#chatgpt-retry-prompt").input_value()
            assert nonce in retry_prompt and "Only if the exact file is confirmed absent" in retry_prompt
            add("studio/connections/chatgpt-"+nonce+".json",json.dumps({"version":1,"challenge":nonce,"repository":"owner/private","created_at":"2026-01-01T12:00:00Z"}))
            page.locator("#chatgpt-check").click()
            expect(page.locator("#chatgpt-status")).to_contain_text("Repository write verified")
            assert page.evaluate("Object.keys(localStorage)") == ["postforge.chatgpt.challenge.v1:owner/private"]
            assert page.evaluate("localStorage.getItem(\'postforge.chatgpt.challenge.v1:owner/private\')") == nonce
            assert page.evaluate("sessionStorage.length") == 0
            page.locator("#chatgpt-forget").click()
            expect(page.locator("#chatgpt-status")).to_have_text("Not verified on this device")
            assert page.evaluate("localStorage.length") == 0
            page.locator('#chatgpt-centre [data-go="integrations"]').click()
            expect(page.locator('#integrations a[href="https://chatgpt.com/plugins/github"]')).to_be_visible()
            expect(page.locator("#integration-secrets")).to_have_attribute("href","https://github.com/owner/private/settings/secrets/actions/new")
            page.locator('#integrations [data-go="settings"]').click()
            page.locator('[data-tab="calendar"]').click()

            expect(page.locator("#upgrade-guide")).to_be_hidden()
            expect(page.locator("#access")).to_have_value("")
            page.locator("#start").fill("2030-01-01")
            expect(page.locator("#calendar-rows")).to_contain_text("Mobile example")
            expect(page.locator("#welcome")).to_be_hidden()
            expect(page.locator("#settings")).to_be_hidden()
            expect(page.locator("#research")).to_be_hidden()
            assert page.locator("[data-page]:visible").count()==1
            assert page.locator(".primary-nav").evaluate("(e)=>getComputedStyle(e).position")== "fixed"
            page.set_viewport_size({"width":1280,"height":800})
            assert page.locator(".primary-nav").evaluate("(e)=>getComputedStyle(e).position")== "sticky"
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.set_viewport_size({"width":390,"height":844})
            ref_unavailable=True
            page.locator("#refresh").click()
            expect(page.locator("#settings")).to_be_visible()
            expect(page.locator("#notice")).to_contain_text("GitHub request failed")
            page.locator('[data-tab="drafts"]').click()
            expect(page.locator("#drafts")).to_be_hidden()
            assert not dispatched
            ref_unavailable=False
            page.locator("#settings-refresh").click()
            expect(page.locator("#connection-label")).to_contain_text("reviewed actions enabled")
            page.locator('[data-tab="calendar"]').click()
            expect(page.locator("#calendar-rows")).to_contain_text("Mobile example")
            if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                raise RuntimeError("Mobile layout overflows")
            page.locator('#week-days [data-date="2030-01-02"]').click()
            expect(page.locator("#calendar-rows")).to_contain_text("Mobile example")
            expect(page.locator("#calendar-rows")).not_to_contain_text("Published example")
            page.locator("#week-next").click()
            expect(page.locator("#week-days [data-date='2030-01-08']")).to_be_visible()
            page.locator("#week-prev").click()
            page.locator("#week-all").click()
            page.locator("#calendar-rows").get_by_role("button",name="Published example.",exact=False).click()
            expect(page.locator("#post-dialog")).to_be_visible()
            expect(page.locator("#post-text")).to_contain_text("Read this final sentence.")
            expect(page.locator("#post-media-image")).to_be_visible()
            expect(page.locator("#post-media-status")).to_contain_text("Exact archived upload")
            expect(page.locator("#post-stage [aria-current=step]")).to_have_text("Published")
            expect(page.locator("#linkedin-post")).to_have_attribute("href","https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A123/")
            page.locator("#close-post").click()
            expect(page.locator("#post-dialog")).to_be_hidden()
            page.locator('#calendar [data-go="published-library"]').click()
            expect(page.locator("#published-library")).to_be_visible()
            expect(page.locator("#published-list")).to_contain_text("Exact uploaded image available")
            page.locator("#published-list").get_by_role("button",name="View published post").click()
            expect(page.locator("#post-media-image")).to_be_visible()
            page.locator("#close-post").click()
            page.locator('#published-library [data-go="calendar"]').click()
            page.locator("#search").fill("not present")
            expect(page.locator("#calendar-rows")).to_contain_text("No content matches")
            page.locator("#search").fill("")
            page.locator("#calendar-rows").get_by_role("button",name="Review").click()
            expect(page.locator("#review-data")).to_contain_text("A safe example draft")
            def confirm():
                expect(page.locator("#action-dialog")).to_be_visible()
                page.locator("#confirm-accept").click()
            expect(page.locator("#approval")).to_be_visible()
            expect(page.locator("#approval-list")).to_be_hidden()
            expect(page.locator("#review-status")).to_have_text("Awaiting review")
            expect(page.locator("#review-stage [aria-current=step]")).to_have_text("Review")
            page.get_by_role("button",name="Approve exact draft").click()
            page.locator("#confirm-cancel").click()
            assert not dispatched
            page.get_by_role("button",name="Approve exact draft").click()
            confirm()
            expect(page.locator("#notice")).to_contain_text("not yet saved")
            page.locator("#check-run").click()
            expect(page.locator("#notice")).to_contain_text("GitHub reports success")
            expect(page.locator("#review-status")).to_have_text("Approved")
            page.get_by_role("button",name="Queue approved draft").click()
            confirm()
            expect(page.locator("#notice")).to_contain_text("not yet saved")
            page.locator("#check-run").click()
            expect(page.locator("#review-status")).to_have_text("Queued · not yet published")
            page.get_by_role("button",name="Drafts",exact=True).click()
            page.locator("#new").click()
            expect(page.locator("#compose")).to_be_visible()
            expect(page.locator("#drafts")).to_be_hidden()
            form = page.locator("#draft-form")
            form.locator('[name="id"]').fill("timed-mobile-example")
            form.locator('[name="date"]').fill("2030-07-01")
            form.locator('[name="time"]').fill("09:30")
            form.locator('[name="schedule_zone"]').fill("Europe/London")
            form.locator('[name="title"]').fill("Timed example")
            form.locator('[name="topic"]').fill("AI")
            form.locator('[name="text"]').fill("Draft with a requested time")
            expect(page.locator("#draft-timing-preview")).to_contain_text("2030-07-01 08:30 UTC")
            form.get_by_role("button",name="Save draft only").click()
            confirm()
            expect(page.locator("#notice")).to_contain_text("not yet saved")
            assert dispatched[-1]["action"] == "draft"
            assert dispatched[-1]["draft"]["scheduled_at"] == "2030-07-01T08:30:00+00:00"
            assert dispatched[-1]["draft"]["date"] == "2030-07-01"
            page.locator("#check-run").click()
            expect(page.locator("#notice")).to_contain_text("GitHub reports success")
            if not any(method=="POST" and path.endswith("/dispatches") for method,path in calls):
                raise RuntimeError("Dispatch not exercised")
            if page.evaluate("localStorage.length || sessionStorage.length"):
                raise RuntimeError("Unexpected browser persistence")
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#connect-panel")).to_be_visible()
            # Explicit opt-in persists only encrypted credentials and never grants write mode.
            password = "a unique browser test passphrase"
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(TOKEN)
            page.locator("#enable-write").uncheck()
            page.locator("#remember").check()
            page.locator("#vault-pass").fill(password)
            page.locator("#vault-repeat").fill(password)
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#notice")).to_contain_text("Encrypted device unlock saved")
            saved = page.evaluate("localStorage.getItem('postforge.mobile.vault.v1')")
            if not saved or TOKEN in saved or password in saved or "owner/private" in saved:
                raise RuntimeError("Plaintext credential persisted")
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#unlock-panel")).to_be_visible()
            page.locator("#unlock-pass").fill("wrong separate passphrase")
            page.get_by_role("button",name="Unlock workspace").click()
            expect(page.locator("#notice")).to_contain_text("Cannot unlock")
            expect(page.locator("#workspace")).to_be_hidden()
            page.locator("#unlock-pass").fill(password)
            page.get_by_role("button",name="Unlock workspace").click()
            expect(page.locator("#connection-label")).to_contain_text("read only")
            settings()
            page.locator("#enable-edit").click()
            page.locator("#edit-access").fill(TOKEN)
            page.get_by_role("button",name="Authorize editing").click()
            expect(page.locator("#notice")).to_contain_text("separate editing token")
            page.locator("#edit-access").fill(EDIT_TOKEN)
            page.locator("#edit-duration").select_option("43200")
            page.locator("#remember-edit").check()
            page.locator("#edit-pass").fill(password)
            page.locator("#edit-repeat").fill(password)
            page.get_by_role("button",name="Authorize editing").click()
            expect(page.locator("#connection-label")).to_contain_text("reviewed actions enabled")
            expect(page.locator("#edit-access")).to_have_value("")
            if page.evaluate("localStorage.getItem('postforge.mobile.vault.v1')") != saved:
                raise RuntimeError("Editing modified saved read-only vault")
            expect(page.locator("#notice")).to_contain_text("Encrypted authorization saved")
            edit_saved = page.evaluate("localStorage.getItem('postforge.mobile.edit-vault.v1')")
            if not edit_saved or EDIT_TOKEN in edit_saved or password in edit_saved:
                raise RuntimeError("Plaintext editing credential persisted")
            expect(page.locator("#editing-expiry")).to_be_visible()
            settings()
            page.locator("#lock-edit").click()
            expect(page.locator("#connection-label")).to_contain_text("read only")
            expect(page.locator("#notice")).to_contain_text("Read-only connection restored")
            settings()
            page.locator("#disconnect").click()
            page.locator("#unlock-pass").fill(password)
            page.get_by_role("button",name="Unlock workspace").click()
            expect(page.locator("#connection-label")).to_contain_text("read only")
            settings()
            page.locator("#enable-edit").click()
            page.locator("#saved-edit-pass").fill(password)
            page.get_by_role("button",name="Unlock editing").click()
            expect(page.locator("#connection-label")).to_contain_text("reviewed actions enabled")
            if page.evaluate("localStorage.getItem('postforge.mobile.edit-vault.v1')") != edit_saved:
                raise RuntimeError("Unlock renewed or modified original authorization")
            page.evaluate("window.originalNow=Date.now; Date.now=()=>window.originalNow()+31*86400000; document.dispatchEvent(new Event('visibilitychange'))")
            expect(page.locator("#connection-label")).to_contain_text("read only")
            expect(page.locator("#notice")).to_contain_text("Read-only connection restored")
            settings()
            page.locator("#enable-edit").click()
            page.locator("#saved-edit-pass").fill(password)
            page.get_by_role("button",name="Unlock editing").click()
            expect(page.locator("#notice")).to_contain_text("expired")
            page.evaluate("Date.now=window.originalNow")
            settings()
            page.locator("#forget-edit").click()
            confirm()
            expect(page.locator("#saved-edit-form")).to_be_hidden()
            settings()
            page.locator("#disconnect").click()
            page.locator("#forget").click()
            confirm()
            expect(page.locator("#unlock-panel")).to_be_hidden()
            if page.evaluate("localStorage.length || sessionStorage.length"):
                raise RuntimeError("Saved vault not cleared")
            add("scripts/pro_assistant.py","# pro")
            add("scripts/pro_images.py","# image staging")
            add(".github/workflows/pro-ai.yml","name: Pro\n# RESEARCH AND PUBLISH")
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(EDIT_TOKEN)
            page.locator("#enable-write").check()
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#connection-label")).to_contain_text("V2 Pro")
            page.locator('[data-tab="research"]').click()
            expect(page.locator("#pro-panel")).to_be_visible()
            expect(page.locator("#history")).to_be_hidden()
            expect(page.locator("#brief-page")).to_be_hidden()
            expect(page.locator("#connection")).to_be_hidden()
            pro_form = page.locator("#pro-form")
            pro_form.locator('[name="topic"]').fill("Free AWS course")
            pro_form.locator('[name="instructions"]').fill("Find official free training")
            pro_form.locator('[name="domains"]').fill("aws.amazon.com, skillbuilder.aws, AWS.AMAZON.COM, aws.amazon.com, skillbuilder.aws, AWS.AMAZON.COM")
            pro_form.locator('[name="date"]').fill("2030-01-02")
            pro_form.locator('[name="time"]').fill("09:10")
            before=len(dispatched)
            pro_form.locator('[name="domains"]').fill("a.example,b.example,c.example,d.example,e.example,f.example")
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#notice")).to_contain_text("five unique official hostnames")
            assert len(dispatched)==before
            pro_form.locator('[name="domains"]').fill("aws.amazon.com, skillbuilder.aws, AWS.AMAZON.COM, aws.amazon.com, skillbuilder.aws, AWS.AMAZON.COM")
            # Invalid source-image automation must not send a workflow.
            before=len(dispatched)
            pro_form.locator('[name="automation"]').select_option("queue")
            pro_form.locator('[name="find_images"]').check()
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#pro-image-warning")).to_contain_text("Real source images need approval")
            assert len(dispatched)==before
            pro_form.locator('[name="automation"]').select_option("review")
            pro_form.locator('[name="find_images"]').uncheck()
            # Stale before confirmation: refresh without dispatch or consent.
            remote_head = "d"*40
            before=len(dispatched)
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#notice")).to_contain_text("Workspace updated automatically")
            expect(page.locator("#action-dialog")).not_to_be_visible()
            expect(pro_form.locator('[name="topic"]')).to_have_value("Free AWS course")
            assert len(dispatched)==before
            # A failed freshness check is not an ambiguous submission.
            ref_unavailable = True
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#notice")).to_contain_text("Nothing was submitted")
            expect(page.locator("#action-dialog")).not_to_be_visible()
            assert len(dispatched)==before
            ref_unavailable = False
            # A change while the consent dialog is open invalidates that consent.
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#action-dialog")).to_be_visible()
            remote_head = "e"*40
            confirm()
            expect(page.locator("#notice")).to_contain_text("Workspace updated automatically")
            assert len(dispatched)==before
            # New explicit confirmation against the refreshed head is dispatched once.
            pro_form.get_by_role("button",name="Research and generate draft").click()
            confirm()
            expect(page.locator("#notice")).to_contain_text("not yet saved")
            assert len(dispatched)==before+1
            assert dispatched[-1]["head"]==remote_head
            assert dispatched[-1]["scheduled_at"] == "2030-01-02T09:10:00+00:00"
            assert dispatched[-1]["domains"] == ["aws.amazon.com","skillbuilder.aws"]
            assert dispatched[-1]["use_brand"] is False
            assert any(path.endswith("/pro-ai.yml/dispatches") for method,path in calls if method=="POST")
            page.locator("#check-run").click()
            expect(page.locator("#notice")).to_contain_text("GitHub reports success")
            expect(page.locator("#approval")).to_be_visible()
            expect(page.locator("#review-title")).to_have_text("Free AWS course")
            page.locator('[data-tab="research"]').click()
            pro_form.locator('[name="find_images"]').check()
            pro_form.locator('[name="reference_id"]').fill("mobile-example")
            page.locator("#pro-add").click()
            expect(page.locator("#pro-plan-list")).to_contain_text("Free AWS course")
            pro_form.locator('[name="topic"]').fill("Cloud security")
            pro_form.locator('[name="date"]').fill("2030-01-03")
            page.locator("#pro-add").click()
            page.locator("#pro-submit").click()
            confirm()
            expect(page.locator("#notice")).to_contain_text("not yet saved")
            assert len(dispatched[-1]["requests"]) == 2
            assert dispatched[-1]["requests"][0]["find_images"] is True
            assert dispatched[-1]["requests"][0]["reference_id"] == "mobile-example"
            assert dispatched[-1]["requests"][1]["date"] == "2030-01-03"
            page.locator("#check-run").click()
            expect(page.locator("#notice")).to_contain_text("GitHub reports success")
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#connect-panel")).to_be_visible()
            # A failed AI request survives reconnection and restoring it never dispatches.
            add("scripts/pro_recovery.py","# journal")
            add("scripts/smart_visual.py","# smart visual")
            add("scripts/ai_visual.py","# AI visual")
            add("studio/requests/456.json",json.dumps({"run_id":"456","status":"failed","mode":"publish","request":{"topic":"Recover this topic","instructions":"Find relevant official sources","date":"2000-01-01","scheduled_at":"2000-01-01T09:00:00+00:00","domains":["aws.amazon.com"]},"message":"AI selected an unknown research source","draft_ids":[]}))
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(EDIT_TOKEN)
            page.locator("#enable-write").check()
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#connection-label")).to_contain_text("V2 Pro")
            page.locator('[data-tab="research"]').click()
            page.get_by_role("button",name="Activity",exact=True).click()
            expect(page.locator("#history")).to_be_visible()
            expect(page.locator("#pro-recovery-list")).to_contain_text("AI selected an unknown research source")
            before=len(dispatched)
            page.get_by_role("button",name="Restore request",exact=True).click()
            confirm()
            expect(page.locator('#pro-form [name="topic"]')).to_have_value("Recover this topic")
            expect(page.locator('#pro-form [name="time"]')).to_have_value("")
            if len(dispatched)!=before:
                raise RuntimeError("Recovery unexpectedly dispatched a workflow")
            expect(page.locator("#smart-visual-option")).to_be_visible()
            pro_form.locator('[name="automation"]').select_option("queue")
            pro_form.locator('[name="visual_mode"]').select_option("smart")
            pro_form.locator('[name="instructions"]').fill("Find training and include the actual image")
            pro_form.locator('[name="date"]').fill("2030-01-03")
            pro_form.locator('[name="time"]').fill("09:10")
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#action-dialog")).to_be_visible()
            expect(page.locator("#confirm-text")).to_contain_text("Smart Auto Visual")
            page.locator("#confirm-cancel").click()
            assert len(dispatched)==before
            pro_form.locator('[name="visual_mode"]').select_option("ai-illustration")
            expect(page.locator("#ai-visual-help")).to_be_visible()
            pro_form.get_by_role("button",name="Research and generate draft").click()
            expect(page.locator("#confirm-text")).to_contain_text("Optional AI artwork")
            page.locator("#confirm-cancel").click()
            assert len(dispatched)==before
            page.locator("#pro-preferences summary").click()
            page.locator("#save-pro-preferences").click()
            confirm()
            expect(page.locator("#pro-preference-status")).to_contain_text("Defaults saved")
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#connect-panel")).to_be_visible()
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(EDIT_TOKEN)
            page.locator("#enable-write").check()
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#connection-label")).to_contain_text("V2 Pro")
            page.locator('[data-tab="research"]').click()
            expect(pro_form.locator('[name="automation"]')).to_have_value("queue")
            expect(pro_form.locator('[name="visual_mode"]')).to_have_value("ai-illustration")
            page.locator("#pro-preferences summary").click()
            page.locator("#reset-pro-preferences").click()
            expect(pro_form.locator('[name="automation"]')).to_have_value("review")
            expect(pro_form.locator('[name="visual_mode"]')).to_have_value("")
            assert len(dispatched)==before
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#connect-panel")).to_be_visible()
            # A recognised legacy workspace stays read-only even when writes are requested.
            entries[:] = [e for e in entries if e["path"] not in ("VERSION",".postforge-installation.json")]
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(TOKEN)
            page.locator("#enable-write").check()
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#connection-label")).to_contain_text("V1 Publishing Engine")
            expect(page.locator("#connection-label")).to_contain_text("read only")
            settings()
            expect(page.locator("#upgrade-guide")).to_be_visible()
            page.get_by_role("button",name="Drafts",exact=True).click()
            expect(page.locator("#new")).to_be_disabled()
            settings()
            page.locator("#disconnect").click()
            expect(page.locator("#connect-panel")).to_be_visible()
            entries[:] = [e for e in entries if e["path"] != "scripts/publish.py"]
            page.locator("#repo").fill("owner/private")
            page.locator("#access").fill(TOKEN)
            page.get_by_role("button",name="Connect",exact=True).click()
            expect(page.locator("#notice")).to_contain_text("Incompatible repository")
            expect(page.locator("#workspace")).to_be_hidden()
            browser.close()
            print("Mobile browser smoke test passed (390px; mocked GitHub API)")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

def local_dashboard():
    """Exercise the actual localhost dashboard in an isolated temporary workspace."""
    import sys
    import tempfile
    from http.server import BaseHTTPRequestHandler, HTTPServer
    sys.path.insert(0,str(ROOT))
    from scripts import content_studio, studio_dashboard
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        content_studio.save_draft(root,DRAFT)
        server=HTTPServer(("127.0.0.1",0),BaseHTTPRequestHandler)
        authority="127.0.0.1:"+str(server.server_port)
        server.RequestHandlerClass=studio_dashboard.handler_for(root,"fixture-session",authority)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                chrome=shutil.which("google-chrome") or shutil.which("chromium")
                browser=p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
                page=browser.new_page(viewport={"width":1280,"height":800})
                page.goto("http://"+authority+"/")
                page.locator("#start").fill("2030-01-01")
                expect(page.locator("#calendar-rows")).to_contain_text("Mobile example")
                assert page.locator("[data-page]:visible").count()==1
                page.locator("#calendar-rows").get_by_role("button",name="Review").click()
                expect(page.locator("#review-data")).to_have_text(DRAFT["text"])
                expect(page.locator("#review-technical")).to_be_hidden()
                page.get_by_role("button",name="Edit draft",exact=True).click()
                expect(page.locator("#compose")).to_be_visible()
                expect(page.locator("#drafts")).to_be_hidden()
                expect(page.locator('#draft-form [name="text"]')).to_have_value(DRAFT["text"])
                page.get_by_role("button",name="Back to drafts",exact=False).click()
                page.get_by_role("button",name="Import drafts",exact=True).click()
                expect(page.locator("#import-page")).to_be_visible()
                assert page.locator("[data-page]:visible").count()==1
                page.set_viewport_size({"width":390,"height":844})
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                assert not (root/"queue").exists()
                assert not (root/"state").exists()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    print("Local dashboard browser smoke test passed (desktop and phone; isolated workspace)")

if __name__=="__main__":
    main()
    local_dashboard()
