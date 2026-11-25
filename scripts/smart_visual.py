"""Conservative visual selection: exact, owner-authorised immutable assets or original art.

A search hit, an official hostname, or a model statement is not a licence.
The private workspace owner must explicitly register reusable image bytes.
No third-party downloads or extra provider requests happen here.
"""
import re
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

# Recognise names only when they occur in supplied title, topic or post text.
TOOLS=("Splunk","Elastic","Wireshark","NetworkMiner","MITRE ATT&CK","TryHackMe",
       "Microsoft Sentinel","CrowdStrike","Kali Linux","Nmap","Burp Suite","Wazuh",
       "Suricata","Zeek","OpenAI","ChatGPT","Gemini","Claude","PyTorch","TensorFlow",
       "Hugging Face","GitHub","Docker","Kubernetes","AWS","Azure","Google Cloud",
       "Linux","Python","PostgreSQL","React","Next.js","Prisma")
def impact_brief(draft):
    body=re.split(r"\n\s*(?:Sources?|References?)\s*:",draft["text"],maxsplit=1,flags=re.I)[0]
    combined=" ".join((draft["title"],draft["topic"],body))
    found=[]
    for name in TOOLS:
        match=re.search(r"(?<![\w])"+re.escape(name)+r"(?![\w])",combined,re.I)
        if match: found.append((match.start(),name))
    names=[name for _,name in sorted(found)][:6]
    # Extract short, actual phrases from the draft, not invented benefits.
    chunks=re.split(r"(?<=[.!?])\s+|[\n;]+",body)
    phrases=[]
    for chunk in chunks:
        chunk=re.sub(r"^\s*[-•*]\s*","",chunk).strip()
        if not chunk or re.search(r"https?://|www\.|#",chunk,re.I): continue
        if len(chunk)>80: chunk=chunk[:77].rsplit(" ",1)[0]+"…"
        if len(chunk)>=5 and chunk not in phrases: phrases.append(chunk)
    points=(phrases+[draft["topic"][:80],draft["title"][:80]])[:4]
    if len(points)<2: points=[draft["topic"][:80],draft["title"][:80]]
    return {"title":draft["title"][:70],"points":points,"layout":"impact","labels":names if len(names)>=2 else points[:4]}

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
        draft["visual"]=impact_brief(draft)
        print("Visual: original graphic selected.",flush=True)
    elif mode=="source-only":
        print("Visual: no authorised reusable source image; hold for review.",flush=True)
