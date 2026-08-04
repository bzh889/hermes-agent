# 09 — Preserve semantic continuity across compression and strategy versions

**What to build:** Preserve multiple long-lived Intent Threads and their Strategy Activations across session resume, context compression, old-message retrieval, and manifest updates. A late follow-up or correction can select the right prior work without TTL, while each run remains reproducible against one immutable strategy version.

**Blocked by:** 05 — Bind Strategy Activation to basic Intent Threads.

**Status:** ready-for-agent

- [ ] Intent References, compact semantic summaries, activations, and capability-run references persist as structured session metadata outside the alternating model transcript.
- [ ] Context compression preserves or regenerates the compact intent index without rewriting prior user or assistant messages or changing cached prompt bytes.
- [ ] An explicit Teams reply/message relation supplies a candidate anchor but does not override semantic classification.
- [ ] When the candidate exchange is outside active context, same-conversation history retrieval provides the relevant prior user and assistant evidence before relation selection.
- [ ] Multiple old Intent Threads can be resumed correctly after intervening unrelated work, session resume, and compression, with no time-based expiration.
- [ ] Ambiguous continuation that could cause a side effect or durable mutation asks the user; low-risk read-only continuation may proceed only with its interpretation stated.
- [ ] A capability run keeps the immutable manifest snapshot and digest compiled at its start even if the underlying skill changes mid-run.
- [ ] A later follow-up resolves the latest valid manifest while historical traces retain their original version and digest.
- [ ] Installing or editing executable strategies does not alter the current session tool schema by default; availability changes at a new session boundary.
- [ ] Multi-turn persistence/compression tests assert the selected prior intent, operation side effects, manifest versions, and role/cache invariants rather than textual summaries alone.
