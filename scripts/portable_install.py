"""Offline, review-first installer for a clean, trusted PostForge Pro source checkout.
No network calls, credential reads, scheduling changes, automatic commits or pushes.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FILES = tuple([
  "VERSION",
  ".postforge-installation.json",
  "requirements.txt",
  "scripts/publish.py",
  "scripts/content_studio.py",
  "scripts/mobile_action.py",
  "scripts/publish_reviewed.py",
  "scripts/pro_images.py",
  "scripts/pro_recovery.py",
  "scripts/pro_assistant.py",
  "scripts/smart_visual.py",
  "scripts/ai_visual.py",
  "scripts/studio_dashboard.py",
  "scripts/pro_acceptance.py",
  "scripts/v2_manager.py",
  "scripts/upgrade_manager.py",
  "scripts/portable_install.py",
  "dashboard/app.js",
  "dashboard/index.html",
  "dashboard/style.css",
  ".github/workflows/publish.yml",
  ".github/workflows/timed-publish.yml",
  ".github/workflows/mobile-studio.yml",
  ".github/workflows/studio-review.yml",
  ".github/workflows/publish-reviewed.yml",
  ".github/workflows/pro-ai.yml",
  ".github/workflows/pro-release-acceptance.yml",
  ".github/workflows/core-verify.yml",
  ".github/workflows/tests.yml",
  "tests/test_ai_visual.py",
  "tests/test_content_studio.py",
  "tests/test_duplicates.py",
  "tests/test_image_upload.py",
  "tests/test_link_preview.py",
  "tests/test_mobile_action.py",
  "tests/test_multi_post.py",
  "tests/test_pro_acceptance.py",
  "tests/test_pro_assistant.py",
  "tests/test_pro_domains.py",
  "tests/test_pro_images.py",
  "tests/test_pro_recovery.py",
  "tests/test_publish.py",
  "tests/test_smart_visual.py",
  "tests/test_studio_dashboard.py",
  "tests/test_upgrade_manager.py",
  "tests/test_v2_manager.py",
  "tests/test_visual_layout.py",
  "tests/test_mobile_api.mjs",
  "tests/test_mobile_vault.mjs",
  "tests/mobile_browser_smoke.py",
  "tests/test_portable_install.py",
  "docs/mobile/api.mjs",
  "docs/mobile/app.mjs",
  "docs/mobile/index.html",
  "docs/mobile/style.css",
  "docs/mobile/sw.js",
  "docs/mobile/vault.mjs",
  "docs/mobile/logo.svg",
  "docs/mobile/logo-pro.svg",
  "docs/mobile/logo-shared.svg",
  "docs/mobile/icon-192.svg",
  "docs/mobile/icon-512.svg",
  "docs/mobile/manifest.webmanifest",
  "docs/mobile/trust.html",
  "docs/mobile/terms.html",
  "docs/mobile/privacy.html",
  "docs/mobile/responsible-ai.html",
  "docs/assets/logo-v2.svg",
  "docs/assets/edition-v1.svg",
  "docs/assets/edition-v2.svg",
  "docs/assets/edition-v2-pro.svg",
  "docs/assets/upgrade-v1-v2.svg",
  "docs/assets/upgrade-v2-pro.svg",
  "docs/assets/edition-install-web-app.svg",
  "docs/assets/pages-setup.svg",
  "docs/assets/install-web-app.svg",
  "docs/assets/v2-token-setup.svg",
  "docs/assets/v2-editing-setup.svg",
  "docs/assets/v2-workspace-connect.svg",
  "docs/assets/v2-review-publish.svg",
  "docs/assets/pro-groq-key.svg",
  "docs/assets/pro-tavily-key.svg",
  "docs/assets/pro-groq-secret.svg",
  "docs/assets/pro-tavily-secret.svg",
  "docs/assets/pro-model-variable.svg",
  "docs/assets/pro-enable-variable.svg",
  "docs/assets/pro-first-research.svg",
  "docs/assets/setup-detail-01.svg",
  "docs/assets/setup-detail-02.svg",
  "docs/assets/setup-detail-03.svg",
  "docs/assets/setup-detail-04.svg",
  "docs/assets/setup-detail-05.svg",
  "docs/assets/setup-detail-06.svg",
  "docs/assets/setup-detail-07.svg",
  "docs/assets/setup-detail-08.svg",
  "docs/assets/pro-setup-flow.svg",
  "docs/CONTENT-STUDIO.md",
  "docs/V2-PRO.md",
  "docs/VISUAL-SETUP.md",
  "docs/MOBILE.md",
  "docs/EDITION-SETUP.md",
  "docs/VERSIONING.md",
  "docs/V2.md",
  "docs/PORTABLE-INSTALL.md",
  "examples/studio-brand.json",
  "examples/studio-draft.json"
])
SOURCE = Path(__file__).resolve().parents[1]

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def safe_path(root, name):
    path = root / name
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
        raise ValueError("Symlink refused: " + name)
    if path.exists() and not path.is_file():
        raise ValueError("Expected regular file: " + name)
    return path

def protected(root):
    result = {}
    for directory in ("queue", "state", "studio", "scheduled"):
        base = root / directory
        if base.is_symlink():
            raise ValueError("Symlink refused: " + directory)
        if not base.exists():
            continue
        if not base.is_dir():
            raise ValueError("Expected directory: " + directory)
        for p in base.rglob("*"):
            if p.is_symlink():
                raise ValueError("Symlink in protected data")
            if p.is_file():
                result[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return result

def clean(root):
    if root != Path(git(root, "rev-parse", "--show-toplevel")).resolve():
        raise ValueError("Select the repository root")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Repository must be clean")

def plan(root, source=SOURCE):
    root, source = root.resolve(), source.resolve()
    if root == source or root in source.parents or source in root.parents:
        raise ValueError("Source and destination must be separate checkouts")
    clean(root)
    clean(source)
    if git(root, "branch", "--show-current") != "main":
        raise ValueError("Use the private target main branch")
    readme = safe_path(root, "README.md")
    workflow = safe_path(root, ".github/workflows/publish.yml")
    if not readme.exists() or not re.search(r"^# PostForge AI(?:\s|$)", readme.read_text(), re.M):
        raise ValueError("Not a recognised PostForge deployment")
    if not workflow.exists() or "name: PostForge Publisher" not in workflow.read_text():
        raise ValueError("Missing publisher signature")
    version_path = safe_path(root, "VERSION")
    version = version_path.read_text().strip() if version_path.exists() else "1.x"
    if not (version == "1.x" or re.fullmatch(r"[12]\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version)):
        raise ValueError("Unsupported version")
    # Never copy personal data, launch workflow, .git, secrets or old rollback metadata.
    files = []
    for name in FILES:
        src, dst = safe_path(source, name), safe_path(root, name)
        if not src.is_file():
            raise ValueError("Incomplete release source: " + name)
        before = sha(dst.read_bytes()) if dst.exists() else None
        after = sha(src.read_bytes())
        if before != after:
            files.append({"path": name, "before": before, "after": after})
    result = {"target_head": git(root, "rev-parse", "HEAD"), "source_head": git(source, "rev-parse", "HEAD"),
              "target_version": version, "changes": files}
    result["plan_sha256"] = sha(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
    return result

def apply(root, source=SOURCE, expected="", verify=True):
    root, source = root.resolve(), source.resolve()
    current = plan(root, source)
    if not re.fullmatch(r"[a-f0-9]{64}", expected) or current["plan_sha256"] != expected:
        raise ValueError("Plan changed or was not explicitly reviewed")
    if not current["changes"]:
        return current
    before = protected(root)
    originals = {}
    created_dirs = []
    try:
        for entry in current["changes"]:
            name = entry["path"]
            src, dst = safe_path(source, name), safe_path(root, name)
            blob = src.read_bytes()
            if sha(blob) != entry["after"]:
                raise ValueError("Source changed")
            prev = dst.read_bytes() if dst.exists() else None
            if (sha(prev) if prev is not None else None) != entry["before"]:
                raise ValueError("Target changed")
            for parent in reversed(list(dst.parents)):
                if root in parent.parents and not parent.exists():
                    parent.mkdir()
                    created_dirs.append(parent)
            originals[dst] = prev
            dst.write_bytes(blob)
        if protected(root) != before:
            raise ValueError("Protected data changed")
        if verify:
            # No provider credentials or publishing opt-ins are inherited.
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG", "LC_ALL")}
            env.update(LIVE_PUBLISH="false", TIMED_PUBLISH="false", PRO_AI_ENABLED="false", PYTHONDONTWRITEBYTECODE="1")
            subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=root, env=env, check=True)
        if protected(root) != before:
            raise ValueError("Protected data changed")
    except BaseException:
        for dst, old in reversed(list(originals.items())):
            if old is None:
                dst.unlink(missing_ok=True)
            else:
                dst.write_bytes(old)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    return current

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("plan", "apply"))
    p.add_argument("target", type=Path)
    p.add_argument("--expect", default="")
    a = p.parse_args()
    try:
        result = plan(a.target) if a.action == "plan" else apply(a.target, expected=a.expect)
        print(json.dumps(result, indent=2))
        if a.action == "apply":
            print("Applied and tested locally. Review git diff; nothing has been committed or pushed.")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        p.exit(1, "Installation refused: " + str(exc) + "\n")
if __name__ == "__main__":
    main()
