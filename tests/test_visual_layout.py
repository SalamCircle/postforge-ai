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
