"""Manual release acceptance using a temporary workspace. Never publishes."""
import datetime as dt
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from . import ai_visual, content_studio as studio, pro_assistant as pro, pro_recovery

def require(condition, message):
    if not condition:
        raise ValueError(message)

def verify(style="original", *, transport=pro.call, image_transport=ai_visual.fetch, env=None):
    env=os.environ if env is None else env
    require(style in {"original","ai-illustration"}, "Unsupported acceptance style")
    if style!="original":
        require(ai_visual.configured(env),"Optional image provider is not configured for Workers Free")
    when=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).replace(second=0,microsecond=0)
    request={"topic":"AWS beginner cloud training","instructions":"Find current free learning options and include the official course link. Do not claim certificates without evidence.",
             "date":when.date().isoformat(),"scheduled_at":when.isoformat(),"domains":["aws.amazon.com","skillbuilder.aws","AWS.AMAZON.COM"," aws.amazon.com ","skillbuilder.aws","aws.amazon.com"],"visual_mode":style}
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)/"review"
        queued=Path(folder)/"queue-check"
        root.mkdir()
        queued.mkdir()
        draft=pro.generate(root,request,env.get("TAVILY_API_KEY"),env.get("GROQ_API_KEY"),env.get("PRO_AI_MODEL","openai/gpt-oss-20b"),transport)
        if style!="original":
            result=ai_visual.apply(root,draft,style,env=env,transport=image_transport)
            require(result=="generated","Live AI artwork unavailable; local fallback is available but not a passed artwork acceptance")
        pro_recovery.validate_visuals([draft],root=root)
        studio.validate_draft(draft)
        require(bool(draft["sources"]),"No grounded sources")
        pro.save_generated(root,[draft],"review")
        require(studio.status(root,studio.read_draft(root,draft["id"]))=="draft","Review mode must remain unapproved")
        require(not (root/"queue").exists(),"Review mode must not queue")
        if draft.get("ai_image"):
            asset=studio.pro_images.asset_path(root,draft["ai_image"]["sha256"])
            destination=studio.pro_images.asset_path(queued,draft["ai_image"]["sha256"])
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(asset,destination)
        pro.save_generated(queued,[draft],"queue")
        saved=studio.read_draft(queued,draft["id"])
        require(studio.status(queued,saved)=="queued","Auto-queue did not create exact approved queue entry")
        path=queued/"queue"/studio.queue_name(saved)
        require(studio.load(path)==studio.payload(saved),"Queued content differs from approved draft")
        with patch.object(studio.publish,"ROOT",queued),patch.dict(os.environ,{"LIVE_PUBLISH":"false","LINKEDIN_ACCESS_TOKEN":""}),patch.object(studio.publish,"request",side_effect=AssertionError("Unexpected LinkedIn request")) as network:
            studio.publish.publish_one(path,saved["date"],reviewed_now=True)
            require(not network.called,"Dry run contacted LinkedIn")
        require(not (queued/"state").exists(),"Dry run created a publication receipt")
        print("PASS: grounded generation, visual validation, review-only saving, auto-queue and publisher dry run. Temporary workspace removed on exit. No LinkedIn call.",flush=True)

def main():
    try:
        verify(os.environ.get("ACCEPTANCE_STYLE","original"))
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,AssertionError) as err:
        # Avoid echoing provider responses or unpublished post content.
        safe={"Optional image provider is not configured for Workers Free","Live AI artwork unavailable; local fallback is available but not a passed artwork acceptance"}
        reason=str(err) if str(err) in safe else pro.safe_reason(err)
        raise SystemExit("Acceptance failed: "+reason+". No LinkedIn publication attempted.") from None

if __name__=="__main__":
    main()
