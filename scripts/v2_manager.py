"""Offline V2 planning tools. No network calls or credential access."""
import argparse
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIONS = {"comment", "reply", "reaction", "edit", "delete", "profile"}
REACTIONS = {"LIKE", "PRAISE", "APPRECIATION", "EMPATHY", "INTEREST", "ENTERTAINMENT"}

def plan(action, target, text=""):
    if action not in ACTIONS:
        raise ValueError("Unsupported action")
    if not isinstance(target, str) or not target.strip() or len(target) > 500:
        raise ValueError("Provide an explicit target")
    if not isinstance(text, str) or len(text) > 3000:
        raise ValueError("Invalid content")
    if action in {"comment", "reply", "edit", "profile"} and not text.strip():
        raise ValueError("Reviewed draft required")
    if action == "reaction" and text not in REACTIONS:
        raise ValueError("Unsupported reaction")
    return {"action": action, "target": target, "draft": text,
            "status": "draft_only", "approval_required": True,
            "live_execution": False}

def schedule_preview(local_time, timezone="Europe/London"):
    value = dt.datetime.fromisoformat(local_time)
    if value.tzinfo is not None:
        raise ValueError("Use local time without an offset")
    zone = ZoneInfo(timezone)
    first, second = value.replace(tzinfo=zone, fold=0), value.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("Ambiguous or nonexistent local time; choose another time")
    utc = first.astimezone(dt.timezone.utc)
    return {"local": first.isoformat(), "utc": utc.isoformat(),
            "status": "preview_only", "scheduled": False}

def history(root=ROOT):
    result = []
    for path in sorted((root / "state").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        result.append({k: item[k] for k in ("date", "status", "post_id", "queue") if k in item})
    return result

def queue(root=ROOT):
    return sorted(p.name for p in (root / "queue").glob("*.json")
                  if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9_-]{1,64})?\.json", p.name))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("history")
    sub.add_parser("queue")
    p = sub.add_parser("plan")
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("target")
    p.add_argument("--text", default="")
    s = sub.add_parser("schedule-preview")
    s.add_argument("local_time")
    s.add_argument("--timezone", default="Europe/London")
    a = parser.parse_args()
    if a.command == "history": result = history()
    elif a.command == "queue": result = queue()
    elif a.command == "plan": result = plan(a.action, a.target, a.text)
    else: result = schedule_preview(a.local_time, a.timezone)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
