# 05 — Bind Strategy Activation to basic Intent Threads

**What to build:** Bind an explicitly loaded Capability Strategy to the semantic work it was selected for. The main model can declare a new Intent Thread, resume it as a follow-up, or append a correction, while unrelated work remains separate and direct provider calls retain the correct Adaptive or guarded behavior.

**Blocked by:** 04 — Execute one local Contracted Strategy end to end.

**Status:** ready-for-agent

- [ ] Explicit skill loading creates Strategy Activation for a stable Intent Thread; listing, discovery, installation, or subject similarity alone does not activate it.
- [ ] The normal model turn can submit `new`, `follow_up`, or `correction` plus an Intent Reference through the strategy execution interface without a separate classification model call.
- [ ] A new relation creates a stable Intent Reference, while follow-up and correction require an existing compatible Intent Thread.
- [ ] Strategy continuity has no TTL and is not inferred solely from turn adjacency, session ID, conversation ID, or reply metadata.
- [ ] Multiple Intent Threads can coexist in one conversation without sharing activation or capability-run state.
- [ ] A correction appends a new user turn and amended run; it does not rewrite prior transcript messages, traces, or outcomes.
- [ ] A direct provider call with no matching activation remains Adaptive and preserves existing behavior.
- [ ] A direct call to an underlying contracted operation after activation is rejected before side effects and directs the run back through the active strategy.
- [ ] Structurally invalid or incompatible Intent References return a controlled diagnostic rather than silently selecting the newest thread.
- [ ] High-level multi-turn tests prove new, follow-up, correction, unrelated work, direct Adaptive calls, and active-strategy bypass behavior through observable operations and persisted intent metadata.
