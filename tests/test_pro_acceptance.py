import io
import json
import unittest
from PIL import Image
from scripts import pro_acceptance as acceptance, pro_assistant as pro, ai_visual

class ReleaseAcceptanceTests(unittest.TestCase):
    def transport(self,endpoint,key,body):
        if endpoint==pro.SEARCH:
            return {"results":[{"url":"https://aws.amazon.com/training/","content":"Cloud training resources"}]}
        return {"choices":[{"message":{"content":json.dumps({"title":"Cloud learning","text":"Explore AWS training.","sources":["S1"]})}}]}
    def test_current_runtime_local_acceptance_without_network(self):
        acceptance.verify(transport=self.transport,env={"TAVILY_API_KEY":"fixture","GROQ_API_KEY":"fixture"})
    def test_optional_artwork_acceptance_and_failure(self):
        env={"TAVILY_API_KEY":"fixture","GROQ_API_KEY":"fixture","PRO_IMAGE_ENABLED":"true",
             "PRO_IMAGE_FREE_ONLY":ai_visual.ACK,"CLOUDFLARE_ACCOUNT_ID":"a"*32,"CLOUDFLARE_IMAGE_TOKEN":"x"*25}
        out=io.BytesIO()
        Image.new("RGB",(512,512),"navy").save(out,format="PNG")
        acceptance.verify("ai-illustration",transport=self.transport,image_transport=lambda *_:out.getvalue(),env=env)
        with self.assertRaisesRegex(ValueError,"not a passed artwork acceptance"):
            acceptance.verify("ai-illustration",transport=self.transport,image_transport=lambda *_:b"bad",env=env)
        with self.assertRaisesRegex(ValueError,"not configured"):
            acceptance.verify("ai-illustration",transport=self.transport,env={})
