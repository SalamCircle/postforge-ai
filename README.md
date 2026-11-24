# PostForge AI

<img src="docs/assets/logo.svg" width="120" alt="PostForge AI logo">

**Research. Create. Publish.**

MIT-licensed, LLM-independent publishing engine. LinkedIn is the first supported platform. External AI tools supply researched content; GitHub Actions validates, renders and publishes it using the member API.

## Start here — five steps to publish

![PostForge AI quick-start flow](docs/assets/publish-anytime.svg)

| Step | What to do | Open setup |
|---|---|---|
| 01 | Create your own private deployment | [Create repository](https://github.com/new) |
| 02 | Enable LinkedIn API products and generate a token | [Developer apps](https://www.linkedin.com/developers/apps) · [OAuth tools](https://www.linkedin.com/developers/tools/oauth) |
| 03 | Add `LINKEDIN_ACCESS_TOKEN` as a repository secret | [Secrets walkthrough](docs/START-HERE.md#step-5--store-your-token-securely) |
| 04 | Run a dry test, then set `LIVE_PUBLISH` to `true` as a repository variable | [Variables and live mode](docs/START-HERE.md#step-8--verify-your-live-post) |
| 05 | Draft with your chosen AI and publish | [Publish anytime](#publish-anytime--your-choice-of-ai) |

[Full beginner walkthrough](docs/START-HERE.md) · [GitHub Secrets documentation](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) · [GitHub Variables documentation](https://docs.github.com/en/actions/learn-github-actions/variables)

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

## Quick start
Read [Setup](docs/SETUP.md), [LLM prompts](docs/PROMPTS.md) and [Security review](docs/AUDIT.md). Deploy in your own private repository with your own LinkedIn app and secret. Live publishing is disabled by default. Public copies cannot publish using the supplied workflow.

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

## Guided setup links

| Step | Open |
|---|---|
| Create private deployment | [Create repository](https://github.com/new) |
| Create developer application | [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps) |
| Request publishing access | [Share on LinkedIn instructions](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin) |
| Request identity access | [OpenID Connect instructions](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) |
| Generate member token | [OAuth tools](https://www.linkedin.com/developers/tools/oauth) |
| Secure token storage | [GitHub Secrets instructions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) |
| Configure connector | [GitHub installations](https://github.com/settings/installations) |
| Check tests | [Community CI](https://github.com/SalamCircle/postforge-ai/actions) |
| Inspect publication | [LinkedIn feed](https://www.linkedin.com/feed/) |

Follow the [full guided setup](docs/SETUP.md) before enabling live mode.

## Visual onboarding

[Illustrated setup guide](docs/SETUP.md) · [Verification walkthrough](docs/VERIFY.md)

![Setup checklist](docs/assets/setup-visual.svg)

![Verification checklist](docs/assets/verification.svg)

## Multiple posts and duplicate protection

![Multi-post automation workflow](docs/assets/multi-post-flow.svg)

[Follow the visual multi-post scheduling and verification guide](docs/MULTI-POST.md). Choose your own publishing frequency, create unique queue files and preserve content-based receipts. The diagram illustrates intended behaviour; live verification is separate.
