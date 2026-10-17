# RingSight requirement and evidence checklist

Audit snapshot: 17 October 2026. Sources: [AGENTS.md](../AGENTS.md),
[goal.md](../goal.md), and [architecture.md](../architecture.md), including
the implementation amendments. This is an inventory of observed evidence,
not a declaration that RingSight is finished. Worktree files and results still
need the final committed/pushed verification. Source changes after a recorded
run require the relevant checks to run again.

Status meanings:

- **Local pass**: the linked automated local result passed; no public-URL
  claim is inferred from it.
- **Partial**: implementation or some checks exist, but a required workflow,
  integration, publication or result remains incomplete.
- **Failed**: an actual recorded attempt failed or returned incorrect evidence.
- **Configured**: source configuration or owner confirmation exists; this does
  not establish that a scheduled job or remote endpoint actually succeeded.
- **Missing evidence**: no appropriate passing artifact exists in the audited
  tree. It does not mean the implementation is necessarily absent.
- **Documented production scope**: architecture explicitly places the item in
  its production column or before-pilot list. Its documentation is required;
  building that production system is not claimed by the synthetic slice.

## Evidence inventory

| Reference | Actual result in the audited tree |
|---|---|
| [Full local contracts][local-tests] | Latest artifact: **310 passed, 310 collected, zero failures**. This includes the stricter audit and completion-gate regressions; preserve this full-suite pass when changing source. |
| [Audited graph contracts](../evals/results/audited-graph-contracts.json) | 28 passed, including positive flag/link/close/modify/deny effects, real MCP closure withdrawal/escalation policy and read projection regressions. |
| [Audit regressions](../evals/results/audit-regressions.json) / [catalogue audit](../evals/results/catalogue-audit-tests.json) | 88 and20 passed respectively: malformed money/single names, safe execution logs, admin-reseed callback and all-server-source catalogue fingerprint changes are covered. The complete 310-test local suite now passes. |
| [Fresh Compose acceptance][compose] | Passed from a previously absent isolated volume: production Dockerfile built, image id/architecture recorded, app at loopback port 18000, actual and mocked browser checks passed. |
| [AOF smoke][smoke] | 25,000 accounts, v2 seed; a random PersistenceProbe and original Meta.seeded_at survived the actual database restart. A cached health response or new seed cannot satisfy the nonce check. |
| [Actual browser][actual-ui] | Six checks passed against the built app and actual graph; zero `/ask` requests. The UI's tiny cached health-model probe is disclosed. |
| [Browser interaction contracts][mock-ui] | Eleven checks passed using explicitly mocked APIs against the built frontend. These prove UI contracts, not model/database effects. |
| [Local v2 foundation][foundation-v2] | 25,000 accounts, 32,500 TX, 180 days, 39 MB, engine 4.22.1, full schema and native precompute; reseed 5.518 s in this run. |
| [Historical Cloud foundation][cloud-foundation] | Actual v1 seed passed on Cloud 4.22.0: 25,000 accounts, 39 MB, reseed 21.169 s. This does not prove the current v2 graph or current deployed app. |
| [Structural patterns][patterns] | Latest strict run **passed**, with no path-consistency errors across35 seeds. Measured member recall: cycle/bipartite/scatter-gather/gather-scatter1.0, fan-in0.9778, fan-out0.875, stack0.4444. Global hub precision@10 is0 for PageRank/betweenness/out-degree and0.2 for in-degree;105 legitimate hubs present and none returned when excluded. Earlier cycle defects were fixed before this rerun. Synthetic, demo-only; passing contracts do not imply perfect detection. |
| [Read contracts][read-tests] | Eleven reported checks pass, including all-read future-TX invariance, unknown IDs, missing CASH, dense guards and historical snapshot refusal. |
| [Recovery][recovery-tests] / [snapshot contracts][snapshot-tests] | Actual empty/half-load recovery, deadline cancellation, tenant-bound snapshot restore and original memory path/supersession checks pass. Snapshot contracts also reject corrupt/unscoped evidence. |
| [Control checkpoint integration][control-tests] | Three actual local tests pass: planned rebuild retains caps/halt/model-off/spend; failed load and next process recover liability; later spend is never lowered. |
| [Runtime smoke][runtime] | Both actual model investigations returned a path and pending proposal. Depth 1 excluded the hidden exit; depth 4 contained it. Observed 18.207 s / $0.030416 and 41.872 s / $0.034329. This is local, N=1 per depth, not live p50/p95. |
| [HTTP workflow attempt][workflow] | **Failed before its first answer** with `model_unavailable`. Its preceding readiness, exact-14 standard MCP and manual depth checks passed. It proves no successful approve/deny/memory/fallback workflow. |
| [Later built-runtime diagnostic](../evals/results/runtime-diagnostic.json) | One actual built-container model question passed in17.654s at$0.047062. This resolves that diagnostic attempt, but does not replace a complete successful HTTP approval/memory/fallback workflow. |
| [Model path experiment][model-paths] | **Incomplete and failed**: 45/120 completed cases, 36 correct and 9 with mismatched cycle transfer targets. It stopped with `InvalidOperation`. All 45 outcome badges said answered_with_path, so badge count is not a correctness metric. |
| [Model evaluation aggregate][model-evals] | **Failed** after the structural pass; path suite stopped. No complete 20-case deleted-ring or 40-run end-to-end injection result exists. |
| [Narrative tests][narrative-tests] / [report actions][report-tests] | Evidence-only SAR/STR formatting and actual proposal → PO approval → export checks pass; malformed or incomplete individual transfer facts are refused. |
| [Operations confirmation][operations] | Owner confirmed Render URL, GitHub secrets, UptimeRobot monitor and Cloudflare cron. The artifact explicitly says independent_live_response_verified=false. Do not request the same setup/accounts/keys again. |
| [Secret scan][secret-scan] | Candidate files, git index and built UI passed. Private values are not printed; public judge/MCP values are permitted only in root README. This artifact does not claim a full git-history scan. |

