"""Private, run-scoped recovery journal. Never performs provider or publication calls."""
import datetime as dt
import re
from scripts import content_studio as studio

def path(root, run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r"[1-9][0-9]{0,19}",run_id):
        raise ValueError("Invalid recovery run identifier")
    return studio.path_for(root,"studio","requests",run_id+".json")

def start(root, run_id, request, mode):
    p=path(root,run_id)
    if p.exists():
        raise ValueError("Request already recorded; inspect its outcome before submitting a new request")
    record={"run_id":run_id,"mode":mode,"request":request,"status":"started",
            "message":"Request recorded. If interrupted, check the original workflow before taking further action.",
            "draft_ids":[]}
    update(root,record,replace=False)
    return record

def update(root, record, *, status=None, message=None, draft_ids=None, replace=True):
    if status is not None: record["status"]=status
    if message is not None: record["message"]=message
    if draft_ids is not None: record["draft_ids"]=draft_ids
    record["updated_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
    studio.write(path(root,record["run_id"]),record,replace=replace)

def review_expired(drafts, now):
    """Retain generated content, but never silently change a publication schedule."""
    expired=any(studio.day(d["date"])<now.date() or
        (d.get("scheduled_at") and studio.publish.parse_scheduled(d["scheduled_at"])<=now)
        for d in drafts)
    if not expired: return False
    for d in drafts:
        if studio.day(d["date"])<now.date() or (d.get("scheduled_at") and
                studio.publish.parse_scheduled(d["scheduled_at"])<=now):
            d["date"]=now.date().isoformat()
            d.pop("scheduled_at",None)
    return True

def validate_visuals(drafts,root=None):
    for d in drafts:
        if d.get("ai_image"):
            studio.pro_images.load_generated(root or studio.ROOT,d["ai_image"])
        if d.get("visual"):
            png=studio.publish.render(d["visual"])
            if not isinstance(png,bytes) or not png.startswith(bytes.fromhex("89504e470d0a1a0a")):
                raise ValueError("Requested visual could not be rendered")
