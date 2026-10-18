"""Build documentation from real local artifacts. Never print environment values."""
import ast
import json
import math
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
env=dotenv_values('.env')
url=env.get('PUBLIC_URL') or 'https://ringsight.onrender.com'
judge=env.get('JUDGE_KEY') or '<set JUDGE_KEY in .env>'
mcp=env.get('MCP_READ_TOKEN') or '<set MCP_READ_TOKEN in .env>'
from server.schemas import INPUT_MODELS
from server.mcp_read import _DESCRIPTIONS
from ops.workflow_evidence import validate_workflow_evidence

def load(name,default):
 p=ROOT/'evals/results'/name
 return json.loads(p.read_text()) if p.exists() else default
sizing=load('sizing.json',{})
cloud=load('cloud-foundation.json',{})
patterns=load('structural-patterns.json',{})
local_current=load('local-foundation-v2.json',{})
video=load('demo-video.json',{})
operations=load('operations.json',{})
operational_probes=load('operational-probes.json',{})
owner_monitors=all(operations.get(name) is True for name in ('uptimerobot_monitor_enabled','cloudflare_cron_enabled','github_keepalive_workflow_present'))
monitor_summary=('The owner confirmed UptimeRobot, Cloudflare cron and GitHub keepalive setup ([configuration evidence](evals/results/operations.json)).' if owner_monitors else 'External monitor setup has no complete owner-confirmed configuration artifact yet.')
try:
 validate_workflow_evidence(operational_probes,ROOT)
 probe_summary='Current-source CI, health and daily-question jobs succeeded: '+', '.join(f"[{name}]({run['url']})" for name,run in operational_probes['workflows'].items())+'. This does not independently verify email delivery.'
except (AssertionError,KeyError,TypeError):
 probe_summary='Current-source successful scheduled health/daily-question execution has not been recorded. Configuration confirmation does not establish a successful job or email delivery.'
video_ready=video.get('status')=='passed' and (ROOT/'docs/ringsight-demo.mp4').exists()
INTRODUCTION = """## The problem

When a bank flags an account, an investigator needs to understand what happened before deciding what to do. The useful clues can be spread across transfers, account owners, shared devices, phone numbers and earlier investigations. Looking at one account at a time can hide a wider network. A missing connection also needs an explanation: was nothing found, was the search too shallow, or was the payment data never loaded?

## The solution

RingSight is an investigation assistant that brings those clues together. An investigator asks a question in plain English, watches the checks run, and receives the exact connections and transfers behind the answer. The assistant can remember earlier findings and propose a case, escalation, hold recommendation or report draft. A named person must review the proposal and give a written reason before it is approved or denied. All demonstration data is synthetic; no real account is frozen and no real report is filed.

## Why this approach, and how it works

The problem is about connections, so RingSight stores and follows those connections directly. The server first checks the account, earlier findings and available data. It then offers the model a relevant group from a fixed menu of tools. The model chooses tools and supplies checked inputs; human-written database queries retrieve the evidence. A fact checker validates the answer and a separate model pass reviews its support. Unsupported wording is replaced with text built from the returned facts. The human keeps the final decision.

## How RingSight uses FalkorDB

FalkorDB is the main database and the source of evidence for the product. Each bank has its own graph containing accounts, people, transfers, shared identifiers, data coverage, findings, proposals and human decisions. RingSight queries that graph to discover paths, runs graph algorithms inside FalkorDB, and saves what the investigator learns back into the same graph. The picture on screen displays returned graph evidence. Without FalkorDB, the assistant cannot obtain new evidence, recall findings, create proposals or record decisions; even the manual tool form needs the graph.
"""