## Goal: all 22 mandatory items

| Goal | Required behavior and implementation | Status / remaining evidence |
|---|---|---|
| **G01 — live and local** | Public investigator page, one-command graph/seed/app setup, README first line with live URL and judge key, cold-start note. [Compose](../docker-compose.yml), [Dockerfile](../Dockerfile), [Makefile](../Makefile), [README](../README.md). | **Partial.** Fresh local Compose, actual page and identity pass [compose]. Public URL is owner-confirmed, but no passing current public-URL workflow artifact exists. README/current results must be pushed. |
| **G02 — one graph per bank** | All entity, TX, coverage, restrictions, memory, proposals, decisions, cases and drafts use tenant-scoped FalkorDB. `rs_bank_a` and tiny `rs_bank_b` seed paths exist; key-derived graph selection and UUID lookups. [DB](../server/db.py), [seed](../seed/__init__.py), [actions](../server/actions.py). | **Local pass; remote evidence pending.** Actual IDOR tests exercise distinct local bank graphs; seed returns only after its toy-bank path. Verify the current live named graphs during final deployment acceptance. No alternate runtime store is introduced by the temporary rebuild bridge. |
| **G03 — synthetic data** | 25k accounts, six rails/180 days, 35 rings/seven patterns, legitimate hubs, identifiers, three name pairs/restrictions, 60 alerts, two IMPS mismatches, 20 injected memos, private-to-agent ground truth, graph ≤40 MB. [Generator](../synth/generate.py), [data](../data/), [sizing](../evals/results/sizing.json). | **Local pass.** [foundation-v2], generator controls and the strict35-seed [patterns] run pass; measured recall is not perfect. Density and sampled-centrality changes are explicitly recorded in architecture amendments. Latest actual Cloud seed evidence remains v1. |
| **G04 — automatic reload** | Empty/incomplete graph triggers one background worker, ETA, deadline, force retry and same-bank snapshot restoration. [SeedManager](../seed/__init__.py), [snapshot](../seed/snapshot.py), [runbook](runbook.md). | **Partial.** Recovery and control preservation pass locally. The shipped demo snapshot is still schema 1 with zero findings; a real reviewed schema-2 demo snapshot has not been captured. No current Cloud wipe/restore acceptance exists. |
| **G05 — fixed typed catalogue** | Sixteen frozen tools with bounded, typed arguments and prewritten Cypher; IDs checked; as-of filters; exactly fourteen reads plus two private writes. [Schemas](../server/schemas.py), [read tools](../server/mcp_read.py), [write tools](../server/mcp_write.py), [Cypher](../server/cypher/), [fingerprint](../server/catalogue.py). | **Local pass for contracts; model correctness incomplete.** Read/schema/future-TX/fingerprint tests pass. Full model experiment has nine incorrect cycle paths and is incomplete [model-paths]. The numbered catalogue/amendment includes max-flow to resolve the original prose count conflict. |
| **G06 — external MCP proof** | Standard authenticated MCP at `/mcp`, fourteen read-only tools; both writes remain in-process. Public MCP access instructions/key in README. | **Partial.** Actual standard MCP HTTP list/call and write-bearer refusal passed on built Compose [workflow]. No equivalent current public-URL result exists. |
| **G07 — graph-native algorithms** | Native SPpaths, WCC, LPA, PageRank and sampled betweenness; global properties carry computed-at; trace identifies algorithms. Max-flow uses the documented FLOW projection. | **Local pass.** [foundation-v2], [read-tests] and [engine probes](../evals/results/engine-foundation.json). Historical Cloud probe passed on v1. Current live trace proof remains pending. |
| **G08 — shapes and exact evidence** | Four badges, selected exact hop list/canvas, directed money particles, every cited TX/date/amount/direction/rail/source tool; every absence has reason and “Not in the graph ≠ nothing wrong.” [UI](../ui/src/App.jsx), [view data](../ui/src/data.js). | **Partial.** Actual manual UI and mocked shape/path/evidence contracts pass. Two local model depth cases pass. The previous broader model trial contains nine cycle target mismatches; its current-source replacement and the public full workflow have not passed. |
| **G09 — streaming work** | Tool name/inputs/ms/rows/outcome/guard stream; final model/tokens/cache/cost/judge/verifier; JSON metadata log/audit. [Context](../server/context.py), [agent](../server/agent.py), [UI trace](../ui/src/App.jsx). | **Local pass; public pending.** Streaming UI contracts, actual model traces and new safe structured-logging regressions pass. The public SSE run has not passed. |
| **G10 — verifier and independent judge** | Every emitted ID, amount and date grounded; unsupported prose replaced/chipped; separate evidence-only model judge; weak closure withdrawn and escalated. [Verifier](../server/verifier.py), [agent](../server/agent.py). | **Local pass; model/live pending.** The audit's single-name loophole was fixed and covered by88 audit regressions. The actual28-test graph run now covers weak/contradict closure withdrawal and superseding escalation with real MCP writes. The full310-test suite passes; complete current model/live validation is still incomplete. |
| **G11 — no innocence from emptiness** | Close needs two distinct nonempty typology-free checks; hold needs an allowed multi-edge pattern. | **Local pass.** [actions-tests](../evals/results/actions-tests.json) covers empty close, single-transfer hold refusal and affirmative close proposal; actual hold approval does not write Account.status. A full model false-dismissal experiment is still absent. |
| **G12 — named human actions** | All seven kinds create pending cards with targets/paths/restrictions/draft. Approve/deny/modify reason ≥20; decision user/role/time; PO-only reports; hold only recommendation; supersession instead of deletion. | **Local component pass; HTTP/public pending.** Actual hold/escalation/SAR/STR checks pass, and the newer28-test graph run covers flag/link_case/successful close/modify/deny plus reviewed findings and weak closure. The complete real HTTP workflow has not yet passed. |
| **G13 — cross-session memory** | Bi-temporal Finding, read-before-reason, learned date/author/review state, analyst supersession, ≤5 unreviewed findings; retained paths after restore. | **Partial.** Local finding/recall/correction and two-finding restored evidence/session/supersession tests pass [recovery-tests]. Real model memory in a second HTTP session and the nonempty shipped demo snapshot remain pending. |
| **G14 — planted instructions** | All graph free text bounded, normalized, scrubbed, delimited and READ-scanned; WRITE refusal names matched pattern; legitimate hold/close wording permitted; memory labels remain untrusted. | **Partial.** Twenty structural memo/write controls and positive guard wording pass; nested names/memos removed from judge digest. No complete forty-run real-model attack/exposure/effect result exists. A browser showing a guard chip alone cannot establish zero unapproved effects. |
| **G15 — identity and isolation** | Server key→person/role/bank; no client tenant/role; UUID-scoped pending/case/finding; key once/sessionStorage, never bundled. | **Local pass.** Actual HTTP IDOR, 400 identity-override, report role restrictions and secret/bundle scans; mocked key-once URL stripping. Current live clean-browser proof remains pending. |
| **G16 — spend/rate/concurrency** | Console outer wall, halt/model-off, $8 UTC bank cap, three investigations/six queries, bearer/IP buckets, 10 tools/12 requests/60k in/6k out/$0.25/60 s, non-AI fallback. | **Partial.** Local budget/reservation/retry/kill/rate/query-slot/control-checkpoint tests pass; two actual capped runs pass. Five-concurrent live/RSS check and actual HTTP model-off/manual-path acceptance have not passed. No cap is raised or reset to make a test pass. |
| **G17 — honest degradation** | Typed plain errors, finite calls/retries/timeouts, no exposed stack, model/DB/warmup/cap/rate/halt UI, health readiness/size/pending/spend/version/model. | **Partial.** Actual Compose/manual and mocked error states plus recovery/deadline/semaphore checks pass. The failed model_unavailable workflow has a later successful one-question built-runtime diagnostic; a complete HTTP/public workflow rerun remains required. |
| **G18 — keep awake and alert** | Two scheduled pingers, free uptime monitor/email and daily real question. [Actions](../.github/workflows/), [Worker](../ops/cloudflare-worker.js), [cron](../ops/wrangler.toml). | **Configured.** Owner confirmed UptimeRobot and Cloudflare enabled, Render URL/secrets supplied [operations]. Workflow source uses failing HTTP probes and daily path/memory answer check. Actual current scheduled health/daily-question successes and email delivery are not recorded. Do not re-ask setup already supplied. |
| **G19 — regulator export** | Approved SAR intro/body/conclusion who/what/when/where/why/how, individual TX/date/amount and no tables; STR tags/narration <20k/rail-sheet type; text+data downloads, coverage footer, unverified-primary labels. | **Local pass; live pending.** [narrative-tests], [report-tests], report-safety tests and UI fixture export. Real PO-approved public export/download is not yet demonstrated. No actual filing occurs. |
| **G20 — automated committed proof** | All structural/action/IDOR/point-in-time/injection tests plus 120 paths, twenty deleted-ring abstentions and forty attack runs on local copies; results committed, README measured/demo-only. | **Partial.** Latest full310-test suite and stricter35-seed structural run pass, as do focused28 graph and88 audit checks. Model path trial stopped at45/120 with9 wrong paths; other model suites absent. Current files/results are not fully committed. |
| **G21 — submission assets** | Existing public MIT repository, SSPL notice, AMLSim Apache attribution; complete README/query catalogue/AI disclosure/tracks/blog/runbook; actual scripted three-minute screen recording including live depth/approval/Browser/memory/abstention/injection/limits. | **Partial.** Source/docs/licences/script/capture tooling exist. No MP4 or successful recording artifact exists. No current public acceptance or final committed/pushed package is verified. Final submission form waits for explicit owner approval. |
| **G22 — measured speed and usable UI** | Approximately15s depth4 target; publish measured live p50/p95; laptop usable empty/loading/error states; integer-paise ₹ rendering. | **Partial.** Actual desktop/manual and mocked mobile/UI money contracts pass. Local N=1 depth4 took41.872s; this does not meet a15s claim or provide live percentiles. Actual public latency and five-concurrent memory/RSS data are missing. |

