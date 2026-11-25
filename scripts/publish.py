"""PostForge AI: explicit opt-in LinkedIn publisher."""
import datetime
import hashlib
import unicodedata
import json
import os
import pathlib
import re
import subprocess
import urllib.request
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def upload_url_ok(url):
    p = urllib.parse.urlsplit(url)
    return p.scheme == "https" and p.hostname in {"www.linkedin.com", "api.linkedin.com", "media.licdn.com"} and not p.username and not p.password and p.port in (None, 443)

def parse_scheduled(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\+00:00", value):
        raise ValueError("Expected UTC schedule at minute precision")
    return datetime.datetime.fromisoformat(value)

def due(item, now, timed_only=False):
    value = item.get("scheduled_at")
    if value is None:
        return not timed_only
    scheduled = parse_scheduled(value)
    return scheduled <= now <= scheduled + datetime.timedelta(hours=2) and scheduled.date() == now.date()

def validate(item, day):
    if item.get("date") != day:
        raise ValueError("Date mismatch")
    if "scheduled_at" in item and parse_scheduled(item["scheduled_at"]).date().isoformat() != day:
        raise ValueError("Scheduled UTC date mismatch")
    text = item.get("text")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000:
        raise ValueError("Invalid text")
    v = item.get("visual")
    if v is not None:
        if not isinstance(v, dict) or not isinstance(v.get("title"), str) or not 1 <= len(v["title"]) <= 70:
            raise ValueError("Invalid visual title")
        points = v.get("points")
        if not isinstance(points, list) or not 2 <= len(points) <= 4 or any(not isinstance(p, str) or not 1 <= len(p) <= 80 for p in points):
            raise ValueError("Invalid visual points")
    image = item.get("approved_image")
    if image is not None:
        if v is not None or item.get("link_preview") is not None:
            raise ValueError("Choose only one image format")
        try:
            from . import pro_images
        except ImportError:
            import pro_images
        pro_images.validate(image)
        if image["source"] not in text:
            raise ValueError("Image source URL must appear in caption")
    if "ai_image" in item:
        if v is not None or image is not None or item.get("link_preview") is not None:
            raise ValueError("Choose only one image format")
        try:
            from . import pro_images
        except ImportError:
            import pro_images
        pro_images.validate_generated(item["ai_image"])
        if "AI-generated conceptual illustration (not an official image)." not in text:
            raise ValueError("AI image disclosure required")
    link = item.get("link_preview")
    if link is not None:
        if v is not None or not isinstance(link, dict):
            raise ValueError("Link preview cannot be combined with generated visual")
        if (link.get("source") != "https://github.com/SalamCircle/postforge-ai" or
            link.get("poster_url") not in {"https://raw.githubusercontent.com/SalamCircle/postforge-ai/main/docs/assets/postforge-ai-followup.jpg", "local:v2-approved-assets"}):
            raise ValueError("Unapproved link preview source or poster")
        if (not isinstance(link.get("title"), str) or not 1 <= len(link["title"]) <= 100 or
            not isinstance(link.get("description"), str) or not 1 <= len(link["description"]) <= 250):
            raise ValueError("Invalid link preview metadata")
        if link["source"] not in text:
            raise ValueError("Repository URL must also appear in caption")
    return item

def request(url, token, payload=None, raw=None, method=None, raw_mime="image/png"):
    if not upload_url_ok(url):
        raise ValueError("Untrusted endpoint")
    headers = {"Authorization": "Bearer " + token, "Content-Type": raw_mime if raw is not None else "application/json", "X-Restli-Protocol-Version": "2.0.0"}
    if urllib.parse.urlsplit(url).path.startswith("/rest/"):
        headers["Linkedin-Version"] = os.environ.get("LINKEDIN_API_VERSION", "202609")
    data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            body = response.read()
            return response.status, response.headers, json.loads(body) if body and raw is None else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("Network failure; inspect before retrying") from None

def visual_theme(visual):
    """Choose a restrained topic-specific editorial treatment, no provider required."""
    content = " ".join([visual["title"], *visual["points"]]).lower()
    for pattern, name, top, bottom, accent in (
        (r"\b(cyber\w*|security|defen[cs]e|defender|threat|mfa|phishing)\b", "SECURITY / FIELD NOTES", (7, 22, 41), (15, 40, 63), "#34D9F5"),
        (r"\b(cloud|aws|azure|infrastructure|devops)\b", "CLOUD / ENGINEERING", (9, 31, 39), (18, 58, 61), "#70E1C7"),
        (r"\b(ai|artificial intelligence|model|llm|machine learning)\b", "AI / TECHNOLOGY", (22, 17, 45), (41, 34, 76), "#B8B0FF"),
    ):
        if re.search(pattern, content):
            return name, top, bottom, accent
    return "PRACTICAL / INSIGHTS", (10, 29, 47), (21, 48, 73), "#83CEFF"


def render(visual):
    """Render an unbranded editorial graphic locally, without remote assets."""
    import io
    import re
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 1200))
    draw = ImageDraw.Draw(image)
    category, top_color, bottom_color, theme = visual_theme(visual)
    for y in range(1200):
        t = y / 1199
        draw.line((0, y, 1200, y), fill=tuple(int(a+(b-a)*t) for a,b in zip(top_color,bottom_color)))
    # Quiet technical grid and accent arcs, outside the reading area.
    for x in range(48, 1200, 64):
        draw.line((x, 0, x, 1200), fill="#142D43", width=1)
    for y in range(48, 1200, 64):
        draw.line((0, y, 1200, y), fill="#142D43", width=1)
    for radius in (40, 68, 96):
        draw.arc((1048-radius, 108-radius, 1048+radius, 108+radius), 5, 175, fill="#48677E", width=2)
    draw.rounded_rectangle((48, 48, 1152, 1152), radius=28, outline="#2B6078", width=2)
    def font(size, bold=False):
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)

    def wrap(text, f, max_width):
        lines, line = [], ""
        words=[]
        for word in text.split():
            while draw.textlength(word,font=f)>max_width:
                split=1
                while split<len(word) and draw.textlength(word[:split+1],font=f)<=max_width:
                    split+=1
                words.append(word[:split]); word=word[split:]
            if word: words.append(word)
        for word in words:
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=f) <= max_width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines

    draw.rounded_rectangle((88, 83, 108, 127), radius=5, fill=theme)
    draw.text((125, 91), category, font=font(25, True), fill="#EAF8FF")
    title = visual["title"]
    for title_size in range(74, 39, -2):
        title_font = font(title_size, True)
        title_lines = wrap(title, title_font, 1010)
        if title_lines is not None and len(title_lines) <= 2:
            break
    else:
        raise ValueError("Visual title cannot fit")
    for i, line in enumerate(title_lines):
        draw.text((88, 191+i*(title_size+10)), line, font=title_font, fill="#F4FAFF")
    draw.line((88, 367, 1112, 367), fill="#32708D", width=2)
    points = visual["points"]
    draw.text((88, 392), f"{len(points):02d} KEY TAKEAWAYS", font=font(24, True), fill=theme)
    # A wide editorial list keeps longer copy legible on phones.
    top, bottom, gap = 456, 1068, 14
    row_h = (bottom-top-gap*(len(points)-1))//len(points)
    accents = ("#36CFEA", "#7C9EFF", "#53DFC0", "#C3A2FF")
    for index, point in enumerate(points):
        accent = accents[index]
        y0 = top+index*(row_h+gap)
        y1 = y0+row_h
        draw.rounded_rectangle((88,y0,1112,y1), radius=16, fill="#112B43", outline="#3A5970", width=2)
        draw.rounded_rectangle((88,y0+10,94,y1-10),radius=3,fill=accent)
        # Avoid duplicate decorative numbering supplied by earlier prompts.
        point = re.sub(r"^\s*0?[1-4]\s*(?:[|:.)]|[-–—])\s+", "", point, count=1) or point
        draw.text((115,y0+22),f"{index+1:02d}",font=font(42,True),fill=accent)
        draw.line((198,y0+20,198,y1-20),fill="#31536B",width=2)
        for size in range(45 if len(points)<4 else 41,23,-2):
            f=font(size)
            lines=wrap(point,f,878)
            line_height=size+8
            if lines and len(lines)*line_height <= row_h-20:
                break
        else:
            raise ValueError("Visual point cannot fit card")
        text_y=y0+(row_h-len(lines)*line_height)//2
        for n,line in enumerate(lines):
            draw.text((220,text_y+n*line_height),line,font=f,fill="#E5F2FC")
    output=io.BytesIO()
    image.save(output,format="PNG",optimize=True)
    return output.getvalue()

