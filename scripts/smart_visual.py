"""Conservative visual selection: exact, owner-authorised immutable assets or original art.

A search hit, an official hostname, or a model statement is not a licence.
The private workspace owner must explicitly register reusable image bytes.
No third-party downloads or extra provider requests happen here.
"""
import re
from urllib.parse import urlsplit
from scripts import content_studio as studio, pro_images

MODES={"smart","original","source-only","text","ai-photo","ai-illustration","ai-poster"}
REAL=re.compile(r"\b(?:actual|real|official|source)\s+images?\b",re.I)
VISUAL=re.compile(r"\b(?:add|include|create|generate|with)\s+(?:(?:an?|the|original|a relevant)\s+)?(?:visuals?|images?|graphics?|posters?|infographics?)\b",re.I)

def mode_for(item, automation="review"):
    explicit=item.get("visual_mode")
    if explicit is not None:
        if not isinstance(explicit,str) or explicit not in MODES:
            raise ValueError("Invalid visual mode")
        return explicit
    instructions=str(item.get("instructions",""))
    if automation!="review" and (item.get("find_images") or REAL.search(instructions)):
        return "smart"
    if item.get("add_visual") or VISUAL.search(instructions):
        return "smart" if automation!="review" else "original"
    return None

def reusable_image(root, sources, caption):
    """Return an exact permission entry only when its source is actually cited."""
    try:
        p=studio.path_for(root,"studio","reusable-images.json")
        if not p.is_file() or p.stat().st_size>60000:
            return None
        entries=studio.load(p)
        if not isinstance(entries,list) or len(entries)>50:
            return None
    except (ValueError,OSError,TypeError):
        return None
    for entry in entries:
        try:
            if not isinstance(entry,dict) or set(entry)!={"image","permission","attribution"} or entry["permission"]!="OWNER_CONFIRMED_REUSABLE_WITHOUT_EXPIRY":
                continue
            meta=pro_images.validate(entry["image"])
            if meta["source"] not in sources:
                continue
            attribution=entry["attribution"]
            if not isinstance(attribution,str) or not 1<=len(attribution.strip())<=240 or any(ord(c)<32 for c in attribution) or re.search(r"https?://|www\.",attribution,re.I):
                continue
            text=caption+"\n\nImage credit: "+attribution.strip()
            if len(text)>3000:
                continue
            pro_images.load(root,meta)
            return meta,text
        except (ValueError,OSError,TypeError,KeyError):
            continue
    return None

def apply(root,draft,mode):
    if mode in {"smart","source-only"}:
        selected=reusable_image(root,draft["sources"],draft["text"])
        if selected:
            meta,caption=selected
            pair={"url":meta["url"],"source":meta["source"]}
            draft["image_candidates"]=[pair]+[i for i in draft.get("image_candidates",[]) if i!=pair][:4]
            draft["approved_image"]=meta
            draft["text"]=caption
            print("Visual: matched a previously authorised reusable source image.",flush=True)
            return
    if mode in {"smart","original","ai-photo","ai-illustration","ai-poster"}:
        host=urlsplit(draft["sources"][0]).hostname or "Research source"
        draft["visual"]={"title":draft["title"][:70],"points":[draft["topic"][:80],("Source: "+host)[:80],"Read the linked source for details"]}
        print("Visual: original graphic selected.",flush=True)
    elif mode=="source-only":
        print("Visual: no authorised reusable source image; hold for review.",flush=True)
