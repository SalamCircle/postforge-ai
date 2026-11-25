import test from "node:test";
import assert from "node:assert/strict";
import {Client,view,digest,FILE,draftTiming,timingFields,RECOVERY_FILE,sourceImageRequested,proImagePreflight} from "../docs/mobile/api.mjs";
const head="a".repeat(40),tree="b".repeat(40),blob="c".repeat(40),token="github_pat_example_only";
const draft={id:"example",date:"2030-01-02",title:"First post",topic:"AI",text:"Test draft",sources:["https://example.com"]};
function mock({privateRepo=true,branch="main",workflow=true,edition="core",invalid=false,pro=false,delivery=false,automation=false,recovery=false,smartVisual=false,aiVisual=false}={}){
 const calls=[];
 const blobs=new Map();const entries=[];
 const add=(path,content)=>{const sha=(entries.length+100).toString(16).padStart(40,"0");entries.push({path,type:"blob",mode:"100644",sha,size:Buffer.byteLength(content)});blobs.set(sha,content);};
 if(edition!=="other"){add("README.md","# PostForge AI\n");add("scripts/publish.py","# publisher");add(".github/workflows/publish.yml","name: PostForge Publisher\nrun: python3 scripts/publish.py");add("requirements.txt","");}
 if(edition==="core"||edition==="alpha")add("VERSION",invalid?"3.0.0":"2.0.0-alpha.1");
 if(edition==="core"){add(".postforge-installation.json",JSON.stringify({product:"postforge-ai",edition:"v2-core",mobile_protocol:1}));for(const p of ["scripts/content_studio.py","scripts/studio_dashboard.py","scripts/mobile_action.py"])add(p,automation&&p==="scripts/mobile_action.py"?'"delete-many"':"# core");if(workflow)add(".github/workflows/mobile-studio.yml","name: Mobile");}
 if(delivery){add("scripts/publish_reviewed.py","# reviewed");add(".github/workflows/publish-reviewed.yml","name: Publish now");add(".github/workflows/timed-publish.yml","17,47 * * * *");}
 if(pro){add("scripts/pro_assistant.py","# pro");add(".github/workflows/pro-ai.yml",automation?"RESEARCH AND PUBLISH":"name: Pro");}
 if(smartVisual)add("scripts/smart_visual.py","# smart visual");
 if(aiVisual)add("scripts/ai_visual.py","# AI image");
 if(recovery){add("scripts/pro_recovery.py","# journal");add("studio/requests/123.json",JSON.stringify({run_id:"123",status:"failed",mode:"publish",request:{topic:"Cloud",instructions:"Find training",date:"2030-01-02"},message:"AI selected an unknown research source",draft_ids:[]}));}
 add("studio/drafts/example.json",JSON.stringify(draft));add("queue/2030-01-02-example.json",JSON.stringify({date:draft.date,text:"Legacy post"}));entries.push({path:".env",type:"blob",mode:"100644",sha:"d".repeat(40),size:100});
 const fetcher=async (url,opts)=>{
  calls.push([url,opts]);
  const p=new URL(url).pathname;
  assert.equal(new URL(url).origin,"https://api.github.com");
  assert.equal(opts.headers.Authorization,"Bearer "+token);
  assert.equal(opts.cache,"no-store");assert.equal(opts.redirect,"error");
  let value;
  if(p==="/repos/owner/private")value={private:privateRepo};
  else if(p.endsWith("/git/ref/heads/"+branch))value={object:{sha:head}};
  else if(p.endsWith("/git/commits/"+head))value={tree:{sha:tree}};
  else if(p.endsWith("/git/trees/"+tree))value={truncated:false,tree:entries};
  else if(p.includes("/git/blobs/")&&blobs.has(p.split("/").pop()))value={encoding:"base64",content:Buffer.from(blobs.get(p.split("/").pop())).toString("base64")};
  else if(p.endsWith("/dispatches")){const b=JSON.parse(opts.body);assert.equal(b.ref,"main");assert.equal(b.inputs.confirmation,p.includes("/pro-ai.yml/")?({review:"GENERATE DRAFT ONLY",queue:"RESEARCH AND QUEUE",publish:"RESEARCH AND PUBLISH"}[JSON.parse(b.inputs.payload).automation||"review"]):p.includes("/publish-reviewed.yml/")?"PUBLISH NOW":"APPLY REVIEWED ACTION");assert.equal(JSON.parse(b.inputs.payload).head,head);value={workflow_run_id:123};}
  else if(p.endsWith("/actions/runs/123"))value={status:"completed",conclusion:"success"};
  else throw Error("Unexpected endpoint "+p);
  return {ok:true,status:200,json:async()=>value};
 };
 return {calls,fetcher};
}
test("reads only approved files from a pinned private snapshot",async()=>{
 const {calls,fetcher}=mock();const c=new Client("owner/private",token,"main",fetcher);
 const files=await c.snapshot();assert.deepEqual(files["studio/drafts/example.json"],draft);
 assert.equal(Object.keys(files).length,2);assert.equal(c.compatibility.edition,"V2");assert.equal(c.head,head);assert.equal(c.writable,true);
 assert.equal(calls.some(([url])=>url.includes("d".repeat(40))),false);
 assert.equal(FILE.test(".env"),false);assert.equal(FILE.test("studio/drafts/../../.env"),false);
 assert.equal(JSON.stringify(c).includes(token),false);
});
test("public repository and development writes are rejected",async()=>{
 const pub=mock({privateRepo:false});await assert.rejects(new Client("owner/private",token,"main",pub.fetcher).snapshot(),/private/);
 const dev=mock({branch:"v2-core-development"});const c=new Client("owner/private",token,"v2-core-development",dev.fetcher);await c.snapshot();await assert.rejects(c.dispatch({action:"draft"}),/not installed/);
});
test("dispatch binds to reviewed snapshot, does not claim execution",async()=>{
 const m=mock(),c=new Client("owner/private",token,"main",m.fetcher);await c.snapshot();
 const r=await c.dispatch({action:"draft",draft});assert.equal(r.workflow_run_id,123);
 assert.equal((await c.run(123)).conclusion,"success");await assert.rejects(c.dispatch({action:"publish"}),/not installed/);
});
test("calendar and exact draft digest reflect real files",async()=>{
 const h=await digest(draft);
 const files={"studio/drafts/example.json":draft,"studio/approvals/example.json":{digest:h}};
 const r=await view(files,"2030-01-01",30);assert.equal(r.calendar[0].status,"approved");assert.equal(r.drafts[0].digest,h);
 const q="2030-01-02-studio-example.json";files["queue/"+q]={date:draft.date,text:draft.text};assert.equal((await view(files,"2030-01-01",30)).calendar[0].status,"queued");
 files["state/receipt.json"]={queue:q,status:"published",post_id:"example"};assert.equal((await view(files,"2030-01-01",30)).calendar[0].status,"published");
});

