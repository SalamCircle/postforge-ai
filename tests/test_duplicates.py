import json
import tempfile
import unittest
from pathlib import Path
from scripts.publish import fingerprint, duplicate

class DuplicateTests(unittest.TestCase):
    def test_normalized(self):
        self.assertEqual(fingerprint("Hello, WORLD!"), fingerprint("hello world"))
    def test_previous_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "2026-01-01.json").write_text(json.dumps({"status":"claimed","fingerprint":fingerprint("Example post")}))
            self.assertTrue(duplicate({"text":"EXAMPLE POST!"}, p))
            self.assertFalse(duplicate({"text":"Different post"}, p))
