# Explain RingSight in your own words

This is a code-review and demo preparation guide for Baharul. It is not an
attestation of personal understanding or a script claiming work you did not
do. Follow the links, run the safe walkthrough, and explain each decision in
your own words before declaring the submission ready.

## The product and the two tracks

An investigator asks whether a synthetic flagged account connects to a ring.
RingSight returns dated graph evidence, proposes a next step and waits for a
named human's decision. It never files a real report or changes account status.
Track 01, **Agents That Act on Connected Data**, is primary. Track 02,
**Agent Memory and Coordination**, covers persistent dated findings and
human decisions across sessions.

Be able to explain why this is more than a chat interface: the graph supplies
the path, transfer facts, coverage, restrictions, memory and approval state.
The model selects bounded operations. It cannot invent Cypher or approve its
own proposed action. Removing FalkorDB removes those capabilities.

## Read the graph before the agent

Open [the diagram](architecture.svg), [generator](../synth/generate.py),
[indexes](../server/cypher/indexes.cypher), [precomputation](../server/cypher/precompute.cypher)
and [seed module](../seed/__init__.py). The README also prints schema and
control queries inline.

- An Account has directed TX edges to another Account. TX stores an opaque
  id, integer paise, UTC epoch time, rail and guarded memo.
- A Person owns an Account; shared Device/Phone/Address/owner relationships
  can connect accounts that a transfer-only first hop misses.
- Rail/IngestionDay state explains loaded and missing data. Restriction and
  Alert nodes supply controls, rather than asking the model to remember them.
- Finding, Session and ToolCall retain learned facts and original evidence.
  PendingAction, Decision, Case, HoldProposal and SARDraft represent human
  workflow in the same tenant graph.
- The server maps a key to a person, role and bank. It selects `rs_bank_a` or
  the toy second bank graph; a browser cannot submit another tenant identity.

Explain the hidden exit using the actual returned path:
`ACC-4471 → DEV-f31c → ACC-10477 → PER-2291 → ACC-55820`.
Identify which hops mean shared identifiers/ownership, and which returned
edges are transfers. Do not describe that whole identifier path as money
flow. Explain why depth 1 cannot include the fourth-hop exit.

The generator plants 35 rings in seven families and also legitimate busy
accounts. Ground truth stays outside the runtime graph. The current measured
25k-account graph is below 40 MB; read [actual foundation evidence](../evals/results/local-foundation-v2.json)
instead of repeating an estimate. The reduced background transfer density
and 32 betweenness samples are measured engineering tradeoffs, not a claim of
real-bank detection performance.

## Walk one fixed query and one native algorithm

Read [typed input schemas](../server/schemas.py),
[read-tool handlers](../server/mcp_read.py) and the matching file in
[server/cypher/](../server/cypher/). Pick `rs_neighbourhood` and `rs_cycles`.
Trace one input from bounded schema through id existence checks, parameter
binding, a graph query and the evidence envelope.

For the neighbourhood query, explain relationship direction, hop bound,
amount/time window, and where `as_of` excludes future transfers. For cycles,
explain why it needs 3–5 directed edges, bounded elapsed time and decaying
amounts. Find the regression that checks returned TX endpoints rather than
trusting the outcome badge.

Then inspect the native algorithm calls in the README and
[precomputation code](../seed/__init__.py). Explain WCC, label propagation,
PageRank, sampled betweenness and shortest paths in plain language. Global
properties have a computed-at time; they are not silently recalculated for
an earlier historical question. The dated FLOW projection is used only for
max-flow because parallel transfer edges need aggregation.

There are exactly **fourteen public read tools and two private write tools**.
The numbered catalogue's written amendment resolves the original conflicting
tool-count prose by including max-flow. Backlog and queue tools stay outside
the slice. Explain how publishing writes or a free-form Cypher tool would
change the authority boundary.

## Trace a question, proposal and decision

Read [agent.py](../server/agent.py), [verifier.py](../server/verifier.py),
[mcp_write.py](../server/mcp_write.py), [actions.py](../server/actions.py)
and [HTTP routes](../server/app.py).

1. The server resolves entity ids, recalls dated findings and checks coverage.
   Unknown accounts and missing CASH data can abstain without an investigation
   model call. An absent path never establishes innocence.
2. The planner selects typed tools. A bounded projection goes to the model;
   original evidence stays in FalkorDB and the UI. Staged subsets accommodate
   observed strict-compiler limits without adding new tools.
