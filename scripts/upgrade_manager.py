"""Offline, additive upgrade manager. Never runs GitHub Actions or accesses tokens."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess

FILES = ("scripts/v2_manager.py", "tests/test_v2_manager.py", "docs/V2.md", "docs/VERSIONING.md", "scripts/upgrade_manager.py", "tests/test_upgrade_manager.py", "VERSION", "docs/assets/logo-v2.svg")
MARKER = ".postforge-v2.json"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

def safe(root, name):
    p = root / name
    if any(x.is_symlink() for x in (p, *p.parents) if x != root and root in x.parents):
        raise ValueError("Symlink refused")
    return p

def snapshot(root):
    result = {}
    for folder in ("queue", "state"):
        base = safe(root, folder)
        for p in sorted(base.rglob("*")):
            safe(root, str(p.relative_to(root)))
            if p.is_file():
                result[str(p.relative_to(root))] = digest(p)
    for name in ("scripts/publish.py", ".github/workflows/publish.yml", "requirements.txt"):
        p = safe(root, name)
        if not p.is_file():
            raise ValueError("Missing V1 file: " + name)
        result[name] = digest(p)
    return result

def clean(root):
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Working tree must be clean")

def upgrade(root, source):
    root, source = root.resolve(), source.resolve()
    clean(root)
    before = snapshot(root)
    names = (*FILES, MARKER)
    if any(safe(root, n).exists() for n in names):
        raise ValueError("Existing V2 files or marker; refusing overwrite")
    for n in FILES:
        if not safe(source, n).is_file():
            raise ValueError("Incomplete source: " + n)
    created = []
    try:
        for n in FILES:
            p = safe(root, n)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("xb") as out:
                created.append(p)
                out.write(safe(source, n).read_bytes())
        if snapshot(root) != before:
            raise ValueError("Protected files changed")
        manifest = {"version": 2, "base_commit": git(root, "rev-parse", "HEAD"),
                    "added": {n: digest(root / n) for n in FILES}}
        with (root / MARKER).open("x") as out:
            created.append(root / MARKER)
            json.dump(manifest, out, indent=2)
        return manifest
    except Exception:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise

def rollback(root):
    root = root.resolve()
    marker = safe(root, MARKER)
    data = json.loads(marker.read_text())
    if data.get("version") != 2 or set(data.get("added", {})) != set(FILES):
        raise ValueError("Invalid manifest")
    for n in FILES:
        if digest(safe(root, n)) != data["added"][n]:
            raise ValueError("Modified V2 file; manual review required")
    before = snapshot(root)
    for n in FILES:
        safe(root, n).unlink()
    marker.unlink()
    if snapshot(root) != before:
        raise ValueError("Protected files changed during rollback")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["inspect", "upgrade", "rollback"])
    p.add_argument("root", type=pathlib.Path)
    p.add_argument("--source", type=pathlib.Path)
    a = p.parse_args()
    if a.action == "inspect":
        print(json.dumps({"version": 2 if (a.root / MARKER).exists() else 1,
                          "protected_files": len(snapshot(a.root.resolve()))}))
    elif a.action == "upgrade":
        if not a.source: p.error("--source required")
        print(json.dumps(upgrade(a.root, a.source), indent=2))
    else:
        rollback(a.root)
        print("V2 additions removed; V1 data retained")

if __name__ == "__main__":
    main()
