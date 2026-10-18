Live: https://ringsight.onrender.com · Judge access key: `424b676a8a7818860fe95ecfca65dbcd`

# RingSight

**Track 01 **

## The problem

When a bank flags an account, an investigator needs to understand what happened before deciding what to do. The useful clues can be spread across transfers, account owners, shared devices, phone numbers and earlier investigations. Looking at one account at a time can hide a wider network. A missing connection also needs an explanation: was nothing found, was the search too shallow, or was the payment data never loaded?

## The solution

RingSight is an investigation assistant that brings those clues together. An investigator asks a question in plain English, watches the checks run, and receives the exact connections and transfers behind the answer. The assistant can remember earlier findings and propose a case, escalation, hold recommendation or report draft. A named person must review the proposal and give a written reason before it is approved or denied. All demonstration data is synthetic; no real account is frozen and no real report is filed.

## Why this approach, and how it works

The problem is about connections, so RingSight stores and follows those connections directly. The server first checks the account, earlier findings and available data. It then offers the model a relevant group from a fixed menu of tools. The model chooses tools and supplies checked inputs; human-written database queries retrieve the evidence. A fact checker validates the answer and a separate model pass reviews its support. Unsupported wording is replaced with text built from the returned facts. The human keeps the final decision.

## How RingSight uses FalkorDB

FalkorDB is the main database and the source of evidence for the product. Each bank has its own graph containing accounts, people, transfers, shared identifiers, data coverage, findings, proposals and human decisions. RingSight queries that graph to discover paths, runs graph algorithms inside FalkorDB, and saves what the investigator learns back into the same graph. The picture on screen displays returned graph evidence. Without FalkorDB, the assistant cannot obtain new evidence, recall findings, create proposals or record decisions; even the manual tool form needs the graph.

## Map of the graph

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

## How the components fit together

![Architecture](docs/architecture.svg)

**Verification status:** structural results below are recorded test evidence. Live/model completion is claimed only when its passing results exist in `evals/results/`. The public deployment may take about **60 seconds** to wake from a cold start.

## 1. Try the investigator console