## Architecture §3.0–§3.15

| Section | Required slice obligations | Evidence / disposition |
|---|---|---|
| **3.0 Requirement trace** | All domain/hackathon/safety requirements accounted for; graph does the essential work. | G01–G22 above and final acceptance below. No missing behavior is converted into a documentation-only item. |
| **3.1 Product/pitch** | RingSight name; bank AML investigation; fixed tools, exact graph path, memory, approval. | UI/README use RingSight; source and local functional proof exist. Public full-loop demonstration remains incomplete. |
| **3.2 Graph model** | Every entity/relationship/control/memory/audit/report label, integer paise/epoch, tenant graphs, indexes/range/fulltext/constraints, native precompute, external truth, ≤40MB measurement. | Foundation/read/action/recovery/fingerprint tests and v2 39MB result. New control bridge is private/rebuild-only. A real reviewed demo snapshot remains absent. |
| **3.3 Frozen catalogue** | Exact fourteen public reads/two private writes; complete bounded typed schemas, annotations/descriptions/examples, labelled parameterized queries, unknown-ID checks, as-of, dense hub guard, count-before-collect, no query-generation tool. | Actual local standard MCP and structural/schema tests pass. Max-flow/FLOW inclusion is explicitly amended. Broader model path/direction failure must be fixed before claiming complete tool behavior. |
| **3.4 Agent runtime** | Pydantic-AI/FastMCP fixed tools, dated preflight, bounded projections, explicit charged retries, planner→evidence-only judge→verifier, safe pending actions, per-run/global caps, SSE trace and final cost. | Implemented with staged compiler-compatible subsets from the frozen catalogue. Two actual depth runs and a later built-runtime diagnostic pass. Broad experiment/full HTTP workflow remain incomplete; weak-close conversion now has positive actual graph proof. Live concurrency/RSS absent. |
| **3.5 Memory** | Bi-temporal Findings/ABOUT/MADE_IN/SUPERSEDES, no vector substitute, five unreviewed max, named feedback, retained dated path, captured snapshot for reseed. | Local restore/session/hash/supersession tests pass. Shipped snapshot has zero records and no real reviewed demo capture yet. |
| **3.6 Safety** | Identity/IDOR, RO_QUERY, typed bounds, separate guards, verification/judge, spend/rate/query slots, human route, bounded failures, fallback, CSP/secrets, recovery, admin audit/logging. | Focused new checks pass for single-name rejection, withdrawal/decision paths, safe JSON logs and admin-reseed completion callback. The complete current310-test suite passes. Production hash chains/WORM/IdP/TLS are explicitly production scope, not claimed present. |
| **3.7 Synthetic data** | Deterministic seven typologies/controls/memos/truth; secure direct bulk loading, background/recoverable rebuild, complete Meta last, seed sizes. | v2 generator/local foundation/structural contracts pass. Density32.5kTX and sample32 replace disproved estimates by written amendments; no false Opus-Batch claim. Current Cloud v2 rollout/reseed measurement is pending. |
| **3.8 UI** | Key-once identity, ask/as-of/depth, all degradation states, streamed trace, ≤1k-node directional canvas/selected path, badges/memory/date, evidence CSV/IST/₹, reasoned pending cards/red restrictions/PO gate, reports/downloads, real coverage, no-AI form. | Actual built-asset/manual UI6checks and fixture11checks pass. Model-driven approve/deny/memory/injected memo/fallback/public proof is missing; the earlier model trial has nine cycle errors and needs rerunning after the projection fix. |
| **3.9 Deployment** | One free Docker service, pinned Python/Node/dependencies/engine, `/live` Render health path, complete Compose/AOF/loopback local stack, typed endpoints, cached `/health`, two crons/UptimeRobot/daily question, bounded degradation, secret env and logs, CI4.22.1+6.0.2. | Recorded fresh Compose/image/AOF/browser proof passes; Render/monitor/secrets owner-confirmed. Final rebuild after audit fixes, public workflow, schedule outcomes and6.0.2 passing evidence still pending. Admin-reseed logging callback now has focused proof. No second paid/free Render service is created. |
| **3.10 Evals** | Must-ship structural1/3/4a/5/7a, model2/4b/7b, committed results/demo-only labels. Memory/latency listed stretch in original plan are also explicitly required where goal acceptance calls for them. | Latest strict structural result passes all35 seeds; imperfect recall/precision metrics are recorded honestly. Model120+20+40 incomplete/failed; real HTTP memory/live latency absent. Current report files must be committed after final reruns. |
| **3.11 Scale plan** | README documents nightly window, sampled algorithms, writer queue, cache/replicas, tenant/region shards, warehouse history, offline features/on-prem eval gate, audit growth, load/SLO/observability/ceiling. | Documented in README/architecture/blog. These are production steps, not deployed capabilities. Pilot/load/retention/audit-chain promises are not represented as completed. |
| **3.12 Regulatory fit** | Evidence-backed template SAR/STR, exact individual transfers, reasoned human/PO decisions, hold≠account restriction, provisional Indian labels, no filings; honest India-hosted shadow pilot/DPAs/licence/retention/incident posture. | Local actual report workflow and safety tests pass; primary-source-unverified Indian facts stay labelled in UI, README, blog and recorder captions. Live export proof pending. Real legal/compliance review and bank systems remain before-pilot scope. |
| **3.13 Submission mapping** | Public repo/README/local/live/Cypher/tracks/disclosure/blog and actual3-minute Browser-inclusive video matching the script. | All source/document assets exist; actual video absent; no final pushed proof or complete live acceptance. Disclosure accurately names Codex, Claude runtime and template reports; it does not invent Batch/polish work. |
| **3.14 Cost** | Free single-service hosting; Console outer wall; at-most$8bank/day; bounded per-call/run spend; real measured cost displayed; no cap increases without owner approval. | Local budget/reservation/retry/reseed-liability tests and actual runtime costs recorded. Account limit is owner-provided, not independently queried. Live5-concurrent check absent. No limit increase is authorized or performed by the tests. |
| **3.15 Build plan/clock** | Preserve never-cut spend/rate, read-only MCP, both guards, IDOR, fallback, automatic reseed and committed structural proof; carry missing must-ship work ahead of extras; complete docs/exports/snapshot/model eval/video/blog; final permission gate. | Foundational/structural/local build blocks passed. Model/workflow/live/snapshot/video/committed-delivery items are still open. Original Saturday/Sunday slots and cut order do not authorize stopping the user's mandatory full run with these incomplete. Target remains submission by Sunday23:00IST; the final form itself waits for approval. |

