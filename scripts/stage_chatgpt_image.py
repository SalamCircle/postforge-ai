"""Stage a local ChatGPT PNG without contacting any image provider."""
import argparse
import json
from pathlib import Path
from . import pro_images


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image",type=Path)
    parser.add_argument("--confirm",required=True)
    args=parser.parse_args()
    with args.image.open("rb") as f:
        raw=f.read(pro_images.MAX_BYTES+1)
    root=Path(__file__).resolve().parents[1]
    meta=pro_images.stage_chatgpt(root,raw,args.confirm)
    print(json.dumps({"asset_path":"studio/assets/"+meta["sha256"]+".png","ai_image":meta},indent=2))


if __name__=="__main__":
    main()
