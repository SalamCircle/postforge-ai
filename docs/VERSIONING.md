# PostForge AI — edition strategy

## V1: Publishing Engine
Existing main branch and public community edition remain unchanged. On-demand and daily scheduled publishing, images, receipts and duplicate protection continue independently.

## V2: Professional Presence Manager (development preview)
Separate release and deployment, with its own README, setup, visual guide, tests and permission matrix. V2 must preserve V1 publishing capabilities before release. Offline planning is implemented; live engagement and custom-time execution are not yet verified.

## Choose your deployment
- Stay on V1: no migration or configuration changes.
- Upgrade: back up the private deployment, stop V1 live publishing, reconcile claimed receipts, copy queue and state for the SAME account, configure V2 privately, run dry tests, verify account identity and only then enable V2. Never run both live publishers for the same account during migration.
- Use both: create two independent private repositories for different authorised accounts. Each must have its own LinkedIn token, queue, state, Actions settings and explicit live opt-in. Do not copy receipts between accounts. Follow LinkedIn account and API terms.

## Release gates
Keep public V1 main unchanged. Publish V2 as a separate distribution only after regression, security and permission tests pass. No mandatory paid dependencies; third-party quotas and optional charges apply. Never ship personal credentials, private queues or receipts in public source.

V2 profile editing remains draft-only unless official access is granted. Comments, reactions, edits and deletes remain offline plans until endpoint access and ownership checks are verified. No scraping or permission bypass.
