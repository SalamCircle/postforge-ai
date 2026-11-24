# Start with PostForge AI V2

![PostForge AI V2](assets/logo-v2.svg)

**Developer preview — 2.0.0-alpha.1.** No V1 installation required. Live engagement and exact-time scheduling are not implemented. Do not enable production publishing until verification is complete.

## 1. Create a blank private repository

[Create your private repository](https://github.com/new). Select Private and do not initialise with a README, licence or gitignore. Check GitHub Actions billing and avoid paid overages.

## 2. Install V2 directly

On your computer with Git and Python installed, open PowerShell. Replace YOUR-OWNER and YOUR-REPO with your own new private repository.

```powershell
git clone --single-branch --branch v2-alpha https://github.com/SalamCircle/postforge-ai.git postforge-v2
cd postforge-v2
git remote rename origin upstream
git remote add origin https://github.com/YOUR-OWNER/YOUR-REPO.git
git branch -M main
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Stop if any command fails. Check that origin points to your private repository using git remote -v. Only after tests pass, run git push -u origin main. Do not push to the upstream repository. No tokens belong in the repository or command line.

## 3. Configure your account once

Follow [LinkedIn and secret setup](START-HERE.md#step-2--create-a-linkedin-developer-application). Keep LIVE_PUBLISH unset for dry runs. The publisher runs only in private repositories on main. Do not enable live publishing in this alpha until release verification is complete.

## 4. Connect your preferred LLM

Grant repository access to your chosen assistant. Ask it to read VERSION, docs/V2.md and docs/PROMPTS.md. V2 offline tools can inspect history, queue and draft actions. No additional LLM API key is bundled or required by PostForge.

## 5. Verify the installation

Run python scripts/v2_manager.py history and python scripts/v2_manager.py queue. Check VERSION is 2.0.0-alpha.1 and README displays the V2 logo. Run the publisher dry-run according to START-HERE.md, without enabling LIVE_PUBLISH. A successful dry run does not prove LinkedIn authentication.

Already using V1? Do not use this fresh installation route; see [upgrade preview](ALPHA-INSTALL.md).
