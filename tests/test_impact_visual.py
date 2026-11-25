import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image, ImageDraw
from scripts import publish, smart_visual

class ImpactTests(unittest.TestCase):
    def fixture(self):
        return {"title":"Cybersecurity tools for defenders","points":["Build a practical security toolkit.","Verify your findings."],"layout":"impact","labels":["Splunk","Elastic","Wireshark","NetworkMiner","MITRE ATT&CK","TryHackMe"]}

    def test_original_six_card_visual(self):
        visual=self.fixture()
        with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            raw=publish.render(visual)
        im=Image.open(io.BytesIO(raw))
        self.assertEqual(im.size,(1200,1200))
        self.assertEqual(im.format,"PNG")
        self.assertGreater(len(raw),25000)
        self.assertEqual(raw,publish.render(visual))

    def test_layouts_themes_long_labels(self):
        for title in ("Cyber security","AI models","Cloud architecture","Professional skills"):
            for n in range(2,7):
                v=dict(self.fixture(),title=title,labels=["W"*80]*n)
                self.assertEqual(Image.open(io.BytesIO(publish.render(v))).size,(1200,1200))

    def test_no_unrequested_tool_or_brand(self):
        v=self.fixture()
        seen=[]
        original=ImageDraw.ImageDraw.text
        def capture(self,xy,text,*args,**kwargs):
            seen.append(text)
            return original(self,xy,text,*args,**kwargs)
        with patch.object(ImageDraw.ImageDraw,"text",capture):
            publish.render(v)
        for label in v["labels"]:
            self.assertIn(label,seen)
        self.assertNotIn("POSTFORGE AI",seen)
        self.assertNotIn("Nmap",seen)

    def test_smart_brief_grounded_and_local(self):
        with TemporaryDirectory() as tmp:
            draft={"title":"Security tools","topic":"Cybersecurity","text":"Study Splunk, Elastic, Wireshark, NetworkMiner, MITRE ATT&CK and TryHackMe.","sources":["https://example.org"]}
            smart_visual.apply(Path(tmp),draft,"original")
            self.assertEqual(draft["visual"]["labels"],self.fixture()["labels"])
            self.assertEqual(draft["visual"]["layout"],"impact")
            publish.validate({"date":"2030-01-01","text":draft["text"],"visual":draft["visual"]},"2030-01-01")
            self.assertNotIn("Nmap",draft["visual"]["labels"])

    def test_invalid_labels_rejected_and_legacy_works(self):
        for value in (["x"],["x"]*7,["x","bad\nlabel"],["x",9]):
            with self.assertRaises(ValueError):
                publish.validate({"date":"2030-01-01","text":"Post","visual":dict(self.fixture(),labels=value)},"2030-01-01")
        v=self.fixture();v.pop("labels");v.pop("layout")
        self.assertEqual(Image.open(io.BytesIO(publish.render(v))).size,(1200,1200))
