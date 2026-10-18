# What the case file asks of a graph agent

*Draft for the Graph Hacks side prize. RingSight is synthetic, demo-only, and
not a regulated reporting service. Track 01 (primary) · Track 02 (memory).*

An account-risk score is the beginning of an investigation. The investigator
still needs to know which accounts sent the money, where it went next, whether
the owners share a device or phone, and which facts justify the proposed
action. A regulator-facing case file needs dates, individual amounts, recorded
reasons and a named human decision. That is the problem RingSight explores.

The product has one question box. Behind it is a graph containing accounts,
owners, identifiers, transfers, restrictions, ingestion coverage and the
investigation's own memory. A model chooses typed tools from a frozen
catalogue; it never produces Cypher. Every actual query is checked into the
repository so the builder, investigator and judge can inspect what it does.

## The connection that a shallow view misses

The synthetic generator plants seven families of patterns: fan-in, fan-out,
cycles, bipartite transfers, stacks, scatter-gather and gather-scatter. It also
creates legitimate merchants, payroll accounts and exchanges. A busy node is
not automatically a laundering node.

The demo begins with the same account at depth one and then depth four. The
second run follows a shared device and an owner connection to an exit account
that a transfer-only first hop cannot explain. The answer includes the exact
hop list and directed transfers. The graph canvas is a view of those returned
rows, and the table keeps each transfer's integer-paise amount and timestamp.
No hand-drawn “fraud ring” is substituted for a query result.

FalkorDB does the graph work. Weakly connected components, label propagation,
PageRank and sampled betweenness are computed at load time and read as dated
properties. The path tool runs the engine's shortest-path algorithm and also
performs an as-of-safe traversal. Algorithm snapshots have their own computed
time: they are not presented as live historical recalculations.

## Four answers an investigator can act on

RingSight gives four explicit answer shapes. An answer with a path cites the
returned connections. A memory answer says when the finding was learned, who
wrote it and whether a human reviewed it. An unknown entity answer offers
candidates without silently substituting one. A not-in-graph answer states
the reason: the selected depth, missing window, missing rail or isolation.

The coverage statement matters as much as the path. The demo deliberately
omits CASH and cross-border rails and includes two mismatched IMPS feed days.
The agent cannot use missing data to imply that an account is clean. “Not in
the graph ≠ nothing wrong” stays on the answer card.

## A small catalogue makes a visible boundary

The public MCP endpoint exposes fourteen read-only tools. The running
application has two additional tools for recording findings and proposing
actions. Neither write capability is published to an external MCP client.
There is no free-form query tool. Typed inputs bound traversal depth, windows,
limits and permitted relationship types, while every entity id is checked
before a query runs.

The live trace shows each selected tool, arguments, elapsed time, row count,
outcome and guard hits. The final line records the actual model, tokens, cache
reads, cost, evidence-only judge verdict and deterministic verifier result.
The verifier compares ids, money amounts and dates with the evidence and
replaces unsupported prose with a sentence derived from rows.

## Memory is a dated finding, not a chat summary

Each finding has both the time the evidence was true and the time the system
learned it. New sessions read prior findings before reasoning. Assistant
findings are labelled unreviewed, and no more than five unreviewed findings
are injected into a new model session. A human correction creates a
superseding finding; it does not erase the original.

That memory lives in the same tenant graph as the evidence and human
decisions. There is no second vector store carrying an opaque chat summary.
A seed snapshot preserves reviewed demo memory across a free-tier rebuild;
the README states the recovery limits for newer judge-created work.

## Approval is an audited transition

A proposal creates a pending node. A human route requires a bearer key mapped
on the server to a person, role and bank, and a reason of at least twenty
characters. The model cannot call that route. A second bank graph proves that
an id from another bank cannot be approved or exported by the first bank's
key.

A hold needs multi-step evidence and creates only a recommendation for the
Principal Officer. It never changes Account.status. Closing needs affirmative,
non-empty checks, and a weak judge verdict converts a closing proposal to an
escalation. Reports require Principal Officer approval. Indian-format facts
and provisional transaction-sheet mappings remain **[unverified-primary]**;
the exported draft says so. No report is actually filed.