test("legacy V1 and V2 Alpha are read only with upgrade guidance",async()=>{
 for(const [edition,label] of [["v1","V1 Publishing Engine"],["alpha","V2 Alpha"]]){
  const m=mock({edition}),c=new Client("owner/private",token,"main",m.fetcher);
  const files=await c.snapshot();assert.equal(c.compatibility.edition,label);assert.equal(c.compatibility.upgrade,true);assert.equal(c.writable,false);
  assert.equal(Object.keys(files).length,1);assert.equal(files["studio/drafts/example.json"],undefined);
  await assert.rejects(c.dispatch({action:"draft"}),/not installed/);
 }
});
test("unrelated repositories, unsupported versions and incomplete Core fail before content reads",async()=>{
 for(const options of [{edition:"other"},{invalid:true},{workflow:false}]){
  const m=mock(options),c=new Client("owner/private",token,"main",m.fetcher);
  await assert.rejects(c.snapshot(),/Incompatible|Unsupported|Incomplete/);assert.equal(c.head,null);assert.equal(c.writable,false);
  assert.equal(m.calls.some(([u,o])=>o.method==="POST"),false);
 }
});

test("full saved posts and receipt-only history are available without LinkedIn reads",async()=>{
 const full="A long published post. ".repeat(20)+"Final sentence.";
 const name="2030-01-02-legacy.json";
 const files={["queue/"+name]:{date:"2030-01-02",text:full},"state/receipt.json":{queue:name,status:"published",post_id:"urn:li:share:123",date:"2030-01-02"},"state/older.json":{queue:"2030-01-03-older.json",status:"published",post_id:"urn:li:ugcPost:456",date:"2030-01-03"}};
 const result=await view(files,"2030-01-01",30);
 assert.equal(result.posts[name].text,full);
 assert.equal(result.posts[name].post_id,"urn:li:share:123");
 assert.equal(result.posts["2030-01-03-older.json"].text,null);
 assert.equal(result.calendar.length,2);
});
test("separate token comparison does not expose stored token",()=>{
 const c=new Client("owner/private",token);
 assert.equal(c.usesToken(token),true);
 assert.equal(c.usesToken("github_pat_separate"),false);
 assert.equal(JSON.stringify(c).includes(token),false);
});
test("draft editor converts London summer and winter time, including UTC day rollover",()=>{
 const now=Date.parse("2026-01-01T00:00:00Z");
 assert.deepEqual(draftTiming("2027-07-01","09:30","Europe/London",now),{date:"2027-07-01",scheduled_at:"2027-07-01T08:30:00+00:00"});
 assert.deepEqual(draftTiming("2027-01-01","09:30","Europe/London",now),{date:"2027-01-01",scheduled_at:"2027-01-01T09:30:00+00:00"});
 assert.deepEqual(draftTiming("2027-07-01","00:15","Europe/London",now),{date:"2027-06-30",scheduled_at:"2027-06-30T23:15:00+00:00"});
 assert.deepEqual(draftTiming("2027-07-01","09:00","Asia/Kolkata",now),{date:"2027-07-01",scheduled_at:"2027-07-01T03:30:00+00:00"});
});
test("draft editor rejects invalid, past and ambiguous times; clearing time restores date-only",()=>{
 const now=Date.parse("2026-01-01T00:00:00Z");
 assert.throws(()=>draftTiming("2027-03-28","01:30","Europe/London",now),/ambiguous/);
 assert.throws(()=>draftTiming("2027-10-31","01:30","Europe/London",now),/ambiguous/);
 assert.throws(()=>draftTiming("2025-01-01","09:00","UTC",now),/future/);
 assert.throws(()=>draftTiming("2027-02-30","09:00","UTC",now),/valid publication date/);
 assert.throws(()=>draftTiming("2027-01-01","09:00","Not/AZone",now),/timezone/);
 assert.deepEqual(draftTiming("2027-07-01",""),{date:"2027-07-01"});
 const saved=draftTiming("2027-07-01","00:15","Europe/London",now), fields=timingFields(saved);
 assert.deepEqual(draftTiming(fields.date,fields.time,fields.timezone,now),saved);
});
test("Pro generation is optional and targets only the private AI draft workflow",async()=>{
 const core=mock(),a=new Client("owner/private",token,"main",core.fetcher);await a.snapshot();await assert.rejects(a.generateDraft({topic:"AWS"}),/Install/);
 const m=mock({pro:true}),c=new Client("owner/private",token,"main",m.fetcher);await c.snapshot();
 assert.equal(c.compatibility.edition,"V2 Pro");assert.equal(c.compatibility.pro,true);
 assert.equal((await c.generateDraft({topic:"AWS",scheduled_at:"2030-01-02T09:10:00+00:00"})).workflow_run_id,123);
 const call=m.calls.find(([url,opts])=>opts.method==="POST");assert.ok(call[0].endsWith("/pro-ai.yml/dispatches"));
});
test("reviewed publication is capability-gated and targets the dedicated workflow",async()=>{
 const old=mock(),a=new Client("owner/private",token,"main",old.fetcher);await a.snapshot();
 await assert.rejects(a.dispatch({action:"publish-now"}),/delivery controls/);
 const m=mock({delivery:true}),c=new Client("owner/private",token,"main",m.fetcher);await c.snapshot();
 assert.equal(c.compatibility.delivery,true);assert.equal(c.compatibility.timedChecks,true);
 await c.dispatch({action:"publish-now",id:"example",digest:await digest(draft),confirmation:"PUBLISH NOW"});
 assert.ok(m.calls.some(([url])=>url.endsWith("/publish-reviewed.yml/dispatches")));
 assert.equal(await c.headChanged(),false);
});
test("missed queue entries outside the calendar window remain visible",async()=>{
 const result=await view({"queue/2000-01-01-old.json":{date:"2000-01-01",text:"Old unclaimed post"}},"2030-01-01",30);
 assert.equal(result.calendar.length,0);assert.equal(result.delivery[0].status,"missed-review");
});