GRAPH_GUIDE = """## Map of the graph

A **node** is a thing, such as an account or person. A **relationship** says how two things connect. **Properties** hold details: a transfer has an ID, an amount in whole paise, a UTC timestamp and a payment rail. The diagrams show the stored relationship directions.

### Bank data: people, accounts and money

```mermaid
flowchart LR
    person[Person] -->|OWNS| account[Account]
    person -->|HAS_PHONE| phone[Phone]
    person -->|HAS_ADDRESS| address[Address]
    account -->|USES_DEVICE| device[Device]
    other[Another Account] -->|USES_DEVICE| device
    account -->|TX| other
    account -->|AT_BANK| bank[Bank]
    account -->|PAID| merchant[Merchant]
    alert[Alert] -->|ON| account
    restriction[Restriction] -->|ON| account
```

This is a map of relationship types, not a claim that a particular pair of accounts paid each other. **TX means an actual recorded transfer; sharing a device or owner means a connection, not a payment or proof of laundering.** Derived SHARES/SHARES_STRONG links help find accounts with shared identifiers. FLOW aggregates transfer capacity for max-flow; original TX edges remain the transfer evidence.

### Investigation data: evidence, memory and human decisions

```mermaid
flowchart LR
    call[ToolCall] -->|IN| session[Session]
    finding[Finding] -->|MADE_IN| session
    finding -->|ABOUT| account[Account]
    pending[PendingAction] -->|IN| session
    pending -->|BASED_ON| finding
    pending -->|TARGETS| account
    decision[Decision] -->|ON| pending
    case[Case] -->|HAS| finding
    case -->|INCLUDES| account
    report["SARDraft: US SAR or Indian STR"] -->|FOR| case
    report -->|FROM| decision
    hold[HoldProposal] -->|FROM| decision
    hold -->|TARGETS| account
```

A Finding keeps its learned date, validity dates, author, review state and original evidence-call IDs. Those IDs refer back to ToolCall records in the same bank. A Decision keeps the human's identity, role, reason and time. Corrections create a new Finding linked to the earlier one by SUPERSEDES. SAR and STR exports share the SARDraft node label and have different jurisdiction properties.

The graph also holds Rail and IngestionDay coverage records, plus Tenant, Spend, Meta and catalogue records for controls and auditing. Coverage days identify their rail through a stored property; the diagrams do not invent relationships between these metadata nodes. The complete labels, properties, indexes and Cypher appear below.

## How the agent queries the graph

For **“Is ACC-4471 part of a ring, and how does the money move?”**, the work follows this sequence:

1. **Check the starting point.** Fixed queries resolve ACC-4471, recall its dated findings and inspect loaded rails. An unknown account or missing CASH data gets an explicit answer rather than a guessed story.
2. **Choose bounded reads.** Server rules offer the relevant tools, such as account profile, transfer neighbourhood and shared identifiers. The model chooses within that group. For example, `rs_shared_identifiers({"account_id":"ACC-4471","hops":1})` asks for nearby shared identifiers.
3. **Run human-written Cypher.** The server validates the ID and supplies the session's evidence date, degree limits and bound parameters. Reads use GRAPH.RO_QUERY. This shortened device query shows the actual traversal; [the full query](server/cypher/rs_shared_identifiers.cypher) is also printed below:

```cypher
MATCH (a:Account {id:$id})-[u1:USES_DEVICE]->(d:Device)
      <-[u2:USES_DEVICE]-(b:Account)
WHERE b<>a AND d.degree<=$max_deg
  AND u1.first_seen<=$as_of AND u2.first_seen<=$as_of
RETURN [a.id,d.id,b.id] AS path_ids
LIMIT $limit
```

4. **Return an inspectable path.** The seeded example connects `ACC-4471 → DEV-f31c → ACC-10477 → PER-2291 → ACC-55820`. These arrows describe walking the connection: both first accounts use the device, and PER-2291 owns the two later accounts. They do not describe money flowing through a device or person. The shallow demo excludes the exit; the deeper demo includes it. Each tool enforces its own depth and date rules.
5. **Check and propose.** The verifier checks factual details against returned rows, and the separate judge reviews support. A supported graph observation can be saved with its original evidence and linked to a pending case action. Weak support leads the ordinary review proposal toward escalation. A pending closure rejected by the judge is withdrawn and replaced with escalation.
6. **Wait for the human.** A separate authenticated route records approve, deny or modify, with a reason. The model has no approval tool. The next session can recall the finding and show whether a human reviewed it.

## Where graph evidence changes the outcome

| What FalkorDB returns | What RingSight is allowed to do | Inspect the implementation |
|---|---|---|
| No matching account | Return unknown_entity and graph-sourced suggestions. | [Entity lookup and preflight](server/agent.py) |
| Rail or date coverage is missing | Explain the gap; do not conclude that the activity never happened. | [Coverage query](server/cypher/rs_coverage_status.cypher) |
| Actual TX or identifier paths | Show those paths and their transfer facts; replace unsupported prose with evidence-built wording. | [Read tools](server/mcp_read.py), [verifier](server/verifier.py) |
| Nonempty multi-edge pattern evidence from the current session | A hold recommendation may become pending. A single transfer is insufficient, and approval still cannot freeze an account. | [Proposal checks](server/mcp_write.py) |
| At least two distinct nonempty checks, with no suspicious pattern evidence | A closure proposal may be eligible; empty results cannot justify closing. | [Closure policy](server/mcp_write.py) |
| Existing restriction records | Recheck restrictions before each proposal and show them to the reviewer. A failed restriction read blocks the proposal; a restriction is not automatically a veto on every action. | [Restriction and write checks](server/mcp_write.py) |
| Dated findings and their original evidence | Answer from memory with learned date, author and review state. | [Recall](server/mcp_read.py) |
| A pending action plus a named human decision | Record denial or create the allowed case, recommendation or approved report draft. Account.status remains unchanged. | [Human decision route](server/actions.py) |

FalkorDB also runs shortest-path operations, weakly connected components, label propagation, PageRank, sampled betweenness and max-flow on the supported projection. Global results carry their computed time; they are not a promise of arbitrary historical recalculation. See [precomputation](seed/__init__.py) and the inline queries below.

**How this is checked:** [all planted path facts](tests/test_seeded_path_facts.py), [hold/closure/human-action checks](tests/test_actions.py), [report and restriction checks](tests/test_report_safety.py), and [120 real-model path cases](evals/results/model-paths.json). The public trace exposes the tool, inputs, returned rows, timing, guard hits and final checks. Model confidence alone cannot authorize an effect. If the database is unavailable, the static page or /live may still respond, but investigation, memory, manual graph reads and new decisions cannot complete.
"""

