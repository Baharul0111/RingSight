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

`make smoke` starts the local Compose stack, waits for a populated graph,
restarts FalkorDB and confirms that the account count survives. It does not
require a successful model response. Database ports bind to loopback only.

## Recovery and data-loss statement

FalkorDB Cloud Free has no persistence, backups or TLS. All data is synthetic.
An empty graph or missing `Meta.seed_complete` triggers background regeneration
and restoration of the committed findings snapshot. Newer findings, decisions
and the daily spend ledger can be lost in a Cloud restart; the Console limit
still bounds spend. Hackathon RPO is the deterministic graph plus the latest
snapshot; RTO is the measured reseed duration plus free-host wake-up time.

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
probe checks `answered_with_path` rather than only container liveness.

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
