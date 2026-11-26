import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from scripts import pro_images, publish


def picture():
    out=io.BytesIO()
    Image.new("RGB",(1254,1254),"orange").save(out,format="PNG")
    return out.getvalue()


class ChatGPTImageTests(unittest.TestCase):
    def test_exact_bytes_and_disclosure(self):
        raw=picture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            meta=pro_images.stage_chatgpt(root,raw,pro_images.CHATGPT_CONFIRMATION)
            self.assertEqual(meta,{"sha256":hashlib.sha256(raw).hexdigest(),"model":"chatgpt:user-attested"})
            self.assertEqual(pro_images.load_generated(root,meta),raw)
            self.assertEqual(pro_images.stage_chatgpt(root,raw,pro_images.CHATGPT_CONFIRMATION),meta)
            day="2026-11-26"
            item={"date":day,"text":"Original poster. AI-generated conceptual illustration (not an official image).","ai_image":meta}
            self.assertEqual(publish.validate(item,day),item)
            with self.assertRaises(ValueError):
                publish.validate({**item,"text":"No disclosure"},day)
            with self.assertRaises(ValueError):
                publish.validate({**item,"visual":{"title":"Do not substitute","points":["One","Two"]}},day)
            pro_images.asset_path(root,meta["sha256"]).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                pro_images.load_generated(root,meta)

    def test_wrong_provenance_invalid_bytes_and_provider_path_rejected(self):
        raw=picture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):
                pro_images.stage_chatgpt(root,raw,"")
            with self.assertRaises(ValueError):
                pro_images.stage_chatgpt(root,b"\x89PNG\r\n\x1a\ninvalid",pro_images.CHATGPT_CONFIRMATION)
            with self.assertRaises(ValueError):
                pro_images.stage_generated(root,raw,pro_images.CHATGPT_IMAGE_MODEL)
            with self.assertRaises(ValueError):
                pro_images.validate_generated({"sha256":"a"*64,"model":"unverified-provider"})
            self.assertFalse((root/"studio").exists())