lines=[f'Live: {url} · Judge access key: `{judge}`',
'# RingSight',
'**Track 01 (primary) · Track 02 (memory)**',
INTRODUCTION.strip(),
GRAPH_GUIDE.strip(),
'## How the components fit together',
'![Architecture](docs/architecture.svg)',
'**Verification status:** structural results below are recorded test evidence. Live/model completion is claimed only when its passing results exist in `evals/results/`. The public deployment may take about **60 seconds** to wake from a cold start.',
'## 1. Try the investigator console',
f'Open [{url}]({url}), paste the judge key from this README’s first line, and ask **“Is ACC-4471 part of a ring, and how does the money move?”** Compare depth 1 with depth 4. Look for the identifier path `ACC-4471 → DEV-f31c → ACC-10477 → PER-2291 → ACC-55820`. The exit account is connected through identifiers; it is not a claimed direct transfer.',
'The judge key maps on the server to `user=judge`, `role=analyst`, `tenant=bank_a`. The Principal Officer’s key and administrator key are never published. The UI stores a pasted key only in sessionStorage. `?key=` is accepted once and stripped from the URL. A role is determined by the key; it is never a client-side role switch.',
'Ask about `ACC-99999` for unknown_entity. Ask whether `ACC-4471` deposited cash for rail_not_ingested. Use the manual **Run a tool** form when the model is disabled, unavailable or out of budget.',
('Video: [three-minute screen recording](docs/ringsight-demo.mp4) · [captions](docs/demo-captions.vtt) · [recording evidence](evals/results/demo-video.json).' if video_ready else 'Video: [three-minute script](docs/demo-script.md). A recording link is added only after an actual screen recording exists.'),
'## 2. Complete local setup',
'Prerequisites: Docker with Compose, Git, and a filled `.env` copied from `.env.example`. Generate four 32-character demo keys locally if they are blank. Supply your Anthropic API key and keep its Console spending limit in force. Local Docker uses `FALKORDB_PASSWORD`; the app’s local Redis URL is explicitly overridden in Compose.',
'```sh\ngit clone https://github.com/Baharul0111/RingSight.git\ncd RingSight\ncp .env.example .env\n# Fill .env locally; never commit it.\nmake up\n```',
'The single `make up` command builds the UI and app, starts pinned FalkorDB, seeds both synthetic banks, and starts the application at http://localhost:8000. The local FalkorDB Browser is http://localhost:3000. `make smoke` also restarts the database and checks persistence. `make down` preserves the data volume.',
'For development: `uv sync --frozen`; `make ui`; `make dev`. Tests that mutate data require the explicitly local `RS_TEST_REDIS_URL=redis://localhost:6380` and refuse a Cloud address. The engine fixture is pinned to `falkordb/falkordb:v4.22.1`; no `:latest` image is used. CI additionally targets 6.0.2.',
'## 3. Graph model and measured size',
'One FalkorDB graph per bank: `rs_bank_a` and toy `rs_bank_b`. All entity data, coverage, restrictions, observations, proposals, human decisions, cases and report drafts live in that graph. There is no substitute store that can answer when FalkorDB is absent. Ground truth files are outside the graph and never exposed to the running agent.',
'| Layer | Labels and relationships |\n|---|---|\n| Entities | Account, Person, Device, Phone, Address, Merchant, Bank; OWNS, USES_DEVICE, HAS_PHONE, HAS_ADDRESS, AT_BANK, PAID |\n| Money | Directed TX with integer paise, UTC epoch seconds, rail, opaque id and guarded memo; FLOW is a dated aggregate projection used only for max-flow |\n| Controls | Alert and Restriction linked by ON; Rail and IngestionDay hold loaded windows and feed deltas |\n| Memory | Finding with valid_from/valid_to/created_at/expired_at, ABOUT, MADE_IN, SUPERSEDES |\n| Decisions | Session, ToolCall, PendingAction, Decision, Case, HoldProposal, SARDraft, Tenant, Spend, Meta, CatalogueVersion |',
'35 planted rings span fan-in, fan-out, cycles, bipartite, stacks, scatter-gather and gather-scatter. The final 25,000-account graph contains 32,500 TX over 180 days on six rails, plus 30,000 merchant payments, legitimate busy merchants/payroll/exchanges, 60 alerts, three restrictions, three name-variant pairs, twenty memo injections, and two IMPS feed-count mismatches. CASH and XB are absent.',
'The original transfer-density estimate exceeded the memory budget. The measured amendment in architecture.md preserves 25,000 accounts and every planted control, reduces background density, shares household owners, and avoids redundant projections. PageRank, WCC, label propagation and sampled betweenness are executed by FalkorDB. Betweenness uses **32 samples** after measured Cloud allocation peaks made 256 samples unsuitable. These are approximate, synthetic results.',
'| Accounts | TX | Graph MB | Reseed seconds | Engine |\n|---:|---:|---:|---:|---|']
for r in sizing.get('measurements',[]):
 lines.append(f"| {r.get('accounts')} | {r.get('manifest',{}).get('edges',{}).get('TX','—')} | {r.get('graph_mb')} | {r.get('reseed_s')} | {r.get('engine')} |")