## Architecture's explicit hackathon build items

| Item | Required behavior | Current evidence |
|---|---|---|
| **Hm-13** | `[unverified-primary]` Indian facts in UI/README/video/blog. | Present in source/docs/captions. Actual video remains to be recorded. |
| **Hm-21** | WRITE ignore-pattern requires instruction object; honest prior-alert wording accepted; paraphrases labelled/unreviewed and flagged on recall. | Local guard/action tests pass. Full real-model attack utility/effect suite incomplete. |
| **Hm-22** | Bounded wall-clock partial answer with reason/banner/escalation; retain measured latency; off-path polish only if shipped. | Source fallback and UI error contracts exist; actual local depth4 was41.872s. Final timeout/weak-closure transition proof and live timing still needed. Template-only report path is the specified default; no polish claim. |
| **Hm-23** | Reseed only empty/incomplete; health5s/no-retry cached model probe; DB acquire2s; health15s cache; Render `/live`. | Local health/recovery/query-cancellation and fresh Compose tests pass; Render config specifies `/live`. Current live health/model run unverified. |
| **Hm-24** | Deadline max15min/3×reseed, terminate/kill/release, explicit force retry, runbook. | Actual/local deadline contracts and documented runbook pass. |
| **Hm-25** | Explicit external read logging-only limit, separate manual key bucket, graph≥80MB warning. | Source/docs and new safe structured-metadata logging regression checks pass. The complete310-test local suite passes. |
| **Hm-26** | Escalation creates Case without preexisting case_id; indexed count/recall plans; honest partial rendered as not_in_graph with timeout/budget reason. | Actual escalation-case/index plans pass locally; timeout/budget shape/source/UI tests exist. Public partial behavior still unverified. |