test("automation is opt-in and deletion is capability gated",async()=>{
 const old=mock({pro:true}),a=new Client("owner/private",token,"main",old.fetcher);await a.snapshot();
 await assert.rejects(a.generateDraft({automation:"publish"}),/automation support/);
 await assert.rejects(a.dispatch({action:"delete"}),/deletion support/);
 const m=mock({pro:true,automation:true}),c=new Client("owner/private",token,"main",m.fetcher);await c.snapshot();
 assert.equal(c.compatibility.automation,true);assert.equal(c.compatibility.deletion,true);
 await c.generateDraft({topic:"test",automation:"queue",add_visual:true});
 await c.generateDraft({topic:"test",automation:"publish"});
 await c.dispatch({action:"delete",id:"example",digest:await digest(draft),confirmation:"DELETE DRAFTS"});
 assert.equal(m.calls.filter(([u,o])=>o.method==="POST").length,3);
});

test("private recovery journal is capability-gated and tied to its run ID",async()=>{
 const m=mock({pro:true,recovery:true}),c=new Client("owner/private",token,"main",m.fetcher);
 const files=await c.snapshot();assert.equal(c.compatibility.recovery,true);
 const result=await view(files,"2030-01-01",30);
 assert.equal(result.recovery.length,1);assert.equal(result.recovery[0].run_id,"123");
 assert.equal(result.recovery[0].status,"failed");assert.equal(result.recovery[0].request.topic,"Cloud");
 assert.equal(RECOVERY_FILE.test("studio/requests/../.env"),false);
 files["studio/requests/124.json"]={...result.recovery[0],run_id:"123"};
 assert.equal((await view(files,"2030-01-01",30)).recovery.length,1);
 const old=mock({pro:true}),legacy=new Client("owner/private",token,"main",old.fetcher);
 await legacy.snapshot();assert.equal(legacy.compatibility.recovery,false);
});

