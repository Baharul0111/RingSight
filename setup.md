# RingSight — Setup (only what YOU must provide)
> Everything below needs your identity, your browser, or your approval — the coding agent cannot complete account-side controls for you. Everything else (installing tools, running commands, creating files, generating the synthetic data, writing the queries, building the UI, deploying from the repo) the coding agent does itself; none of that is listed here. Finish this file once, and the build never asks you for anything. Total time ≈ 45 minutes. Do items 1–4 on Friday evening before Claude Code starts.

## Checklist
- [x] 1. Hackathon registration confirmed (wemakedevs.org) — do today
- [x] 2. Anthropic Console: API key + workspace spending limit
- [x] 3. FalkorDB Cloud: free instance → connection string
- [x] 4. GitHub: signed in on this machine + public repo name chosen
- [x] 5. Render: account + web service created from the repo (after the first push) + env vars pasted
- [x] 6. UptimeRobot: free monitor on the live `/health` URL (after item 5)
- [x] 7. Cloudflare Worker cron (optional second pinger)
- [x] 8. Access keys for the demo (fixed choices)
- [x] 9. `.env` created and complete

## 1. Hackathon registration
**Why the project needs it:** the submission is made from your WeMakeDevs account; the registration panel is also where the team and the submission form live.
**Cost:** free   **Time:** ~3 minutes
**Steps:**
1. Go to https://www.wemakedevs.org/hackathons/falkordb.
2. Click **Sign in** (top right), create or use your WeMakeDevs account.
3. Back on the hackathon page click **Register now** (top right / in the Registration panel).
4. Confirm you are registered solo. Note where the **Submit** panel is — you will come back here on Sunday before 23:00 IST.
**You'll end with:** a registered status on the page.
**Where it goes:** nowhere in code — this is for the Sunday submission.
**Official guide:** https://www.wemakedevs.org/hackathons/falkordb/rules

