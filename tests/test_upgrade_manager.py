import unittest
import tempfile
import pathlib
import subprocess
from scripts.upgrade_manager import FILES, MARKER, snapshot, upgrade, rollback

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name) / "v1"
        self.source = pathlib.Path(self.temp.name) / "v2"
        self.root.mkdir()
        self.source.mkdir()
        for name in ("scripts/publish.py", ".github/workflows/publish.yml", "requirements.txt", "queue/2026-11-25.json", "state/claimed.json", "state/published.json"):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(name)
        for name in FILES:
            p = self.source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(name)
        for args in (["init"], ["config","user.email","test@example.invalid"], ["config","user.name","Test"], ["add","."], ["commit","-m","fixture"]):
            subprocess.run(["git","-C",str(self.root),*args],check=True,capture_output=True)

    def test_upgrade_rollback(self):
        before = snapshot(self.root)
        upgrade(self.root,self.source)
        self.assertEqual(snapshot(self.root),before)
        self.assertTrue((self.root / MARKER).exists())
        rollback(self.root)
        self.assertEqual(snapshot(self.root),before)
        self.assertFalse((self.root / MARKER).exists())

    def test_dirty_refused(self):
        (self.root / "queue/2026-11-25.json").write_text("changed")
        with self.assertRaises(ValueError):
            upgrade(self.root,self.source)

    def test_missing_source(self):
        (self.source / FILES[-1]).unlink()
        with self.assertRaises(ValueError):
            upgrade(self.root,self.source)
        self.assertFalse((self.root / FILES[0]).exists())

    def test_modified_v2_refused(self):
        upgrade(self.root,self.source)
        (self.root / FILES[0]).write_text("changed")
        with self.assertRaises(ValueError):
            rollback(self.root)
        self.assertTrue((self.root / MARKER).exists())

    def test_new_receipt_survives_rollback(self):
        upgrade(self.root,self.source)
        p = self.root / "state/new.json"
        p.write_text("new receipt")
        rollback(self.root)
        self.assertEqual(p.read_text(),"new receipt")
