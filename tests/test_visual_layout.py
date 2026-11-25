import unittest
from io import BytesIO
from PIL import Image
from scripts.publish import render

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

    def test_branded_visual_is_deterministic_and_number_prefix_is_not_repeated(self):
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
