# PostForge AI

<img src="docs/assets/logo.svg" width="120" alt="PostForge AI logo">

**Research. Create. Publish.**

MIT-licensed, LLM-independent publishing engine. LinkedIn is the first supported platform. External AI tools supply researched content; GitHub Actions validates, renders and publishes it using the member API.

## Choose your experience

[![V1 — Publishing Engine](docs/assets/edition-v1.svg)](#start-here--five-steps-to-publish)

[![V2 — Presence Manager development roadmap](docs/assets/edition-v2.svg)](docs/V2-ROADMAP.md)

**V1 remains the production edition. V2 is an unverified alpha preview, not a stable release.**

| New users | Existing V1 users |
| --- | --- |
| [**Start with V2 — Alpha Preview**](https://github.com/SalamCircle/postforge-ai/blob/v2-alpha/docs/INSTALL-V2.md) | [**Upgrade to V2 — Rehearsal only**](https://github.com/SalamCircle/postforge-ai/blob/v2-alpha/docs/ALPHA-INSTALL.md) |

Use a disposable private repository for V2 testing. Do not upgrade a live deployment or enable live engagement until verification is complete. Separate authorised accounts can use independent private deployments.

## Start here — five steps to publish

**From setup to your first post.**

Five simple steps. Your AI. Your timing. Tap each card to continue.

[![Step 1 — Create your private repository](docs/assets/setup-card-01.svg)](https://github.com/new)

[![Step 2 — Connect LinkedIn API](docs/assets/setup-card-02.svg)](https://www.linkedin.com/developers/apps)

[![Step 3 — Configure GitHub Secrets](docs/assets/setup-card-03.svg)](docs/START-HERE.md#step-5--store-your-token-securely)

[![Step 4 — Enable live publishing](docs/assets/setup-card-04.svg)](docs/START-HERE.md#step-8--verify-your-live-post)

[![Step 5 — Choose your AI and publish](docs/assets/setup-card-05.svg)](#publish-anytime--your-choice-of-ai)

[Full beginner walkthrough](docs/START-HERE.md) · [OAuth token tools](https://www.linkedin.com/developers/tools/oauth)

**Open your own private repository → Settings → Secrets and variables → Actions.** Use the Secrets tab for the token and the Variables tab for the live switch. Do not configure credentials in the public source repository.

## Publish anytime — your choice of AI

PostForge AI is free MIT-licensed software, not a bundled AI subscription. Draft with any LLM (ChatGPT, Gemini, Claude, a local model) or write manually. Review the content before saving it. No particular LLM API key is required by the publisher.

**On demand:** in your configured private deployment, create a unique `queue/YYYY-MM-DD-topic.json` file using today's UTC date and commit it to main. This triggers publishing automatically. Alternatively, open Actions → PostForge Publisher → Run workflow on main. The workflow processes today's queue, not future dates.

**Scheduled:** queue a future UTC date. The workflow checks daily at 9 AM UK time (with daylight-saving adjustment); GitHub may delay scheduled runs. For other time zones, adjust both the cron and time guard. Multiple unique posts per day are supported; identical content is blocked by persistent receipts.

Example queue content (replace the date with today's UTC date or your intended future date):

```json
{
  "date": "2026-11-24",
  "text": "Your reviewed LinkedIn post goes here."
}
```

Ask your preferred LLM: “Draft a factual LinkedIn post about my chosen topic. Return JSON with date and text, no invented claims, maximum 3000 characters.” Save it to the private queue only after reviewing it. Live publishing requires your own authorized LinkedIn token and explicit LIVE_PUBLISH opt-in. GitHub Actions quotas, LinkedIn API limits and optional AI provider fees apply; check your plan and avoid paid overages. See [Setup](docs/SETUP.md) and [verification](docs/VERIFY.md).

## Documentation
[LLM prompts](docs/PROMPTS.md) · [Security review](docs/AUDIT.md)

## Features
- Dated JSON queue and optional original PNG graphics.
- Explicit live opt-in, dry-run validation and persistent content-based claims and multiple posts per day.
- HTTPS endpoint restrictions and no redirect following.
- Automated unit tests and reusable provider-neutral prompts.

## Architecture

![Independent deployment architecture](docs/assets/architecture.svg)
External scheduler → private queue → GitHub Actions → LinkedIn API → publication receipt.

## Community edition status

This is the clean-history source distribution. It has **no deployment token or personal posting receipts**. Each user should create a private deployment with their own LinkedIn developer application and credentials. The included test suite and security audit must pass in each deployment. See [setup](docs/START-HERE.md).

## Licence
[MIT](LICENSE). See [Security](SECURITY.md) for responsible reporting.

## Multiple posts and duplicate protection

![Multi-post automation workflow](docs/assets/multi-post-flow.svg)

[Follow the visual multi-post scheduling and verification guide](docs/MULTI-POST.md). Choose your own publishing frequency, create unique queue files and preserve content-based receipts. The diagram illustrates intended behaviour; live verification is separate.
