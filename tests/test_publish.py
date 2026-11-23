import unittest
from scripts.publish import validate, upload_url_ok, render

class PublisherTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate({"date":"2026-01-01","text":"Example"},"2026-01-01")["text"],"Example")
    def test_invalid(self):
        for item in ({"date":"wrong","text":"x"},{"date":"2026-01-01","text":""},{"date":"2026-01-01","text":"x","visual":{"title":"x","points":[]}}):
            with self.assertRaises(ValueError): validate(item,"2026-01-01")
    def test_hosts(self):
        self.assertTrue(upload_url_ok("https://www.linkedin.com/upload"))
        for url in ("https://linkedin.com.evil.test/x","http://www.linkedin.com/x","https://evil.test/x","https://user@www.linkedin.com/x"):
            self.assertFalse(upload_url_ok(url))
    def test_render(self):
        self.assertTrue(render({"title":"Security basics","points":["Check links","Use MFA"]}).startswith(b"\x89PNG"))

if __name__ == "__main__": unittest.main()