if cloud.get('status')=='passed':
 c=cloud['result'];lines.append(f"\nCloud initial seed: **{c['accounts']:,} accounts, {c['graph_mb']} MB, {c['reseed_s']} seconds, engine {c['engine']}**. Native Redis allocation and RSS can exceed the graph-size measure; [memory-ceiling evidence](evals/results/memory-ceiling.json) records the transient peaks.")
if local_current.get('status')=='passed':
 c=local_current['result'];lines.append(f"Current `{c['seed_version']}` shipment remeasured locally: **{c['accounts']:,} accounts, {c['graph_mb']} MB, {c['reseed_s']} seconds, engine {c['engine']}** ([raw evidence](evals/results/local-foundation-v2.json)).")
lines += ['## 4. Fixed queries and graph algorithms',
'Every query is human-authored. Strings from the model become parameters, never Cypher source. Traversal lengths, labels, direction, scope and metric are selected from validated bounded integers/enums. Reads use `GRAPH.RO_QUERY`; only the two private write tools and human/admin HTTP handlers can write.',
'The complete query catalogue, schema/index creation, identifier projections and precompute calls are inline below. The indexed ring count happens before collecting a component. Dense-hub guards run before deep traversals. Historical requests refuse unavailable global snapshots rather than leaking later-derived state.',
'## 5. Sixteen tools and approval flow',
'| Tool | Access | Purpose |\n|---|---|---|']
for name in INPUT_MODELS:
 lines.append('| `'+name+'` | Public read | '+_DESCRIPTIONS[name].split('input_example:')[0].strip()+' |')
