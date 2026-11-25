"""Stage a user-authorized official AWS image as immutable repository bytes."""
import hashlib
import io
import re
import urllib.parse
import urllib.request
from pathlib import Path

# Initial supported source family. Do not accept user-defined download hosts.
SOURCE_HOSTS={"aws.amazon.com","skillbuilder.aws","explore.skillbuilder.aws"}
IMAGE_HOSTS=SOURCE_HOSTS|{"a0.awsstatic.com","d1.awsstatic.com","awsstatic.com"}
MAX_BYTES=5_000_000
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def allowed(url,hosts):
    try:
        p=urllib.parse.urlsplit(url)
        return isinstance(url,str) and len(url)<=1000 and not any(c.isspace() for c in url) and p.scheme=="https" and p.hostname in hosts and p.username is None and p.password is None and p.port in (None,443)
    except (ValueError,TypeError,AttributeError):
        return False

def download(url):
    if not allowed(url,IMAGE_HOSTS):
        raise ValueError("Image host is not supported")
    # No redirects, no credentials, no arbitrary hosts and no environment proxy.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    req=urllib.request.Request(url,headers={"Accept":"image/png,image/jpeg","User-Agent":"PostForge-Image-Review/1.0"})
    with opener.open(req,timeout=20) as response:
        if response.headers.get_content_type() not in {"image/png","image/jpeg"}:
            raise ValueError("Unsupported image response")
        raw=response.read(MAX_BYTES+1)
    return raw

def normalize(raw):
    from PIL import Image
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:
        raise ValueError("Image too large or empty")
    with Image.open(io.BytesIO(raw)) as im:
        if im.format not in {"JPEG","PNG"} or not 1<=im.width<=4096 or not 1<=im.height<=4096 or im.width*im.height>12_000_000 or getattr(im,"n_frames",1)!=1:
            raise ValueError("Unsupported image dimensions or format")
        im.load()
        im=im.convert("RGB")
        im.thumbnail((1200,1200))
        out=io.BytesIO()
        im.save(out,format="PNG",optimize=True)
        data=out.getvalue()
    if len(data)>MAX_BYTES:
        raise ValueError("Normalized image too large")
    return data

def validate(meta):
    if not isinstance(meta,dict) or set(meta)!={"sha256","url","source","rights"} or not isinstance(meta["sha256"],str) or not re.fullmatch(r"[0-9a-f]{64}",meta["sha256"]) or meta["rights"]!="USER_CONFIRMED_PERMISSION" or not allowed(meta["url"],IMAGE_HOSTS) or not allowed(meta["source"],SOURCE_HOSTS):
        raise ValueError("Invalid reviewed image metadata")
    return meta

def asset_path(root,digest):
    if not re.fullmatch(r"[0-9a-f]{64}",digest):
        raise ValueError("Invalid image digest")
    p=root
    for part in ("studio","assets",digest+".png"):
        p=p/part
        if p.is_symlink(): raise ValueError("Unsafe image path")
    return p

def load(root,meta):
    validate(meta)
    p=asset_path(root,meta["sha256"])
    if not p.is_file() or p.stat().st_size>MAX_BYTES:
        raise ValueError("Reviewed image missing or oversized")
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta["sha256"] or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Reviewed image bytes changed")
    return raw

def stage(root,url,source,confirmation,fetch=download):
    if confirmation!="I HAVE IMAGE REUSE PERMISSION" or not allowed(source,SOURCE_HOSTS) or not allowed(url,IMAGE_HOSTS):
        raise ValueError("Explicit image permission and supported source required")
    raw=normalize(fetch(url))
    digest=hashlib.sha256(raw).hexdigest()
    meta={"sha256":digest,"url":url,"source":source,"rights":"USER_CONFIRMED_PERMISSION"}
    path=asset_path(root,digest)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): load(root,meta)
    else:
        with path.open("xb") as out: out.write(raw)
    return meta


GENERATED_MODEL="@cf/black-forest-labs/flux-1-schnell"

def validate_generated(meta):
    if not isinstance(meta,dict) or set(meta)!={"sha256","model"} or not isinstance(meta["sha256"],str) or not re.fullmatch(r"[0-9a-f]{64}",meta["sha256"]) or meta["model"]!=GENERATED_MODEL:
        raise ValueError("Invalid AI image metadata")
    return meta

def load_generated(root,meta):
    validate_generated(meta)
    p=asset_path(root,meta["sha256"])
    if not p.is_file() or p.stat().st_size>MAX_BYTES:
        raise ValueError("AI image missing or oversized")
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta["sha256"] or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("AI image bytes changed")
    return raw

def stage_generated(root,png,model):
    if not isinstance(png,bytes) or not 1<=len(png)<=MAX_BYTES or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid normalized AI image")
    meta=validate_generated({"sha256":hashlib.sha256(png).hexdigest(),"model":model})
    p=asset_path(root,meta["sha256"])
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        load_generated(root,meta)
    else:
        with p.open("xb") as out: out.write(png)
    return meta
