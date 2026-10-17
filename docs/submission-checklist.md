# Graph Hacks submission rules and owner checks

This checklist maps the 18 supplied hackathon rules to RingSight. It records
project evidence separately from facts only a participant can attest. A file,
commit date or AI-written explanation cannot establish a person's eligibility,
actual start time, contribution, understanding or ownership agreement.

The official competition window supplied by the organisers is **15 October
2026, 00:01 IST through 18 October 2026, 23:59 IST**. RingSight's earlier internal
deadline in [goal.md](../goal.md) is **18 October 2026, 23:00 IST**. Keep the
earlier build target; the official closing time does not authorize lateness.
Registration is already confirmed by the owner and is not requested again.

| Rule | Requirement | Evidence or remaining owner action |
|---|---|---|
| 1 | Solo or team of at most four; each participant belongs to one team. | **Owner-only attestation.** Confirm the actual participant roster is within the limit and nobody entered on another team. A personal repository does not prove a solo entry. |
| 2 | FalkorDB is the primary graph database and central to the product. | [Graph model](../architecture.md), [database adapter](../server/db.py), [frozen queries](../server/cypher/), [foundation evidence](../evals/results/local-foundation-v2.json). Entities, money, coverage, memory, proposals and decisions use tenant graphs. |
| 3 | The graph does real work; the product must not work when FalkorDB is removed. | Native traversal/community/centrality and all runtime evidence/state depend on FalkorDB. [Requirement checklist](requirement-checklist.md) maps this dependency; graph-outage contracts and recovery checks are in the [test suite](../tests/) and [results](../evals/results/). A manual form still requires FalkorDB. Final acceptance requires the relevant tests to pass. |
| 4 | Docker, self-hosted or Cloud are allowed; any language, frontend and deployment. | Python/FastAPI/Pydantic-AI, React, Cloud graph and one Render service; [Dockerfile](../Dockerfile), [Compose](../docker-compose.yml), [local setup](../README.md). Permission to use a platform is not a claim that live verification passed. |
| 5 | Name every entered track. | **Track 01: Agents That Act on Connected Data (primary)** and **Track 02: Agent Memory and Coordination (memory)** are named in README, [blog](blog.md) and [demo script](demo-script.md). Company Brain is not claimed as an entered track. The owner must choose the same two tracks on the final form. |
| 6 | Use only public, synthetic or owned data; exclude private, restricted, personal, paywalled or login-protected source data. | [Deterministic generator](../synth/generate.py), [data statement](../NOTICE), synthetic ground truth in [data/](../data/). No bank/customer feed or restricted dataset is used. Account credentials configure owned services; they are not a dataset. The owner must avoid adding private material to the video or form. |
| 7 | Build and submit within the official window. | Window and earlier internal deadline are stated above. **Owner-only final timing check.** Actual submission is not performed until explicit approval; a prepared repository is not a submitted entry. |
| 8 | Main coding and design begin after the start; prior ideas, notes, graph sketches and diagrams are allowed. | **Owner-only historical attestation.** Check the actual work history against 15 October 00:01 IST. Git timestamps alone do not prove when code or design was created. Do not claim this is verified by the agent. |
| 9 | Frameworks, OSS, APIs, tools, templates, public data and assets are allowed; original hackathon work is judged. | [AI disclosure](../README.md), [MIT licence](../LICENSE), [upstream notices](../NOTICE), [AMLSim attribution](../licenses/AMLSim-Apache-2.0.txt), checked-in queries and implementation. The original work is the investigation catalogue, graph/control/memory integration, approval flow, synthetic controls, UI and verification. Do not present upstream database/framework code as RingSight-authored. |
| 10 | Public repository; README setup and graph model; Cypher/algorithms; working demo video; live demo or complete local setup; track. | Existing public repo: [Baharul0111/RingSight](https://github.com/Baharul0111/RingSight). [README](../README.md), inline queries, [architecture diagram](architecture.svg), [Compose acceptance](../evals/results/compose-acceptance.json), [recording script](demo-script.md). **Final proof remains gated:** actual passing video manifest/MP4, deployment acceptance and final pushed assets must exist. A script or recorder is not a finished video. |
| 11 | AI coding assistance is allowed and must be disclosed. | README names **OpenAI Codex** as coding assistant and Claude API models as the runtime. Template report drafts are disclosed. No unsupported claim of Claude Code authorship, Batch execution or narrative polishing is made. Copy the same accurate disclosure into the final form/video description. |
| 12 | Participants understand and can explain graph model, queries, architecture and decisions. | [Explanation guide](explain-ringsight.md) points to concrete code, queries and questions. **Owner-only demonstration.** Read the code, perform the walkthrough and explain the decisions in your own words; possessing this guide is not proof of understanding. |
| 13 | Entirely AI-generated work without meaningful participant contribution, verification or understanding may be rejected. | The owner supplied deployment/account setup, updated the model credential, ran terminal verification and reported actual graph/runtime failures during the build. Those are concrete observed setup/verification contributions. **Owner must personally review and explain the implementation**, make any remaining product decisions, and truthfully describe their contribution. The agent cannot certify that the organisers will judge it sufficient. |
| 14 | Prize information. | Informational rule; it adds no code or submission action. No prize, selection or outcome is claimed. |
| 15 | Developed IP belongs to participant/team; teams are encouraged to agree ownership. | RingSight code is [MIT](../LICENSE), copyright Baharul Islam; third-party licences remain separate in [NOTICE](../NOTICE). **Owner-only confirmation:** verify rights to contributions/assets and, if a team exists, agree ownership and submission credit with its members. No team agreement is fabricated. |
| 16 | Respect participants, organisers, sponsors, speakers, judges and community. | Follow the [official Code of Conduct](https://www.wemakedevs.org/coc). No messages, outreach or public submissions are sent by this checklist. The owner remains responsible for conduct in project presentations and community interactions. |
| 17 | Harassment, discrimination, plagiarism and judging manipulation can disqualify. | Attribute reused work, disclose AI, use truthful measurements and synthetic labels, and preserve failed attempts without claiming them as passes. No copied authorship, fake engagement, contact campaign or judging manipulation is part of the project. **Owner conduct obligation** continues through judging. |
| 18 | Rules or Code of Conduct violations may disqualify. | Review all rows and the [official Code of Conduct](https://www.wemakedevs.org/coc) before submission. Technical completeness is checked separately by [check_completion.py](../ops/check_completion.py). Personal eligibility/conduct attestations remain the owner's responsibility. |

## Owner-only steps when the technical package is ready

1. Confirm the real roster/one-team rule, work start timing and any team IP
   agreement. Only you can attest these facts; the agent does not tick them.
2. Use [explain-ringsight.md](explain-ringsight.md) to inspect and explain the
   model, a query, the fixed-tool boundary, human approval and the actual test
   results. Run the local/manual walkthrough and review the generated video.
3. State your actual contribution and AI assistance honestly. You may record
   your own narration or video; the automated captioned recording is actual
   screen capture only after its passing artifact exists.
4. Review the public repository, working video, live/local access, exact track
   names, attribution, disclosure and measured limitations. Do not paste a
   Principal Officer/admin key, model credential or database password into the
   form, video or public issue.
5. **Give explicit go-ahead for the final hackathon form.** Then submit before
   the official close with Track 01 and Track 02 selected. No form has been
   submitted by these documents. Increasing either spending limit separately
   also requires explicit approval.

The remaining product/evidence work is tracked in
[requirement-checklist.md](requirement-checklist.md), rather than converted
into owner attestations or silently omitted.