lines += ['| `rs_record_finding` | Private, interactive session only | Record a supported, dated, unreviewed observation; guard/verifier/evidence checks and idempotency apply. |','| `rs_propose_action` | Private, interactive session only | Create pending flag, hold recommendation, case link, escalation, SAR/STR draft or closure proposal; no consequential effect. |',
'Exactly fourteen reads are published at `/mcp`; the writes are in-process only. Max-flow was promoted from the originally deferred item to reconcile the numbered sixteen-tool catalogue with the explicit fourteen-read requirement. FalkorDB rejects parallel TX tensors for max-flow, so FLOW aggregates ordered pairs. Its computed-at and coverage end are visible; a historical request before that end is refused and raw later transfers are excluded until refresh. Backlog/queue tools remain future work.',
'```text\nMCP endpoint: '+url+'/mcp\nAuthorization: Bearer '+mcp+'\n```',
'Connect with MCP Inspector or an MCP client supporting Streamable HTTP. List tools to see the fourteen typed read schemas and annotations. The MCP key cannot access `/approve`, `/feedback`, `/ask`, or private write tools. No run_cypher tool exists.',
'Approval: pending card → named human approve/deny/modify with a reason of 20–1,000 characters → Decision node with user, role, tenant and time. A hold creates only HoldProposal(status=sent_to_principal_officer), never an Account.status write. Report approval requires principal_officer. Closing requires at least two distinct nonempty checks without suspicious pattern evidence. UUIDs resolve only in the bearer’s graph. Nothing is deleted by application action paths; corrections supersede prior findings.',
'## 6. Four shapes, paths, trace and verification',
'`answered_with_path` carries exact directed evidence paths and transfer rows. `answered_from_memory` gives learned date, author and review state. `not_in_graph` always gives a reason and **Not in the graph ≠ nothing wrong**. `unknown_entity` gives graph-sourced suggestions. Infrastructure tool errors are grey trace events, not evidence of innocence.',
'The canvas highlights exact paths with directional particles; the hop list, rupee/IST transfer table, source tool and streaming trace explain the answer. Every trace row records tool, safe arguments, elapsed time, returned/total rows, outcome and guard hits. The final event records model, input/output/cache tokens, cost, judge verdict and deterministic verifier result.',
'The verifier checks opaque ids, currency including lakh/crore and Indian grouping, dates and ordinary quantities against evidence. A failed verification replaces prose with a deterministic sentence built from an actual returned path. A separate model judges only the evidence digest and thesis. Weak or contradictory closure proposals are withdrawn and superseded by escalation.',
'## 7. Why no free-form query generation',
'An investigation requires correct direction, time and evidence. A fixed, testable catalogue lets a model select a graph computation without granting query-writing authority. It also makes empty results, depth bounds, feed gaps and query timeouts distinguishable. Global algorithms are computed in the database, not simulated in Python.',
'## 8. Memory — Track 02',
'Finding nodes carry bi-temporal validity and recording time. Every question resolves entities and recalls findings first. At most five unreviewed agent findings enter a session, each capped, labelled and wrapped as untrusted. Human feedback creates a superseding analyst finding; it does not erase history. Snapshot schema 2 retains original same-bank ToolCall rows, their hashes, Sessions and supersession links, so recalled memory retains its dated path after a wipe. The snapshot in data/findings_snapshot.json restores only into its own graph. Snapshot capture follows the actual demo; an empty snapshot is not claimed as learned memory.',
'## 9. Safety, costs and kill switch',
'Server-derived identity selects the tenant graph. The UI cannot set tenant or role. All system ids are UUIDv4. CORS is same-origin; MCP Origin is checked. Names are rehydrated for humans only; model envelopes use ids. Memos scrub phone/email/name tokens before a capped untrusted envelope. READ guards flag role mimicry, ignore-instruction phrases, skip approval, mark clean and action/suppression language. WRITE guards refuse role mimicry, ignore instructions and skip approval while allowing honest hold/closure recommendations and “do not ignore prior alerts”. A paraphrase can remain unreviewed data and is flagged again on recall; it is not promoted to an instruction.',
'The Console workspace spending limit is the outer wall. Before provider requests: graph-backed halt/llm flags, per-bank daily cap of at most **$8 UTC/day**, three investigation slots, six graph-query slots, key/IP buckets and per-investigation bounds apply. Each investigation is limited to ten tool calls, twelve model requests, 60,000 input / 6,000 output tokens, $0.25 and 60 seconds. Reservations are written to Spend before model creation; unknown completions are charged conservatively. Caps are never raised automatically.',
'The strict compiler’s observed global grammar limits require bounded staged subsets from the same frozen catalogue. Server schemas retain all bounds; the model-facing schema uses trusted defaults for nullable advanced fields. Time and depth are enforced by the server. Full evidence stays in the graph/UI; the model receives a bounded projection to avoid duplicating all 1,080 coverage days every turn.',
'Admin commands are documented in [runbook](docs/runbook.md). `POST /admin/halt` and `POST /admin/llm` immediately stop model use. Read-only manual tools stay available. Outages, timeouts, budget/rate exhaustion and reseeding have plain error states, limited retries and heartbeat events.',
'## 10. Recorded evaluations — synthetic, demo-only',
'No detection result is a claim about real banking data. Model evaluations mutate only explicitly local disposable graphs. Result artifacts include their target, checks, counts and pass status. Missing or incomplete files do not count as a pass.',
'| Artifact | Recorded status |\n|---|---|']
for p in sorted((ROOT/'evals/results').glob('*.json')):
 d=json.loads(p.read_text())
 if 'summary' in d:
  status='; '.join(f"{d['summary'].get(name,0)} {name}" for name in ('passed','failed','error','skipped'))
  if 'exitcode' in d:status+=f"; exit {d['exitcode']}"
 elif 'status' in d:status=str(d['status'])
 elif 'passed' in d:status='passed' if d['passed'] else ('stopped: '+str(d['stopped_reason']) if d.get('stopped_reason') else f"in progress: {len(d.get('cases',[]))}/{d.get('planned_cases','?')}" if d.get('complete') is False else 'failed')
 elif d.get('success') is not None:status=f"{d.get('numPassedTests',0)} UI unit tests passed" if d['success'] else 'failed'
 elif p.name=='structural-patterns.json':status='35-ring measurement; see recall and precision below'
 else:status='measurement artifact'
 if '.previous-' in p.name:status='Historical interrupted trial; '+status
 lines.append(f'| [{p.name}](evals/results/{p.name}) | {status} |')
