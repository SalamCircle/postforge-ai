"""Apply one reviewed mobile action to a clean private checkout. No API calls."""
import json
import os
import re
import subprocess
from pathlib import Path
try:
    from . import studio_dashboard as dashboard, content_studio as studio, pro_images
except ImportError:
    import studio_dashboard as dashboard
    import content_studio as studio
    import pro_images

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = re.compile(r"(?:studio/brand\.json|studio/requests/[1-9][0-9]{0,19}\.json|studio/assets/[a-f0-9]{64}\.png|studio/(?:drafts|approvals|archive)/[a-z0-9][a-z0-9-]{0,47}\.json|queue/\d{4}-\d{2}-\d{2}-studio-[a-z0-9][a-z0-9-]{0,47}\.json)")
ACTIONS = {"brand", "draft", "revise", "import", "schedule", "approve", "export", "archive", "cancel", "stage-image", "reschedule", "delete", "delete-many"}

def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout

def apply(data):
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        raise ValueError("Unsupported mobile action")
    expected = data.pop("head", None)
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{40}", expected):
        raise ValueError("Missing snapshot commit")
    if git("rev-parse", "HEAD").strip() != expected or git("status", "--porcelain").strip():
        raise ValueError("Workspace changed; refresh before retrying")
    if data["action"]=="stage-image":
        draft=studio.read_draft(ROOT,data["id"])
        if studio.digest(draft)!=data["digest"] or studio.status(ROOT,draft) not in {"draft","approved"}:
            raise ValueError("Review the current unqueued draft before attaching an image")
        candidate={"url":data["url"],"source":data["source"]}
        if candidate not in draft.get("image_candidates",[]) or "visual" in draft or "ai_image" in draft:
            raise ValueError("Choose a discovered image candidate and remove generated visual first")
        draft["approved_image"]=pro_images.stage(ROOT,data["url"],data["source"],data.get("confirmation"))
        studio.save_draft(ROOT,draft,edit=True)
    else:
        dashboard.action(ROOT, data)
    commit_workspace()

def commit_workspace():
    names = git("status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    changed = []
    for entry in filter(None, names):
        if entry[:2] not in {"??", " M", " D"} or not ALLOWED.fullmatch(entry[3:]):
            raise ValueError("Unexpected workspace change")
        changed.append(entry[3:])
    if not changed:
        print("No changes required")
        return
    git("add", "--", *changed)
    git("diff", "--cached", "--check")
    git("config", "user.name", "postforge-studio")
    git("config", "user.email", "postforge-studio@users.noreply.github.com")
    git("commit", "-m", "Apply reviewed mobile studio action")
    git("push", "origin", "HEAD:main")
    print("Reviewed mobile action committed. No LinkedIn request made.")

def main():
    raw = os.environ.get("MOBILE_ACTION", "")
    if not 1 <= len(raw.encode()) <= 60000:
        raise ValueError("Invalid mobile action size")
    try:
        apply(json.loads(raw))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError):
        raise SystemExit("Mobile action refused or concurrent update; refresh and inspect the run before retrying.") from None

if __name__ == "__main__":
    main()
