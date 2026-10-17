# If the demo is down

The Render liveness check is `/live`. Monitoring uses `/health`, which also
tests graph readiness and the cached model path. A cold Render container can
take about one minute to answer. Keep one free Render service in the workspace
through judging; its 750 monthly hours are a shared allowance.

| Observed state | Action |
|---|---|
| First request is slow | Wait about a minute, then open `/health`. Actions, Cloudflare and UptimeRobot should continue pinging during judging. |
| `reseeding:true` | Leave the background seed worker running. The UI shows its estimated seconds. Do not start another seed. |
| `reseed_failed:true`, or a stuck reseed | Check `last_error`. The deadline is `max(15 minutes, 3 × last reseed duration)`; the worker is stopped and its lock released. Correct the underlying issue, then run `uv run python ops/admin.py reseed-force`. This is available only in demo mode. |
| `db:unavailable` | Check the existing FalkorDB Cloud instance is running and the Render `REDIS_URL` matches its current connection string. Reconnect/retry is bounded. Do not regenerate live data merely because a connection failed. |
| `db:busy` | Wait 15 seconds. Every API path shares the six-query semaphore. Narrow deep/dense queries. |
| `model:auth_error` | Verify the existing API key and workspace in the Anthropic Console, update Render's environment if needed, and redeploy. Never paste a key into chat, logs or git. |
| `model:spend_limit` or budget exhausted | Keep the human tool console available. Do not raise the daily cap or Console spending limit without Baharul's explicit go-ahead. The Console limit is the outer spending wall. |
| `model:unreachable` | Wait for bounded retries; use manual tools. Check the provider status and model id in the existing environment. |
| `halted:true` | Confirm the investigation is intentionally halted. An administrator can resume with the command below; the read-only tools remain available. |
| One tool times out | The trace displays a grey tool error. Narrow the time window or depth; try fan-pattern/hub-rank on dense hubs. A timeout never means the account is clean. |
| `graph_mb_warning:true` | Memory is at least 80 MB. Stop broad queries and inspect new trail growth before adding more data. The shipped entity graph must remain below 40 MB. |
| Public judge key abused | Halt the model, rotate the judge key in the local `.env` and Render environment, update the README public judge key and GitHub Actions secret. Keep administrator and Principal Officer keys private. |
| Render suspends the free service | Check workspace free-hour consumption and e-mail notices. Redeploy the same image when the issue is resolved. A paid Fly.io fallback needs a separately approved hosting decision; no paid instance is created by this repository. |

Administrator commands read the secret from the environment and never put it
in command-line arguments. Set `PUBLIC_URL` for the intended deployment, or
pass `--url http://127.0.0.1:8000` explicitly for local work.

```sh
uv run python ops/admin.py halt
uv run python ops/admin.py model-off
uv run python ops/admin.py model-on
uv run python ops/admin.py resume
uv run python ops/admin.py reseed-force
```

`make smoke` starts the local Compose stack, checks the compiled page and
server-assigned identity, creates a random `PersistenceProbe` node, restarts
FalkorDB and checks that the exact original nonce and seed timestamp survive.
It verifies AOF is enabled with `appendfsync everysec`. Readiness and recovery
are read directly from the local graph, bypassing `/health` and its cache.
An automatic reseed cannot reproduce the random nonce. No model call is made.
Evidence is written to `evals/results/local-smoke.json`; this tests a clean
container restart, not machine or power loss. Database ports bind to loopback.

For a single command that builds an isolated project, proves actual AOF
persistence and runs actual plus mocked headless UI checks against the built
assets, use:

```sh
.venv/bin/python ops/verify_compose.py
```

The wrapper passes project `rs_acceptance` and app/Redis/Browser ports
`18000`/`16379`/`13000` explicitly into every child command. No shell exports
are required. It records the actual app image id and architecture, whether the
volume existed, and hashes of freshly written child result files in
`evals/results/compose-acceptance.json`. It retains existing volumes. To test
an empty volume, choose a new name with `--project rs_acceptance_fresh`.
No investigation is submitted; the real UI's cached health probe may run.

For the lower-level smoke alone, the equivalent command is:

```sh
COMPOSE_PROJECT_NAME=rs_acceptance RS_APP_PORT=18000 RS_REDIS_PORT=16379 RS_BROWSER_PORT=13000 make smoke
```

The default ports remain app `8000`, Redis `6379`, Browser `3000`.

## Recovery and data-loss statement

FalkorDB Cloud Free has no persistence, backups or TLS. All data is synthetic.
An empty graph or missing `Meta.seed_complete` triggers background regeneration
and restoration of the committed findings snapshot. Newer findings, decisions
and the daily spend ledger can be lost in a spontaneous Cloud restart; the
Console limit still bounds spend. Hackathon RPO is the deterministic graph
plus the latest snapshot; RTO is the measured reseed duration plus free-host
wake-up time.

A planned rebuild first saves Tenant controls and all Spend rows to a temporary
private recovery checkpoint under ignored `artifacts/private/reseed-control/`.
Its directory uses the database URL's hash and its file is scoped to the graph;
no connection URL or credential is written. The file is mode `0600`, atomically
replaced and fsynced before any graph deletion. A failed capture aborts deletion.
Outstanding reservations are conservatively charged as spent; the largest
known liability is restored, caps can only stay equal or decrease, and halt or
model-off settings survive. The checkpoint is restored after bulk load and
after failure, remains available to the next loader process if the graph is
missing, and is removed only when the rebuild completes. It is never a runtime
store or part of the public findings snapshot. A container loss can also lose
this temporary file; the Console spending limit remains the outer wall.

