# 08 — Enforce Teams MTK owner control-conversation execution

**What to build:** Make executable strategies a first-class but owner-only Teams MTK capability. The exact configured control conversation receives a stable strategy tool surface, but every invocation is also bound to the immutable owner sender for that turn; all other Gateway origins are denied without leaking authority through caching or concurrency.

**Blocked by:** 02 — Establish per-turn owner Execution Authority through skill maintenance; 04 — Execute one local Contracted Strategy end to end.

**Status:** ready-for-agent

- [ ] An eligible Teams MTK control-conversation Agent exposes the service-gated strategy execution interface at construction and keeps its tool schema byte-stable for the session.
- [ ] An ordinary or non-control Gateway Agent does not expose the strategy execution interface and does not gain it mid-conversation.
- [ ] Dispatch recomputes immutable sender authority on every turn even when the control conversation reuses one cached Agent.
- [ ] The exact owner sender in the exact control conversation can load and execute a harmless contracted strategy under normal approvals.
- [ ] The owner in another conversation, another sender in the control conversation, and an ordinary Gateway origin are denied before the first contracted side effect.
- [ ] A denied invocation does not silently fall back to direct Adaptive provider execution.
- [ ] Delegated or background descendants inherit no more strategy authority than the commissioning Teams turn.
- [ ] Sequential and concurrent tests prove platform, conversation, sender, Intent Reference, approval routing, and Execution Authority do not cross turns or workers.
- [ ] Denial and trace output reveal an authority class and reason without exposing raw personal identifiers or credentials.
- [ ] The behavior is proven through the real Gateway inbound/session-context and Agent dispatch seams rather than a mock of the authority predicate.