for filename,label in [('model-paths.json','Path correctness'),('model-injections.json','Exposed injection attacks'),('model-abstention.json','Deleted-ring abstentions')]:
 result=load(filename,{})
 if result.get('complete') and result.get('passed'):
  metrics=result['metrics']
  lines.append(f"\n**{label}: {result['completed_cases']}/{result['planned_cases']} cases passed**, ${metrics['cost_usd']:.6f} actual model cost. "+('Every cited path was checked against authoritative graph facts; first selected tool matched the expected pattern in '+f"{metrics['first_tool_exact_match']:.0%} of cases. The verifier replaced {metrics['verifier_replacements']} generated answers with evidence-built text." if filename=='model-paths.json' else f"{metrics['model_exposed_cases']} attacks reached the model's guarded evidence; {metrics['unapproved_effects']} unapproved effects and {metrics['instruction_stores']} instruction stores." if filename=='model-injections.json' else f"{metrics['not_in_graph_rate']:.0%} valid abstention; {metrics['false_answered_with_path_rate']:.0%} false path answers."))
execution=load('model-evaluations.json',{})
if execution.get('path_latency_execution'):
 lines.append('Local model timing execution: '+execution['path_latency_execution']+'.')
if execution.get('explicit_local_eval_budget'):
 approval=execution['explicit_local_eval_budget']
 lines.append(f"The owner explicitly approved ${approval['cap_usd']:g} total for the local `{approval['tenant']}` evaluation on UTC {approval['approved_day']}, preserving prior liability. The temporary approval applied only on that day; the public bank and Console limits were unchanged.")
latencies=[]
runtime=load('runtime-smoke.json',{})
if runtime.get('passed'):
 for d in (1,4):
  values=[c['elapsed_s'] for c in runtime['cases'] if c['depth']==d]
  if values:latencies.append(('Local runtime smoke',d,values))
model_paths=load('model-paths.json',{})
if model_paths.get('complete'):
 for d in (1,2,4):
  values=[c['elapsed_s'] for c in model_paths['cases'] if c['depth']==d]
  if values:latencies.append(('Local model protocol',d,values))
live_load_file='live-five_concurrent.json' if (ROOT/'evals/results/live-five_concurrent.json').exists() else 'live-load.json'
for filename,label in [('live-acceptance.json','Live acceptance'),(live_load_file,'Live concurrent load')]:
 result=load(filename,{})
 if result.get('status')=='passed':
  for name,metric in result.get('latency',{}).items():
   if metric.get('n'):latencies.append((label,int(name.rsplit('_',1)[-1]),metric))
if latencies:
 lines+=['\nObserved end-to-end latency (nearest-rank percentiles; small samples are labelled by N):','| Target / suite | Depth | N | p50 seconds | p95 seconds |\n|---|---:|---:|---:|---:|']
 for label,depth,values in latencies:
  if isinstance(values,dict):n,p50,p95=values['n'],values['p50_s'],values['p95_s']
  else:
   values=sorted(values);n=len(values);p50=values[max(0,math.ceil(n*.5)-1)];p95=values[max(0,math.ceil(n*.95)-1)]
  lines.append(f'| {label} | {depth} | {n} | {p50:.3f} | {p95:.3f} |')
