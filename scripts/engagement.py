"""Experimental single-comment client. No background or bulk engagement."""
import argparse
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import hashlib
from pathlib import Path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def request(path, token, version, payload=None):
    if not path.startswith(("/rest/socialActions/", "/v2/userinfo")):
        raise ValueError("Unsupported endpoint")
    headers = {"Authorization": "Bearer " + token, "Linkedin-Version": version,
               "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    req = urllib.request.Request("https://api.linkedin.com" + path,
          data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
        return response.status, response.read(), response.headers.get("x-restli-id")

def prepare(target, text, version):
    if not re.fullmatch(r"urn:li:(share|ugcPost):[0-9]+", target):
        raise ValueError("Explicit share or ugcPost URN required")
    if not text.strip() or len(text) > 1250:
        raise ValueError("Comment must contain 1–1250 characters")
    if not re.fullmatch(r"20[0-9]{2}(0[1-9]|1[0-2])", version):
        raise ValueError("Specify a supported LinkedIn API version")
    return {"target": target, "text": text, "version": version}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("target")
    p.add_argument("text")
    p.add_argument("--version", required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    draft = prepare(a.target, a.text, a.version)
    print(json.dumps(draft, ensure_ascii=True, indent=2))
    if not a.execute:
        return
    if os.environ.get("LIVE_ENGAGEMENT") != "true":
        p.error("Engagement is disabled; separate explicit opt-in required")
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        p.error("Authorised token required in local environment")
    try:
        _, body, _ = request("/v2/userinfo", token, a.version)
        sub = json.loads(body)["sub"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sub):
            raise ValueError("Invalid member identity")
        actor = "urn:li:person:" + sub
        print("Acting as:", actor)
        if input("Type PUBLISH COMMENT to approve this exact action: ") != "PUBLISH COMMENT":
            return
        key = hashlib.sha256(json.dumps([actor,a.target,a.text], ensure_ascii=True).encode()).hexdigest()
        root = Path("state/engagement")
        root.mkdir(parents=True, exist_ok=True)
        claim = root / (key + ".json")
        with claim.open("x") as out:
            json.dump({"status":"claimed","target":a.target}, out)
        path = "/rest/socialActions/" + urllib.parse.quote(a.target, safe="") + "/comments"
        status, _, receipt = request(path, token, a.version,
            {"actor":actor,"object":a.target,"message":{"text":a.text}})
        claim.write_text(json.dumps({"status":"published","http_status":status,"id":receipt}))
        print("Comment accepted:", status)
    except urllib.error.HTTPError as exc:
        p.exit(1, "LinkedIn rejected request (HTTP %d). Review permissions and any claim; do not retry automatically.\n" % exc.code)
    except (OSError, ValueError, KeyError):
        p.exit(1, "Action not confirmed. Inspect any claim before retrying.\n")

if __name__ == "__main__":
    main()