def render_v2_assets():
    """Rasterize the two repository-owned SVG assets without remote resources."""
    import io
    import cairosvg
    from PIL import Image
    canvas = Image.new("RGB", (1280, 1000), "#ffffff")
    for name, width, height, position in (
        ("logo-v2.svg", 200, 200, (540, 35)),
        ("edition-v2.svg", 1200, 656, (40, 280)),
    ):
        data = (ROOT / "docs" / "assets" / name).read_bytes()
        if len(data) > 100000 or any(x in data.lower() for x in (b"<!doctype", b"<!entity", b"href=", b"url(", b"<image", b"<foreignobject")):
            raise ValueError("Unsafe SVG asset")
        png = cairosvg.svg2png(bytestring=data, output_width=width, output_height=height)
        layer = Image.open(io.BytesIO(png)).convert("RGBA")
        canvas.paste(layer, position, layer)
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=95)
    return output.getvalue()


def fetch_approved_poster(url):
    """Fetch only the exact uploaded public JPEG; no new artwork is generated."""
    if url == "local:v2-approved-assets":
        return render_v2_assets()
    allowed = "https://raw.githubusercontent.com/SalamCircle/postforge-ai/main/docs/assets/postforge-ai-followup.jpg"
    if url != allowed:
        raise ValueError("Poster URL is not approved")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(urllib.request.Request(url), timeout=30) as response:
            blob = response.read(6_000_001)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Poster fetch HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("Poster fetch failed") from None
    if not blob.startswith(bytes([255, 216, 255])) or not 10_000 < len(blob) <= 6_000_000:
        raise ValueError("Invalid or oversized uploaded JPEG poster")
    if hashlib.sha256(blob).hexdigest() != "6ca6c5eb625f7f553ae90025fa884afd6f6de5d128ed3e505ab958fa607133f1":
        raise ValueError("Poster bytes do not match the approved uploaded artwork")
    return blob


