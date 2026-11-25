import {Client,view,draftTiming,timingFields,sourceImageRequested,proImagePreflight} from "./api.mjs";
import {seal,unseal,sealEditing,unsealEditing,editDeadline,remainingEdit} from "./vault.mjs";
"use strict";
if(window.top!==window.self){document.body.replaceChildren(document.createTextNode("Open the mobile studio directly in your browser."));throw Error("Embedded use is disabled");}
const $=id=>document.getElementById(id);
let client=null, readClient=null, writeEnabled=false, pending=null, repoName="", editUntil=0, editTimer=null;
const VAULT="postforge.mobile.vault.v1",EDIT_VAULT="postforge.mobile.edit-vault.v1";
let data=null, selected=null, editing=null, busy=false;
const lines=s=>s.split("\n").map(v=>v.trim()).filter(Boolean);
const json=o=>JSON.stringify(o,null,2);
let actionTimer=null,pendingMeta=null;
const actionNames={delete:"Delete draft","delete-many":"Delete selected drafts","publish-now":"Publish now",reschedule:"Reschedule queued post",approve:"Approve draft",export:"Queue approved draft",draft:"Save draft",revise:"Save changes",import:"Import drafts",schedule:"Change publication time",brand:"Save brand memory",archive:"Archive draft",cancel:"Cancel queue entry","stage-image":"Attach source image","pro-generate":"Research and generate draft"};
function confirmAction(title,message,label="Confirm"){
 const d=$("action-dialog");if(d.open)return Promise.resolve(false);
 $("confirm-title").textContent=title;$("confirm-text").textContent=message;$("confirm-accept").textContent=label;
 d.returnValue="cancel";return new Promise(resolve=>{d.addEventListener("close",()=>resolve(d.returnValue==="confirm"),{once:true});d.showModal();});
}
function actionStatus(kind,title,detail){
 const panel=$("action-panel");panel.hidden=false;panel.dataset.state=kind;
 $("action-title").textContent=title;$("action-detail").textContent=detail;
 $("check-run").hidden=!pending;$("recover-run").hidden=pending!=="unknown";
 $("dismiss-action").hidden=Boolean(pending);$("action-history").hidden=!pendingMeta;
 if(pendingMeta)$("action-history").href="https://github.com/"+repoName.split("/").map(encodeURIComponent).join("/")+"/actions/"+(pending&&pending!=="unknown"?"runs/"+pending:pendingMeta.runId?"runs/"+pendingMeta.runId:"workflows/"+pendingMeta.workflow);
 if(pending!=="unknown"){$("recovery-list").hidden=true;$("recovery-list").replaceChildren();}
}
function stopActionPoll(){clearTimeout(actionTimer);actionTimer=null;}
function pollAction(){stopActionPoll();if(pending&&pending!=="unknown"&&client&&!document.hidden)actionTimer=setTimeout(()=>{if(busy){pollAction();return;}void checkAction();},5000);}
document.addEventListener("visibilitychange",()=>{if(document.hidden)stopActionPoll();else pollAction();});
$("dismiss-action").addEventListener("click",()=>{$("action-panel").hidden=true;});
function confirmText(action){
 return ({delete:"Remove this draft and its approval from the current workspace. Git history and shared image assets remain. No LinkedIn post is deleted.","delete-many":"Remove all selected drafts and approvals from the current workspace. Git history and shared image assets remain.","publish-now":"Send this exact approved queued post to LinkedIn now, overriding its scheduled time. This is a live public publication. No automatic retry.",reschedule:"Remove the old unclaimed queue entry and save the new requested time. You must review, approve and queue it again.","pro-generate":"Your request and any selected brand or follow-up content will be shared with the configured AI and research providers. Results are saved as drafts only.",approve:"Approve the exact reviewed text, schedule and attachments. This does not queue or publish the post.",export:"Queue this approved version for the existing publisher. It may publish when eligible. Check the requested date and time before continuing.",archive:"Archive this draft. No LinkedIn post will be deleted.",cancel:"Remove this future queue entry. This does not delete a published post.","stage-image":"Confirm you have permission to reuse this source image. The changed draft will need fresh approval.",schedule:"Save the requested date and time. Any earlier approval will be invalidated.",revise:"Save the revised content. Any earlier approval will be invalidated."})[action]||"Save this reviewed change to your private workspace. This does not directly publish anything.";
}
function note(message,error=false){$("notice").textContent=message;$("notice").className=error?"error":"";}
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
async function api(path){if(!client)throw Error("Connect a workspace first");const q=new URL(path,"https://example.invalid").searchParams;return view(await client.snapshot(),q.get("start")||undefined,Number(q.get("days")||30));}
const routeParent={compose:"drafts","import-page":"settings",brand:"settings",history:"settings","brief-page":"settings",health:"settings",delivery:"calendar",manage:"drafts"};
function tab(id){if(!data&&client&&$("connect-panel").hidden)id="settings";const pages=[...document.querySelectorAll("[data-page]")];if(!pages.some(p=>p.id===id))return;for(const p of pages)p.hidden=p.id!==id;for(const b of document.querySelectorAll("[data-tab]")){const active=b.dataset.tab===(routeParent[id]||id);b.classList.toggle("active",active);if(active)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");}window.scrollTo(0,0);}
function showApprovalList(){selected=null;clearImagePreview();$("review").hidden=true;$("approval-list").hidden=false;$("approval-empty").hidden=false;window.scrollTo(0,0);}
function paginate(list,limit=8){const rows=[...list.children];if(rows.length<=limit)return;let shown=limit;for(const row of rows.slice(limit))row.hidden=true;const more=node("button","Show more","secondary show-more");more.type="button";more.addEventListener("click",()=>{for(const row of rows.slice(shown,shown+limit))row.hidden=false;shown+=limit;if(shown>=rows.length)more.remove();else more.textContent="Show more ("+(rows.length-shown)+" remaining)";});list.append(more);}

async function load(){const q=new URLSearchParams({days:$("days").value});if($("start").value)q.set("start",$("start").value);try{data=await api("/api/model?"+q);render();connectionStatus();if($("connect-panel").hidden)$("workspace").hidden=false;}catch(e){data=null;if(client&&$("connect-panel").hidden){$("workspace").hidden=false;$("connection-label").textContent="Workspace unavailable — refresh or reconnect";$("connection").hidden=false;tab("settings");}else $("workspace").hidden=true;throw e;}}
// A refresh is read-only; never reuse consent against a different snapshot.
async function freshForAction(active,head){
 if(busy||pending||client!==active||!canWrite()||client.head!==head){note("Workspace or editing access changed. Review the current draft again.",true);return false;}
 busy=true;
 try{
  const changed=await active.headChanged();
  if(client!==active||!canWrite()||pending||active.head!==head){note("Workspace or editing access changed. Review the current draft again.",true);return false;}
  if(!changed)return true;
  await load();fillBrand();
  note("Workspace updated automatically. Nothing was submitted. Review the latest information and confirm your action again.",true);
  return false;
 }catch(e){note("Could not verify the latest workspace. Nothing was submitted. Refresh or reconnect before trying again. "+e.message,true);return false;}
 finally{busy=false;}
}
async function run(body,message){
 if(busy||!client||!data)return;
 if(body.action==="reuse"){const r=data.drafts.find(d=>d.draft.id===body.id);return r?.status==="published"?{original:r.draft,instruction:"Create a substantially updated draft with new evidence and a new identifier."}:null;}
 if(!canWrite()){note("Read-only mode. Enable editing to make changes.",true);return;}
 if(pending){actionStatus("pending","Another action is awaiting confirmation","Check its status below before sending a new request.");$("action-panel").scrollIntoView({block:"nearest"});return;}
 const label=actionNames[body.action]||"Save reviewed change",active=client,head=client.head;
 const mode=body.action==="pro-generate"?(body.request.automation||"review"):"review";
 if(body.action==="pro-generate"){try{proImagePreflight(body.request,client?.compatibility?.smartVisual,client?.compatibility?.aiVisual);}catch(e){$("pro-image-warning").textContent=e.message;$("pro-image-warning").hidden=false;tab("research");$("pro-image-warning").scrollIntoView({block:"center"});return;}const items=body.request.requests||[body.request];if(mode==="publish"&&(items.length!==1||items[0].scheduled_at||items[0].date!==new Date().toISOString().slice(0,10))){note("Publish immediately requires one request for today with no scheduled time.",true);return;}if(mode==="queue"&&items.some(i=>!i.scheduled_at||Date.parse(i.scheduled_at)<=Date.now())){note("Automatic queueing requires a future publication time for each post.",true);return;}}
 const shared="Your request and selected brand or follow-up content will be sent to the configured AI and research providers. ";
 let consent=mode==="queue"?"Research, generate and automatically queue the resulting content without reviewing it first. It may publish publicly at the requested time. Only continue if you trust the sources and accept the risk of AI errors. "+shared:mode==="publish"?"Research and publish the generated content publicly to LinkedIn as soon as possible, without another review. This overrides scheduling. Only continue if you accept the risk of AI errors. "+shared:confirmText(body.action);
 if(body.action==="pro-generate"&&client?.compatibility?.smartVisual)consent+=" Smart Auto Visual may use a previously authorised image or an original graphic. Source-only requests are held if no authorised image is available.";
 if(body.action==="pro-generate"&&(body.request.requests||[body.request]).some(i=>["ai-photo","ai-illustration","ai-poster"].includes(i.visual_mode)))consent+=" Optional AI artwork shares the topic and generated title with the configured image provider; an original local graphic is used if unavailable.";
 if(!await freshForAction(active,head))return;
 if(!await confirmAction(label,consent,body.action==="approve"?"Approve":body.action==="export"?"Queue post":body.action==="publish-now"||mode==="publish"?"Publish to LinkedIn":mode==="queue"?"Research and queue":body.action.startsWith("delete")?"Delete":"Confirm"))return;
 if(!await freshForAction(active,head))return;
 if(!canWrite()||client!==active||client.head!==head||busy||pending){note("Workspace or editing access changed. Review the current draft again.",true);return;}
 const isPro=body.action==="pro-generate",workflow=isPro?"pro-ai.yml":body.action==="publish-now"?"publish-reviewed.yml":"mobile-studio.yml";
 pendingMeta={workflow,mode,items:body.items,action:body.action,id:body.id||body.draft?.id||null,digest:body.digest||null,priorIds:isPro?new Set(data.drafts.map(r=>r.draft.id)):null,repo:repoName,started:Date.now(),label,message};
 busy=true;pending="unknown";actionStatus("pending",isPro?"Researching your topic":"Submitting reviewed action","Sending a single request to your private workspace. No automatic resubmission.");
 try{
  $("runs-link").href="https://github.com/"+repoName.split("/").map(encodeURIComponent).join("/")+"/actions/workflows/"+workflow;
  const result=await(isPro?client.generateDraft(body.request):client.dispatch(body));
  const id=String(result?.workflow_run_id||"");pending=/^[1-9][0-9]*$/.test(id)?id:"unknown";
  actionStatus("pending",pending==="unknown"?"Request awaiting confirmation":isPro?"AI generation in progress":"Action in progress",pending==="unknown"?"GitHub did not return a run ID. Find the previous action below; do not submit it again.":"Action submitted, not yet saved. Status updates automatically while this app is open.");
  note("Action submitted, not yet saved.");
 }catch(e){
  if([400,401,403,404,422,429].includes(e.httpStatus)){pending=null;actionStatus("error","Request rejected",e.message+" No automatic retry. Check access or configuration before trying again.");}
  else actionStatus("warning","Submission outcome uncertain","The request may have reached GitHub. Find the previous action before submitting another.");
  note(e.message,true);
 }finally{busy=false;pollAction();}
}
function canWrite(){return Boolean(data&&client?.writable&&writeEnabled&&Date.now()<editUntil);}
function tickEdit(){clearTimeout(editTimer);if(!writeEnabled)return;const remaining=remainingEdit(editUntil);if(!remaining){void endEditing();return;}editTimer=setTimeout(tickEdit,Math.min(remaining,60000));}
function startEditClock(deadline){editUntil=deadline;tickEdit();}
document.addEventListener("visibilitychange",()=>{if(!document.hidden)tickEdit();});
window.addEventListener("pageshow",tickEdit);
function clearEditForm(){for(const id of ["edit-access","edit-pass","edit-repeat","saved-edit-pass"])$(id).value="";$("edit-session").hidden=true;$("saved-edit-form").hidden=true;}
function savedEditingExists(){try{return Boolean(localStorage.getItem(EDIT_VAULT));}catch{return false;}}
async function endEditing(){if(busy){clearTimeout(editTimer);editTimer=setTimeout(endEditing,500);return;}clearTimeout(editTimer);editUntil=0;writeEnabled=false;clearEditForm();if(!readClient){client=null;data=null;location.reload();return;}client=readClient;editing=null;connectionStatus();busy=true;try{await load();fillBrand();note(pending?"Editing ended. Inspect workflow history to reconcile the last submitted action.":"Editing ended. Read-only connection restored.");}catch(e){note(e.message,true);}finally{busy=false;}}
$("enable-edit").addEventListener("click",()=>{if(!busy&&client?.writable&&!canWrite()){$("edit-session").hidden=false;$("saved-edit-form").hidden=!savedEditingExists();}});
$("cancel-edit").addEventListener("click",clearEditForm);
$("lock-edit").addEventListener("click",endEditing);
$("remember-edit").addEventListener("change",()=>{const on=$("remember-edit").checked;$("edit-vault-fields").hidden=!on;for(const id of ["edit-pass","edit-repeat"])$(id).required=on;});
async function activateEditing(token,deadline){
 if(!remainingEdit(deadline))throw Error("Editing authorization expired.");
 if(!readClient||readClient.usesToken(token))throw Error("Use a separate editing token, not the read-only token.");
 const next=new Client(repoName,token,"main");const files=await next.snapshot();if(!next.writable)throw Error("Editing requires installed V2 on main.");
 const fresh=await view(files,$("start").value||undefined,Number($("days").value));
 if(!remainingEdit(deadline))throw Error("Editing authorization expired.");
 client=next;data=fresh;writeEnabled=true;startEditClock(deadline);editing=null;clearEditForm();render();connectionStatus();fillBrand();note("Editing enabled until "+new Date(deadline).toLocaleString()+". GitHub checks permission on dispatch.");
}
$("edit-session").addEventListener("submit",async e=>{e.preventDefault();if(busy||!readClient||!client?.writable||canWrite())return;const token=$("edit-access").value.trim(),minutes=Number($("edit-duration").value),remember=$("remember-edit").checked,password=$("edit-pass").value,repeat=$("edit-repeat").value;for(const id of ["edit-access","edit-pass","edit-repeat"])$(id).value="";busy=true;try{const createdAt=Date.now(),expiresAt=editDeadline(minutes,createdAt);if(remember&&(password!==repeat||password.length<12))throw Error("Use a matching strong passphrase of at least 12 characters.");let encrypted=null;if(remember)encrypted=await sealEditing({repo:repoName,token,branch:"main",createdAt,expiresAt,minutes},password);await activateEditing(token,expiresAt);if(encrypted){try{localStorage.setItem(EDIT_VAULT,encrypted);note("Editing enabled. Encrypted authorization saved until "+new Date(expiresAt).toLocaleString()+".");}catch{note("Editing enabled, but authorization could not be saved.",true);}}}catch(err){note(err.message,true);}finally{busy=false;}});
$("saved-edit-form").addEventListener("submit",async e=>{e.preventDefault();if(busy||!readClient||!client?.writable||canWrite())return;const password=$("saved-edit-pass").value;$("saved-edit-pass").value="";busy=true;try{const saved=await unsealEditing(localStorage.getItem(EDIT_VAULT),password,repoName);await activateEditing(saved.token,saved.expiresAt);}catch(err){note(err.message,true);}finally{busy=false;}});
$("forget-edit").addEventListener("click",async()=>{if(await confirmAction("Forget editing authorization","Remove the saved editing authorization from this device. Revoke its GitHub token if needed.","Forget")){try{localStorage.removeItem(EDIT_VAULT);$("saved-edit-form").hidden=true;note("Saved editing authorization removed. Revoke its GitHub token if needed.");}catch{note("Unable to clear saved editing authorization.",true);}}});
function connectionStatus(){const c=client.compatibility;if(!c)return;renderRecovery();$("edition-title").textContent=c.pro?"PostForge AI V2 Pro":"PostForge AI V2";$("connection-label").textContent=repoName+" · "+c.branch+" · "+c.edition+" ("+c.version+") · "+(canWrite()?"reviewed actions enabled (permission checked on dispatch)":"read only");$("upgrade-guide").hidden=!c.upgrade;$("pro-panel").hidden=!c.pro;$("automation-options").hidden=!c.automation;$("smart-visual-option").hidden=!c.smartVisual;$("ai-visual-help").hidden=!c.aiVisual;for(const option of document.querySelectorAll("[data-ai-visual]")){option.hidden=!c.aiVisual;option.disabled=!c.aiVisual;}$("visual-option").hidden=!c.automation||c.smartVisual;$("source-image-option").hidden=!!c.smartVisual;drawProPlan();$("access-explanation").textContent=c.upgrade?"Publishing history only. Upgrade to compatible V2 to manage drafts and approvals.":canWrite()?"Reviewed changes are submitted to GitHub; actual token write permission is checked by GitHub.":"Viewing only. Enable temporary editing on compatible V2 main with a separate Actions write token.";for(const id of ["new","draft-form","import-form","brand-form","pro-form"]){const e=$(id);for(const control of (e.tagName==="FORM"?e.querySelectorAll("input,textarea,button,select"):[e]))control.disabled=!canWrite();}$("enable-edit").hidden=!client.writable||canWrite()||!readClient;$("lock-edit").hidden=!canWrite();$("editing-expiry").hidden=!canWrite();$("editing-expiry").textContent=canWrite()?"Editing ends: "+new Date(editUntil).toLocaleString():"";if(selected&&data)review(selected,false);}
function statusLabel(status){return ({draft:"Awaiting review",approved:"Approved",queued:"Queued",published:"Published",archived:"Archived","review-claim":"Needs reconciliation","missed-review":"Missed schedule","queue-conflict":"Queue conflict"})[status]||status;}
function scheduleLabel(d){if(d.scheduled_at&&Number.isFinite(Date.parse(d.scheduled_at))){return new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(d.scheduled_at))+" (device time) · "+d.scheduled_at.slice(0,16).replace("T"," ")+" UTC";}return d.date+" · Daily schedule";}
function renderApproval(){const list=$("approval-list");list.replaceChildren();const rows=data.drafts.filter(r=>["draft","approved"].includes(r.status));$("approval-count").textContent=String(rows.filter(r=>r.status==="draft").length);$("approval-count").dataset.empty=String(!rows.some(r=>r.status==="draft"));for(const r of rows){const b=node("button",undefined,"approval-item");b.type="button";b.append(node("span",r.draft.title,"approval-item-title"),node("span",statusLabel(r.status)+" · "+scheduleLabel(r.draft),"muted"));b.addEventListener("click",()=>review(r.draft.id));list.append(b);}if(!rows.length)list.append(node("p","All caught up. New manual and AI drafts will appear here.","muted"));paginate(list);}
function deliveryLabel(r){if(r.status==="published")return "Published · receipt recorded";if(r.status==="review-claim")return "Publication uncertain · reconcile before retrying";if(r.status==="missed-review")return "Delivery window missed · review or reschedule";if(r.status!=="queued")return statusLabel(r.status);if(r.scheduled_at&&Date.parse(r.scheduled_at)<=Date.now())return "Overdue · awaiting publisher check";return "Queued · not yet published";}
function renderDelivery(){const el=$("delivery-info");el.replaceChildren();const rows=data.delivery||[];if(client?.compatibility?.timedChecks){const next=new Date();next.setUTCSeconds(0,0);do{next.setUTCMinutes(next.getUTCMinutes()+1);}while(![17,47].includes(next.getUTCMinutes()));el.append(node("p","Next configured timed check: "+next.toLocaleString()+" (if enabled; GitHub may delay runs).","muted"));}for(const r of rows){const b=node("button",r.title+" · "+deliveryLabel(r),"approval-item");b.type="button";b.addEventListener("click",()=>data.drafts.some(d=>d.draft.id===r.id)?review(r.id):openPost(r.id));el.append(b);}if(!rows.length)el.append(node("p","No queued or overdue posts in this workspace.","muted"));paginate(el);}
function renderDelete(){const section=$("bulk-delete"),list=$("delete-list");section.hidden=!client?.compatibility?.deletion;$("manage-unavailable").hidden=!!client?.compatibility?.deletion;list.replaceChildren();for(const r of data.drafts.filter(r=>["draft","approved","archived"].includes(r.status))){const label=node("label",undefined,"delete-row"),input=document.createElement("input");input.type="checkbox";input.value=r.draft.id;input.disabled=!canWrite();label.append(input,node("span",r.draft.title));list.append(label);} $("delete-selected").disabled=!canWrite();}
$("delete-selected").addEventListener("click",()=>{const items=[...$("delete-list").querySelectorAll("input:checked")].map(e=>data.drafts.find(r=>r.draft.id===e.value)).filter(Boolean).map(r=>({id:r.draft.id,digest:r.digest}));if(!items.length){note("Select at least one draft.",true);return;}void run({action:"delete-many",items,confirmation:"DELETE DRAFTS"},"Drafts removed");});
function render(){renderRecovery();renderApproval();renderDelete();renderDelivery();const r=data.calendar;$("metrics").replaceChildren();for(const [label,count] of [["Planned",r.length],["Awaiting review",r.filter(x=>x.status==="draft").length],["Published",r.filter(x=>x.status==="published").length]]){const box=node("div",undefined,"metric");box.append(node("small",label),node("strong",count));$("metrics").append(box);}calendar();$("draft-list").replaceChildren();for(const item of data.drafts){const line=node("div",undefined,"row"), info=node("div",undefined,"rowbody"), button=node("button","Review","secondary");info.append(node("strong",item.draft.title),node("small",item.draft.date+(item.draft.scheduled_at?" · "+item.draft.scheduled_at.slice(11,16)+" UTC":"")+" · "+item.status));button.addEventListener("click",()=>review(item.draft.id));line.append(info,button);$("draft-list").append(line);}if(!data.drafts.length)$("draft-list").append(node("p","No drafts yet. Create one or import an AI plan."));$("brief").textContent=json(data.brief);$("health-data").textContent=json(data.health);const health=$("health-summary");health.replaceChildren();for(const [label,count] of [["Published receipts",data.health.published_receipts],["Unresolved claims",data.health.unresolved_claims],["Overdue queue",data.health.overdue_queue_files.length]]){const card=node("div",undefined,"metric");card.append(node("small",label),node("strong",String(count)));health.append(card);}paginate($("draft-list"));if(selected)review(selected,false);}
let weekOffset=0,calendarDay="",calendarWindow="";
function renderWeek(){
 const start=$("start").value||new Date().toISOString().slice(0,10),days=Number($("days").value),key=start+"/"+days;
 if(key!==calendarWindow){calendarWindow=key;weekOffset=0;calendarDay="";}
 const dateAt=i=>new Date(Date.parse(start+"T00:00:00Z")+i*86400000);
 const fmt=new Intl.DateTimeFormat(undefined,{month:"short",day:"numeric",timeZone:"UTC"});
 const weekday=new Intl.DateTimeFormat(undefined,{weekday:"short",timeZone:"UTC"});
 $("week-label").textContent=fmt.format(dateAt(weekOffset))+" – "+fmt.format(dateAt(Math.min(days-1,weekOffset+6)))+" (UTC)";
 $("week-prev").disabled=weekOffset===0;$("week-next").disabled=weekOffset+7>=days;
 $("week-all").setAttribute("aria-pressed",String(!calendarDay));$("week-filter").textContent=calendarDay?"Showing "+calendarDay:"Showing all dates in window";
 const list=$("week-days");list.replaceChildren();
 for(let i=weekOffset;i<Math.min(days,weekOffset+7);i++){
  const date=dateAt(i),day=date.toISOString().slice(0,10),count=data.calendar.filter(r=>r.date===day).length;
  const b=node("button",undefined,"calendar-day");b.type="button";b.dataset.date=day;b.setAttribute("aria-pressed",String(calendarDay===day));b.setAttribute("aria-label",day+", "+count+" posts");b.append(node("small",weekday.format(date)),node("strong",String(date.getUTCDate())),node("small",count?String(count)+" post"+(count===1?"":"s"):"—"));b.addEventListener("click",()=>{calendarDay=calendarDay===day?"":day;calendar();});list.append(b);
 }
}
$("week-prev").addEventListener("click",()=>{weekOffset=Math.max(0,weekOffset-7);calendarDay="";calendar();});
$("week-next").addEventListener("click",()=>{weekOffset+=7;calendarDay="";calendar();});
$("week-all").addEventListener("click",()=>{calendarDay="";calendar();});
function calendar(){if(!data)return;renderWeek();const rows=$("calendar-rows");rows.replaceChildren();const filter=$("filter").value,q=$("search").value.toLowerCase();for(const item of data.calendar.filter(x=>(!calendarDay||x.date===calendarDay)&&(!filter||x.status===filter)&&[x.title,x.topic,x.series].join(" ").toLowerCase().includes(q))){const row=node("div",undefined,"row"), info=node("div",undefined,"rowbody");const title=node("button",item.title,"post-title-button");title.type="button";title.addEventListener("click",()=>openPost(item.id));info.append(title,node("small",[item.topic,item.series,item.scheduled_at].filter(Boolean).join(" · ")),node("span",deliveryLabel(item),"status "+item.status));row.append(node("div",item.date.slice(5),"date"),info);if(data.drafts.some(d=>d.draft.id===item.id)){const b=node("button","Review","secondary");b.addEventListener("click",()=>review(item.id));row.append(b);}rows.append(row);}if(!rows.children.length)rows.append(node("p","No content matches this view."));paginate(rows);}
let openPostId=null;
function openPost(id){const post=data?.posts?.[id];if(!post)return;openPostId=id;$("post-title").textContent=post.title;$("post-meta").textContent=post.date+" · "+post.status+" · "+post.source;$("post-text").textContent=post.text===null?"Full text is not retained in this repository. Use the LinkedIn link if available.":post.text;$("post-visual").textContent=post.visual?["Visual: "+(post.visual.title||""),...(Array.isArray(post.visual.points)?post.visual.points:[])].join(" • "):"";$("copy-post").disabled=post.text===null;$("post-copy-status").textContent="";const link=$("linkedin-post");link.hidden=!(typeof post.post_id==="string"&&/^urn:li:(?:share|ugcPost|activity):[0-9]+$/.test(post.post_id));link.removeAttribute("href");if(!link.hidden)link.href="https://www.linkedin.com/feed/update/"+encodeURIComponent(post.post_id)+"/";if(!$("post-dialog").open)$("post-dialog").showModal();}
$("close-post").addEventListener("click",()=>$("post-dialog").close());
$("post-dialog").addEventListener("close",()=>{openPostId=null;$("post-text").textContent="";$("post-visual").textContent="";$("linkedin-post").removeAttribute("href");});
$("copy-post").addEventListener("click",async()=>{const post=data?.posts?.[openPostId];if(typeof post?.text!=="string")return;try{await navigator.clipboard.writeText(post.text);$("post-copy-status").textContent="Full post copied.";}catch{$("post-copy-status").textContent="Select and copy the text manually.";}});
function review(id,switchTab=true){const r=data.drafts.find(d=>d.draft.id===id);if(!r){selected=null;clearImagePreview();$("review").hidden=true;$("approval-list").hidden=false;$("approval-empty").hidden=false;return;}selected=id;if(switchTab)tab("approval");$("review").hidden=false;$("approval-list").hidden=true;$("approval-empty").hidden=true;$("review-title").textContent=r.draft.title;$("review-status").textContent=deliveryLabel({...r.draft,status:r.status});$("review-status").dataset.status=r.status;$("review-meta").textContent=scheduleLabel(r.draft)+" · "+r.draft.topic+(r.draft.series?" · "+r.draft.series:"");$("review-data").textContent=r.draft.text;$("review-visual").textContent=r.draft.visual?["Generated visual: "+r.draft.visual.title,...(r.draft.visual.points||[])].join(" • "):"";$("review-warning").textContent=r.same_topic?.length?"Similar topics exist in your workspace. Check for repeated content before approval.":"";const sources=$("review-sources");sources.replaceChildren();for(const value of r.draft.sources||[]){try{const url=new URL(value);if(url.protocol!=="https:"||url.username||url.password)continue;const link=node("a",url.hostname+" · "+url.pathname);link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";sources.append(link);}catch{}}if(sources.children.length)sources.prepend(node("h4","Research sources"));const actions=$("review-actions");actions.replaceChildren();showImageCandidates(r);if(client?.compatibility?.pro&&["draft","approved","published"].includes(r.status)){const follow=node("button","Ask AI for follow-up","secondary");follow.disabled=!canWrite();follow.addEventListener("click",()=>{const f=$("pro-form");f.elements.reference_id.value=r.draft.id;f.elements.topic.value=r.draft.topic;f.elements.instructions.value="Create a distinct follow-up with new verified information.";tab("research");});actions.append(follow);}function button(label,action,confirmation){const b=node("button",label,["approve","export","publish-now"].includes(action)?"":"secondary");b.disabled=action!=="reuse"&&(!canWrite()||Boolean(pending));b.addEventListener("click",async()=>{const result=await run({action,id,digest:r.digest,confirmation},action==="export"?"Queued after workflow success.":"Workspace updated.");if(action==="reuse"&&result){$("brief").textContent=json(result);tab("brief-page");}});actions.append(b);}
if(["draft","approved"].includes(r.status)){const edit=node("button","Edit draft","secondary");edit.disabled=!canWrite();edit.addEventListener("click",()=>{tab("compose");editDraft(r);});actions.append(edit);if(r.status==="draft")button("Approve exact draft","approve","APPROVE");button("Archive","archive","ARCHIVE");}if(client?.compatibility?.deletion&&["draft","approved","archived"].includes(r.status))button("Delete draft","delete","DELETE DRAFTS");if(r.status==="approved")button("Queue approved draft","export","QUEUE");if(r.status==="queued"&&r.draft.date>new Date().toISOString().slice(0,10))button("Cancel future queue entry","cancel","CANCEL");if(client?.compatibility?.delivery&&["queued","missed-review"].includes(r.status)){button("Publish now","publish-now","PUBLISH NOW");}if(r.status==="published"){const post=data.posts[id];if(typeof post?.post_id==="string"&&/^urn:li:(?:share|ugcPost|activity):[0-9]+$/.test(post.post_id)){const link=node("a","View published post on LinkedIn");link.href="https://www.linkedin.com/feed/update/"+encodeURIComponent(post.post_id)+"/";link.target="_blank";link.rel="noopener noreferrer";actions.append(link);}button("Create reuse brief","reuse","REUSE");}$("schedule").disabled=!canWrite()||!(["draft","approved"].includes(r.status)||(client?.compatibility?.delivery&&["queued","missed-review"].includes(r.status)));$("schedule").textContent=["queued","missed-review"].includes(r.status)?"Remove from queue and reschedule":"Set requested time";}
let imageObjectUrl=null;
function clearImagePreview(){if(imageObjectUrl){URL.revokeObjectURL(imageObjectUrl);imageObjectUrl=null;}const panel=$("image-candidates");panel.replaceChildren();panel.hidden=true;}
function showImageCandidates(r){
 clearImagePreview();const draft=r.draft,panel=$("image-candidates");
 if(!client?.compatibility?.pro)return;
 if((draft.approved_image&&client.compatibility.sourceImages)||(draft.ai_image&&client.compatibility.aiVisual)){const meta=draft.ai_image||draft.approved_image,button=node("button","Load exact saved image","secondary");panel.append(node("p",draft.ai_image?"AI-generated conceptual illustration. Review these exact saved bytes.":"Saved source image (permission confirmed). Review these exact bytes before approving."),button);panel.hidden=false;
 button.addEventListener("click",async()=>{const active=client,head=client.head;try{button.disabled=true;const blob=await active.reviewedImage(meta.sha256);if(client!==active||client.head!==head||selected!==draft.id||!panel.contains(button))return;if(imageObjectUrl)URL.revokeObjectURL(imageObjectUrl);imageObjectUrl=URL.createObjectURL(blob);const img=document.createElement("img");img.className="reviewed-source-image";img.alt=draft.ai_image?"Exact saved AI-generated illustration":"Exact saved source image";img.src=imageObjectUrl;panel.append(img);button.remove();}catch(err){note(err.message,true);button.disabled=false;}});
 }
 for(const item of draft.image_candidates||[]){try{
 const url=new URL(item.url),source=new URL(item.source);
 if(url.protocol!=="https:"||source.protocol!=="https:"||url.username||url.password||source.username||source.password)continue;
 const row=node("div","");row.className="image-candidate";
 for(const [label,href] of [["Open image candidate",url.href],["View source page",source.href]]){const a=node("a",label);a.href=href;a.target="_blank";a.rel="noopener noreferrer";row.append(a,document.createTextNode(" · "));}
 if(client.compatibility.sourceImages&&["draft","approved"].includes(r.status)){
 const b=node("button","Attach with reuse permission","secondary");b.disabled=!canWrite();b.addEventListener("click",async()=>{await run({action:"stage-image",id:draft.id,digest:r.digest,url:item.url,source:item.source,confirmation:"I HAVE IMAGE REUSE PERMISSION"},"Source image saved; review and approve the changed draft.");});row.append(b);
 }
 panel.append(row);panel.hidden=false;
 }catch{}}
 if(!panel.hidden&&!draft.ai_image)panel.prepend(node("p","Source images — initial attachment support is restricted to supported AWS hosts. A source link alone does not grant reuse rights."));
}
function updateDraftTiming(){
 const f=$("draft-form").elements;
 $("draft-date-label").textContent=f.time.value?"Publication date (local)":"Publication date (UTC)";
 if(!f.date.value||!f.time.value){$("draft-timing-preview").textContent="Leave time blank to use the existing date-only publishing schedule.";return;}
 try{const value=draftTiming(f.date.value,f.time.value,f.schedule_zone.value.trim());$("draft-timing-preview").textContent="Requested: "+f.date.value+" at "+f.time.value+" ("+f.schedule_zone.value.trim()+"). Stored as "+value.scheduled_at.slice(0,16).replace("T"," ")+" UTC.";}catch(err){$("draft-timing-preview").textContent=err.message;}
}
for(const name of ["date","time","schedule_zone"])$("draft-form").elements[name].addEventListener("input",updateDraftTiming);
function editDraft(r){editing=r;const f=$("draft-form");f.reset();$("editor-title").textContent="Edit "+r.draft.id;for(const k of ["id","date","title","topic","series","text"])f.elements[k].value=r.draft[k]||"";const timing=timingFields(r.draft);f.elements.date.value=timing.date;f.elements.time.value=timing.time;f.elements.schedule_zone.value=timing.timezone;updateDraftTiming();f.elements.id.readOnly=true;f.elements.sources.value=(r.draft.sources||[]).join("\n");f.elements.remove_source_image.checked=false;f.elements.remove_source_image.disabled=!(r.draft.approved_image||r.draft.ai_image);f.elements.visual_title.value=r.draft.visual?.title||"";f.elements.visual_points.value=(r.draft.visual?.points||[]).join("\n");}
$("new").addEventListener("click",()=>{editing=null;$("draft-form").reset();$("draft-form").elements.id.readOnly=false;$("draft-form").elements.remove_source_image.disabled=true;$("editor-title").textContent="Create draft";updateDraftTiming();tab("compose");});
$("draft-form").addEventListener("submit",async e=>{e.preventDefault();const f=new FormData(e.target),d={};for(const k of ["id","date","title","topic","text"])d[k]=f.get(k);if(f.get("series"))d.series=f.get("series");d.sources=lines(f.get("sources"));if(editing?.draft.image_candidates){const images=editing.draft.image_candidates.filter(x=>d.sources.includes(x.source));if(images.length)d.image_candidates=images;}if(editing?.draft.approved_image&&!f.get("remove_source_image")&&!f.get("visual_title")&&!f.get("visual_points")&&d.sources.includes(editing.draft.approved_image.source))d.approved_image=editing.draft.approved_image;if(editing?.draft.ai_image&&!f.get("remove_source_image")&&!f.get("visual_title")&&!f.get("visual_points"))d.ai_image=editing.draft.ai_image;if(f.get("visual_title")||f.get("visual_points"))d.visual={title:f.get("visual_title"),points:lines(f.get("visual_points"))};try{Object.assign(d,draftTiming(f.get("date"),f.get("time"),String(f.get("schedule_zone")||"").trim()));}catch(err){note(err.message,true);return;}const result=await run(editing?{action:"revise",id:d.id,digest:editing.digest,draft:d}:{action:"draft",draft:d},"Draft saved. No publication triggered.");if(result){editing=null;e.target.reset();e.target.elements.id.readOnly=false;$("editor-title").textContent="Create draft";updateDraftTiming();review(d.id);}});
$("schedule").addEventListener("click",()=>{const r=data.drafts.find(d=>d.draft.id===selected);if(r)run({action:["queued","missed-review"].includes(r.status)?"reschedule":"schedule",confirmation:"RESCHEDULE",id:selected,digest:r.digest,local_time:$("local-time").value,timezone:$("timezone").value},"Requested time saved; review and approve again.");});
$("import-form").addEventListener("submit",async e=>{e.preventDefault();try{if(await run({action:"import",drafts:JSON.parse($("plan").value)},"Content plan saved as drafts."))e.target.reset();}catch(err){note("Invalid JSON: "+err.message,true);}});
$("brand-form").addEventListener("submit",e=>{e.preventDefault();const f=new FormData(e.target),brand={};for(const k of ["name","audience","voice"])brand[k]=f.get(k);for(const k of ["goals","pillars","avoid"])brand[k]=lines(f.get(k));run({action:"brand",brand},"Brand context saved.");});
let proPlan=[];
function restoreRecovery(record){
 const items=record.request?.requests||[record.request];
 if(!Array.isArray(items)||items.length<1||items.length>3||items.some(i=>!i||typeof i.topic!=="string"||typeof i.instructions!=="string")){note("This request cannot be restored automatically.",true);return;}
 const today=new Date().toISOString().slice(0,10);
 const clean=items.map(i=>{const item={...i,domains:[...new Set((Array.isArray(i.domains)?i.domains:[]).map(x=>String(x).trim().toLowerCase()))]};if(item.date<today||(item.scheduled_at&&Date.parse(item.scheduled_at)<=Date.now())){item.date=today;delete item.scheduled_at;}return item;});
 const f=$("pro-form");f.elements.automation.value="review";f.elements.automation.dispatchEvent(new Event("change"));
 if(clean.length===1){const i=clean[0],timing=timingFields(i);proPlan=[];for(const [name,value] of Object.entries({topic:i.topic,instructions:i.instructions,domains:(i.domains||[]).join(", "),reference_id:i.reference_id||"",date:timing.date,time:timing.time,zone:timing.timezone}))f.elements[name].value=value;for(const name of ["use_brand","find_images","add_visual"])f.elements[name].checked=i[name]===true;f.elements.visual_mode.value=i.visual_mode|| (i.find_images&&client?.compatibility?.smartVisual?"smart":i.add_visual&&client?.compatibility?.smartVisual?"original":"");}else{proPlan=clean;}
 drawProPlan();tab("research");note("Request restored in review-only mode. Check the topic, sources and time before submitting. Expired times were removed.");
 f.scrollIntoView({block:"start"});
}
function renderRecovery(){
 const section=$("pro-recovery"),list=$("pro-recovery-list");section.hidden=!client?.compatibility?.recovery;$("history-unavailable").hidden=!!client?.compatibility?.recovery;list.replaceChildren();
 if(section.hidden||!data)return;
 const records=data.recovery||[];
 if(!records.length){list.append(node("p","No recorded AI requests yet.","muted"));return;}
 for(const r of records){
  const item=node("article",undefined,"recovery-item");
  const title=r.request?.topic||r.request?.requests?.map(i=>i.topic).join(" / ")||"AI request";
  const labels={started:"Interrupted or still running",failed:"Needs correction",draft:"Draft saved",queued:"Queued",published:"Published","needs-review":"Review required","publication-pending":"Publication needs reconciliation"};
  item.append(node("strong",String(title).slice(0,300)),node("p",labels[r.status]+" · Run #"+r.run_id,"muted"),node("p",String(r.message||"").slice(0,500)));
  const actions=node("div",undefined,"actions");
  for(const id of r.draft_ids){if(!data.drafts.some(d=>d.draft.id===id))continue;const b=node("button","View draft","secondary");b.type="button";b.addEventListener("click",()=>review(id));actions.append(b);}
  if(r.status==="failed"){const b=node("button","Restore request","secondary");b.type="button";b.disabled=!canWrite()||Boolean(pending);b.addEventListener("click",async()=>{if(!canWrite()||pending)return;if(!await confirmAction("Restore failed request","This fills the form or plan only, switches to review required and does not submit or publish. Review any changed timing before submitting.","Restore request"))return;restoreRecovery(r);});actions.append(b);}
  const link=node("a","Workflow details");link.href="https://github.com/"+repoName.split("/").map(encodeURIComponent).join("/")+"/actions/runs/"+r.run_id;link.target="_blank";link.rel="noopener noreferrer";actions.append(link);item.append(actions);list.append(item);
 }
 paginate(list);
}
const PREFERENCES="postforge.mobile.pro-preferences.v1";
function applyPreferences(){
 const c=client?.compatibility,f=$("pro-form");$("pro-preferences").hidden=!c?.pro;
 f.elements.automation.value="review";f.elements.visual_mode.value="";
 try{
  const p=JSON.parse(localStorage.getItem(PREFERENCES)||"null");
  if(p&&p.version===1){
   if(c?.automation&&["review","queue","publish"].includes(p.automation))f.elements.automation.value=p.automation;
   if(c?.smartVisual&&["","smart","original","source-only","text",...(c.aiVisual?["ai-photo","ai-illustration","ai-poster"]:[])].includes(p.visual))f.elements.visual_mode.value=p.visual;
   $("pro-preference-status").textContent="Saved device defaults loaded. Confirm each request before submission.";
  }else $("pro-preference-status").textContent="Using safe defaults.";
 }catch{$("pro-preference-status").textContent="Device preferences unavailable; using safe defaults.";}
 f.elements.automation.dispatchEvent(new Event("change"));
}
$("save-pro-preferences").addEventListener("click",async()=>{
 if(!client?.compatibility?.pro)return;
 const active=client,f=$("pro-form"),automation=proMode(),visual=client.compatibility.smartVisual?f.elements.visual_mode.value:"";
 if(!await confirmAction("Save device defaults","Remember these selections on this browser. They do not authorize or schedule any publication. Confirm each request separately.","Save defaults")||client!==active)return;
 try{localStorage.setItem(PREFERENCES,JSON.stringify({version:1,automation,visual}));$("pro-preference-status").textContent="Defaults saved on this device.";}catch{$("pro-preference-status").textContent="Device storage is unavailable.";}
});
$("reset-pro-preferences").addEventListener("click",()=>{try{localStorage.removeItem(PREFERENCES);}catch{$("pro-preference-status").textContent="Could not clear device storage.";return;}applyPreferences();});
const proMode=()=>client?.compatibility?.automation?$("pro-form").elements.automation.value:"review";
$("pro-form").elements.automation.addEventListener("change",()=>{$("pro-image-warning").hidden=true;const mode=proMode();$("automation-help").textContent=mode==="publish"?"Publishes one post today without further approval. Leave publication time blank.":mode==="queue"?"Automatically queues posts at their selected future times. Delivery is best effort.":"Save drafts for review. No post is published.";});
function normalizedDomains(raw){const hosts=[...new Set(String(raw||"").split(",").map(x=>x.trim().toLowerCase()).filter(Boolean))];if(hosts.length>5||hosts.some(h=>h.length>100||!/^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+$/.test(h)))throw Error("Enter up to five unique official hostnames, without https:// or paths.");return hosts;}
function proRequest(){const f=new FormData($("pro-form"));const request={topic:String(f.get("topic")).trim(),instructions:String(f.get("instructions")).trim(),domains:normalizedDomains(f.get("domains")),use_brand:f.get("use_brand")==="on",find_images:f.get("find_images")==="on",...draftTiming(f.get("date"),f.get("time"),String(f.get("zone")).trim())};if(client?.compatibility?.automation&&f.get("add_visual")==="on")request.add_visual=true;const ref=String(f.get("reference_id")||"").trim();if(ref)request.reference_id=ref;if(client?.compatibility?.smartVisual){const choice=String(f.get("visual_mode")||"");const real=sourceImageRequested(request);if(choice)request.visual_mode=choice;else if(real)request.visual_mode="smart";else if(request.add_visual)request.visual_mode="original";delete request.add_visual;request.find_images=false;return request;}if(sourceImageRequested(request))request.find_images=true;if(request.find_images&&!request.domains.length){$("pro-image-warning").textContent="Enter official source domains to find real source images, or request an original generated graphic instead.";$("pro-image-warning").hidden=false;throw Error("Enter official source domains for image discovery.");}return request;}
function drawProPlan(){const list=$("pro-plan-list");list.replaceChildren();$("pro-plan").hidden=!proPlan.length||!client?.compatibility?.pro;$("pro-submit").disabled=!canWrite();proPlan.forEach((item,i)=>{const row=node("div",item.topic+" · "+(item.scheduled_at||item.date)+(item.visual_mode?" · "+({"smart":"Smart Auto Visual","original":"Original graphic","source-only":"Source image only","text":"Text only","ai-photo":"AI concept photo","ai-illustration":"AI illustration","ai-poster":"AI poster artwork"}[item.visual_mode]||""):""));const remove=node("button","Remove","secondary");remove.type="button";remove.addEventListener("click",()=>{proPlan.splice(i,1);drawProPlan();});row.append(remove);list.append(row);});}
$("pro-add").addEventListener("click",()=>{if(!canWrite()||busy||!$("pro-form").reportValidity())return;try{if(proPlan.length>=3)throw Error("Maximum 3 requests per plan.");proPlan.push(proRequest());drawProPlan();note("Request added to upcoming plan.");}catch(err){note(err.message,true);}});
$("pro-submit").addEventListener("click",async()=>{if(!proPlan.length||!canWrite()||busy||pending)return;await run({action:"pro-generate",request:{requests:proPlan,...(proMode()!=="review"?{automation:proMode()}:{})}},"AI plan created");if(pending&&pending!=="unknown"){proPlan=[];drawProPlan();}});
$("pro-form").addEventListener("submit",async e=>{e.preventDefault();$("pro-image-warning").hidden=true;try{await run({action:"pro-generate",request:{...proRequest(),...(proMode()!=="review"?{automation:proMode()}:{})}},"AI draft created");}catch(err){note(err.message,true);}});
$("copy-brief").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("brief").textContent);note("AI brief copied.");}catch(e){note("Select and copy the brief manually.",true);}});
for(const b of document.querySelectorAll("[data-tab],[data-go]"))b.addEventListener("click",()=>{const id=b.dataset.tab||b.dataset.go;if(id==="approval")showApprovalList();tab(id);});$("back-approvals").addEventListener("click",showApprovalList);for(const id of ["filter","search"])$(id).addEventListener("input",calendar);
async function refresh(){if(busy)return;busy=true;try{await load();}catch(e){note(e.message,true);}finally{busy=false;}}
for(const id of ["start","days"])$(id).addEventListener("change",refresh);$("refresh").addEventListener("click",refresh);$("approval-refresh").addEventListener("click",refresh);$("settings-refresh").addEventListener("click",refresh);
function fillBrand(){const brand=data.brief.brand||{};for(const k of ["name","audience","voice","goals","pillars","avoid"])$("brand-form").elements[k].value=Array.isArray(brand[k])?brand[k].join("\n"):brand[k]||"";}
function showVault(){try{$("unlock-panel").hidden=!localStorage.getItem(VAULT);}catch{$("unlock-panel").hidden=true;}}
$("remember").addEventListener("change",()=>{$("vault-fields").hidden=!$("remember").checked;for(const id of ["vault-pass","vault-repeat"])$(id).required=$("remember").checked;});
$("enable-write").addEventListener("change",()=>{if($("enable-write").checked){$("remember").checked=false;$("remember").dispatchEvent(new Event("change"));}$("remember").disabled=$("enable-write").checked;$("direct-duration-field").hidden=!$("enable-write").checked;});
async function connect(credential,write=false){
 proPlan=[];$("pro-form").elements.automation.value="review";$("automation-help").textContent="Save drafts for review. No post is published.";clearImagePreview();stopActionPoll();if(repoName&&repoName!==credential.repo){pending=null;pendingMeta=null;$("action-panel").hidden=true;}repoName=credential.repo;writeEnabled=write;client=new Client(repoName,credential.token,credential.branch);readClient=write?null:client;if(write)startEditClock(editDeadline(Number($("direct-duration").value)));await load();fillBrand();$("connect-panel").hidden=true;$("connection").hidden=false;$("workspace").hidden=false;document.body.classList.add("workspace-connected");tab("calendar");connectionStatus();applyPreferences();$("runs-link").href="https://github.com/"+repoName.split("/").map(encodeURIComponent).join("/")+"/actions/workflows/mobile-studio.yml";note("Connected to recognised PostForge installation. Data stays in your private repository.");
}
function failed(err){proPlan=[];clearImagePreview();clearTimeout(editTimer);editUntil=0;writeEnabled=false;client=null;readClient=null;data=null;$("workspace").hidden=true;$("connection").hidden=true;$("connect-panel").hidden=false;document.body.classList.remove("workspace-connected");note(err.message,true);}
$("connect-form").addEventListener("submit",async e=>{e.preventDefault();if(busy)return;busy=true;const credential={repo:$("repo").value.trim(),token:$("access").value.trim(),branch:$("branch").value};const remember=$("remember").checked,write=$("enable-write").checked,password=$("vault-pass").value,repeat=$("vault-repeat").value;
 $("access").value="";$("vault-pass").value="";$("vault-repeat").value="";
 try{if(remember&&(write||password!==repeat||password.length<12))throw Error("Use a matching separate passphrase of at least 12 characters and read-only access.");await connect(credential,write);if(remember){try{localStorage.setItem(VAULT,await seal(credential,password));showVault();note("Connected. Encrypted device unlock saved; use Disconnect to lock.");}catch{note("Connected, but the encrypted connection could not be saved.",true);}}}catch(err){failed(err);}finally{busy=false;}
});
$("unlock-form").addEventListener("submit",async e=>{e.preventDefault();if(busy)return;busy=true;const password=$("unlock-pass").value;$("unlock-pass").value="";try{const credential=await unseal(localStorage.getItem(VAULT),password);await connect(credential,false);}catch(err){failed(err);}finally{busy=false;}});
$("forget").addEventListener("click",async()=>{if(await confirmAction("Forget saved connection","Remove both encrypted authorizations from this device. Revoke their tokens in GitHub if needed.","Forget")){try{localStorage.removeItem(VAULT);localStorage.removeItem(EDIT_VAULT);localStorage.removeItem(PREFERENCES);showVault();note("Saved connection removed from this browser. Revoke its token in GitHub if needed.");}catch{note("Unable to clear browser storage.",true);}}});
showVault();
async function checkAction(){
 if(busy||!pending||!client)return;
 if(pending==="unknown"){await recoverAction();return;}
 const runId=pending,meta=pendingMeta,active=client;stopActionPoll();busy=true;
 try{
  const result=await active.run(runId);
  if(client!==active||pending!==runId)return;
  if(result.status!=="completed"){
  const waiting=["queued","requested","waiting","pending"].includes(result.status),elapsed=Math.max(0,Math.floor((Date.now()-(meta?.started||Date.now()))/1000));
  actionStatus("pending",waiting?"Waiting for GitHub runner":meta?.action==="pro-generate"?"Research workflow running":"Action in progress","GitHub status: "+result.status+" · "+Math.floor(elapsed/60)+"m "+elapsed%60+"s elapsed. "+(waiting?"No execution confirmed yet.":"Research, validation and saving occur on GitHub.")+" The app checks again automatically.");return;
 }
  await load();fillBrand();
  let confirmed=result.conclusion==="success";
  if(confirmed&&meta?.action==="delete")confirmed=!data.drafts.some(r=>r.draft.id===meta.id);
  if(confirmed&&meta?.action==="delete-many")confirmed=meta.items.every(i=>!data.drafts.some(r=>r.draft.id===i.id));
  if(confirmed&&meta?.action==="approve")confirmed=data.drafts.some(r=>r.draft.id===meta.id&&r.digest===meta.digest&&r.status==="approved");
  if(confirmed&&meta?.action==="publish-now")confirmed=data.drafts.some(r=>r.draft.id===meta.id&&r.digest===meta.digest&&r.status==="published"&&data.posts[r.draft.id]?.post_id);
  if(confirmed&&meta?.action==="reschedule")confirmed=data.drafts.some(r=>r.draft.id===meta.id&&r.status==="draft"&&r.digest!==meta.digest);
  if(confirmed&&meta?.action==="export")confirmed=data.drafts.some(r=>r.draft.id===meta.id&&r.digest===meta.digest&&["queued","published","missed-review","review-claim"].includes(r.status));
  const journal=meta?.action==="pro-generate"?data.recovery?.find(r=>r.run_id===String(runId)):null;
  const generated=confirmed&&meta?.action==="pro-generate"?data.drafts.filter(r=>client.compatibility?.recovery?journal?.draft_ids.includes(r.draft.id):!meta.priorIds.has(r.draft.id)&&r.draft.id.startsWith("ai-")):[];
  if(meta)meta.runId=String(runId);
  if(meta?.action==="pro-generate"&&confirmed){confirmed=generated.length>0&&(meta.mode==="publish"?generated.every(r=>r.status==="published"&&data.posts[r.draft.id]?.post_id):meta.mode==="queue"?generated.every(r=>["queued","published","missed-review"].includes(r.status)):generated.every(r=>r.status==="draft"));}
  if(journal?.status==="needs-review"&&result.conclusion==="success"&&generated.length&&generated.every(r=>r.status==="draft")){
    pending=null;actionStatus("warning","Draft saved — review required",journal.message);note(journal.message);tab("approval");if(generated.length===1)review(generated[0].draft.id);connectionStatus();return;
  }
  pending=null;
  actionStatus(confirmed?"success":"warning",confirmed?(meta?.action==="publish-now"||meta?.mode==="publish"?"Published to LinkedIn":meta?.action==="export"||meta?.mode==="queue"?"Queued — check delivery status":meta?.action?.startsWith("delete")?"Drafts removed":"Action completed"):"Review action outcome",confirmed?(journal?.message||"GitHub reports success. Workspace refreshed."):result.conclusion==="success"?"GitHub completed, but the expected workspace change was not found. Inspect workflow details before retrying.":(journal?.message||"GitHub reports "+result.conclusion+". No automatic retry."));
  note(confirmed?"GitHub reports success. Workspace refreshed.":journal?.message||"Action outcome needs review.",!confirmed);
  if(confirmed&&meta?.action==="pro-generate"){tab(meta.mode==="review"?"approval":"calendar");if(generated.length===1)review(generated[0].draft.id);}
  if(confirmed&&meta?.id&&data.drafts.some(r=>r.draft.id===meta.id)&&["approve","export","draft","revise","schedule","stage-image","publish-now","reschedule"].includes(meta.action))review(meta.id);
  connectionStatus();
 }catch(e){actionStatus("warning","Status temporarily unavailable",e.message+" Your request has not been resubmitted.");note(e.message,true);stopActionPoll();return;}
 finally{busy=false;if(pending&&$("action-panel").dataset.state!=="warning")pollAction();}
}
async function recoverAction(){
 if(busy||!client||pending!=="unknown"||!pendingMeta)return;
 busy=true;const list=$("recovery-list");list.hidden=false;list.replaceChildren(node("p","Loading recent workflow activity…"));
 try{
  const runs=await client.recentRuns(pendingMeta.workflow);list.replaceChildren(node("p","Select a run only if you recognise it as your request. Times and status are shown below; the app will not guess."));
  for(const r of runs){const b=node("button","Run #"+r.id+" · "+r.status+(r.conclusion?" / "+r.conclusion:"")+" · "+(r.created_at||"Unknown time"),"secondary");b.type="button";b.addEventListener("click",async()=>{if(pending!=="unknown"||busy)return;if(!await confirmAction("Track this workflow","Only select this run if it matches the request you submitted.","Track run"))return;pending=String(r.id);list.hidden=true;await checkAction();});list.append(b);}
  if(!runs.length)list.append(node("p","No recent runs were returned. A request may still be pending; inspect workflow history."));
 }catch(e){list.replaceChildren(node("p",e.message));}
 finally{busy=false;}
 const clear=node("button","Clear after manual reconciliation","secondary");clear.type="button";clear.addEventListener("click",async()=>{if(busy||pending!=="unknown")return;if(!await confirmAction("Clear pending marker","Only clear this after confirming the previous request finished or was never accepted. This will not cancel a GitHub workflow.","Clear marker"))return;pending=null;stopActionPoll();await refresh();actionStatus("warning","Pending marker cleared","Workspace refreshed. Review existing drafts before making another request.");connectionStatus();});list.append(clear);
}
$("check-run").addEventListener("click",checkAction);
$("recover-run").addEventListener("click",recoverAction);
$("disconnect").addEventListener("click",async()=>{if(pending&&!await confirmAction("Disconnect workspace","A request may still be running. Disconnecting removes local tracking, not the GitHub workflow. Check workflow history before resubmitting.","Disconnect"))return;stopActionPoll();client=null;data=null;location.reload();});
if("serviceWorker" in navigator&&location.protocol==="https:")navigator.serviceWorker.register("./sw.js").catch(()=>{});


// Read-only receipt refresh, only while the dashboard is visible and idle.
setInterval(async()=>{if(document.hidden||busy||pending||!client||!data||$("action-dialog").open||["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)||!(data.delivery||[]).length)return;const active=client;busy=true;try{if(await active.headChanged()&&client===active)await load();else if(client===active)renderDelivery();}catch{/* Manual refresh remains available; never resubmit an action. */}finally{busy=false;}},60000);