## Final acceptance: every clause of “How we know it is finished”

| Acceptance check | Current evidence | Completion condition |
|---|---|---|
| Fresh clone/filled env/one local command starts DB+seed+app | Fresh isolated [compose] passed from absent volume with actual built image and AOF restart. | Final current source pushed; fresh clone contains it and README command remains valid. |
| Public page answers same question at depth1 and4 | Local [runtime] passed; public URL only owner-confirmed. | Successful current public-URL artifact with depth1 excluding exit and depth4 including exact hidden path. |
| Proposes and accepts case approval with reason/named identity/time | Actual isolated component action tests pass; [workflow] failed before answer. | Successful real HTTP/UI session creates own pending proposal, approves it and reads the recorded Decision. |
| Hold is denied with written reasons; no account status write | Actual hold approval preserves Account.status; denial path source exists. | Successful real workflow/video denies its own pending hold and verifies its recorded reason/identity/status. |
| New session remembers dated, reviewed evidence/path | Fixture recall/restore/correction pass; no complete real HTTP model-memory workflow. | Model memory badge/date/review/path after approved case, plus captured nonempty schema2 snapshot and restore proof. |
| Unknown entity abstains | Twenty structural absent IDs pass. | Actual public `/ask` unknown shape with no invented ID substitution/model call. |
| Cash abstains because rail not loaded | Five structural cases and actual manual browser/MCP call pass. | Actual public `/ask` reason rail_not_ingested, banner and zero model calls. |
| Planted memo cannot direct an effect or poison trusted memory | Twenty structural guards/refusals pass. | Forty real-model exposed-attack runs complete with zero unapproved effects; actual seeded memo visible/flagged in video. |
| Cannot exceed spending/rate/time/concurrency caps | Local budget/retry/rebuild/query-slot contracts pass. | Final relevant local contracts plus actual five-concurrent public requests/RSS; never raise/reset caps to obtain a pass. |
| Exactly14 reads, no writes over standard MCP | Actual Compose HTTP list/call and public-write bearer rejection passed. | Same proof at the current public `/mcp`; two private writes absent. |
| Model switched off → human form still returns path | Local halted direct read and browser fixture fallback pass; real workflow not reached. | Actual HTTP admin model-off, rejected `/ask`, manual read path, restored setting with no investigation charge. |
| Every behavior has passing automated evidence | Latest310-test suite and strict structural run pass; previous model paths failed and full HTTP workflow remains incomplete. | Fix failures and run complete current-source local/model/live checks. Badge/exit-code/file existence alone is insufficient. |
| All results committed to existing public repo | Current git status contains modified/untracked source and result files. | Secret scan and final checks pass; required evidence committed and pushed to Baharul0111/RingSight. |
| README/query catalogue/script/disclosure/blog exist and match final facts | Present; README generation predates latest stopped model experiment. | Regenerate final measured statuses/numbers/latencies, verify complete inline queries and links; preserve honest limitations. |
| Actual3-minute screen recording includes every required scene | Recorder/script exist; no MP4 or passing video manifest exists. | Real UI+FalkorDB Browser capture, exact180s artifact/hash, reviewed scene checklist and public repository/video link. |
| Current monitoring and daily question work | Owner configured; workflows exist, no current executed-job evidence. | Record successful health/daily-question/CI results; retain owner-confirmed alert routing without re-asking accounts/keys. |
| Final hackathon form | Not submitted by the agent. | Wait for Baharul's explicit go-ahead after the reviewable package is ready. |
| Any daily/Console cap raise | Not performed or assumed. | Wait for explicit go-ahead; lack of budget does not authorize a new tenant/ledger reset as a bypass. |