def publish_clickable_article(item, author, token, receipt, digest, day, path):
    """Official article preview: clicking the preview opens the public GitHub source."""
    link = item["link_preview"]
    blob = fetch_approved_poster(link["poster_url"])
    _, _, registered = request(
        "https://api.linkedin.com/rest/images?action=initializeUpload",
        token, {"initializeUploadRequest": {"owner": author}})
    image_info = registered["value"]
    image_urn = image_info["image"]
    if not image_urn.startswith("urn:li:image:"):
        raise ValueError("Unexpected image URN")
    request(image_info["uploadUrl"], token, raw=blob, method="PUT", raw_mime="image/jpeg")
    article = {
        "author": author,
        "commentary": item["text"],
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "content": {"article": {
            "source": link["source"],
            "thumbnail": image_urn,
            "title": link["title"],
            "description": link["description"]
        }},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }
    media = archive_visual(blob, "jpg")
    record(receipt, {"status": "claimed", "fingerprint": digest,
                     "date": day, "queue": path.name, "format": "linked_article", "published_media": media})
    status, headers, _ = request("https://api.linkedin.com/rest/posts", token, article)
    post_id = headers.get("X-RestLi-Id")
    if status != 201 or not post_id:
        raise RuntimeError("Article publication uncertain; inspect manually before retrying")
    record(receipt, {"status": "published", "post_id": post_id, "visual": True,
                     "fingerprint": digest, "date": day, "queue": path.name,
                     "format": "linked_article", "source": link["source"], "published_media": media})


def archive_visual(blob, extension):
    """Store the exact uploaded image once, private and content-addressed.
    Called only on live publication before the claim is committed. No API calls.
    """
    if extension not in ("png", "jpg") or not isinstance(blob, bytes) or not 8 <= len(blob) <= 6_000_000:
        raise ValueError("Invalid publication image")
    if (extension == "png" and not blob.startswith(bytes.fromhex("89504e470d0a1a0a"))) or (extension == "jpg" and not blob.startswith(bytes.fromhex("ffd8ff"))):
        raise ValueError("Invalid publication image signature")
    sha = hashlib.sha256(blob).hexdigest()
    folder = ROOT / "state" / "media"
    if folder.is_symlink() or folder.parent.is_symlink():
        raise ValueError("Unsafe publication image directory")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (sha + "." + extension)
    if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_bytes() != blob)):
        raise ValueError("Publication image integrity conflict")
    if not target.exists():
        with target.open("xb") as out:
            out.write(blob)
    return {"sha256": sha, "extension": extension}

def record(path, value):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    paths = [str(path)]
    media = value.get("published_media")
    if media:
        sha, ext = media["sha256"], media["extension"]
        if not re.fullmatch(r"[a-f0-9]{64}", sha) or ext not in ("png", "jpg"):
            raise ValueError("Invalid publication media reference")
        saved = ROOT / "state" / "media" / (sha + "." + ext)
        if saved.is_symlink() or not saved.is_file() or hashlib.sha256(saved.read_bytes()).hexdigest() != sha:
            raise ValueError("Missing or changed archived image")
        paths.append(str(saved))
    for args in (["add", "--", *paths], ["commit", "-m", "Record publication state"], ["push", "origin", "HEAD:main"]):
        subprocess.run(["git", *args], cwd=ROOT, check=True)

