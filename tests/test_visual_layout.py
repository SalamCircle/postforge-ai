import unittest
from io import BytesIO
from PIL import Image, ImageDraw
from unittest.mock import patch
from scripts.publish import render, visual_theme

class VisualLayoutTests(unittest.TestCase):
    def test_variants_and_output_dimensions(self):
        for count in (2, 3, 4):
            visual = {
                "title": "Reliable AI publishing systems",
                "points": ["Review credentials before authorising integrations",
                           "Check original source material before publishing",
                           "Prevent duplicate public messages",
                           "Investigate uncertain API requests before retrying"][:count],
            }
            result = render(visual)
            image = Image.open(BytesIO(result))
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1200,1200))
            self.assertGreater(len(result), 15000)

    def test_editorial_visual_is_deterministic_and_number_prefix_is_not_repeated(self):
        visual = {"title": "Think like a cyber defender: the 30-minute challenge",
                  "points": ["Study one adversary technique", "Identify relevant security evidence",
                             "Plan an investigation and check false positives",
                             "Challenge with AI. Verify with evidence."]}
        numbered = dict(visual, points=[f"{i+1:02d} | {point}" for i, point in enumerate(visual["points"])])
        result = render(visual)
        self.assertEqual(result, render(numbered))
        self.assertEqual(result, render(visual))
        image = Image.open(BytesIO(result))
        for y, colour in [(480, (54,207,234)), (637, (124,158,255)), (794, (83,223,192)), (951, (195,162,255))]:
            self.assertEqual(image.getpixel((91, y)), colour)

    def test_long_valid_points(self):
        point = "Check the source and verify the evidence before approving automated publication"
        self.assertLessEqual(len(point), 80)
        result = render({"title": "Responsible AI publishing and verification", "points": [point]*4})
        self.assertEqual(Image.open(BytesIO(result)).size, (1200,1200))

    def test_topic_themes_and_long_unbroken_terms(self):
        themes = [visual_theme({"title": t, "points": ["First insight", "Second insight"]})[0] for t in ("Cyber security", "Cloud engineering", "AI models", "Professional habits")]
        self.assertEqual(len(set(themes)), 4)
        for title in ("AI models", "Cloud architecture", "Cyber security", "Professional habits"):
            result = render({"title": title, "points": ["W"*80, "Short takeaway"]})
            self.assertEqual(Image.open(BytesIO(result)).size, (1200,1200))

    def test_standard_visual_has_no_automatic_product_branding(self):
        drawn = []
        original = ImageDraw.ImageDraw.text
        def record(self, xy, text, *args, **kwargs):
            drawn.append(text)
            return original(self, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, "text", record):
            render({"title": "Cyber security lessons", "points": ["Verify evidence", "Review alerts"]})
        self.assertIn("SECURITY / FIELD NOTES", drawn)
        self.assertIn("Cyber security lessons", drawn)
        for item in ("POSTFORGE AI", "PRO", "PF / AI", "RESEARCH  •  CREATE  •  PUBLISH"):
            self.assertNotIn(item, drawn)