3. A deterministic verifier checks ids, amounts, dates, names and quantities.
   Unsupported prose is replaced by a statement built from rows. A separate
   evidence-only model judges the conclusion; weak closure is withdrawn and
   superseded by escalation.
4. Recording a Finding or proposing an action requires this session's
   nonempty evidence. A close needs two distinct affirmative checks without
   suspicious pattern hits; a hold needs multi-edge pattern evidence.
5. The pending card is still a proposal. The human HTTP route requires a
   reason of at least 20 characters and records identity, role and time.
   Reports require the Principal Officer. A hold writes only a recommendation,
   never `Account.status`. Corrections supersede rather than erase history.

Explain all four answer badges, why a memory answer displays learned date and
review state, and why original ToolCall evidence must survive snapshot restore.
Identify the route the model cannot call, rather than relying on a prompt
saying “please ask a human.”

## Explain the boundaries and failures honestly

Read [safety.py](../server/safety.py), [guard.py](../server/guard.py),
[runbook](runbook.md) and the README's safety/limitations sections.

Graph text is untrusted data: bounded, scrubbed, delimited and scanned.
READ guards flag an instruction in a memo. WRITE guards reject role mimicry,
instruction overrides and approval bypasses while permitting honest hold or
closure rationales. A paraphrase may be stored as unreviewed data and scanned
again on recall; deterministic guards do not prove prompt injection solved.

Explain the spending layers: Console outer wall, graph-backed halt/model flag,
at most $8 UTC daily bank cap, key/IP limits, three investigations, six graph
queries, per-run request/token/tool/cost/time bounds and charged reservations.
When model calls stop, manual read tools still require the graph. A spontaneous
Cloud loss can lose new decisions or its ledger; automatic synthetic rebuild
and the saved snapshot restore a defined recovery point, with the Console
limit remaining the outer wall. A private planned-rebuild checkpoint preserves
known controls/liability without becoming a second runtime datastore.

Free-tier cold starts, sampled algorithms, imperfect synthetic hub precision,
single-process rate limits and provisional Indian report formats are disclosed.
SAR/STR exports are evidence-only templates, not actual filings or a legal
compliance certification. Read the actual measured live p50/p95 when available;
a target of 15 seconds is not a guarantee.

## Perform the walkthrough and inspect real evidence

Start the filled-env local stack using the README's `make up`. Keep credentials
outside screenshots. In the UI, compare depths 1/4, inspect the exact hop list
and TX table, approve your own case proposal and deny your own hold with
written reasons, start a new session, ask about an unknown account and CASH,
and inspect the planted memo's guard trace. Do not paste a new attack into the
question as a substitute for the seeded memo. Follow [demo-script.md](demo-script.md)
for the real recording and safe reversible model-off/manual-tool demonstration.

Read [pytest.json](../evals/results/pytest.json),
[structural-patterns.json](../evals/results/structural-patterns.json),
[model-paths.json](../evals/results/model-paths.json) and the eventual live,
injection, video and CI results. Explain a failing or incomplete artifact as
such. A pass badge, a file's existence, or a correct-looking canvas does not
establish path correctness or zero unapproved effects.

Use [requirement-checklist.md](requirement-checklist.md) and the read-only
`.venv/bin/python ops/check_completion.py` to inspect remaining proof. Check
that results are committed and pushed before presenting them as the public
entry. Write down what you personally reviewed, tested, changed and learned;
do not claim to have handwritten code produced with Codex.

## Questions to answer without reading a prepared sentence

1. Which graph entities make the fourth-hop exit visible, and how do their
   semantics differ from TX edges?
2. Show where one typed argument becomes a Cypher parameter. Where are the
   depth, date, direction and row bounds enforced?
3. Why does a high-degree payroll account differ from a planted laundering
   pattern, and what do imperfect hub precision numbers tell you?
4. Which two capabilities can write, and why can an external MCP client call
   neither? What exact human route produces a Decision?
5. What stops empty evidence from closing an account? What remains true after
   a hold is approved?
6. What is bi-temporal memory? How does a human correction retain the old
   observation and original path?
7. What happens when the model is off, the graph is gone, a cap is exhausted
   or the service cold-starts? Which operations can still succeed?
8. Which facts do the automated tests establish, which measurements are
   synthetic, and which eligibility/ownership/conduct facts must you attest?

If you cannot answer one, follow its source links and test it before claiming
understanding. The [submission checklist](submission-checklist.md) keeps those
personal attestations separate from technical evidence.