def fingerprint(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = " ".join(re.findall(r"\w+", normalized))
    return hashlib.sha256(normalized.encode()).hexdigest()

def duplicate(item, directory):
    digest = fingerprint(item["text"])
    for path in directory.glob("*.json"):
        previous = json.loads(path.read_text())
        if previous.get("fingerprint") == digest:
            return True
    return False

def queue_paths(day):
    return sorted(p for p in (ROOT / "queue").glob(day + "*.json")
                  if re.fullmatch(re.escape(day) + r"(?:-[A-Za-z0-9_-]{1,64})?\.json", p.name))

def main():
    day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    for path in queue_paths(day):
        publish_one(path, day)

def publish_one(path, day, *, reviewed_now=False):
    if path.stat().st_size > 24000: raise ValueError("Queue too large")
    item = validate(json.loads(path.read_text()), day)
    if not reviewed_now and not due(item, datetime.datetime.now(datetime.timezone.utc), os.environ.get("TIMED_ONLY") == "true"):
        print("Not due or outside scheduled delivery window; no publication"); return
    if reviewed_now:
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    legacy = ROOT / "state" / (day + ".json")
    if legacy.exists() and not json.loads(legacy.read_text()).get("fingerprint"):
        raise RuntimeError("Legacy receipt lacks fingerprint; reconcile before publishing")
    receipt = ROOT / "state" / (fingerprint(item["text"]) + ".json")
    if receipt.exists(): print("Already claimed; inspect receipt"); return
    if duplicate(item, ROOT / "state"):
        print("Duplicate content blocked"); return
    digest = fingerprint(item["text"])
    visual = item.get("visual")
    png = render(visual) if visual else None
    if item.get("approved_image"):
        try:
            from . import pro_images
        except ImportError:
            import pro_images
        png = pro_images.load(ROOT,item["approved_image"])
    if item.get("ai_image"):
        try:
            from . import pro_images
        except ImportError:
            import pro_images
        png = pro_images.load_generated(ROOT,item["ai_image"])
    if item.get("link_preview", {}).get("poster_url") == "local:v2-approved-assets":
        render_v2_assets()
    if os.environ.get("LIVE_PUBLISH") != "true":
        print("Dry run: queue and visual validated; no network request"); return
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token: raise ValueError("Missing secret")
    _, _, profile = request("https://api.linkedin.com/v2/userinfo", token)
    member = profile["sub"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", member): raise ValueError("Invalid member ID")
    author = "urn:li:person:" + member
    if item.get("link_preview"):
        publish_clickable_article(item, author, token, receipt, digest, day, path)
        return
    share = {"shareCommentary":{"text":item["text"]},"shareMediaCategory":"NONE"}
    if png:
        _, _, reg = request("https://api.linkedin.com/v2/assets?action=registerUpload", token, {"registerUploadRequest":{"recipes":["urn:li:digitalmediaRecipe:feedshare-image"],"owner":author,"serviceRelationships":[{"relationshipType":"OWNER","identifier":"urn:li:userGeneratedContent"}]}})
        value = reg["value"]
        url = value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        request(url, token, raw=png, method="PUT")
        share.update({"shareMediaCategory":"IMAGE","media":[{"status":"READY","media":value["asset"],"description":{"text":visual["title"] if visual else "AI-generated conceptual illustration" if item.get("ai_image") else "Reviewed source image"}}]})
    media = {"published_media": archive_visual(png, "png")} if png else {}
    record(receipt, {"status":"claimed","fingerprint":digest,"date":day,"queue":path.name,**media})
    status, headers, _ = request("https://api.linkedin.com/v2/ugcPosts", token, {"author":author,"lifecycleState":"PUBLISHED","specificContent":{"com.linkedin.ugc.ShareContent":share},"visibility":{"com.linkedin.ugc.MemberNetworkVisibility":"PUBLIC"}})
    if status != 201 or not headers.get("X-RestLi-Id"): raise RuntimeError("Publication uncertain; inspect manually")
    record(receipt, {"status":"published","post_id":headers["X-RestLi-Id"],"visual":bool(png),"fingerprint":digest,"date":day,"queue":path.name,**media})

if __name__ == "__main__":
    main()