## 2. Anthropic Console — API key and spending limit
**Why the project needs it:** Claude Sonnet 5.5 is the planner and judge, Opus 5.5 writes the narrative, Haiku 5.5 is the health probe; the workspace spending limit is the hard wall that makes the public demo safe.
**Cost:** from your existing $200 credit (plan ≈ $70–130)   **Time:** ~5 minutes
**Steps:**
1. Go to https://platform.claude.com/ and sign in.
2. Open **Settings → Workspaces** (left sidebar). Click **Create workspace**, name it `ringsight` (keeping the hackathon's spend separate from everything else).
3. In that workspace open **Limits** (or the workspace's **Settings** tab) and set the **monthly spend limit** to **120** USD. Save.
4. Open **API keys** (left sidebar), click **Create key**, choose the `ringsight` workspace, name it `ringsight-render`, click **Create**. Copy the key immediately — it is shown once.
**You'll end with:** a key starting with `sk-ant-api03-…`.
**Where it goes:** the `ANTHROPIC_API_KEY=` line of `.env`.
**Official guide (if a button has moved):** https://platform.claude.com/docs/en/api/getting-started · https://platform.claude.com/docs/en/build-with-claude/spend-limits

## 3. FalkorDB Cloud — free instance
**Why the project needs it:** the live deployment's graph. Free tier = 100 MB, no persistence, stopped after 1 idle day, deleted after 7 — the app's keep-alive and auto-reseed are designed around exactly this.
**Cost:** free (no card)   **Time:** ~10 minutes
**Steps:**
1. Go to https://app.falkordb.cloud and sign up (GitHub or e-mail).
2. Click **Create instance** (or **New instance**).
3. Pick the **Free** tier, a nearby region (any US region is fine; Render Free runs in Oregon), name it `ringsight`, click **Create**. Wait until the status shows running (1–2 minutes).
4. Open the instance. Copy the **host**, **port** (6379 or the one shown), **username** (usually `falkordb` or `default`) and **password** from the connection panel.
5. Assemble one line: `redis://USERNAME:PASSWORD@HOST:PORT` (if the panel offers a ready-made connection URL, use that).
**You'll end with:** a host like `r-xxxxxxxx.instance-xxxx.hc-xxxx.us-east-1.cloud.falkordb.io`, a port, and a password.
**Where it goes:** the `REDIS_URL=` line of `.env` (the whole `redis://…` line).
**Official guide:** https://docs.falkordb.com/cloud/tiers/free · https://docs.falkordb.com/getting-started/

## 4. GitHub — sign-in on this machine and the repository name
**Why the project needs it:** rule 10 requires a public repository; Claude Code pushes code and the keep-alive workflow needs the GitHub Actions free tier.
**Cost:** free   **Time:** ~5 minutes
**Steps:**
1. In a terminal run `gh auth login`, choose **GitHub.com → HTTPS → Login with a web browser**, complete the browser prompt. (If `gh` is not installed, Claude Code installs it; you only do the browser login.)
2. Decide the repository name. Default: **`ringsight`** under your personal account, **public**. The existing repository is https://github.com/Baharul0111/RingSight; initialise this folder and push there. Do not create another repository.
3. After the first push (Claude Code does it), open the repo → **Settings → Secrets and variables → Actions → New repository secret** and add `HEALTH_URL` = your Render URL + `/health` and `JUDGE_KEY` = the judge key from item 8. (Claude Code can set these with `gh secret set` once you are logged in — only do it by hand if it asks.)
**You'll end with:** `gh auth status` showing you logged in; a repo URL like `https://github.com/<you>/ringsight`.
**Where it goes:** the repo name is a fixed choice — tell it in the build prompt (already filled: `ringsight`). Nothing goes in `.env`.
**Official guide:** https://cli.github.com/manual/gh_auth_login

## 5. Render — the live web service
**Why the project needs it:** judges prefer a live deployment; Render Free hosts the single container at $0.
**Cost:** free (750 h/month per workspace — run **one** free service only)   **Time:** ~10 minutes, after Claude Code has pushed the repo
**Steps:**
1. Go to https://dashboard.render.com and sign up with **GitHub** (so it can see the repo).
2. Click **New +** (top right) → **Web Service**.
3. Choose **Build and deploy from a Git repository**, connect your GitHub if asked, select `ringsight`.
4. Settings: Name `ringsight` · Region **Oregon** · Runtime **Docker** (it will detect the `Dockerfile`) · Instance type **Free**.
5. Scroll to **Environment Variables** → **Add from .env** (paste the contents of your `.env`) or add each line by hand. Add also `PORT`=`8000` only if Render does not set it automatically (it normally does).
6. Click **Create Web Service**. Wait for the first deploy (3–6 minutes). Copy the public URL shown at the top (`https://ringsight.onrender.com` or similar).
7. Under **Settings → Health Check Path** set `/live` (not `/health` — the design keeps them separate).
**You'll end with:** a live URL; `<URL>/health` returns JSON.
**Where it goes:** tell Claude Code the URL (it is public, not a secret); it goes into the README first line, the GitHub Actions secret `HEALTH_URL`, and item 6.
**Official guide:** https://render.com/docs/free · https://render.com/docs/docker

## 6. UptimeRobot — free monitor and alert
**Why the project needs it:** tells you by e-mail if the demo goes down during judging week, and is a third keep-alive pinger.
**Cost:** free (50 monitors, 5-minute interval, no card)   **Time:** ~5 minutes, after item 5
**Steps:**
1. Go to https://uptimerobot.com, create a free account with your e-mail.
2. Click **+ New Monitor** → type **HTTP(s)**, friendly name `ringsight-health`, URL = your Render URL + `/health`, interval **5 minutes**.
3. Under alert contacts tick your e-mail. Click **Create Monitor**.
**You'll end with:** a green monitor; a test e-mail if you pause/resume it.
**Where it goes:** nowhere in code.
**Official guide:** https://uptimerobot.com/help/

## 7. Cloudflare Worker cron (optional, second pinger)
**Why the project needs it:** GitHub Actions cron can be delayed; a second free scheduler keeps Render inside its 15-minute spin-down. Skip if you are short on time — Actions + UptimeRobot already give two pingers.
**Cost:** free   **Time:** ~10 minutes
**Steps:**
1. Go to https://dash.cloudflare.com, create a free account.
2. **Workers & Pages → Create → Create Worker**, name `ringsight-ping`, click **Deploy**, then **Edit code**. Claude Code gives you the 6-line script (a `scheduled()` handler that fetches your `/health` URL); paste it, **Deploy**.
3. In the Worker's **Settings → Triggers → Cron Triggers → Add Cron Trigger**, enter `8-59/15 * * * *`, save.
**You'll end with:** the Worker's logs showing a request every 15 minutes.
**Where it goes:** nowhere in code.
**Official guide:** https://developers.cloudflare.com/workers/configuration/cron-triggers/

## 8. Access keys for the demo (fixed choices)
**Why the project needs it:** every request carries a key that the server maps to a person, a role and a bank. These are plain random strings; Claude Code generates them, but you decide the names and you must paste the same values into Render.
**Cost:** free   **Time:** ~2 minutes
**Steps:**
1. Accept the defaults below, or change the two names. Claude Code will generate the four random values and write them into `.env` if the lines are empty — your only job is to copy the final `.env` into Render (item 5, step 5) and to put `JUDGE_KEY` in the README/GitHub secret.
   - Analyst identity for judges: user `judge`, role `analyst`, tenant `bank_a`
   - Principal Officer identity for the video: user `baharul`, role `principal_officer`, tenant `bank_a`
2. Product name **RingSight**, repo **ringsight**, tenant graph **rs_bank_a** (+ toy **rs_bank_b**) are fixed choices already approved.
**You'll end with:** four random strings of ~32 characters.
**Where it goes:** `MCP_READ_TOKEN=`, `JUDGE_KEY=`, `PO_DEMO_KEY=`, `ADMIN_TOKEN=` in `.env` (Claude Code also builds `HUMAN_KEYS_JSON` from them).

## 9. The .env file
1. In the project folder, create a file named exactly `.env`.
2. Paste this template into it, then fill every line with the values from the items above (leave the four key lines empty if you want Claude Code to generate them):

```env
# --- Claude (item 2) ---
ANTHROPIC_API_KEY=
MODEL_PLANNER=claude-sonnet-5-5
MODEL_JUDGE=claude-sonnet-5-5
MODEL_NARRATIVE=claude-opus-5-5
MODEL_PROBE=claude-haiku-5-5
DAILY_USD_CAP=8

# --- FalkorDB Cloud Free (item 3); the live graph ---
REDIS_URL=
GRAPH_NAME=rs_bank_a

# --- local docker-compose only (Claude Code chooses the password; leave as is) ---
FALKORDB_PASSWORD=change-me-local
ACCOUNTS=25000

# --- access keys (item 8) ---
MCP_READ_TOKEN=
JUDGE_KEY=
PO_DEMO_KEY=
ADMIN_TOKEN=

# --- deployment ---
ENV=demo
GUARD=deterministic
PUBLIC_URL=
```

3. Three rules: `.env` is never committed or shared · never paste its values into any chat · Claude Code never reads or prints it — it uses the values from the environment while building. (You will paste the same lines into Render's environment panel yourself — item 5.)


Configuration confirmed on 16 October 2026: Render https://ringsight.onrender.com, health path `/live`; owner set GitHub `HEALTH_URL`/`JUDGE_KEY` secrets and confirmed UptimeRobot plus Cloudflare cron enabled. Do not ask for keys or repeat these setup steps. Actual live/model test results remain separate from this configuration checklist.
