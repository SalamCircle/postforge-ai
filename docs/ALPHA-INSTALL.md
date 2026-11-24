# V2 alpha — developer preview only
Use a local checkout of this public branch. Run `python -m unittest discover -s tests -v` before use. For a simulated migration use a disposable clean V1 clone and `python scripts/upgrade_manager.py upgrade /path/to/test-v1 --source .`. Do not enable live publishing or migrate production using this preview. Existing V1 users can stay on main. The automatic production workflow is not released.

## Existing V1 users: upgrade contract
Upgrade in the same private repository. Preserve LINKEDIN_ACCESS_TOKEN and LIVE_PUBLISH exactly as configured; never copy, print, rotate or request the token. LIVE_PUBLISH is a repository variable, not a secret. The alpha manager does not change either setting. Before production migration, suspend publishing and other writers and wait for active jobs; restore the previous publishing configuration only after verification. Never enable publishing if it was previously disabled. Expired tokens or additional LinkedIn permissions may require separate authorisation.

## Continue with your preferred LLM
Connect or otherwise grant your chosen LLM access to your private repository. Ask it to inspect VERSION, read docs/V2.md and use existing queue and state files. Never paste credentials into chat. Existing V1 publishing continues through its original workflow; V2 alpha tools only inspect history and prepare drafts or schedule previews. No bundled LLM API key is required. Live V2 engagement and automatic production upgrade are not yet available.
