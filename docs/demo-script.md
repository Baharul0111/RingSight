# RingSight — three-minute screen recording

Track 01 (primary) · Track 02 (memory). Use only the synthetic graph. This is
the recording script, not a claim that a video has already been recorded.

Before recording, pre-warm the Render page and `/health` five minutes ahead.
Keep FalkorDB Browser at `http://localhost:3000` ready. Obtain the planted demo
ids from `data/manifest.json` under `demo`, and the injected account from
`data/injections.json`; do not paste an attack into the question. Start with a
fresh investigation so the first answer is a path, then use a new session to
show memory. Keep the Principal Officer key private and outside the recording.

| Time | Picture | Narration and action |
|---|---|---|
| 0:00–0:20 | Live console; coverage strip; six rails loaded and CASH/XB missing | “An account alert needs an explanation a human can check. RingSight follows accounts, people, devices and transfers. This is synthetic data; nothing is filed.” |
| 0:20–0:45 | Ask the same demo question with depth 1 | “Is ACC-4471 part of a ring, and how does the money move?” Show tool names, bounded inputs, row counts, amounts in rupees and dates in IST. “The model chooses from a fixed catalogue. It never writes a database query.” |
| 0:45–1:15 | Repeat at depth 4; highlight the hidden exit path and read the hop list | Point to the device → account → owner → exit link returned by the seeded graph. Read the actual ids on screen. “A shallow view misses this connection. Every claim comes with its graph path.” Do not narrate invented counts; use the current evidence table. |
| 1:15–1:40 | Pending cards; approve a case, deny a hold; Browser | Enter “The connected evidence warrants a case for human investigation.” to approve the case. Deny the hold with “A case is warranted; a hold recommendation needs additional human assessment.” Show the named decision, reason and time. “A hold is a recommendation to the Principal Officer; account status stays unchanged.” In Browser, show Finding, PendingAction and Decision nodes. |
| 1:40–2:05 | New session, same question; unknown account; cash coverage question | Show “answered from memory”, learned date, author and reviewed flag. Ask about an absent id; show suggestions. Ask “Did ACC-4471 deposit cash?” “Cash is not loaded. Not in the graph does not mean nothing wrong.” |
| 2:05–2:30 | Investigate the pre-planted injected account; trace guard hit | “The memo contains instructions aimed at the agent. The read guard flags it as untrusted data. Instruction-like text cannot be written into memory. A paraphrase remains unreviewed and is scanned again on recall.” Show no approved effect and a guarded write refusal if present in the trace. |
| 2:30–2:45 | Disable the model using the administrator route, then run a read tool | “When the model is unavailable or the budget is exhausted, an analyst can still run the fourteen read-only graph tools.” Show a path with no model call; restore the demo setting afterwards. |
| 2:45–3:00 | Architecture and limits; repository/results | “Remove FalkorDB and RingSight cannot answer, remember, propose, approve or report coverage. Detection metrics are synthetic and demo-only. Indian report-format facts are unverified against the official document. No real filings. The next step is an India-hosted, shadow-mode pilot with real validation.” |

For the video description: accurately disclose the coding assistant and runtime
models actually used. The repository's README disclosure is the authoritative
wording; never imply that a browser review or video recording occurred if it
has not. Include the live URL and public repository link.

Do not submit the final hackathon form until Baharul explicitly approves it.
