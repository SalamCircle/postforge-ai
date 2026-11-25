"""Offline checks for the root-ready public dashboard and setup."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PublicHostingTests(unittest.TestCase):
    def test_root_entry_has_relative_dashboard(self):
        page = (ROOT / "index.html").read_text()
        self.assertIn("url=./docs/mobile/", page)
        self.assertIn('href="./docs/mobile/"', page)
        self.assertTrue((ROOT / ".nojekyll").is_file())
        for name in ("index.html", "app.mjs", "api.mjs", "style.css", "vault.mjs", "manifest.webmanifest", "sw.js"):
            self.assertTrue((ROOT / "docs/mobile" / name).is_file(), name)

    def test_guide_separates_private_publisher_and_public_host(self):
        guide = (ROOT / "docs/UNIFIED-HOSTING.md").read_text()
        self.assertIn("separate public website repository", guide)
        self.assertIn("main → / (root) → Save", guide)
        self.assertIn("Never connect the public copy as a publishing workspace", guide)
        self.assertIn("https://github.com/SalamCircle/postforge-ai/generate", guide)
