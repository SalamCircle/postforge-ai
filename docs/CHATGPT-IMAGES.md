# Use an exact ChatGPT-generated poster

PostForge supports a locally supplied, user-attested ChatGPT PNG without an additional image API, paid provider or payment card. This is separate from the optional Cloudflare image engine. It does not establish cryptographic model provenance.

## Stage the original

On your own authenticated **private** PostForge deployment, save the original PNG and run from the repository root:

```sh
python -m pip install -r requirements.txt
python -m scripts.stage_chatgpt_image "/path/to/poster.png" --confirm "I CONFIRM THIS IS MY CHATGPT GENERATED IMAGE"
```

The command prints a SHA-256-addressed asset path and `ai_image` metadata. It validates the PNG (single frame, bounded dimensions and maximum 5 MB), preserves the exact bytes and refuses an invalid or altered image. Commit only that asset to your private repository using your own authorised Git client; never add private images, content or credentials to the public template. Staging an asset alone does not publish.

For a connector that can upload binary data directly, the same contract is `studio/assets/<sha256>.png` with the original PNG bytes and `ai_image: {"sha256":"<verified digest>","model":"chatgpt:user-attested"}`. The attestation must come from the user. Verify the actual stored bytes before queuing. If the connector cannot transfer bytes, stage the original locally; do not fabricate a hash or substitute another poster.

## Publish or schedule

Use the metadata in the reviewed draft or authorised queue JSON. Include the exact disclosure `AI-generated conceptual illustration (not an official image).` in the caption. Do not also set `visual`, `approved_image` or `link_preview`. Retain all normal scheduling, duplicate protection, approval and receipt requirements. Missing, altered or invalid bytes fail closed. LinkedIn may resize displayed media, but the publisher sends and archives the exact validated PNG.

No new credentials or provider configuration are required. GitHub Actions and LinkedIn usage limits still apply.