test("source-image automation conflicts fail before sending any GitHub request",async()=>{
 const m=mock({pro:true,automation:true}),c=new Client("owner/private",token,"main",m.fetcher);
 await c.snapshot();const before=m.calls.length;
 for(const automation of ["queue","publish"]){
  for(const item of [{find_images:true,instructions:"Find training"},{instructions:"Include the official image"},{instructions:"Use a real image"},{instructions:"Include an actual image"},{instructions:"Use the source image"}]){
   assert.equal(sourceImageRequested(item),true);
   await assert.rejects(c.generateDraft({...item,automation}),/Real source images need approval/);
   assert.throws(()=>proImagePreflight({automation,requests:[{instructions:"Cloud training"},item]}),/Real source images need approval/);
   assert.doesNotThrow(()=>proImagePreflight({...item,automation:"review"}));
  }
  assert.doesNotThrow(()=>proImagePreflight({automation,instructions:"Add visual",add_visual:true}));
 }
 assert.equal(m.calls.length,before);
 await c.generateDraft({automation:"publish",instructions:"Add visual",add_visual:true});
 assert.equal(m.calls.length,before+1);
});

test("smart visual capable clients accept automatic source-image requests without another approval",async()=>{
 const m=mock({pro:true,automation:true,smartVisual:true}),c=new Client("owner/private",token,"main",m.fetcher);
 await c.snapshot();assert.equal(c.compatibility.smartVisual,true);
 const before=m.calls.length;
 for(const visual_mode of ["smart","original","source-only","text"]){
  await c.generateDraft({automation:"publish",instructions:"Include an actual image",visual_mode});
 }
 assert.equal(m.calls.length,before+4);
 await c.generateDraft({automation:"queue",find_images:true,instructions:"Include an official image"});
 assert.equal(m.calls.length,before+5);
 assert.throws(()=>proImagePreflight({automation:"publish",visual_mode:"unknown"},true),/Smart Auto Visual/);
 assert.throws(()=>proImagePreflight({automation:"publish",visual_mode:"smart"}),/Smart Auto Visual/);
});

test("optional AI image styles are capability gated and queue metadata is preserved",async()=>{
 const old=mock({pro:true,automation:true,smartVisual:true}),a=new Client("owner/private",token,"main",old.fetcher);await a.snapshot();
 await assert.rejects(a.generateDraft({automation:"publish",visual_mode:"ai-photo"}),/Smart Auto Visual/);
 const m=mock({pro:true,automation:true,smartVisual:true,aiVisual:true}),c=new Client("owner/private",token,"main",m.fetcher);await c.snapshot();
 assert.equal(c.compatibility.aiVisual,true);
 for(const visual_mode of ["ai-photo","ai-illustration","ai-poster"])await c.generateDraft({automation:"publish",visual_mode});
 const d={id:"ai-visual-test",date:"2030-01-01",title:"Cloud",topic:"Cloud",text:"AI-generated conceptual illustration (not an official image).",sources:["https://example.com"],ai_image:{sha256:"a".repeat(64),model:"@cf/black-forest-labs/flux-1-schnell"}};
 const r=await view({"studio/drafts/ai-visual-test.json":d,"queue/2030-01-01-studio-ai-visual-test.json":{date:d.date,text:d.text,ai_image:d.ai_image}},"2030-01-01",30);
 assert.equal(r.drafts[0].status,"queued");
});