Open [https://ringsight.onrender.com](https://ringsight.onrender.com), paste the judge key from this README’s first line, and ask **“Is ACC-4471 part of a ring, and how does the money move?”** Compare depth 1 with depth 4. Look for the identifier path `ACC-4471 → DEV-f31c → ACC-10477 → PER-2291 → ACC-55820`. The exit account is connected through identifiers; it is not a claimed direct transfer.

The judge key maps on the server to `user=judge`, `role=analyst`, `tenant=bank_a`. The Principal Officer’s key and administrator key are never published. The UI stores a pasted key only in sessionStorage. `?key=` is accepted once and stripped from the URL. A role is determined by the key; it is never a client-side role switch.

Ask about `ACC-99999` for unknown_entity. Ask whether `ACC-4471` deposited cash for rail_not_ingested. Use the manual **Run a tool** form when the model is disabled, unavailable or out of budget.

Video: [three-minute screen recording](docs/ringsight-demo.mp4) · [captions](docs/demo-captions.vtt) · [recording evidence](evals/results/demo-video.json).

## 2. Complete local setup

Prerequisites: Docker with Compose, Git, and a filled `.env` copied from `.env.example`. Generate four 32-character demo keys locally if they are blank. Supply your Anthropic API key and keep its Console spending limit in force. Local Docker uses `FALKORDB_PASSWORD`; the app’s local Redis URL is explicitly overridden in Compose.

```sh
git clone https://github.com/Baharul0111/RingSight.git
cd RingSight
cp .env.example .env
# Fill .env locally; never commit it.
make up
```

The single `make up` command builds the UI and app, starts pinned FalkorDB, seeds both synthetic banks, and starts the application at http://localhost:8000. The local FalkorDB Browser is http://localhost:3000. `make smoke` also restarts the database and checks persistence. `make down` preserves the data volume.

For development: `uv sync --frozen`; `make ui`; `make dev`. Tests that mutate data require the explicitly local `RS_TEST_REDIS_URL=redis://localhost:6380` and refuse a Cloud address. The engine fixture is pinned to `falkordb/falkordb:v4.22.1`; no `:latest` image is used. CI additionally targets 6.0.2.

## 3. Graph model and measured size

One FalkorDB graph per bank: `rs_bank_a` and toy `rs_bank_b`. All entity data, coverage, restrictions, observations, proposals, human decisions, cases and report drafts live in that graph. There is no substitute store that can answer when FalkorDB is absent. Ground truth files are outside the graph and never exposed to the running agent.

| Layer | Labels and relationships |
|---|---|
| Entities | Account, Person, Device, Phone, Address, Merchant, Bank; OWNS, USES_DEVICE, HAS_PHONE, HAS_ADDRESS, AT_BANK, PAID |
| Money | Directed TX with integer paise, UTC epoch seconds, rail, opaque id and guarded memo; FLOW is a dated aggregate projection used only for max-flow |
| Controls | Alert and Restriction linked by ON; Rail and IngestionDay hold loaded windows and feed deltas |
| Memory | Finding with valid_from/valid_to/created_at/expired_at, ABOUT, MADE_IN, SUPERSEDES |
| Decisions | Session, ToolCall, PendingAction, Decision, Case, HoldProposal, SARDraft, Tenant, Spend, Meta, CatalogueVersion |

35 planted rings span fan-in, fan-out, cycles, bipartite, stacks, scatter-gather and gather-scatter. The final 25,000-account graph contains 32,500 TX over 180 days on six rails, plus 30,000 merchant payments, legitimate busy merchants/payroll/exchanges, 60 alerts, three restrictions, three name-variant pairs, twenty memo injections, and two IMPS feed-count mismatches. CASH and XB are absent.

The original transfer-density estimate exceeded the memory budget. The measured amendment in architecture.md preserves 25,000 accounts and every planted control, reduces background density, shares household owners, and avoids redundant projections. PageRank, WCC, label propagation and sampled betweenness are executed by FalkorDB. Betweenness uses **32 samples** after measured Cloud allocation peaks made 256 samples unsuitable. These are approximate, synthetic results.

| Accounts | TX | Graph MB | Reseed seconds | Engine |
|---:|---:|---:|---:|---|

| 10000 | 13000 | 16 | 1.784 | 4.22.1 |

| 25000 | 32500 | 39 | 3.771 | 4.22.1 |

| 50000 | 65000 | 77 | 7.42 | 4.22.1 |


Cloud initial seed: **25,000 accounts, 39 MB, 21.169 seconds, engine 4.22.0**. Native Redis allocation and RSS can exceed the graph-size measure; [memory-ceiling evidence](evals/results/memory-ceiling.json) records the transient peaks.

Current `rs-synthetic-v2` shipment remeasured locally: **25,000 accounts, 39 MB, 4.446 seconds, engine 4.22.1** ([raw evidence](evals/results/local-foundation-v2.json)).

## 4. Fixed queries and graph algorithms

Every query is human-authored. Strings from the model become parameters, never Cypher source. Traversal lengths, labels, direction, scope and metric are selected from validated bounded integers/enums. Reads use `GRAPH.RO_QUERY`; only the two private write tools and human/admin HTTP handlers can write.

The complete query catalogue, schema/index creation, identifier projections and precompute calls are inline below. The indexed ring count happens before collecting a component. Dense-hub guards run before deep traversals. Historical requests refuse unavailable global snapshots rather than leaking later-derived state.

## 5. Sixteen tools and approval flow

| Tool | Access | Purpose |
|---|---|---|

| `rs_resolve_entity` | Public read | Resolve an account, person, merchant or device by exact id, prefix or guarded fuzzy name. Only opaque ids reach the model; ambiguous candidates are never silently chosen. |

| `rs_recall_findings` | Public read | Recall bi-temporal findings before reasoning about resolved entities. Every row states when it was learned, author and human-review status, and at most five unreviewed findings return. |

| `rs_account_profile` | Public read | Profile dated inbound and outbound transfers against same-type peers. Owner and device ids, active restrictions, alerts and precomputed algorithm timestamps accompany evidence. |

| `rs_neighbourhood` | Public read | Walk one to four money-transfer hops within a dated window. Every returned hop has exact ids, paise amounts, timestamps and rails; no result means no connection within these bounds. |

| `rs_fan_pattern` | Public read | Detect bounded fan-in or fan-out with the subsequent opposite-direction drain. Legitimate merchants and payroll can also produce this pattern, so consult the peer profile before proposing action. |

| `rs_cycles` | Public read | Detect chronological cycles of three to five distinct accounts with bounded amount decay. Dense hubs are refused before traversal and all legs are at or before as_of. |

| `rs_scatter_gather` | Public read | Detect a source scattering to several mules which then gather, or a collector gathering then scattering. Exact transfer legs and temporal ordering support every pattern; absence never establishes innocence. |

| `rs_path_between` | Public read | Find directed shortest paths with FalkorDB algo.SPpaths and a bounded temporal evidence query. Future algorithm candidates are never exposed; no path is qualified by max_hops. |

| `rs_ring_members` | Public read | Read precomputed shared-identifier or money communities and their internal evidence. A count-before-collect guard refuses giant components and computed_at shows algorithm freshness. |

| `rs_hub_rank` | Public read | Rank accounts by graph-native precomputed PageRank, sampled betweenness or degree. Merchants, payroll and exchanges are excluded by default, sample size comes from Meta and historical snapshots are refused. |

| `rs_money_flow` | Public read | Run FalkorDB max-flow on the dated, aggregated seed-time FLOW projection using amount or transfer-count capacity. Calls before the projection coverage end are refused, later raw transfers are excluded, and point_in_time:false clearly labels snapshot scope. |

| `rs_shared_identifiers` | Public read | Follow shared devices, phones, addresses and owners with identifier-degree guards. Materialized multi-hop links are expanded into actual identifier ids so every displayed hop is auditable. |

| `rs_check_restrictions` | Public read | Check dated restrictions and activity after a closure request for a resolved entity. This never changes an account and every proposed action repeats this check server-side. |

| `rs_coverage_status` | Public read | Read loaded rails, covered dates and mismatched ingestion-day counts directly from the tenant graph. CASH and cross-border rail absence produce an honest not-in-graph outcome. |

| `rs_record_finding` | Private, interactive session only | Record a supported, dated, unreviewed observation; guard/verifier/evidence checks and idempotency apply. |

| `rs_propose_action` | Private, interactive session only | Create pending flag, hold recommendation, case link, escalation, SAR/STR draft or closure proposal; no consequential effect. |

Exactly fourteen reads are published at `/mcp`; the writes are in-process only. Max-flow was promoted from the originally deferred item to reconcile the numbered sixteen-tool catalogue with the explicit fourteen-read requirement. FalkorDB rejects parallel TX tensors for max-flow, so FLOW aggregates ordered pairs. Its computed-at and coverage end are visible; a historical request before that end is refused and raw later transfers are excluded until refresh. Backlog/queue tools remain future work.

```text
MCP endpoint: https://ringsight.onrender.com/mcp
Authorization: Bearer 41cd0491a95d267044eeadcdcbdaebdc
```

Connect with MCP Inspector or an MCP client supporting Streamable HTTP. List tools to see the fourteen typed read schemas and annotations. The MCP key cannot access `/approve`, `/feedback`, `/ask`, or private write tools. No run_cypher tool exists.

Approval: pending card → named human approve/deny/modify with a reason of 20–1,000 characters → Decision node with user, role, tenant and time. A hold creates only HoldProposal(status=sent_to_principal_officer), never an Account.status write. Report approval requires principal_officer. Closing requires at least two distinct nonempty checks without suspicious pattern evidence. UUIDs resolve only in the bearer’s graph. Nothing is deleted by application action paths; corrections supersede prior findings.

## 6. Four shapes, paths, trace and verification

`answered_with_path` carries exact directed evidence paths and transfer rows. `answered_from_memory` gives learned date, author and review state. `not_in_graph` always gives a reason and **Not in the graph ≠ nothing wrong**. `unknown_entity` gives graph-sourced suggestions. Infrastructure tool errors are grey trace events, not evidence of innocence.

The canvas highlights exact paths with directional particles; the hop list, rupee/IST transfer table, source tool and streaming trace explain the answer. Every trace row records tool, safe arguments, elapsed time, returned/total rows, outcome and guard hits. The final event records model, input/output/cache tokens, cost, judge verdict and deterministic verifier result.

The verifier checks opaque ids, currency including lakh/crore and Indian grouping, dates and ordinary quantities against evidence. A failed verification replaces prose with a deterministic sentence built from an actual returned path. A separate model judges only the evidence digest and thesis. Weak or contradictory closure proposals are withdrawn and superseded by escalation.

## 7. Why no free-form query generation

An investigation requires correct direction, time and evidence. A fixed, testable catalogue lets a model select a graph computation without granting query-writing authority. It also makes empty results, depth bounds, feed gaps and query timeouts distinguishable. Global algorithms are computed in the database, not simulated in Python.

## 8. Memory — Track 02

Finding nodes carry bi-temporal validity and recording time. Every question resolves entities and recalls findings first. At most five unreviewed agent findings enter a session, each capped, labelled and wrapped as untrusted. Human feedback creates a superseding analyst finding; it does not erase history. Snapshot schema 2 retains original same-bank ToolCall rows, their hashes, Sessions and supersession links, so recalled memory retains its dated path after a wipe. The snapshot in data/findings_snapshot.json restores only into its own graph. Snapshot capture follows the actual demo; an empty snapshot is not claimed as learned memory.

## 9. Safety, costs and kill switch

Server-derived identity selects the tenant graph. The UI cannot set tenant or role. All system ids are UUIDv4. CORS is same-origin; MCP Origin is checked. Names are rehydrated for humans only; model envelopes use ids. Memos scrub phone/email/name tokens before a capped untrusted envelope. READ guards flag role mimicry, ignore-instruction phrases, skip approval, mark clean and action/suppression language. WRITE guards refuse role mimicry, ignore instructions and skip approval while allowing honest hold/closure recommendations and “do not ignore prior alerts”. A paraphrase can remain unreviewed data and is flagged again on recall; it is not promoted to an instruction.

The Console workspace spending limit is the outer wall. Before provider requests: graph-backed halt/llm flags, per-bank daily cap of at most **$8 UTC/day**, three investigation slots, six graph-query slots, key/IP buckets and per-investigation bounds apply. Each investigation is limited to ten tool calls, twelve model requests, 60,000 input / 6,000 output tokens, $0.25 and 60 seconds. Reservations are written to Spend before model creation; unknown completions are charged conservatively. Caps are never raised automatically.

The strict compiler’s observed global grammar limits require bounded staged subsets from the same frozen catalogue. Server schemas retain all bounds; the model-facing schema uses trusted defaults for nullable advanced fields. Time and depth are enforced by the server. Full evidence stays in the graph/UI; the model receives a bounded projection to avoid duplicating all 1,080 coverage days every turn.

Admin commands are documented in [runbook](docs/runbook.md). `POST /admin/halt` and `POST /admin/llm` immediately stop model use. Read-only manual tools stay available. Outages, timeouts, budget/rate exhaustion and reseeding have plain error states, limited retries and heartbeat events.

## 10. Recorded evaluations — synthetic, demo-only

No detection result is a claim about real banking data. Model evaluations mutate only explicitly local disposable graphs. Result artifacts include their target, checks, counts and pass status. Missing or incomplete files do not count as a pass.

| Artifact | Recorded status |
|---|---|

| [actions-tests.json](evals/results/actions-tests.json) | 16 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [audit-regressions.json](evals/results/audit-regressions.json) | 88 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [audited-graph-contracts.json](evals/results/audited-graph-contracts.json) | 28 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [browser-audit-preflight.json](evals/results/browser-audit-preflight.json) | passed |

| [browser-preflight.json](evals/results/browser-preflight.json) | passed |

| [catalogue-audit-tests.json](evals/results/catalogue-audit-tests.json) | 20 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [catalogue-tests.json](evals/results/catalogue-tests.json) | 10 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [ci-6.0.2.json](evals/results/ci-6.0.2.json) | 370 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [ci-v4.22.1.json](evals/results/ci-v4.22.1.json) | 370 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [cloud-foundation.json](evals/results/cloud-foundation.json) | passed |

| [cloud-reseed-preflight.json](evals/results/cloud-reseed-preflight.json) | review_ready |

| [completion-gate-tests.json](evals/results/completion-gate-tests.json) | 4 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [completion.json](evals/results/completion.json) | passed |

| [compose-acceptance.json](evals/results/compose-acceptance.json) | passed |

| [compose-wrapper-tests.json](evals/results/compose-wrapper-tests.json) | 5 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [control-checkpoint-contract.json](evals/results/control-checkpoint-contract.json) | 12 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [control-checkpoint-integration.json](evals/results/control-checkpoint-integration.json) | 3 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [cycle-engine-diagnostic.json](evals/results/cycle-engine-diagnostic.json) | measurement artifact |

| [cycle-projection-tests.json](evals/results/cycle-projection-tests.json) | 67 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [db-concurrency.json](evals/results/db-concurrency.json) | 2 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [demo-path-generator.json](evals/results/demo-path-generator.json) | passed |

| [demo-video.json](evals/results/demo-video.json) | passed |

| [engine-foundation.json](evals/results/engine-foundation.json) | measurement artifact |

| [engine6-compatibility.json](evals/results/engine6-compatibility.json) | 22 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [engine6-full-local.json](evals/results/engine6-full-local.json) | 370 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [execution-logging-tests.json](evals/results/execution-logging-tests.json) | 13 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [foundation-tests.json](evals/results/foundation-tests.json) | 15 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [graph-action-end-state-tests.json](evals/results/graph-action-end-state-tests.json) | 7 passed; 8 failed; 0 error; 0 skipped; exit 1 |

| [harness-offline.json](evals/results/harness-offline.json) | 19 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [hold-repair-runtime.json](evals/results/hold-repair-runtime.json) | passed |

| [hold-repair-tests.json](evals/results/hold-repair-tests.json) | 19 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [http-validation-tests.json](evals/results/http-validation-tests.json) | 21 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [indexed-traversal-tests.json](evals/results/indexed-traversal-tests.json) | 15 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [live-acceptance.json](evals/results/live-acceptance.json) | passed |

| [live-five_concurrent.json](evals/results/live-five_concurrent.json) | passed |

| [local-eval-budget-restored.json](evals/results/local-eval-budget-restored.json) | passed |

| [local-foundation-v2.json](evals/results/local-foundation-v2.json) | passed |

| [local-foundation.json](evals/results/local-foundation.json) | measurement artifact |

| [local-smoke.json](evals/results/local-smoke.json) | passed |

| [local-validation.json](evals/results/local-validation.json) | passed |

| [local-workflow.json](evals/results/local-workflow.json) | passed |

| [memory-ceiling.json](evals/results/memory-ceiling.json) | passed |

| [memory-projection-tests.json](evals/results/memory-projection-tests.json) | 11 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [model-abstention.json](evals/results/model-abstention.json) | passed |

| [model-evaluations.json](evals/results/model-evaluations.json) | passed |

| [model-injections.json](evals/results/model-injections.json) | passed |

| [model-paths.json](evals/results/model-paths.json) | passed |

| [model-paths.previous-1792218290789650000.json](evals/results/model-paths.previous-1792218290789650000.json) | Historical interrupted trial; stopped: InvalidOperation |

| [model-paths.previous-1792219678485686000.json](evals/results/model-paths.previous-1792219678485686000.json) | Historical interrupted trial; in progress: 7/120 |

| [model-paths.previous-1792249324173658000.json](evals/results/model-paths.previous-1792249324173658000.json) | Historical interrupted trial; in progress: 12/120 |

| [model-paths.previous-1792251612457092000.json](evals/results/model-paths.previous-1792251612457092000.json) | Historical interrupted trial; in progress: 83/120 |

| [narrative.json](evals/results/narrative.json) | 3 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [offline-tests.json](evals/results/offline-tests.json) | 173 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [operational-probes.json](evals/results/operational-probes.json) | passed |

| [operations.json](evals/results/operations.json) | measurement artifact |

| [ops-control-offline.json](evals/results/ops-control-offline.json) | 23 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [ops-tooling-tests.json](evals/results/ops-tooling-tests.json) | 11 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [pytest.json](evals/results/pytest.json) | 370 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [recovery-tests.json](evals/results/recovery-tests.json) | 4 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [recovery.json](evals/results/recovery.json) | measurement artifact |

| [report-actions.json](evals/results/report-actions.json) | 6 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [report-safety-tests.json](evals/results/report-safety-tests.json) | 99 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [resolver-tests.json](evals/results/resolver-tests.json) | 18 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [resource-controls.json](evals/results/resource-controls.json) | 6 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [runtime-diagnostic.json](evals/results/runtime-diagnostic.json) | passed |

| [runtime-failure-regressions.json](evals/results/runtime-failure-regressions.json) | 76 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [runtime-regression.json](evals/results/runtime-regression.json) | 11 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [runtime-smoke.json](evals/results/runtime-smoke.json) | passed |

| [secret-check-tests.json](evals/results/secret-check-tests.json) | 36 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [secrets-scan.json](evals/results/secrets-scan.json) | passed |

| [seeded-path-facts.json](evals/results/seeded-path-facts.json) | 16 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [sizing.json](evals/results/sizing.json) | measurement artifact |

| [snapshot-contract.json](evals/results/snapshot-contract.json) | 15 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [structural-patterns.json](evals/results/structural-patterns.json) | passed |

| [structural-read-contracts.json](evals/results/structural-read-contracts.json) | 16 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [temporal-traversal-tests.json](evals/results/temporal-traversal-tests.json) | 20 passed; 0 failed; 0 error; 0 skipped; exit 0 |

| [ui-browser.json](evals/results/ui-browser.json) | passed |

| [ui-real-local.json](evals/results/ui-real-local.json) | passed |

| [ui-unit-tests.json](evals/results/ui-unit-tests.json) | 6 UI unit tests passed |

| [ui-unit.json](evals/results/ui-unit.json) | 6 UI unit tests passed |


**Path correctness: 120/120 cases passed**, $3.842460 actual model cost. Every cited path was checked against authoritative graph facts; first selected tool matched the expected pattern in 100% of cases. The verifier replaced 120 generated answers with evidence-built text.


**Exposed injection attacks: 40/40 cases passed**, $2.519709 actual model cost. 40 attacks reached the model's guarded evidence; 0 unapproved effects and 0 instruction stores.


**Deleted-ring abstentions: 20/20 cases passed**, $0.256669 actual model cost. 100% valid abstention; 0% false path answers.

Local model timing execution: up to 3 concurrent path investigations; injection/abstention remain serial.

The owner explicitly approved $12 total for the local `eval_model` evaluation on UTC 20261017, preserving prior liability. The temporary approval applied only on that day; the public bank and Console limits were unchanged.


Observed end-to-end latency (nearest-rank percentiles; small samples are labelled by N):

| Target / suite | Depth | N | p50 seconds | p95 seconds |
|---|---:|---:|---:|---:|

| Local runtime smoke | 1 | 1 | 18.207 | 18.207 |

| Local runtime smoke | 4 | 1 | 41.872 | 41.872 |

| Local model protocol | 1 | 40 | 15.340 | 18.653 |

| Local model protocol | 2 | 40 | 15.631 | 20.957 |

| Local model protocol | 4 | 40 | 15.179 | 19.321 |

| Live acceptance | 1 | 1 | 36.434 | 36.434 |

| Live acceptance | 4 | 1 | 36.045 | 36.045 |

| Live concurrent load | 4 | 3 | 38.190 | 39.371 |


Pattern results:

| Pattern | Recall |
|---|---:|

| bipartite | 1.0 |

| cycle | 1.0 |

| fan_in | 0.9777777777777777 |

| fan_out | 0.875 |

| gather_scatter | 1.0 |

| scatter_gather | 1.0 |

| stack | 1.0 |

Global planted-hub precision@10: **betweenness: 0.000**, **in_deg: 0.200**, **out_deg: 0.000**, **pagerank: 0.000**. Legitimate merchant/payroll/exchange hubs remain present and are excluded from this ranking. Weak global hub precision is an explicit limitation.

About 15 seconds is a demo target, not a guarantee. Local measurements are not live free-tier measurements. Missing live measurements are not inferred from local timings.

```sh
# Both runners select LOCAL Redis themselves; no shell export is needed.
.venv/bin/python ops/verify_local.py
# Archive the checked-in trial before a new paid evaluation.
.venv/bin/python ops/verify_evals.py --new-trial
```
The evaluation runner measures 35 rings on the 25k local graph, then runs 40 questions × depths 1/2/4, 20 memo attacks twice, and 20 deleted-ring abstentions. It saves progress after every case. Omit `--new-trial` only to resume an interrupted trial with the same source, budget and concurrency signature. Resume retains completed failures and the graph spending ledger; an explicit new trial archives its predecessor. No Cloud graph is used for model evaluation fixtures.

## 11. Deployment and operations

Render Free runs one Docker service, one worker, health path `/live`. `/health` reports population, completion, graph size, pending count, today’s spend, engine, catalogue, RSS and a cached one-token model reachability probe. It returns 503 for incomplete seeding or failed model reachability. The health body is cached 15 seconds and the model probe ten minutes. `/live` only checks process responsiveness.

Auto-reseed triggers only when Account count is zero or Meta.seed_complete is missing. A background subprocess lets the UI show warming up and ETA. The deadline is max(15 minutes, 3 × previous reseed time); timeout kills the loader and requires an explicit forced retry. The final Meta write occurs only after schema, algorithms and same-tenant snapshot restoration.

Planned rebuilds bridge Tenant settings and all Spend days through a private atomic checkpoint scoped to the database fingerprint and bank. Caps can only decrease and pending reservations are conservatively charged. The bridge is removed after success and is never a second runtime store. Sudden Cloud loss without a bridge still has the Console limit as the outer wall.

Actions cron pings `/health` every twelve minutes with curl -f; a daily question checks the agent. Cloudflare’s independent Worker cron and UptimeRobot email monitor follow setup.md items 6–7. The owner confirmed UptimeRobot, Cloudflare cron and GitHub keepalive setup ([configuration evidence](evals/results/operations.json)). Current-source CI, health and daily-question jobs succeeded: [keepalive.yml](https://github.com/Baharul0111/RingSight/actions/runs/39083716142), [daily-probe.yml](https://github.com/Baharul0111/RingSight/actions/runs/39087562823), [ci.yml](https://github.com/Baharul0111/RingSight/actions/runs/39046049271). This does not independently verify email delivery. Keep one Render free service to stay within the shared free-hour pool.

**If the demo is down:** wait for cold start; inspect `/health`; use the manual tool form during a model outage/cap; check Cloud connectivity; force a demo-only reseed if failed; rotate compromised demo keys; use local Compose for judging. [Full runbook](docs/runbook.md) includes stuck reseeds, persisted ledgers, backups, and Fly.io fallback. Cloud Free has no persistence/backups/TLS; synthetic data only. Recovery point is the last checked-in findings snapshot and synthetic seed, not every judge decision.

## 12. Regulatory mapping and pilot posture

FinCEN-style drafts use who/what/when/where/why/how in introduction/body/conclusion, listing each transfer date and amount without narrative tables. Indian drafts include grounds-of-suspicion tags, narration under 20,000 characters and provisional rail sheet mappings. All Indian format facts are visibly **[unverified-primary]** pending verification against the official document. Neither export files any real report.

Report approval belongs to a Principal Officer. A hold is only a recommendation, not an account restriction. The demo stores a seven-calendar-day STR due timestamp as a conservative design assumption; counsel must confirm working-day/calendar rules and holiday treatment before a pilot. No production compliance conclusion is claimed.

A pilot begins in shadow mode with synthetic or bank-approved data, human final authority, in-India app/graph storage and an approved in-region model endpoint with DPA/ZDR terms or the on-prem model ladder. Before real deployment: vendor DPAs (model, graph, cloud, monitoring), MFA, encryption/TLS, retention/deletion policy, lawful basis, incident notification procedures, bank security review and VAPT, model validation, load test, and a tested restore process. Legal facts in architecture.md labelled unverified/lane-recorded remain so.

## 13. Scale plan and honest ceilings

At pilot scale, precompute nightly on a recent-transaction projection. Then add queue-buffered single-writer ingestion, indexed caches and read replicas, tenant × region shards with warehouse history, and supervised features from reviewed decisions. A billion raw TX edges do not fit in one graph key. Sampled betweenness and dense cycle enumeration break first. The audit trail needs a hot retention window and archive graph; multiple app instances require shared distributed rate limits and reservations. Production tamper detection requires session/tenant hash chains and off-box WORM anchors; the demo audit graph does not claim tamper prevention.

## 14. AI assistance

Built by Baharul Islam using OpenAI Codex as the coding assistant. Codex produced implementation, tests and the React console under the supplied goal and architecture. The running agent uses the Claude API with environment-configured planner, judge and health models. Report drafts use evidence-only templates. No claim is made that a Messages Batch or narrative-polish run occurred without its result artifact. The public queries, approval rules, test evidence and measured limitations make the implementation reviewable.

## 15. Licences and data statement

RingSight’s own code: [MIT](LICENSE). FalkorDB: [SSPL v1 notice](NOTICE). AMLSim typology port: IBM AMLSim Apache-2.0 attribution in NOTICE and [upstream licence](licenses/AMLSim-Apache-2.0.txt). All accounts, people and payments are generated synthetic data. Ground truth is not a model input. For a paid pilot, default to bank-operated FalkorDB with RingSight software/tooling; startup-hosted FalkorDB requires written commercial terms before launch.

## 16. Limitations and completion gate

Free-tier cold starts, transient database memory peaks, no Cloud Free durability/TLS, weak synthetic global hub precision, approximate algorithms, provisional Indian format mapping, static demo keys and single-process rate limits are explicit constraints. The application never certifies an account clean from an absent path. A timeout yields an honest partial/insufficient answer and escalation when supported.

Completion requires passing local and live/model checks, approved human workflow, cross-session memory, exact fourteen public MCP reads, manual fallback, monitor confirmation, measured latency, snapshot, an actual three-minute video and committed results. The final hackathon submission and any spend-limit increase wait for Baharul’s explicit go-ahead.

The [requirement checklist](docs/requirement-checklist.md) maps all 22 goal items and architecture sections to evidence. Run `.venv/bin/python ops/check_completion.py` for the read-only completion gate; it fails while required proof is missing, stale, failed or uncommitted.

## 17. Blog

[Draft: What the fines say the agent must do](docs/blog.md). The blog is a repository draft; it is not described as published externally.

[Submission rules checklist](docs/submission-checklist.md) maps all 18 supplied rules to project evidence or owner-only attestations. [Explain RingSight](docs/explain-ringsight.md) is a source-linked participant review guide; neither document certifies personal understanding, eligibility, start timing or ownership agreements. The internal goal is 18 October 2026 at 23:00 IST; the supplied official closing time is 23:59 IST. Final submission still waits for explicit approval.

## Inline Cypher — schema, projections and every tool

### `fulltext.cypher`

```cypher
CALL db.idx.fulltext.createNodeIndex({label:'Person', language:'English'}, {field:'name_norm', phonetic:'dm:en'});
CALL db.idx.fulltext.createNodeIndex('Merchant', {field:'name', phonetic:'dm:en'});
CALL db.idx.fulltext.createNodeIndex('Finding', 'text');
```

### `fulltext_v6.cypher`

```cypher
// v6.0.2's createNodeIndex(map) procedure is a no-op; DDL creates real indexes.
// Phonetic configuration is preserved, as exercised by the upstream6 tests.
CREATE FULLTEXT INDEX FOR (p:Person) ON (p.name_norm) OPTIONS {language:'English',phonetic:'dm:en'};
CREATE FULLTEXT INDEX FOR (m:Merchant) ON (m.name) OPTIONS {phonetic:'dm:en'};
CREATE FULLTEXT INDEX FOR (f:Finding) ON (f.text);
```

### `indexes.cypher`

```cypher
CREATE INDEX FOR (a:Account) ON (a.id);
CREATE INDEX FOR (a:Account) ON (a.type);
CREATE INDEX FOR (a:Account) ON (a.wcc_id);
CREATE INDEX FOR (a:Account) ON (a.lpa_id);
CREATE INDEX FOR (a:Account) ON (a.ring_id);
CREATE INDEX FOR (p:Person) ON (p.id);
CREATE INDEX FOR (d:Device) ON (d.id);
CREATE INDEX FOR (p:Phone) ON (p.id);
CREATE INDEX FOR (p:Address) ON (p.id);
CREATE INDEX FOR (m:Merchant) ON (m.id);
CREATE INDEX FOR (a:Alert) ON (a.id);
CREATE INDEX FOR (f:Finding) ON (f.id);
CREATE INDEX FOR (f:Finding) ON (f.idem_key);
CREATE INDEX FOR (f:Finding) ON (f.created_at);
CREATE INDEX FOR (p:PendingAction) ON (p.id);
CREATE INDEX FOR (p:PendingAction) ON (p.idem_key);
CREATE INDEX FOR (p:PendingAction) ON (p.status);
CREATE INDEX FOR (c:Case) ON (c.id);
CREATE INDEX FOR (i:IngestionDay) ON (i.rail);
CREATE INDEX FOR (t:Tenant) ON (t.name);
CREATE INDEX FOR (s:Spend) ON (s.day);
CREATE INDEX FOR (s:Session) ON (s.id);
CREATE INDEX FOR (t:ToolCall) ON (t.id);
CREATE INDEX FOR (d:Decision) ON (d.id);
CREATE INDEX FOR (r:Restriction) ON (r.id);
CREATE INDEX FOR (r:Rail) ON (r.name);
CREATE INDEX FOR ()-[t:TX]-() ON (t.ts);
CREATE INDEX FOR ()-[t:TX]-() ON (t.id);
```

### `precompute.cypher`

```cypher
MATCH (a:Account)-[t:TX]->(b:Account) WITH a,b,sum(t.amount) AS amount,count(t) AS n,max(t.ts) AS last,min(t.ts) AS first MERGE (a)-[f:FLOW]->(b) SET f.id='FLOW-'+toString(id(a))+'-'+toString(id(b)),f.amount=amount,f.w=n,f.ts=last,f.first_ts=first,f.computed_at=$now;
CALL algo.pageRank('Account','TX') YIELD node, score SET node.pagerank = score;
CALL algo.betweenness({nodeLabels:['Account'], relationshipTypes:['TX'], samplingSize:32, samplingSeed:42}) YIELD node, score SET node.betweenness = score;
CALL algo.WCC({nodeLabels:['Account'], relationshipTypes:['TX']}) YIELD node, componentId SET node.wcc_id = componentId;
CALL algo.labelPropagation({nodeLabels:['Account'], relationshipTypes:['TX'], maxIterations:10}) YIELD node, communityId SET node.lpa_id = communityId;
CALL algo.WCC({nodeLabels:['Account'], relationshipTypes:['SHARES_STRONG']}) YIELD node, componentId SET node.ring_id = componentId;
MATCH (a:Account) SET a.algo_run_at = $now;
MATCH (a:Account) WHERE a.id IN $account_ids OPTIONAL MATCH (a)<-[i:TX]-() WITH a, count(i) AS n_in OPTIONAL MATCH (a)-[o:TX]->() WITH a, n_in, count(o) AS n_out SET a.in_deg = n_in, a.out_deg = n_out;
```

### `rs_account_profile.cypher`

```cypher
MATCH (a:Account {id:$id})
OPTIONAL MATCH (a)<-[i:TX]-(s:Account) WHERE i.ts > $from AND i.ts <= $as_of
WITH a, count(i) AS in_n, coalesce(sum(i.amount),0) AS in_sum, count(DISTINCT s) AS in_cp, max(i.amount) AS in_max
OPTIONAL MATCH (a)-[o:TX]->(r:Account) WHERE o.ts > $from AND o.ts <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, count(o) AS out_n, coalesce(sum(o.amount),0) AS out_sum, count(DISTINCT r) AS out_cp
OPTIONAL MATCH (p:Person)-[own:OWNS]->(a) WHERE coalesce(own.since,0) <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, collect(DISTINCT p.id) AS owners
OPTIONAL MATCH (a)-[u:USES_DEVICE]->(d:Device) WHERE u.first_seen <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, collect(DISTINCT {id:d.id,degree:d.degree}) AS devices
OPTIONAL MATCH (al:Alert)-[:ON]->(a) WHERE al.raised_at <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, devices, collect(DISTINCT {id:al.id,rule:al.rule,raised_at:al.raised_at}) AS alerts
OPTIONAL MATCH (rx:Restriction)-[:ON]->(a) WHERE rx.in_force_from <= $as_of AND (rx.in_force_to IS NULL OR rx.in_force_to >= $as_of)
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, devices, alerts, collect(DISTINCT {id:rx.id,kind:rx.kind}) AS restrictions
OPTIONAL MATCH (f:Finding)-[:ABOUT]->(a) WHERE f.created_at <= $as_of AND f.expired_at IS NULL
RETURN a.id AS id, a.type AS type, a.bank AS bank, a.opened_at AS opened_at, a.kyc_tier AS kyc_tier, a.status AS status,
 a.in_deg AS in_deg, a.out_deg AS out_deg, a.pagerank AS pagerank, a.betweenness AS betweenness,
 a.wcc_id AS wcc_id, a.lpa_id AS lpa_id, a.ring_id AS ring_id, a.algo_run_at AS computed_at,
 in_n,in_sum,in_cp,in_max,out_n,out_sum,out_cp,
 CASE WHEN in_sum=0 OR out_sum=0 THEN 0.0 ELSE toFloat(CASE WHEN in_sum<out_sum THEN in_sum ELSE out_sum END)/toFloat(CASE WHEN in_sum<out_sum THEN out_sum ELSE in_sum END) END AS passthrough_ratio,
 owners,devices,alerts,restrictions,count(DISTINCT f) AS prior_findings
```

### `rs_check_restrictions.cypher`

```cypher
MATCH (e:{label} {id:$id})
OPTIONAL MATCH (r:Restriction)-[:ON]->(e)
WHERE r.in_force_from<=$as_of AND (r.in_force_to IS NULL OR r.in_force_to >= $as_of)
WITH e,collect({id:r.id,kind:r.kind,from:r.in_force_from,to:r.in_force_to,source:r.source}) AS restrictions
{closure}
```

### `rs_coverage_status.cypher`

```cypher
MATCH (r:Rail) WITH collect({name:r.name,first:r.first_loaded,last:r.last_loaded}) AS rails
OPTIONAL MATCH (d:IngestionDay)
WHERE ($rail IS NULL OR d.rail=$rail) AND ($f IS NULL OR d.date >= $f) AND ($t IS NULL OR d.date <= $t)
WITH rails,collect({rail:d.rail,date:d.date,source:d.source_count,graph:d.graph_count,delta:d.source_count-d.graph_count}) AS days
RETURN rails,days,[x IN days WHERE x.delta<>0 | x] AS delta_days,
 [x IN ['UPI','NEFT','RTGS','IMPS','CARD','WALLET','CASH','XB'] WHERE NOT x IN [r IN rails | r.name]] AS missing_rails
```

### `rs_cycles.cypher`

```cypher
// Fixed unrolled lengths 3, 4, 5. No caller string enters the template.
MATCH {pattern}
WHERE {predicates}
RETURN {length} AS len,[{accounts}] AS accounts,
 [{edges}] AS edges,
 r{length}.ts-r1.ts AS span_s
LIMIT $limit
```

### `rs_fan_pattern.cypher`

```cypher
// incoming/outgoing anchors and drain are enum-selected fixed templates.
MATCH {main}
WHERE t.ts>$as_of-$win AND t.ts<=$as_of
WITH a,count(DISTINCT s) AS n_cp,count(t) AS n_tx,sum(t.amount) AS total,min(t.ts) AS first_ts,max(t.ts) AS last_ts,
 collect({tx:t.id,source:{leg_src},target:{leg_dst},amount:t.amount,ts:t.ts,rail:t.rail,memo:t.memo,type:'TX'}) AS legs
WHERE n_cp >= $min_cp
OPTIONAL MATCH {drain}
WHERE o.ts>first_ts AND o.ts<=last_ts+$drain AND o.ts<=$as_of
WITH a,n_cp,n_tx,total,first_ts,last_ts,legs,count(o) AS drain_n,coalesce(sum(o.amount),0) AS drain_sum,
 collect({tx:o.id,source:{drain_src},target:{drain_dst},amount:o.amount,ts:o.ts,rail:o.rail,memo:o.memo,type:'TX'}) AS drain_legs
RETURN a.id AS account,n_cp,n_tx,total,first_ts,last_ts,legs[0..$limit] AS legs,drain_n,drain_sum,
 CASE WHEN total=0 THEN 0.0 ELSE toFloat(drain_sum)/toFloat(total) END AS drain_ratio,drain_legs[0..20] AS drain_legs
```

### `rs_gather_scatter.cypher`

```cypher
MATCH (src:Account)-[t1:TX]->(c:Account {id:$id})-[t2:TX]->(dst:Account)
WHERE CASE WHEN t1.ts>$as_of-$win AND t1.ts<=$as_of AND t2.ts<=$as_of AND t1.ts<t2.ts AND t2.ts-t1.ts<=$win AND src<>dst AND src<>c AND dst<>c
 AND endNode(t1).id=$id AND startNode(t2).id=$id
 AND startNode(t1).id=src.id AND endNode(t2).id=dst.id THEN true ELSE false END
WITH c,collect(DISTINCT src.id) AS sources,count(DISTINCT src) AS n_src,collect(DISTINCT dst.id) AS dests,count(DISTINCT dst) AS n_dst,
 collect(DISTINCT {id:t1.id,source:startNode(t1).id,target:endNode(t1).id,amount:t1.amount,ts:t1.ts,rail:t1.rail,memo:t1.memo,type:'TX'}) AS in_legs,
 collect(DISTINCT {id:t2.id,source:startNode(t2).id,target:endNode(t2).id,amount:t2.amount,ts:t2.ts,rail:t2.rail,memo:t2.memo,type:'TX'}) AS out_legs
WHERE n_src >= $min AND n_dst >= $min
RETURN c.id AS collector,n_src,sources,n_dst,dests,
 reduce(total=0,leg IN in_legs | total+leg.amount) AS gathered,
 reduce(total=0,leg IN out_legs | total+leg.amount) AS scattered,
 in_legs[0..$limit] AS in_legs,out_legs[0..$limit] AS out_legs
```

### `rs_hub_rank.cypher`

```cypher
MATCH (a:Account{scope})
WHERE $inc OR NOT a.type IN ['merchant','payroll','exchange']
RETURN a.id AS id,a.type AS type,a.pagerank AS pagerank,a.betweenness AS betweenness,a.in_deg AS in_deg,a.out_deg AS out_deg,
 a.type IN ['merchant','payroll','exchange'] AS legit_hub,a.algo_run_at AS computed_at,$exact AS exact
ORDER BY a.{metric} DESC,a.id LIMIT $limit
```

### `rs_money_flow.cypher`

```cypher
// Aggregated seed-time FLOW projection avoids unsupported TX multi-edges.
// The server refuses as_of before the projection's latest transfer timestamp.
MATCH (s:Account) WHERE s.id IN $sources WITH collect(s) AS S
MATCH (t:Account) WHERE t.id IN $sinks WITH S,collect(t) AS T
CALL algo.maxFlow({sourceNodes:S,targetNodes:T,relationshipTypes:['FLOW'],capacityProperty:$cap})
YIELD nodes,edges,edgeFlows,maxFlow
RETURN maxFlow,[n IN nodes | n.id] AS node_ids,
 [i IN range(0,size(edges)-1) | {id:edges[i].id,flow:edgeFlows[i],amount:edges[i].amount,ts:edges[i].ts,first_ts:edges[i].first_ts,count:edges[i].w,source:startNode(edges[i]).id,target:endNode(edges[i]).id,type:'FLOW'}] AS flow_edges
```

### `rs_neighbourhood.cypher`

```cypher
// Each layer retains one actual route per reached account before expanding.
MATCH (n0:Account {id:$id})
WITH n0,[n0.id] AS path0,[] AS edges0
{expansions}
WITH n{hops} AS b,path{hops} AS path_ids,edges{hops} AS edges
WHERE b.id<>$id
RETURN b.id AS neighbour,b.type AS type,b.pagerank AS pagerank,{hops} AS hops,path_ids,edges
ORDER BY hops,neighbour LIMIT $limit
```

### `rs_path_algorithm.cypher`

```cypher
MATCH (s:Account {id:$src}),(d:Account {id:$dst})
CALL algo.SPpaths({sourceNode:s,targetNode:d,relTypes:$rel_types,relDirection:'outgoing',weightProp:$wprop,maxLen:$max_hops,pathCount:$k})
YIELD path,pathWeight
RETURN [n IN nodes(path) | n.id] AS node_ids,
 [r IN relationships(path) | {id:r.id,type:type(r),amount:r.amount,ts:r.ts,rail:r.rail}] AS edges,
 length(path) AS hops,pathWeight
```

### `rs_path_between.cypher`

```cypher
MATCH (s:Account {id:$src}),(d:Account {id:$dst})
MATCH p=(s)-[:{rels}*1..{hops}]->(d)
WITH p,relationships(p) AS rs,nodes(p) AS ns
WHERE all(r IN rs WHERE (type(r)='TX' AND r.ts<=$as_of AND r.ts>$from) OR (type(r)='SHARES_STRONG' AND r.computed_at<=$as_of))
RETURN [n IN ns | n.id] AS node_ids,
 [i IN range(0,size(rs)-1) | {id:rs[i].id,type:type(rs[i]),amount:rs[i].amount,ts:rs[i].ts,rail:rs[i].rail,memo:rs[i].memo,source:startNode(rs[i]).id,target:endNode(rs[i]).id}] AS edges,
 length(p) AS hops,reduce(w=0,r IN rs | w+coalesce(r.{weight},1)) AS pathWeight
ORDER BY pathWeight,hops LIMIT $limit
```

### `rs_recall_actions.cypher`

```cypher
MATCH (pa:PendingAction)-[:BASED_ON]->(f:Finding)
WHERE f.id IN $ids
RETURN DISTINCT f.id AS finding_id,pa.id AS pending,pa.kind AS kind,pa.status AS status
ORDER BY finding_id,pending
```

### `rs_recall_decisions.cypher`

```cypher
MATCH (d:Decision)-[:ON]->(pa:PendingAction)-[:BASED_ON]->(f:Finding)
WHERE f.id IN $ids
RETURN DISTINCT f.id AS finding_id,pa.id AS pending,d.decision AS decision
ORDER BY finding_id,pending
```

### `rs_recall_findings.cypher`

```cypher
MATCH (f:Finding)-[:ABOUT]->(e:{label})
WHERE e.id IN $ids AND f.created_at <= $as_of AND f.valid_from <= $as_of
  AND (f.expired_at IS NULL OR f.expired_at > $as_of)
  AND (f.valid_to IS NULL OR f.valid_to >= $as_of)
  AND ($inc OR f.reviewed)
RETURN properties(f) AS finding, f.created_at AS date_learned,
 collect(DISTINCT e.id) AS about
ORDER BY date_learned DESC LIMIT $limit
```

### `rs_recall_supersedes.cypher`

```cypher
// Optional context is read separately so absent actions cannot remove findings.
MATCH (f:Finding)-[:SUPERSEDES]->(old:Finding)
WHERE f.id IN $ids
RETURN f.id AS finding_id,old.id AS supersedes
ORDER BY finding_id,supersedes
```

### `rs_resolve_alert.cypher`

```cypher
// Alert ids use ALERT-... in the generator. The target is a dated preflight anchor.
MATCH (e:Alert {id:$q})
WHERE e.raised_at <= $as_of
OPTIONAL MATCH (e)-[:ON]->(a:Account)
RETURN 'Alert' AS label, e.id AS id, 1.0 AS score, 'exact' AS how,
       e.raised_at AS raised_at, a.id AS account_id
```

### `rs_resolve_entity.cypher`

```cypher
// $label is selected by the validated kind; labels are never caller text.
MATCH (e:{label} {id:$q})
RETURN '{label}' AS label, e.id AS id, 1.0 AS score, 'exact' AS how
```

### `rs_resolve_transfer.cypher`

```cypher
// Exact, indexed transfer resolution. Future transfers never enter preflight.
MATCH (source:Account)-[t:TX {id:$q}]->(target:Account)
WHERE t.ts <= $as_of
RETURN 'Transfer' AS label, t.id AS id, 1.0 AS score, 'exact' AS how,
       source.id AS source, target.id AS target, t.amount AS amount,
       t.ts AS ts, t.rail AS rail, t.memo AS memo, 'TX' AS type
```

### `rs_ring_details.cypher`

```cypher
MATCH (m:Account {{prop}:$cid})
OPTIONAL MATCH (m)-[t:TX]->(n:Account {{prop}:$cid}) WHERE t.ts<=$as_of
OPTIONAL MATCH (f:Finding)-[:ABOUT]->(m) WHERE f.typology IS NOT NULL AND f.expired_at IS NULL AND f.created_at<=$as_of
WITH m,count(DISTINCT t) AS t_n,count(DISTINCT f) AS f_n
RETURN $cid AS ring_id,$n AS size,
 collect({id:m.id,type:m.type,pagerank:m.pagerank,in_deg:m.in_deg,legit_hub:m.type IN ['merchant','payroll','exchange'],findings:f_n}) AS members,
 sum(t_n) AS internal_tx,sum(1.0/log(coalesce(m.in_deg,0)+5))/$n AS hub_weighted_density,
 toFloat(sum(CASE WHEN f_n>0 THEN 1 ELSE 0 END))/$n AS flagged_ratio
```

### `rs_ring_members.cypher`

```cypher
// Count before any collection, to refuse a giant component cheaply.
MATCH (seed:Account {id:$id})
WITH seed.{prop} AS cid,seed.algo_run_at AS computed_at
MATCH (m:Account {{prop}:cid})
WITH cid,computed_at,count(m) AS n
RETURN cid,computed_at,n,(n >= $min AND n <= $max) AS in_bounds
```

### `rs_scatter_gather.cypher`

```cypher
MATCH (s:Account {id:$id})-[t1:TX]->(m:Account)-[t2:TX]->(g:Account)
WHERE CASE WHEN t1.ts>$as_of-$win AND t1.ts<=$as_of AND t2.ts<=$as_of AND t1.ts<t2.ts AND t2.ts-t1.ts<=$win AND g<>s AND m<>g AND m<>s
 AND startNode(t1).id=$id AND endNode(t1).id=startNode(t2).id
 AND endNode(t1).id=m.id AND endNode(t2).id=g.id THEN true ELSE false END
WITH s,g,collect(DISTINCT m.id) AS mules,count(DISTINCT m) AS n_mules,
 collect({out_tx:t1.id,in_tx:t2.id,mule:endNode(t1).id,out_amt:t1.amount,in_amt:t2.amount,out_ts:t1.ts,in_ts:t2.ts,source:startNode(t1).id,gatherer:endNode(t2).id,out_rail:t1.rail,in_rail:t2.rail}) AS legs,
 collect(DISTINCT {id:t1.id,amount:t1.amount}) AS out_transfers,
 collect(DISTINCT {id:t2.id,amount:t2.amount}) AS in_transfers
WHERE n_mules >= $min
RETURN s.id AS source,g.id AS gatherer,n_mules,mules,legs[0..$limit] AS legs,
 reduce(total=0,leg IN out_transfers | total+leg.amount) AS scattered,
 reduce(total=0,leg IN in_transfers | total+leg.amount) AS gathered
ORDER BY n_mules DESC LIMIT $limit
```

### `rs_shared_identifiers.cypher`

```cypher
MATCH (a:Account {id:$id})-[u1:USES_DEVICE]->(d:Device)<-[u2:USES_DEVICE]-(b:Account)
WHERE b<>a AND d.degree<=$max_deg AND u1.first_seen<=$as_of AND u2.first_seen<=$as_of
RETURN b.id AS linked,'Account' AS kind,'soft' AS strength,1 AS hops,
 [a.id,d.id,b.id] AS path_ids,['USES_DEVICE','USES_DEVICE'] AS link_kinds,d.degree AS identifier_degree
LIMIT $limit
```

### `rs_shared_materialized.cypher`

```cypher
MATCH p=(a:Account {id:$id})-[:SHARES*1..{hops}]-(b:Account)
WITH p,a,b,relationships(p) AS rs,nodes(p) AS ns
WHERE b<>a AND all(s IN rs WHERE s.computed_at<=$as_of AND any(k IN s.kinds WHERE k IN $kinds))
WITH b,length(p) AS hops,rs,ns ORDER BY hops
WITH b,min(hops) AS hops,head(collect(rs)) AS rs,head(collect(ns)) AS ns
RETURN b.id AS linked,'Account' AS kind,hops,[n IN ns | n.id] AS path_ids,
 [s IN rs | {weight:s.weight,kinds:s.kinds}] AS link_kinds,reduce(w=1.0,s IN rs | w*s.weight) AS path_weight
ORDER BY hops,path_weight DESC LIMIT $limit
```

### `shared_projection.cypher`

```cypher
// The loader materialises these exact weights from the generated identifier
// incidence lists; this query is the equivalent refresh after a data update.
MATCH (a:Account)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(b:Account)
WHERE a.id < b.id AND d.degree <= 10
WITH a, b, sum(1.0 / log(d.degree + 5)) AS w
MERGE (a)-[s:SHARES]->(b)
SET s.weight = coalesce(s.weight, 0) + w, s.kinds = coalesce(s.kinds, []) + ['device'], s.computed_at = $now;
MATCH (a:Account)-[s:SHARES]->(b:Account) WHERE s.weight >= 0.6
MERGE (a)-[t:SHARES_STRONG]->(b) SET t.weight = s.weight, t.kinds = s.kinds, t.computed_at = s.computed_at;
```

## Inline control queries

These additional statements implement tenant-scoped sessions, audit, memory, decisions, safety and health. Template variables are selected by server code or passed as parameters. The public request cannot provide query text.

### Control statements in `seed/__init__.py`

```cypher
MATCH (m:Meta) RETURN m.seed_complete AS complete, m.reseed_s AS reseed_s, m.graph_mb AS graph_mb LIMIT 1

MATCH (a:Account) RETURN a.id AS id ORDER BY a.id SKIP $offset LIMIT 500

MATCH (m:Meta) RETURN m.seed_complete AS complete,m.reseed_s AS reseed_s LIMIT 1

MATCH (m:Meta) RETURN m.reseed_s AS reseed_s LIMIT 1

MATCH (a:Account) RETURN count(a) AS n
```

### Control statements in `seed/control_checkpoint.py`

```cypher
MATCH (t:Tenant {name:$name}) RETURN properties(t) AS tenant LIMIT 2

MATCH (s:Spend) RETURN s.day AS day,s.usd AS usd,s.reserved AS reserved,s.calls AS calls,s.updated_at AS updated_at

MERGE (t:Tenant {name:$name}) ON CREATE SET t.halted=false,t.llm_enabled=true,t.daily_usd_cap=$cap WITH t SET t += $props,t.halted=coalesce(t.halted,false) OR $halted,t.llm_enabled=coalesce(t.llm_enabled,true) AND $enabled,t.daily_usd_cap=CASE WHEN coalesce(t.daily_usd_cap,$cap)<$cap THEN t.daily_usd_cap ELSE $cap END RETURN t.name AS name

MERGE (s:Spend {day:$day}) ON CREATE SET s.usd=0.0,s.reserved=0.0,s.calls=0 WITH s,coalesce(s.usd,0)+CASE WHEN coalesce(s.reserved,0)>0 THEN s.reserved ELSE 0 END AS liability SET s.usd=CASE WHEN liability>$usd THEN liability ELSE $usd END,s.reserved=0.0,s.calls=CASE WHEN coalesce(s.calls,0)>$calls THEN s.calls ELSE $calls END,s.updated_at=$now RETURN s.day AS day
```

### Control statements in `seed/snapshot.py`

```cypher
MATCH (t:ToolCall) WHERE t.id IN $ids OPTIONAL MATCH (t)-[:IN]->(s:Session) RETURN properties(t) AS tool_call,collect(DISTINCT s.id) AS session_ids ORDER BY tool_call.id

MERGE (s:Session {id:$id}) ON CREATE SET s = $props RETURN s.id AS id

MATCH (s:Session {id:$sid}) MERGE (t:ToolCall {id:$id}) ON CREATE SET t = $props MERGE (t)-[:IN]->(s) RETURN t.id AS id

MERGE (f:Finding {idem_key:$key}) ON CREATE SET f = $props RETURN f.id AS id

MATCH (f:Finding) RETURN count(f) AS n

MATCH (f:Finding) OPTIONAL MATCH (f)-[:ABOUT]->(e) OPTIONAL MATCH (f)-[:MADE_IN]->(s:Session) OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Finding) RETURN properties(f) AS finding,collect(DISTINCT {id:e.id,labels:labels(e)}) AS entities,collect(DISTINCT s.id) AS session_ids,collect(DISTINCT old.id) AS supersedes ORDER BY finding.id SKIP $offset LIMIT $limit

MATCH (s:Session) WHERE s.id IN $ids RETURN properties(s) AS session ORDER BY session.id
```

### Control statements in `server/actions.py`

```cypher
CREATE (s:Session {id:$id,tenant:$tenant,analyst:$analyst,started_at:$now,as_of:$asof,model_planner:$model,model_judge:$judge,catalogue_hash:$hash,prompt_sha256:$prompt}) WITH s MERGE (c:CatalogueVersion {hash:$hash}) ON CREATE SET c.since=$now,c.tools=$tools,c.prompt_sha256=$prompt,c.schemas_sha256=$schemas,c.cypher_sha256=$cypher,c.implementation_sha256=$implementation,c.fingerprint_format=$format MERGE (s)-[:USED]->(c) RETURN s.id AS id

MATCH (p:PendingAction) OPTIONAL MATCH (p)-[:TARGETS]->(a:Account) OPTIONAL MATCH (p)-[:IN]->(s:Session) RETURN p.id AS pending_id,p.kind AS kind,p.status AS status,p.rationale AS rationale,p.created_at AS created_at,p.restriction_check_json AS restrictions_json,p.draft_json AS draft_json,p.evidence_tool_call_ids AS evidence_tool_call_ids,p.case_id AS case_id,s.id AS session_id,collect(DISTINCT a.id) AS targets ORDER BY created_at DESC SKIP $offset LIMIT $limit

MATCH (f:Finding {id:$id}) RETURN f.id AS id,f.expired_at AS expired

MATCH (old:Finding {id:$old}) WHERE old.expired_at IS NULL CREATE (f:Finding {id:$id,idem_key:$key,text:$text,typology:'benign_explanation',confidence:'high',author:'analyst',reviewed:true,valid_from:$now,created_at:$now,confidential:true})-[:SUPERSEDES]->(old) SET old.expired_at=$now,old.valid_to=$now WITH old,f MATCH (old)-[:ABOUT]->(e) MERGE (f)-[:ABOUT]->(e) RETURN DISTINCT f.id AS finding_id,f.created_at AS date_learned

MATCH (c:Case {id:$id}) OPTIONAL MATCH (r:SARDraft)-[:FOR]->(c) RETURN c.id AS case_id,c.status AS status,c.str_due_at AS str_due_at,r.id AS report_id,r.jurisdiction AS jurisdiction,r.json AS draft_json,r.narrative AS narrative,r.verified AS verified ORDER BY r.created_at DESC

MATCH (t:ToolCall) WHERE t.id IN $ids RETURN t.id AS id,t.rows_json AS rows_json

MATCH (d:Decision)-[:ON]->(p:PendingAction) WHERE p.id IN $ids RETURN p.id AS pending_id,d.decision AS decision,d.decided_by AS decided_by,d.role AS role,d.at AS at,d.reason AS reason

MATCH (p:PendingAction {id:$id}) RETURN p.kind AS kind,p.status AS status,p.case_id AS case_id,p.draft_json AS draft,p.rationale AS rationale

MATCH (p:PendingAction {id:$id})-[:IN]->(s:Session)<-[:IN]-(t:ToolCall) RETURN t.id AS id,t.rows_json AS rows_json,t.tool AS tool

MATCH (c:Case {id:$cid}),(pa:PendingAction {id:$pid})-[:BASED_ON]->(f:Finding) MERGE (c)-[:HAS]->(f) RETURN count(f) AS n

MATCH (pa:PendingAction {id:$id})-[:BASED_ON]->(f:Finding) SET f.reviewed=true RETURN count(f) AS n
```

### Control statements in `server/agent.py`

```cypher
MATCH (s:Session {id:$id}) SET s.ended_at=$now,s.cost_usd=$cost,s.judge=$judge,s.verifier=$verifier RETURN s.id AS id

MATCH (p:Person) RETURN collect(DISTINCT p.name_norm) AS names

MATCH (p:PendingAction)-[:IN]->(s:Session {id:$sid}) MATCH (f:Finding)-[:MADE_IN]->(s) MATCH (p)-[:TARGETS]->(a:Account)<-[:ABOUT]-(f) MERGE (p)-[:BASED_ON]->(f) RETURN count(f) AS n

MATCH (p:PendingAction {id:$id,status:'pending'}) SET p.status='withdrawn_by_judge' RETURN p.id AS id

MATCH (o:PendingAction {id:$old}),(n:PendingAction {id:$new}) MERGE (o)-[:SUPERSEDED_BY]->(n) RETURN o.id AS id
```

### Control statements in `server/app.py`

```cypher
MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$id,tool:$tool,args_json:$args,at:$now})-[:IN]->(s) RETURN t.id AS id

MATCH (t:Tenant {name:$name}) SET t.halted=$halted,t.halted_by=$by,t.halted_at=$now RETURN t.halted AS halted

MATCH (t:Tenant {name:$name}) SET t.llm_enabled=$enabled RETURN t.llm_enabled AS enabled

MATCH (a:Alert {id:$id}) RETURN a.raised_at AS at

MATCH (m:Meta) RETURN m.seed_complete AS complete,m.seed_version AS seed_version,m.reseed_s AS reseed_s LIMIT 1

MATCH (p:PendingAction {status:'pending'}) RETURN count(p) AS n
```

### Control statements in `server/db.py`

```cypher
MATCH (m:Meta) RETURN m.seed_complete AS complete LIMIT 1
```

### Control statements in `server/mcp_read.py`

```cypher
MATCH (r:Rail) RETURN r.name AS name,r.first_loaded AS first,r.last_loaded AS last

MATCH (a:Account {id:$id}) RETURN coalesce(a.in_deg,0)+coalesce(a.out_deg,0) AS degree

MATCH (r:Rail) RETURN max(r.last_loaded) AS through

MATCH (r:Rail) RETURN min(r.first_loaded) AS first

MATCH (a:Account)-[f:FLOW]->(b:Account) RETURN max(f.ts) AS through,max(f.computed_at) AS computed_at,count(f) AS n

MATCH (a:Account {id:$id})<-[o1:OWNS]-(p:Person)-[o2:OWNS]->(b:Account) WHERE b<>a AND coalesce(o1.since,0)<=$as_of AND coalesce(o2.since,0)<=$as_of WITH a,p,b,count(b) AS n RETURN b.id AS linked,'Account' AS kind,'hard' AS strength,1 AS hops,[a.id,p.id,b.id] AS path_ids,['OWNS','OWNS'] AS link_kinds,1 AS identifier_degree LIMIT $limit

MATCH (p:Account {type:$type}) RETURN percentileDisc(p.in_deg,0.5) AS in_deg_p50,percentileDisc(p.in_deg,0.95) AS in_deg_p95,percentileDisc(p.out_deg,0.5) AS out_deg_p50,percentileDisc(p.out_deg,0.95) AS out_deg_p95,count(p) AS n

MATCH (a:Account {id:$id})-[t:TX]-(b:Account) WHERE t.ts>$from AND t.ts<=$as_of RETURN t.id AS id,startNode(t).id AS source,endNode(t).id AS target,t.amount AS amount,t.ts AS ts,t.rail AS rail,t.memo AS memo,'TX' AS type ORDER BY t.ts DESC LIMIT $limit

MATCH (m:Meta) RETURN m.betweenness_samples AS samples LIMIT 1

MATCH (a:Account {id:$src})-[t:TX]->(b:Account {id:$dst}) WHERE t.ts<=$through AND t.ts<=$as_of RETURN t.id AS id,a.id AS source,b.id AS target,t.amount AS amount,t.ts AS ts,t.rail AS rail,'TX' AS type ORDER BY t.ts LIMIT $limit

MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$id,seq:$seq,tool:$tool,args_json:$args,rows_json:$rows,rows_total:$total,rows_returned:$returned,truncated:$truncated,elapsed_ms:$ms,rows_sha256:$hash,guard_hits:$hits,at:$at}) CREATE (t)-[:IN]->(s) RETURN t.id AS id

MATCH (p:Person) RETURN collect(p.name_norm) AS values
```

### Control statements in `server/mcp_write.py`

```cypher
MATCH (a:Account) WHERE a.id IN $ids RETURN a.id AS id

MATCH (s:Session {id:$sid}) MERGE (f:Finding {idem_key:$key}) ON CREATE SET f.id=$fid,f.text=$text,f.typology=$typ,f.confidence=$conf,f.author='agent',f.reviewed=false,f.model=$model,f.evidence_tool_call_ids=$ev,f.evidence_tx_ids=$tx,f.valid_from=$vf,f.created_at=$now,f.confidential=true MERGE (f)-[:MADE_IN]->(s) RETURN f.id AS finding_id,f.created_at AS date_learned

MERGE (pa:PendingAction {idem_key:$key}) ON CREATE SET pa.id=$pid,pa.kind=$kind,pa.status='pending',pa.rationale=$rationale,pa.proposed_by=$model,pa.created_at=$now,pa.evidence_tool_call_ids=$ev,pa.restriction_check_json=$rc,pa.draft_json=$draft,pa.case_id=$cid WITH pa MATCH (s:Session {id:$sid}) MERGE (pa)-[:IN]->(s) WITH pa UNWIND $targets AS tid MATCH (a:Account {id:tid}) MERGE (pa)-[:TARGETS]->(a) RETURN DISTINCT pa.id AS pending_id,pa.status AS status,pa.kind AS kind

MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$tid,seq:$seq,tool:$tool,args_json:$args,rows_total:$n,rows_returned:$n,truncated:false,elapsed_ms:0,rows_sha256:$hash,result_json:$result,error_reason:$reason,guard_hits:$hits,at:$now})-[:IN]->(s) RETURN t.id AS id

MATCH (f:Finding {id:$id}) RETURN f.id AS id

MATCH (f:Finding {id:$fid}),(old:Finding {id:$old}) SET old.expired_at=$now,old.valid_to=$vf MERGE (f)-[:SUPERSEDES]->(old) RETURN f.id AS id

MATCH (f:Finding)-[:MADE_IN]->(s:Session {id:$sid}) MATCH (f)-[:ABOUT]->(a:Account) WHERE a.id IN $targets AND f.expired_at IS NULL RETURN DISTINCT f.id AS id LIMIT 10

MATCH (pa:PendingAction {id:$pid}) UNWIND $ids AS fid MATCH (f:Finding {id:fid}) MERGE (pa)-[:BASED_ON]->(f) RETURN count(f) AS n

MATCH (c:Case {id:$id}) RETURN c.id AS id

MATCH (f:Finding {id:$id})-[:MADE_IN]->(s:Session {id:$sid}) RETURN f.id AS id

MATCH (f:Finding {id:$fid}) UNWIND $ids AS eid MATCH (e:
```

### Control statements in `server/safety.py`

```cypher
MATCH (t:Tenant {name:$name}) RETURN t.halted AS halted,t.llm_enabled AS llm_enabled,t.daily_usd_cap AS cap

MATCH (s:Spend {day:$day}) RETURN s.usd AS usd,s.reserved AS reserved,s.calls AS calls

MERGE (s:Spend {day:$day}) ON CREATE SET s.usd=0.0,s.reserved=0.0,s.calls=0 WITH s SET s.reserved=coalesce(s.reserved,0)+$upper,s.updated_at=$now RETURN s.usd AS usd

MATCH (s:Spend {day:$day}) SET s.reserved=CASE WHEN coalesce(s.reserved,0)>=$upper THEN coalesce(s.reserved,0)-$upper ELSE 0.0 END,s.usd=coalesce(s.usd,0)+$cost,s.calls=coalesce(s.calls,0)+1,s.updated_at=$now RETURN s.usd AS usd
```