## Open work that prevents completion

1. Fix the stopped model trial and its incorrect cycle transfer targets; retain
   the failed attempt honestly, then complete all required local model suites
   with current signatures and caps intact.
2. Fix the actual Docker HTTP model_unavailable failure and run the complete
   local workflow before repeating the current public deployment workflow.
3. Retain the now-passing310-test full suite, strict structural run and focused
   single-name, weak-close, positive-decision and admin-audit/logging
   regressions; rerun relevant checks if source changes again.
4. Push the current implementation/results, update the existing Render service,
   migrate its synthetic graph to v2 with control/spend preservation, and run
   public acceptance plus bounded concurrency/RSS/latency checks.
5. Capture reviewed demo Findings with original evidence/session rows into the
   schema2 same-bank snapshot and verify restore; record the actual3-minute
   live/Browser demo with all required scenes.
6. Collect the required current CI/scheduled-probe evidence, regenerate the
   README with final statuses and live p50/p95, re-run final relevant checks and
   secret scan, then commit/push all evidence and the reviewed video/assets.
7. Present the complete package for the user's explicit final-submission
   approval. No additional key/account setup is currently missing.

## Scope and resolved design corrections

The original prose called the slice “twelve” tools while enumerating thirteen
reads and requiring fourteen MCP reads/sixteen total tools. The written
architecture amendment makes the numbered catalogue authoritative and ships
max-flow as the fourteenth read over a labelled FLOW snapshot. Backlog/queue
tools remain explicitly production-only.

