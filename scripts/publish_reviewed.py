"""Publish one explicitly reviewed and already queued studio post."""
import json
import os
import re
import subprocess
from scripts import content_studio as studio, publish, mobile_action

def publish_reviewed(root, request):
    if not isinstance(request, dict) or set(request) != {"action", "id", "digest", "confirmation", "head"} or request["action"] != "publish-now" or request["confirmation"] != "PUBLISH NOW":
        raise ValueError("Explicit publish-now confirmation required")
    head = request["head"]
    if not isinstance(head, str) or not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("Invalid workspace snapshot")
    if mobile_action.git("rev-parse", "HEAD").strip() != head or mobile_action.git("status", "--porcelain").strip():
        raise ValueError("Workspace changed; refresh before publishing")
    if os.environ.get("LIVE_PUBLISH") != "true" or not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        raise ValueError("Live publishing is disabled or credentials are missing")
    draft = studio.read_draft(root, request["id"])
    if studio.digest(draft) != request["digest"] or not studio.approval_valid(root, draft):
        raise ValueError("Current content requires explicit approval")
    if studio.status(root, draft) not in {"queued", "missed-review"}:
        raise ValueError("Only unclaimed exact queued posts may be published now")
    path = studio.path_for(root, "queue", studio.queue_name(draft))
    item = studio.load(path)
    if item != studio.payload(draft):
        raise ValueError("Queue content differs from reviewed draft")
    if draft.get("approved_image"):
        studio.pro_images.load(root, draft["approved_image"])
    if draft.get("ai_image"):
        studio.pro_images.load_generated(root, draft["ai_image"])
    # Existing publisher retains claim-before-send and duplicate protection.
    publish.publish_one(path, draft["date"], reviewed_now=True)
    receipt = studio.path_for(root, "state", publish.fingerprint(draft["text"]) + ".json")
    result = studio.load(receipt)
    if result.get("status") != "published" or not result.get("post_id") or result.get("queue") != path.name:
        raise ValueError("No confirmed publication receipt; reconcile before retrying")
    print("PASS: LinkedIn publication receipt recorded.", flush=True)

def main():
    try:
        raw = os.environ.get("MOBILE_PUBLISH_REQUEST", "")
        if not 1 <= len(raw.encode()) <= 4000:
            raise ValueError("Invalid request")
        publish_reviewed(studio.ROOT, json.loads(raw))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError):
        raise SystemExit("Publish now did not produce a confirmed receipt. Check queue, approval, live settings and claim history before retrying.") from None

if __name__ == "__main__":
    main()
