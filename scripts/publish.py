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

def validate(item, day):
    if item.get("date") != day:
        raise ValueError("Date mismatch")
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
    return item

def request(url, token, payload=None, raw=None, method=None):
    if not upload_url_ok(url):
        raise ValueError("Untrusted endpoint")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "image/png" if raw is not None else "application/json", "X-Restli-Protocol-Version": "2.0.0"}
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

def render(visual):
    """Render a readable original square insight graphic without remote assets."""
    import io
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 1200), "#0C1D34")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 1152, 1152), radius=32, outline="#4FCBE7", width=3)
    draw.rounded_rectangle((95, 86, 315, 99), radius=6, fill="#4FCBE7")

    def font(size, bold=False):
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)

    def wrap(text, f, max_width):
        words = text.split()
        lines = []
        line = ""
        for word in words:
            if draw.textlength(word, font=f) > max_width:
                return None
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=f) <= max_width:
                line = candidate
            else:
                if line: lines.append(line)
                line = word
        if line: lines.append(line)
        return lines

    draw.text((100, 117), "TECHNOLOGY  /  PRACTICAL INSIGHTS", font=font(23, True), fill="#81DCEB")

    title = visual["title"]
    for title_size in range(72, 43, -2):
        title_font = font(title_size, True)
        title_lines = wrap(title, title_font, 980)
        if title_lines is not None and len(title_lines) <= 2:
            break
    else:
        raise ValueError("Visual title cannot fit")
    for idx, line in enumerate(title_lines):
        draw.text((100, 183 + idx * (title_size + 10)), line, font=title_font, fill="white")

    draw.line((100, 372, 1100, 372), fill="#31516A", width=2)
    draw.text((100, 403), "FOUR THINGS TO REMEMBER" if len(visual["points"]) == 4 else "PRACTICAL TAKEAWAYS", font=font(24, True), fill="#A1BFD3")

    points = visual["points"]
    cols = 1 if len(points) == 2 else 2
    count_rows = (len(points) + cols - 1) // cols
    gap = 26
    left, right = 100, 1100
    top, bottom = 472, 1060
    card_w = (right - left - gap * (cols - 1)) // cols
    card_h = (bottom - top - gap * (count_rows - 1)) // count_rows

    for index, point in enumerate(points):
        col = index % cols
        row = index // cols
        x0 = left + col * (card_w + gap)
        y0 = top + row * (card_h + gap)
        x1, y1 = x0 + card_w, y0 + card_h
        draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill="#18334D", outline="#244D63", width=2)
        draw.rounded_rectangle((x0+24, y0+27, x0+92, y0+90), radius=15, fill="#235A75")
        draw.text((x0+38, y0+41), f"{index+1:02d}", font=font(24,True), fill="#D4F7FF")
        content_left = x0+28
        max_text_width = card_w-56
        best = None
        for size in range(40, 25, -2):
            f = font(size, False)
            lines = wrap(point, f, max_text_width)
            if lines is None: continue
            line_height = size + 13
            available_height = card_h - 132
            if len(lines)*line_height <= available_height:
                best=(f,lines,line_height)
                break
        if best is None:
            raise ValueError("Visual point cannot fit card")
        f,lines,line_height = best
        for n,line in enumerate(lines):
            draw.text((content_left,y0+108+n*line_height),line,font=f,fill="#E3F2FC")

    draw.text((100, 1097), "LEARN  ·  BUILD  ·  TEST  ·  VERIFY",font=font(22,True),fill="#80B9C9")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()

def record(path, value):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    for args in (["add", str(path)], ["commit", "-m", "Record publication state"], ["push", "origin", "HEAD:main"]):
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

def publish_one(path, day):
    if path.stat().st_size > 24000: raise ValueError("Queue too large")
    item = validate(json.loads(path.read_text()), day)
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
    if os.environ.get("LIVE_PUBLISH") != "true":
        print("Dry run: queue and visual validated; no network request"); return
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token: raise ValueError("Missing secret")
    _, _, profile = request("https://api.linkedin.com/v2/userinfo", token)
    member = profile["sub"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", member): raise ValueError("Invalid member ID")
    author = "urn:li:person:" + member
    share = {"shareCommentary":{"text":item["text"]},"shareMediaCategory":"NONE"}
    if png:
        _, _, reg = request("https://api.linkedin.com/v2/assets?action=registerUpload", token, {"registerUploadRequest":{"recipes":["urn:li:digitalmediaRecipe:feedshare-image"],"owner":author,"serviceRelationships":[{"relationshipType":"OWNER","identifier":"urn:li:userGeneratedContent"}]}})
        value = reg["value"]
        url = value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        request(url, token, raw=png, method="PUT")
        share.update({"shareMediaCategory":"IMAGE","media":[{"status":"READY","media":value["asset"],"description":{"text":visual["title"]}}]})
    record(receipt, {"status":"claimed","fingerprint":digest,"date":day,"queue":path.name})
    status, headers, _ = request("https://api.linkedin.com/v2/ugcPosts", token, {"author":author,"lifecycleState":"PUBLISHED","specificContent":{"com.linkedin.ugc.ShareContent":share},"visibility":{"com.linkedin.ugc.MemberNetworkVisibility":"PUBLIC"}})
    if status != 201 or not headers.get("X-RestLi-Id"): raise RuntimeError("Publication uncertain; inspect manually")
    record(receipt, {"status":"published","post_id":headers["X-RestLi-Id"],"visual":bool(png),"fingerprint":digest,"date":day,"queue":path.name})

if __name__ == "__main__":
    main()