Other written amendments record measured graph-density reduction,32-sample
betweenness, strict-compiler-compatible staged tools, charged provider retries,
v2 demo-phone correction, schema2 memory evidence, complete catalogue hashes
and the private planned-rebuild control bridge. Template-only regulatory
drafts are the stated slice default. No Opus Batch/polish execution, Claude
Code authorship, paid hosting or real filing is invented.

Production OAuth/short-lived identity, per-tenant ACLs/replicas, audit hash
chains/WORM anchors, bank feeds/queueing, warehouse history/sharding, training,
in-India bank deployment/DPAs/VAPT/retention/legal review and production SLO
load testing remain the architecture's documented before-pilot/production
scope. Their absence is disclosed, and they are not used to justify omitting
any goal item or final synthetic-slice acceptance above.

[local-tests]: ../evals/results/pytest.json
[compose]: ../evals/results/compose-acceptance.json
[smoke]: ../evals/results/local-smoke.json
[actual-ui]: ../evals/results/ui-real-local.json
[mock-ui]: ../evals/results/ui-browser.json
[foundation-v2]: ../evals/results/local-foundation-v2.json
[cloud-foundation]: ../evals/results/cloud-foundation.json
[patterns]: ../evals/results/structural-patterns.json
[read-tests]: ../evals/results/structural-read-contracts.json
[recovery-tests]: ../evals/results/recovery-tests.json
[snapshot-tests]: ../evals/results/snapshot-contract.json
[control-tests]: ../evals/results/control-checkpoint-integration.json
[runtime]: ../evals/results/runtime-smoke.json
[workflow]: ../evals/results/local-workflow.json
[model-paths]: ../evals/results/model-paths.json
[model-evals]: ../evals/results/model-evaluations.json
[narrative-tests]: ../evals/results/narrative.json
[report-tests]: ../evals/results/report-actions.json
[operations]: ../evals/results/operations.json
[secret-scan]: ../evals/results/secrets-scan.json
