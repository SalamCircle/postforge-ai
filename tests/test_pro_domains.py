import unittest
from scripts import pro_assistant as pro

class SourceDomainsRegression(unittest.TestCase):
    def test_actual_failed_request(self):
        self.assertEqual(pro.normalize_domains(["github.com","microsoft.github.io","garak.ai","github.com","genai.owasp.org","owasp.org"]),["github.com","microsoft.github.io","garak.ai","genai.owasp.org","owasp.org"])

    def test_normalize_and_preserve_order(self):
        self.assertEqual(pro.normalize_domains([" GitHub.COM ","github.com","aws.amazon.com"]),["github.com","aws.amazon.com"])

    def test_invalid_or_excess_distinct_rejected(self):
        for value in (None,"github.com",[None],["https://github.com"],["github.com/path"],["github.com","a.example","b.example","c.example","d.example","e.example"]):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,"five official hostnames"):
                pro.normalize_domains(value)