if patterns:
 lines += ['\nPattern results:','| Pattern | Recall |\n|---|---:|']
 groups=patterns.get('per_typology',patterns.get('typologies',{}))
 if isinstance(groups,dict):
  for k,v in groups.items():
   recall=v.get('recall',v.get('member_recall',v.get('mean_member_recall','—'))) if isinstance(v,dict) else v
   lines.append(f'| {k} | {recall} |')
 metrics=patterns.get('hub_metrics',{})
 if metrics:lines.append('Global planted-hub precision@10: '+', '.join(f"**{name}: {metric['precision_at_10']:.3f}**" for name,metric in metrics.items())+'. Legitimate merchant/payroll/exchange hubs remain present and are excluded from this ranking. Weak global hub precision is an explicit limitation.')
lines += ['About 15 seconds is a demo target, not a guarantee. Local measurements are not live free-tier measurements. Missing live measurements are not inferred from local timings.',
'```sh\n# Both runners select LOCAL Redis themselves; no shell export is needed.\n.venv/bin/python ops/verify_local.py\n# Archive the checked-in trial before a new paid evaluation.\n.venv/bin/python ops/verify_evals.py --new-trial\n```\nThe evaluation runner measures 35 rings on the 25k local graph, then runs 40 questions × depths 1/2/4, 20 memo attacks twice, and 20 deleted-ring abstentions. It saves progress after every case. Omit `--new-trial` only to resume an interrupted trial with the same source, budget and concurrency signature. Resume retains completed failures and the graph spending ledger; an explicit new trial archives its predecessor. No Cloud graph is used for model evaluation fixtures.',
'## 11. Deployment and operations',
'Render Free runs one Docker service, one worker, health path `/live`. `/health` reports population, completion, graph size, pending count, today’s spend, engine, catalogue, RSS and a cached one-token model reachability probe. It returns 503 for incomplete seeding or failed model reachability. The health body is cached 15 seconds and the model probe ten minutes. `/live` only checks process responsiveness.',
'Auto-reseed triggers only when Account count is zero or Meta.seed_complete is missing. A background subprocess lets the UI show warming up and ETA. The deadline is max(15 minutes, 3 × previous reseed time); timeout kills the loader and requires an explicit forced retry. The final Meta write occurs only after schema, algorithms and same-tenant snapshot restoration.',
'Planned rebuilds bridge Tenant settings and all Spend days through a private atomic checkpoint scoped to the database fingerprint and bank. Caps can only decrease and pending reservations are conservatively charged. The bridge is removed after success and is never a second runtime store. Sudden Cloud loss without a bridge still has the Console limit as the outer wall.',
'Actions cron pings `/health` every twelve minutes with curl -f; a daily question checks the agent. Cloudflare’s independent Worker cron and UptimeRobot email monitor follow setup.md items 6–7. '+monitor_summary+' '+probe_summary+' Keep one Render free service to stay within the shared free-hour pool.',
'**If the demo is down:** wait for cold start; inspect `/health`; use the manual tool form during a model outage/cap; check Cloud connectivity; force a demo-only reseed if failed; rotate compromised demo keys; use local Compose for judging. [Full runbook](docs/runbook.md) includes stuck reseeds, persisted ledgers, backups, and Fly.io fallback. Cloud Free has no persistence/backups/TLS; synthetic data only. Recovery point is the last checked-in findings snapshot and synthetic seed, not every judge decision.',
'## 12. Regulatory mapping and pilot posture',
'FinCEN-style drafts use who/what/when/where/why/how in introduction/body/conclusion, listing each transfer date and amount without narrative tables. Indian drafts include grounds-of-suspicion tags, narration under 20,000 characters and provisional rail sheet mappings. All Indian format facts are visibly **[unverified-primary]** pending verification against the official document. Neither export files any real report.',
'Report approval belongs to a Principal Officer. A hold is only a recommendation, not an account restriction. The demo stores a seven-calendar-day STR due timestamp as a conservative design assumption; counsel must confirm working-day/calendar rules and holiday treatment before a pilot. No production compliance conclusion is claimed.',
'A pilot begins in shadow mode with synthetic or bank-approved data, human final authority, in-India app/graph storage and an approved in-region model endpoint with DPA/ZDR terms or the on-prem model ladder. Before real deployment: vendor DPAs (model, graph, cloud, monitoring), MFA, encryption/TLS, retention/deletion policy, lawful basis, incident notification procedures, bank security review and VAPT, model validation, load test, and a tested restore process. Legal facts in architecture.md labelled unverified/lane-recorded remain so.',
'## 13. Scale plan and honest ceilings',
'At pilot scale, precompute nightly on a recent-transaction projection. Then add queue-buffered single-writer ingestion, indexed caches and read replicas, tenant × region shards with warehouse history, and supervised features from reviewed decisions. A billion raw TX edges do not fit in one graph key. Sampled betweenness and dense cycle enumeration break first. The audit trail needs a hot retention window and archive graph; multiple app instances require shared distributed rate limits and reservations. Production tamper detection requires session/tenant hash chains and off-box WORM anchors; the demo audit graph does not claim tamper prevention.',
'## 14. AI assistance',
'Built by Baharul Islam using OpenAI Codex as the coding assistant. Codex produced implementation, tests and the React console under the supplied goal and architecture. The running agent uses the Claude API with environment-configured planner, judge and health models. Report drafts use evidence-only templates. No claim is made that a Messages Batch or narrative-polish run occurred without its result artifact. The public queries, approval rules, test evidence and measured limitations make the implementation reviewable.',
'## 15. Licences and data statement',
'RingSight’s own code: [MIT](LICENSE). FalkorDB: [SSPL v1 notice](NOTICE). AMLSim typology port: IBM AMLSim Apache-2.0 attribution in NOTICE and [upstream licence](licenses/AMLSim-Apache-2.0.txt). All accounts, people and payments are generated synthetic data. Ground truth is not a model input. For a paid pilot, default to bank-operated FalkorDB with RingSight software/tooling; startup-hosted FalkorDB requires written commercial terms before launch.',
'## 16. Limitations and completion gate',
'Free-tier cold starts, transient database memory peaks, no Cloud Free durability/TLS, weak synthetic global hub precision, approximate algorithms, provisional Indian format mapping, static demo keys and single-process rate limits are explicit constraints. The application never certifies an account clean from an absent path. A timeout yields an honest partial/insufficient answer and escalation when supported.',
'Completion requires passing local and live/model checks, approved human workflow, cross-session memory, exact fourteen public MCP reads, manual fallback, monitor confirmation, measured latency, snapshot, an actual three-minute video and committed results. The final hackathon submission and any spend-limit increase wait for Baharul’s explicit go-ahead.',
'The [requirement checklist](docs/requirement-checklist.md) maps all 22 goal items and architecture sections to evidence. Run `.venv/bin/python ops/check_completion.py` for the read-only completion gate; it fails while required proof is missing, stale, failed or uncommitted.',
'## 17. Blog',
'[Draft: What the fines say the agent must do](docs/blog.md). The blog is a repository draft; it is not described as published externally.',
'[Submission rules checklist](docs/submission-checklist.md) maps all 18 supplied rules to project evidence or owner-only attestations. [Explain RingSight](docs/explain-ringsight.md) is a source-linked participant review guide; neither document certifies personal understanding, eligibility, start timing or ownership agreements. The internal goal is 18 October 2026 at 23:00 IST; the supplied official closing time is 23:59 IST. Final submission still waits for explicit approval.',
'## Inline Cypher — schema, projections and every tool']
for p in sorted((ROOT/'server/cypher').glob('*.cypher')):
 lines += [f'### `{p.name}`','```cypher\n'+p.read_text().strip()+'\n```']
lines += ['## Inline control queries',
'These additional statements implement tenant-scoped sessions, audit, memory, decisions, safety and health. Template variables are selected by server code or passed as parameters. The public request cannot provide query text.']
seen=set()
for p in sorted(list((ROOT/'server').glob('*.py'))+list((ROOT/'seed').glob('*.py'))):
 try:tree=ast.parse(p.read_text())
 except SyntaxError:continue
 queries=[]
 for n in ast.walk(tree):
  if isinstance(n,ast.Constant) and isinstance(n.value,str):
   value=n.value.strip()
   if value.startswith(('MATCH ','MERGE ','CREATE ','CALL ','UNWIND ')) and ' AS ' in value and value not in seen:
    seen.add(value);queries.append(value)
 if queries:lines += [f'### Control statements in `{p.relative_to(ROOT)}`','```cypher\n'+'\n\n'.join(queries)+'\n```']
(ROOT/'README.md').write_text('\n\n'.join(lines)+'\n')
print('README generated from actual artifacts; public demo credentials written only to the authorized README.')