Capture demo findings with `make snapshot`, review that the file contains only
synthetic records, then commit `data/findings_snapshot.json`. A seed restore
does not turn unreviewed assistant findings into reviewed findings.

External `/mcp` and `/tool` reads produce structured application log lines and
do not create persisted `ToolCall` nodes. Interactive agent sessions persist
their calls; human decisions and admin actions are recorded in the tenant
graph. This is an explicit demo audit limit.

## Monitor setup after the first push

Follow [setup.md items 5–7](../setup.md). Render: select the existing public
GitHub repository, Docker runtime, Free plan, Oregon, paste `.env`, health
check `/live`. UptimeRobot: HTTP monitor on `PUBLIC_URL/health`, five-minute
interval, your e-mail alert contact. Cloudflare: deploy
`ops/cloudflare-worker.js`, set `HEALTH_URL` to `PUBLIC_URL/health`, and add
cron `8-59/15 * * * *`. GitHub Actions uses `HEALTH_URL` and `JUDGE_KEY`
repository secrets and fails on non-200 health responses. The daily question
probe checks an evidenced answer rather than only container liveness.

The owner has already confirmed the Render URL, GitHub secrets, UptimeRobot
and Cloudflare setup. Preserve that confirmation; do not request it again.
To record actual current-source execution, push the runtime and tests, let CI
finish, and run the health/daily workflows when needed:

```sh
gh workflow run keepalive.yml --repo Baharul0111/RingSight
gh workflow run daily-probe.yml --repo Baharul0111/RingSight
gh run list --repo Baharul0111/RingSight --limit 10
.venv/bin/python ops/collect_workflow_evidence.py
```

The daily job asks one ordinary capped demo question; dispatch it once, then
inspect its result. The collector only reads public GitHub run metadata and
local Git objects. It never dispatches a job, calls the model, changes secrets
or mutates Git. It refuses uncommitted relevant sources and writes
`evals/results/operational-probes.json` only with the observed status. Each
workflow's latest completed run with identical committed runtime/tests/workflow
content must succeed. A pending equivalent run does not invalidate an earlier
completed proof. Later README/video/evidence-only commits do not require reruns;
changing or deleting relevant source invalidates the proof. A successful
health/daily job does not independently establish UptimeRobot email delivery.

## Deployment acceptance and recording

`ops/live_verify.py` reads `PUBLIC_URL` and keys from `.env`. Its default mode
checks the actual deployment, server-assigned judge identity, exact fourteen
read-only MCP tools, a standard MCP call, and manual depth-1/depth-4 paths.
It requires `Meta.seed_version=rs-synthetic-v2` before any costly questions.

```sh
.venv/bin/python ops/live_verify.py
.venv/bin/python ops/live_verify.py --acceptance --fallback
```

The acceptance mode performs seven live operational questions, approves only
its own synthetic case proposal, denies its own hold recommendation, recalls
reviewed dated memory, checks unknown/CASH outcomes and the planted memo, and
records actual timing and costs. `--fallback` temporarily disables the model,
proves a manual path still works, and restores the previous enabled setting.
It neither deletes ring edges nor runs structural/model fixtures on Cloud.
Those evaluations use disposable local copies.

If the current deployment still holds the old synthetic version, deploy the
new code and follow the separate operator rebuild procedure, preserving the
saved findings and today's spend ledger. Connection failures alone are not a
reason to reseed. Verification itself never reseeds, raises or resets a cap,
clears the spend ledger, or retries a paid question after failure.

Run the concurrency probe separately after the key's 10-minute bucket has
refilled:

```sh
.venv/bin/python ops/live_verify.py --load
```

It submits five simultaneous investigations, checks that excess requests get
the busy response, samples `/health` RSS and reports depth-4 p50/p95 with the
sample count. Health is cached for 15 seconds; sampled RSS is not a process
high-water mark. Five requests fit at most $1.25 under the existing cap.
All modes write incremental sanitized artifacts under `evals/results/` and
mark failures explicitly. A result file's existence alone is not a pass.

For the real three-minute browser recording, follow the commands and disclosure
in [demo-script.md](demo-script.md#executable-capture). Let the request bucket
refill between acceptance, load and recording runs. Stop the local Browser
helper when finished with `docker stop ringsight-browser`.

## Before a real pilot

The default pilot is shadow mode: a bank runs FalkorDB on its own infrastructure
and RingSight supplies software plus the MCP tool pack. Production deployment
is in India, with the bank's identity provider, short-lived credentials,
TLS/private networking, MFA, model/provider agreements and an independent
security and model review. A startup-hosted paid graph pilot requires written
FalkorDB commercial terms before offering it.

The proposed backup posture is a 15-minute off-box RDB plus AOF shipping (or a
replica), with a monthly restore drill; single-primary AOF alone does not
protect against node loss. Regulatory filing, retention, holiday calendars,
privacy rights and incident-reporting timelines need primary-source legal
review. FIU-IND format facts remain `[unverified-primary]` in every demo export.