## Instructions inside the evidence

Twenty synthetic memos contain planted instructions. Before any graph text
reaches a model it is capped, normalised, scrubbed and wrapped as untrusted.
Names are resolved server-side, and only opaque ids reach the model.

There are two guard profiles. The read profile flags instruction-like data.
The write profile refuses role mimicry, instruction overrides and approval
bypasses, while allowing legitimate wording such as recommending that the
Principal Officer hold an account. Instruction-like text cannot be written.
A paraphrase can be stored only as an unreviewed finding and is scanned and
labelled again on recall. This distinction is an honest boundary, not a claim
that string matching solves prompt injection.

## Free hosting has a recovery plan

The demo uses one Render container and FalkorDB Cloud Free. The local path is
Docker Compose with a pinned v4.22.1 image, loopback database ports, an AOF
volume, seed generation and one application worker. The free Cloud graph has
no persistence, backups or TLS, so it contains only synthetic data.

The application detects a missing or incomplete graph, reseeds in a background
worker and reports warming-up progress. A deadline prevents an endless
rebuild. Render checks the lightweight `/live` route; `/health` additionally
checks graph population, memory, coverage, spend and a cached model probe.
Independent GitHub Actions and Cloudflare schedules plus an UptimeRobot
monitor keep the demo awake and report failures.

The Console spending limit is the outer wall. The application also checks a
kill switch, a persisted daily tenant cap, investigation and query concurrency,
key/IP rate buckets, and per-investigation call, token, cost and time limits.
When the model is off or the budget is gone, the human tool console continues
to answer through the graph.

## What the measurements can and cannot say

The committed files in `evals/results/` are the evidence for the README's
numbers. Structural checks run on a local graph, including point-in-time
leakage, planted-pattern recall, legitimate hubs, unknown ids, missing rails,
cross-bank access, action end states, verifier normalisation and planted
instructions. Model experiments use a local graph copy, never the live demo
graph. A clean result on planted synthetic rings is not a production detection
claim; measured recall, precision and latency stay labelled demo-only.

The completed local protocol passed all 180 model cases: 120/120 graph paths
were correct, 40/40 planted memo attacks were exposed and guarded with zero
unapproved effects or instruction stores, and 20/20 deleted-ring questions
abstained correctly. The measured trial cost was **$6.6188376**. All 120 path
answers used the deterministic verifier replacement, so path correctness is
not a claim that unchecked model prose was correct. Both engine suites and
the current GitHub CI run passed 370/370 tests. These are synthetic, demo-only
results, not measured detection performance on real banking data.

The current public acceptance passed 39 checks; depth 1 took 36.434 seconds and
depth 4 took 36.045 seconds, with one sample at each depth. In the five-request
concurrency check, three requests answered and two received the busy response;
accepted depth 4 timings had p50 **38.190 seconds** and p95 **39.371 seconds**
(N=3). The roughly 15-second demo target was missed. The largest sampled app
RSS was 203.19 MB; health is cached for 15 seconds, so this is an observed sample,
not a process high-water mark. The [raw results](../evals/results/) retain the
sample sizes and actual costs rather than promising a free-tier latency SLO.

The scale path starts with a nightly recent-transfer projection, sampled
centrality, a queue-buffered writer and cached bounded reads. It adds replicas
and region/tenant shards when one graph no longer fits in memory. A billion
raw transfers will not fit into one free-tier graph. A paid pilot starts in
shadow mode, with the bank operating its own graph, India-region deployment,
privacy agreements and independent model and compliance validation.

RingSight's most useful property is its dependency on the graph. Stop
FalkorDB and the product loses answers, memory, proposals, approvals and even
its coverage statement. The database is doing the work the explanation is
about.

Source artefacts: [architecture](../architecture.md), [all Cypher](../server/cypher/),
[eval results](../evals/results/), [demo script](demo-script.md),
[AMLSim attribution](../NOTICE). The README contains the final measured
results, deployment address and accurate AI-assistance disclosure.
