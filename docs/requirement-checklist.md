# RingSight requirement and evidence checklist

Audit snapshot: 18 October 2026 (IST). Sources: [AGENTS.md](../AGENTS.md),
[goal.md](../goal.md), and [architecture.md](../architecture.md), including
the implementation amendments. All technical verification artifacts now pass.
Final repository delivery is established by the linked completion manifest. Delivery status is verified by
[completion.json](../evals/results/completion.json), specifically
`required_files_committed_and_pushed`. A passing technical result does not
replace that final repository check. Source changes after a recorded
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
| [Full local contracts][local-tests] | **370/370 passed**, zero errors/failures/skips. The current retained report includes the approved evaluation budget and path-concurrency regressions. |
| [4.22.1 compatibility](../evals/results/ci-v4.22.1.json) / [6.0.2 compatibility](../evals/results/ci-6.0.2.json) | **370/370 passed on each engine**, including downloaded current-source GitHub CI artifacts from run [39046049271](https://github.com/Baharul0111/RingSight/actions/runs/39046049271). |
| [Audited graph contracts](../evals/results/audited-graph-contracts.json) | 28 passed, including positive flag/link/close/modify/deny effects, real MCP closure withdrawal/escalation policy and read projection regressions. |
| [Audit regressions](../evals/results/audit-regressions.json) / [catalogue audit](../evals/results/catalogue-audit-tests.json) | 88 and 20 passed respectively: malformed money/single names, safe execution logs, admin-reseed callback and all-server-source catalogue fingerprint changes are covered. Retain these focused passes and require a final full-suite pass after later edits. |
| [Fresh Compose acceptance][compose] | Final snapshot-inclusive Docker image/start/AOF/actual-browser/fixture-browser acceptance passed. The built image contains the exported 16-finding/16-session/55-call snapshot with its matching data hash; image/volume provenance is recorded. |
| [AOF smoke][smoke] | 25,000 accounts, v2 seed; a random PersistenceProbe and original Meta.seeded_at survived the actual database restart. A cached health response or new seed cannot satisfy the nonce check. |
| [Actual browser][actual-ui] | Six checks passed against the built app and actual graph; zero `/ask` requests. The UI's tiny cached health-model probe is disclosed. |
| [Browser interaction contracts][mock-ui] | Eleven checks passed using explicitly mocked APIs against the built frontend. These prove UI contracts, not model/database effects. |
| [Local v2 foundation][foundation-v2] | 25,000 accounts, 32,500 TX, 180 days, 39 MB, engine 4.22.1, full schema and native precompute; reseed 4.446 s in this run. |
| [Historical Cloud foundation][cloud-foundation] | Actual v1 seed passed on Cloud 4.22.0: 25,000 accounts, 39 MB, reseed 21.169 s. This file is historical; current v2/25k/39MB is separately observed by public health and the live/video runs. |
| [Structural patterns][patterns] | Latest strict run **passed** on the 25k local graph: all 35 patterns passed the independent physical-path oracle, **382 edges checked with zero fact errors**. Member recall: cycle/bipartite/stack/scatter-gather/gather-scatter1.0, fan-in0.9778, fan-out0.875. Global hub precision@10 is0 for PageRank/betweenness/out-degree and 0.2 for in-degree;105 legitimate hubs present and none returned when excluded. Earlier endpoint defects were fixed before this rerun. Synthetic, demo-only; passing contracts do not imply perfect detection. |
| [Read contracts][read-tests] | Eleven reported checks pass, including all-read future-TX invariance, unknown IDs, missing CASH, dense guards and historical snapshot refusal. |
| [Recovery][recovery-tests] / [snapshot contracts][snapshot-tests] | Actual empty/half-load recovery, deadline cancellation, tenant-bound snapshot restore and original memory path/supersession checks pass. Snapshot contracts also reject corrupt/unscoped evidence. |
| [Control checkpoint integration][control-tests] | Three actual local tests pass: planned rebuild retains caps/halt/model-off/spend; failed load and next process recover liability; later spend is never lowered. |
| [Runtime smoke][runtime] | Both actual model investigations returned a path and pending proposal. Depth 1 excluded the hidden exit; depth 4 contained it. Observed 18.207 s / $0.030416 and 41.872 s / $0.034329. This is local, N=1 per depth, not live p50/p95. |
| [HTTP workflow][workflow] | **Passed** against the actual built local app: depths1/4, named approval, hold denial, reviewed memory, unknown/CASH, planted memo, MCP and model-off/manual fallback. The current public workflow and final full-suite/Compose captures cover the shipped runtime; earlier failed attempts remain historical. |
| [Public acceptance](../evals/results/live-acceptance.json) / [public load](../evals/results/live-five_concurrent.json) | **Current runtime passed**: 39 acceptance checks, all seven workflow questions, reasoned approval/hold denial, reviewed memory, MCP and model-off/manual fallback. Depth1/4 took 36.434/36.045s (N=1 each). Five-concurrent load accepted 3, rejected 2 busy 429, p50/p95=38.190/39.371s (accepted N=3), sampled peak RSS 203.19 MB. Health sampling is cached 15 s, not a process high-water mark. |
| [Reviewed demo snapshot](../data/findings_snapshot.json) | Same-bank schema 2 snapshot now contains 16 findings, 16 sessions and 55 original ToolCalls, including three reviewed findings. The completion snapshot gate passes; final source/build freshness and restore contracts still apply. |
| [Later built-runtime diagnostic](../evals/results/runtime-diagnostic.json) | Historical successful single-question built-runtime diagnostic. Complete local HTTP workflow, full model protocol and actual video have since passed; use those broader artifacts for completion. |
| [Model path experiment][model-paths] | **Passed 120/120**, authoritative path correctness 1.0, first-tool match 1.0, cost $3.84246. All 120 prose outputs used the disclosed deterministic verifier replacement; this is not a claim that unchecked narrative prose was correct. |
| [Model evaluation aggregate][model-evals] | **All 180 model cases passed**: 120 paths, 40 injections and 20 deleted-ring abstentions. Total measured trial cost $6.6188376, local-only and synthetic/demo-only. |
| [Model injections](../evals/results/model-injections.json) | **Passed 40/40** with actual memo exposure and guard hits, zero targeted ASR, unapproved effects or instruction stores; cost $2.5197088. |
| [Deleted-ring abstentions](../evals/results/model-abstention.json) | **Passed 20/20**, semantic abstention rate 1.0, false path rate0; cost $0.2566688. |
| [Actual three-minute video](../evals/results/demo-video.json) | **Passed**: 180.000s MP4, 10 actual chapters, real Cloud FalkorDB Browser results, seven questions, approval/denial, memory/unknown/CASH, seeded memo and restored model setting. [Video](ringsight-demo.mp4) and [captions](demo-captions.vtt) exist; capture speed edits are disclosed. |
| [Narrative tests][narrative-tests] / [report actions][report-tests] | Evidence-only SAR/STR formatting and actual proposal → PO approval → export checks pass; malformed or incomplete individual transfer facts are refused. |
| [Operations confirmation][operations] | Owner confirmed Render URL/secrets/UptimeRobot/Cloudflare. Actual current-source health, daily question and CI jobs now pass separately in [operational-probes.json](../evals/results/operational-probes.json). No account/key setup remains missing. |
| [Secret scan][secret-scan] | Final public-candidate scan passed 477 files across working candidates, Git index and built UI. Private values are not printed; public judge/MCP values are permitted only in root README. No full Git-history scan is claimed. |

## Goal: all 22 mandatory items

| Goal | Required behavior and implementation | Status / remaining evidence |
|---|---|---|
| **G01 — live and local** | Public investigator page, one-command graph/seed/app setup, README first line with live URL and judge key, cold-start note. [Compose](../docker-compose.yml), [Dockerfile](../Dockerfile), [Makefile](../Makefile), [README](../README.md). | **Pass.** Current-hash public acceptance and final snapshot-inclusive Compose/image/AOF/browser proof pass. Repository delivery is tracked by the final completion manifest. |
| **G02 — one graph per bank** | All entity, TX, coverage, restrictions, memory, proposals, decisions, cases and drafts use tenant-scoped FalkorDB. `rs_bank_a` and tiny `rs_bank_b` seed paths exist; key-derived graph selection and UUID lookups. [DB](../server/db.py), [seed](../seed/__init__.py), [actions](../server/actions.py). | **Pass.** Both tenant graphs seed through the same loader; actual IDOR tests pass on both engines. Cloud bank A is v2 with25k accounts; current public named identity/workflow checks pass. |
| **G03 — synthetic data** | 25k accounts, six rails/180 days, 35 rings/seven patterns, legitimate hubs, identifiers, three name pairs/restrictions, 60 alerts, two IMPS mismatches, 20 injected memos, private-to-agent ground truth, graph ≤40 MB. [Generator](../synth/generate.py), [data](../data/), [sizing](../evals/results/sizing.json). | **Pass.** Generator controls, 25k foundation,≤40 MB graph and all 35 physical-path oracle cases pass. Current public health confirms Cloud v2 at 25k / 39 MB; the v1 foundation file remains historical only. |
| **G04 — automatic reload** | Empty/incomplete graph triggers one background worker, ETA, deadline, force retry and same-bank snapshot restoration. [SeedManager](../seed/__init__.py), [snapshot](../seed/snapshot.py), [runbook](runbook.md). | **Pass for recovery/restore contracts.** Actual empty/half-load recovery, deadline and control preservation pass locally. The reviewed schema 2 snapshot contains 16 findings, 16 sessions and 55 calls. Current Cloud v2 is loaded; no additional destructive Cloud wipe is required for final acceptance. |
| **G05 — fixed typed catalogue** | Sixteen frozen tools with bounded, typed arguments and prewritten Cypher; IDs checked; as-of filters; exactly fourteen reads plus two private writes. [Schemas](../server/schemas.py), [read tools](../server/mcp_read.py), [write tools](../server/mcp_write.py), [Cypher](../server/cypher/), [fingerprint](../server/catalogue.py). | **Pass.** Typed/read/as-of/fingerprint contracts pass; current model trial has120/120 authoritatively correct nonempty paths and first-tool match 1.0. The catalogue amendment resolves the prose count conflict by including max-flow. |
| **G06 — external MCP proof** | Standard authenticated MCP at `/mcp`, fourteen read-only tools; both writes remain in-process. Public MCP access instructions/key in README. | **Pass.** Current public standard MCP list/call exposes exactly 14 read-only tools; the MCP bearer cannot approve, and both private writes remain absent. |
| **G07 — graph-native algorithms** | Native SPpaths, WCC, LPA, PageRank and sampled betweenness; global properties carry computed-at; trace identifies algorithms. Max-flow uses the documented FLOW projection. | **Pass for algorithms/contracts.** Native foundation and engine probes pass, including current local v2. Current Cloud v2 is loaded; algorithm/source trace is exercised by the actual investigations and video. |
| **G08 — shapes and exact evidence** | Four badges, selected exact hop list/canvas, directed money particles, every cited TX/date/amount/direction/rail/source tool; every absence has reason and “Not in the graph ≠ nothing wrong.” [UI](../ui/src/App.jsx), [view data](../ui/src/data.js). | **Pass.** All 120 model paths are authoritatively correct; current public depth 1/depth 4 paths, all four shapes and actual video/UI evidence pass. Earlier failed trials remain historical. |
| **G09 — streaming work** | Tool name/inputs/ms/rows/outcome/guard stream; final model/tokens/cache/cost/judge/verifier; JSON metadata log/audit. [Context](../server/context.py), [agent](../server/agent.py), [UI trace](../ui/src/App.jsx). | **Pass.** Current public SSE, real model traces, safe structured logs and final model/token/cache/cost/judge/verifier metadata pass. |
| **G10 — verifier and independent judge** | Every emitted ID, amount and date grounded; unsupported prose replaced/chipped; separate evidence-only model judge; weak closure withdrawn and escalated. [Verifier](../server/verifier.py), [agent](../server/agent.py). | **Pass.** Full 370-test suites, 88 audit regressions and 28 actual graph contracts cover verification, invented names/money, decision transitions and weak-close superseding escalation. All 120 model answers used the disclosed deterministic replacement path; no claim of unverified prose quality is made. |
| **G11 — no innocence from emptiness** | Close needs two distinct nonempty typology-free checks; hold needs an allowed multi-edge pattern. | **Pass.** Actual action end-state tests refuse empty close and single-transfer hold, accept supported positive controls and preserve Account.status. Deleted-ring model abstentions pass20/20 with zero false path answers. |
| **G12 — named human actions** | All seven kinds create pending cards with targets/paths/restrictions/draft. Approve/deny/modify reason ≥20; decision user/role/time; PO-only reports; hold only recommendation; supersession instead of deletion. | **Pass.** Actual action contracts cover all seven kinds and positive modify/deny/close/PO reports; current 39-check public workflow and real video pass case approval and hold denial with named reasons/time. |
| **G13 — cross-session memory** | Bi-temporal Finding, read-before-reason, learned date/author/review state, analyst supersession, ≤5 unreviewed findings; retained paths after restore. | **Pass.** Current public second-session reviewed dated memory, original evidence/session snapshot restore, analyst correction and bounded unreviewed recall pass; the actual video includes memory. |
| **G14 — planted instructions** | All graph free text bounded, normalized, scrubbed, delimited and READ-scanned; WRITE refusal names matched pattern; legitimate hold/close wording permitted; memory labels remain untrusted. | **Pass.** Forty real-model attack runs are target-exposed and guarded, with zero targeted action success, unapproved effects or instruction stores. Structural 20-memo controls and the actual seeded-memo video scene also pass. |
| **G15 — identity and isolation** | Server key→person/role/bank; no client tenant/role; UUID-scoped pending/case/finding; key once/sessionStorage, never bundled. | **Pass.** Both-engine IDOR/identity-override/report-role tests, secret scans, actual UI and current public server-assigned judge identity pass. |
| **G16 — spend/rate/concurrency** | Console outer wall, halt/model-off, $8 UTC bank cap, three investigations/six queries, bearer/IP buckets, 10 tools/12 requests/60k in/6k out/$0.25/60 s, non-AI fallback. | **Pass.** Current public load accepted 3 of 5 and rejected 2 busy 429 requests; observed peak RSS 203.19 MB. Budget/rate/query limits, model-off/manual fallback and scoped approval tests pass. Explicit local eval_model $12 total was limited to UTC 20261017; public/default $8 and Console limits remained unchanged and prior liability was retained. |
| **G17 — honest degradation** | Typed plain errors, finite calls/retries/timeouts, no exposed stack, model/DB/warmup/cap/rate/halt UI, health readiness/size/pending/spend/version/model. | **Pass.** Both-engine error/cancellation/recovery contracts, current public fallback and actual manual-tool video pass. Clear failures do not become claims of innocence. |
| **G18 — keep awake and alert** | Two scheduled pingers, free uptime monitor/email and daily real question. [Actions](../.github/workflows/), [Worker](../ops/cloudflare-worker.js), [cron](../ops/wrangler.toml). | **Pass.** Actual current-source [health 39083716142](https://github.com/Baharul0111/RingSight/actions/runs/39083716142), [daily question 39087562823](https://github.com/Baharul0111/RingSight/actions/runs/39087562823) and [CI 39046049271](https://github.com/Baharul0111/RingSight/actions/runs/39046049271) completed successfully; [operational metadata](../evals/results/operational-probes.json) validates their source fingerprints. Owner-confirmed UptimeRobot/Cloudflare configuration remains recorded separately; no independent email-delivery claim is invented. |
| **G19 — regulator export** | Approved SAR intro/body/conclusion who/what/when/where/why/how, individual TX/date/amount and no tables; STR tags/narration <20k/rail-sheet type; text+data downloads, coverage footer, unverified-primary labels. | **Pass.** Actual proposal→PO approval→export, narrative/report-safety and UI contracts verify SAR/STR content and downloads. Indian facts remain labelled unverified-primary; no filing occurs. |
| **G20 — automated committed proof** | All structural/action/IDOR/point-in-time/injection tests plus 120 paths, twenty deleted-ring abstentions and forty attack runs on local copies; results committed, README measured/demo-only. | **Technical evidence complete.** Local/GitHub 370-test suites, 35-pattern / 382-edge oracle, all 180 model cases, current public acceptance/load, snapshot-inclusive Compose and operational jobs pass. Committed/public delivery is determined by completion.json → required_files_committed_and_pushed. |
| **G21 — submission assets** | Existing public MIT repository, SSPL notice, AMLSim Apache attribution; complete README/query catalogue/AI disclosure/tracks/blog/runbook; actual scripted three-minute screen recording including live depth/approval/Browser/memory/abstention/injection/limits. | **Assets/technical checks complete.** Actual 180-second video/captions / 10-chapter manifest, public live/local proof, README/query catalogue, licences, disclosure, blog and rule/understanding guides exist. Final delivery is tracked by the completion manifest; owner attestations/form approval remain separate. |
| **G22 — measured speed and usable UI** | Approximately 15 s depth 4 target; publish measured live p50/p95; laptop usable empty/loading/error states; integer-paise ₹ rendering. | **UI/measurement pass; speed target missed.** Current public depth 1/depth 4 each had N=1: 36.434s/36.045s. Concurrent accepted depth 4 N=3 had p50/p95=38.190/39.371s. These measured values exceed the roughly 15 s target and are disclosed; usable UI/caps remain intact. |

## Architecture §3.0–§3.15

| Section | Required slice obligations | Evidence / disposition |
|---|---|---|
| **3.0 Requirement trace** | All domain/hackathon/safety requirements accounted for; graph does the essential work. | All 22 goals and final acceptance are mapped to passing technical artifacts. The missed 15-second target is disclosed. Repository delivery is determined by the final completion manifest; personal attestations are not fabricated. |
| **3.1 Product/pitch** | RingSight name; bank AML investigation; fixed tools, exact graph path, memory, approval. | RingSight graph paths, memory, proposed actions and named approval pass current public acceptance and the actual recorded demo. |
| **3.2 Graph model** | Every entity/relationship/control/memory/audit/report label, integer paise/epoch, tenant graphs, indexes/range/fulltext/constraints, native precompute, external truth, ≤40 MB measurement. | Foundation/read/action/recovery tests and 25k≤40 MB measurements pass. Reviewed same-bank schema 2 snapshot is present. The private rebuild bridge is not a runtime datastore. |
| **3.3 Frozen catalogue** | Exact fourteen public reads/two private writes; complete bounded typed schemas, annotations/descriptions/examples, labelled parameterized queries, unknown-ID checks, as-of, dense hub guard, count-before-collect, no query-generation tool. | Typed/schema/as-of/MCP/oracle tests and 120 correct model paths pass. Exactly 14 reads/two private writes and max-flow/FLOW amendment remain explicit; previous endpoint defects are fixed and historical. |
| **3.4 Agent runtime** | Pydantic-AI/FastMCP fixed tools, dated preflight, bounded projections, explicit charged retries, planner→evidence-only judge→verifier, safe pending actions, per-run/global caps, SSE trace and final cost. | All 180 model cases, actual local/current-public workflows, bounded concurrency, fallback and the real video pass. Frozen staged tools, independent judgment and verifier replacements are disclosed. |
| **3.5 Memory** | Bi-temporal Findings/ABOUT/MADE_IN/SUPERSEDES, no vector substitute, five unreviewed max, named feedback, retained dated path, captured snapshot for reseed. | Bi-temporal memory, corrections, bounded unreviewed recall and original path/session restoration pass. Shipped snapshot has 16 findings / 16 sessions / 55 ToolCalls and three reviewed findings; actual video shows second-session memory. |
| **3.6 Safety** | Identity/IDOR, RO_QUERY, typed bounds, separate guards, verification/judge, spend/rate/query slots, human route, bounded failures, fallback, CSP/secrets, recovery, admin audit/logging. | Current local and GitHub 370-test suites and full injection experiment pass, including scoped budget expiry, verifier, human transitions, safe logs and recovery. Production hash-chain/WORM/IdP/TLS work remains disclosed before-pilot scope. |
| **3.7 Synthetic data** | Deterministic seven typologies/controls/memos/truth; secure direct bulk loading, background/recoverable rebuild, complete Meta last, seed sizes. | Generator controls, 35-pattern physical-path oracle and 25k foundation pass. Current Cloud health confirms v2 / 25k / 39 MB. Density 32.5kTX and sampled 32 centrality are documented measured amendments; no Batch authorship claim is invented. |
| **3.8 UI** | Key-once identity, ask/as-of/depth, all degradation states, streamed trace, ≤1k-node directional canvas/selected path, badges/memory/date, evidence CSV/IST/₹, reasoned pending cards/red restrictions/PO gate, reports/downloads, real coverage, no-AI form. | Actual built UI, interaction contracts, local/current-public complete workflows and the real 10-chapter video pass. Public timing measurements disclose the missed 15 s target. |
| **3.9 Deployment** | One free Docker service, pinned Python/Node/dependencies/engine, `/live` Render health path, complete Compose/AOF/loopback local stack, typed endpoints, cached `/health`, two crons/UptimeRobot/daily question, bounded degradation, secret env and logs, CI4.22.1+6.0.2. | Final snapshot-inclusive Compose/AOF/browser, local/GitHub 370-case 4.22.1/6.0.2 suites, current public acceptance/load and current-source health/daily/CI jobs pass. Owner monitor setup is confirmed. Final delivery is tracked by completion.json. |
| **3.10 Evals** | Must-ship structural1/3/4a/5/7a, model2/4b/7b, committed results/demo-only labels. Memory/latency listed stretch in original plan are also explicitly required where goal acceptance calls for them. | The 35-pattern / 382-edge oracle,120 correct paths,20 abstentions,40 exposed injections, public 39-check acceptance and five-concurrent load pass. Final measured README is regenerated; committed delivery is determined by the completion manifest. |
| **3.11 Scale plan** | README documents nightly window, sampled algorithms, writer queue, cache/replicas, tenant/region shards, warehouse history, offline features/on-prem eval gate, audit growth, load/SLO/observability/ceiling. | Production scale, retention, audit-growth, load/SLO and hosting plan are documented. They are not represented as deployed banking infrastructure. |
| **3.12 Regulatory fit** | Evidence-backed template SAR/STR, exact individual transfers, reasoned human/PO decisions, hold≠account restriction, provisional Indian labels, no filings; honest India-hosted shadow pilot/DPAs/licence/retention/incident posture. | Actual approved template reports and export safety tests pass; unverified-primary Indian labels appear in UI/docs/video. No filings or legal certification are claimed. Real-bank agreements/hosting/legal review remain before-pilot scope. |
| **3.13 Submission mapping** | Public repo/README/local/live/Cypher/tracks/disclosure/blog and actual 3-minute Browser-inclusive video matching the script. | Public repository and complete documentation/disclosure/blog plus actual 180-second Browser-inclusive video exist. Final evidence/documentation delivery is determined by the completion manifest; explicit form approval remains owner-only. |
| **3.14 Cost** | Free single-service hosting; Console outer wall; at-most$8bank/day; bounded per-call/run spend; real measured cost displayed; no cap increases without owner approval. | All 180 model cases cost $6.6188376. The explicit local-only $12 total approval for UTC 20261017 preserved prior liability and restored the previous cap; public/default $8 and Console limits remained unchanged. Current public limit/load/fallback checks pass. |
| **3.15 Build plan/clock** | Preserve never-cut spend/rate, read-only MCP, both guards, IDOR, fallback, automatic reseed and committed structural proof; carry missing must-ship work ahead of extras; complete docs/exports/snapshot/model eval/video/blog; final permission gate. | All mandatory implementation/model/live/video/operational checks pass. Final public repository delivery is verified by the completion manifest. Internal deadline 18 October 23:00 IST and official close 23:59 IST remain clear; final form approval is owner-only. |

## Architecture's explicit hackathon build items

| Item | Required behavior | Current evidence |
|---|---|---|
| **Hm-13** | `[unverified-primary]` Indian facts in UI/README/video/blog. | Unverified-primary Indian labels are present in UI/README/blog and the actual recorded video. |
| **Hm-21** | WRITE ignore-pattern requires instruction object; honest prior-alert wording accepted; paraphrases labelled/unreviewed and flagged on recall. | Both guard profiles/positive controls and all 40 genuinely exposed model attack cases pass with zero instruction stores/unapproved effects; unreviewed paraphrase handling remains disclosed. |
| **Hm-22** | Bounded wall-clock partial answer with reason/banner/escalation; retain measured latency; off-path polish only if shipped. | Timeout/budget/weak-close transitions pass and measured timings are retained. Current public depth 4 was 36.045s; concurrent p95 was 39.371s (N=3), missing the 15 s target. Template-only reports remain the default. |
| **Hm-23** | Reseed only empty/incomplete; health5s/no-retry cached model probe; DB acquire2s; health15 s cache; Render `/live`. | Health/recovery/cancellation/fresh Compose checks and current public model/graph readiness pass; Cloud v2 is loaded and Render uses /live. |
| **Hm-24** | Deadline max15min/3×reseed, terminate/kill/release, explicit force retry, runbook. | Deadline cancellation/release/force-retry contracts and the documented runbook pass. |
| **Hm-25** | Explicit external read logging-only limit, separate manual key bucket, graph≥80MB warning. | Safe structured external-read metadata logging, separate manual bucket and≥80MB warning have passing current full-suite coverage. |
| **Hm-26** | Escalation creates Case without preexisting case_id; indexed count/recall plans; honest partial rendered as not_in_graph with timeout/budget reason. | Actual escalation Case creation/index plans and honest timeout/budget shapes pass; actual video/fallback demonstrate the human tool route. |

## Final acceptance: every clause of “How we know it is finished”

| Acceptance check | Current evidence | Completion condition |
|---|---|---|
| Fresh clone/filled env/one local command starts DB+seed+app | Final fresh Compose/image/25k/AOF/browser proof passes with the current 16-finding snapshot included and its copied data hash verified. | Final current source pushed; fresh clone contains it and README command remains valid. |
| Public page answers same question at depth 1 and 4 | Current public acceptance passes both exact paths; depth 1 excludes the hidden exit and depth 4 includes it. The actual video also passes. | Successful current public-URL artifact with depth 1 excluding exit and depth 4 including exact hidden path. |
| Proposes and accepts case approval with reason/named identity/time | Current public acceptance and actual video pass reasoned named approval and recorded Decision identity/time. | Successful real HTTP/UI session creates own pending proposal, approves it and reads the recorded Decision. |
| Hold is denied with written reasons; no account status write | Current public acceptance, local/action tests and actual video pass hold denial with a reason; no Account.status write occurs. | Successful real workflow/video denies its own pending hold and verifies its recorded reason/identity/status. |
| New session remembers dated, reviewed evidence/path | Current public reviewed second-session memory and schema2 snapshot restore pass, including original evidence; the actual video shows the learned date. | Model memory badge/date/review/path after approved case, plus captured nonempty schema 2 snapshot and restore proof. |
| Unknown entity abstains | Current public zero-investigation-call unknown outcome, structural20-case controls and actual video pass. | Actual public `/ask` unknown shape with no invented ID substitution/model call. |
| Cash abstains because rail not loaded | Current public zero-investigation-call rail_not_ingested outcome, structural5-case controls and actual video pass. | Actual public `/ask` reason rail_not_ingested, banner and zero model calls. |
| Planted memo cannot direct an effect or poison trusted memory | All 40 real-model exposed/guarded attack cases pass with zero unapproved effects or instruction stores; the actual seeded-memo video scene passes. | Forty real-model exposed-attack runs complete with zero unapproved effects; actual seeded memo visible/flagged in video. |
| Cannot exceed spending/rate/time/concurrency caps | Current public five-concurrent limits pass: 3 accepted, 2 busy 429, sampled 203.19 MB maximum. Full local/CI budget and scoped-approval checks pass with no liability reset. | Final relevant local contracts plus actual five-concurrent public requests/RSS; preserve all liability and require explicit approval for any cap increase. |
| Exactly 14 reads, no writes over standard MCP | Current public MCP list/call and write-bearer refusal pass; both private writes are absent. | Same proof at the current public `/mcp`; two private writes absent. |
| Model switched off → human form still returns path | Current public model-off/refused ask/manual path/restored setting checks and the actual video pass. | Actual HTTP admin model-off, rejected `/ask`, manual read path, restored setting with no investigation charge. |
| Every behavior has passing automated evidence | All 370-test suites, all 180 model cases, current public acceptance/load, snapshot-inclusive Compose, reviewed snapshot, actual 180-second video and current-source operational jobs pass. Delivery is determined by the completion manifest. | Fix failures and run complete current-source local/model/live checks. Badge/exit-code/file existence alone is insufficient. |
| All results committed to existing public repo | Final results/docs/video updates are being prepared; require secret scan, final commit/push and matching delivery gate before claiming publication complete. | Secret scan and final checks pass; required evidence committed and pushed to Baharul0111/RingSight. |
| README/query catalogue/script/disclosure/blog exist and match final facts | All assets exist and README is regenerated from current complete model/live/video results, including actual live p50/p95 and successful workflow links. | Regenerate final measured statuses/numbers/latencies, verify complete inline queries and links; preserve honest limitations. |
| Actual3-minute screen recording includes every required scene | Passed actual 180.000-second MP4/hash/captions and 10 chapters include real Cloud Browser graph results and all scripted scenes. No recapture is required for documentation updates. | Real UI+FalkorDB Browser capture, exact180s artifact/hash, reviewed scene checklist and public repository/video link. |
| Current monitoring and daily question work | **Pass.** Actual current-source [health 39083716142](https://github.com/Baharul0111/RingSight/actions/runs/39083716142), [daily question 39087562823](https://github.com/Baharul0111/RingSight/actions/runs/39087562823) and [CI 39046049271](https://github.com/Baharul0111/RingSight/actions/runs/39046049271) completed successfully; [operational metadata](../evals/results/operational-probes.json) validates their source fingerprints. Owner-confirmed UptimeRobot/Cloudflare configuration remains recorded separately; no independent email-delivery claim is invented. | Record successful health/daily-question/CI results; retain owner-confirmed alert routing without re-asking accounts/keys. |
| Final hackathon form | Not submitted. Owner must review the finished package and explicitly approve the form. | Wait for Baharul's explicit go-ahead after the reviewable package is ready. |
| Any daily/Console cap raise | Only local eval_model $12 total for UTC 20261017 was explicitly approved and used; public/default $8 and Console limits are unchanged. Any additional raise still requires approval. | Enforce local-only/day expiry, preserve all prior liability and restore the previous cap. Any additional increase still waits for explicit approval; no ledger reset is authorized. |

## Final delivery and owner review

All technical evidence now passes, including current-source health, daily
question and CI jobs. Repository delivery is complete when
[completion.json](../evals/results/completion.json) reports `status: passed`
and its `required_files_committed_and_pushed` check passes. That manifest is
verified against the final commit and matching public-origin tracking ref;
this checklist does not claim its own future commit already exists.

The 180-case model protocol and actual video need no rerun for documentation
changes. The 15-second speed target is a measured, disclosed miss. Owner-only
eligibility, contribution/understanding, start-time and IP/conduct checks are
listed separately in [submission-checklist.md](submission-checklist.md). The
final hackathon form and any additional cap increase require explicit approval.

## Scope and resolved design corrections

The original prose called the slice “twelve” tools while enumerating thirteen
reads and requiring fourteen MCP reads/sixteen total tools. The written
architecture amendment makes the numbered catalogue authoritative and ships
max-flow as the fourteenth read over a labelled FLOW snapshot. Backlog/queue
tools remain explicitly production-only.

Other written amendments record measured graph-density reduction, 32-sample
betweenness, strict-compiler-compatible staged tools, charged provider retries,
v2 demo-phone correction, schema 2 memory evidence, complete catalogue hashes
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

## Supplied hackathon rules

[submission-checklist.md](submission-checklist.md) maps all 18 supplied rules;
[explain-ringsight.md](explain-ringsight.md) supports participant code review.
Personal team eligibility, actual work start, understanding, contribution and
IP agreements require truthful owner attestations. They are not replaced by
a passing technical completion gate. Registration and the existing account/
monitor setup are already confirmed and are not requested again.
