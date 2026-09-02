# 34 — Exact-group semantic history retrieval

**What to build:** History retrieval for a restricted group conversation uses reply-chain traversal (backwardLink pagination) first, then sliding-window recent messages, to gather context. There is no mechanical pre-filter — the LLM judges the relevance of each retrieved message. Attachments appear as inline previews; full content requires a two-phase broker fetch (preview → broker). No redaction is applied. History is injected as a standalone user message followed by an assistant ack separator, preserving role alternation and prompt caching. The retrieval identity is bound to the exact `conv_id` from the OriginEgressBinding — no cross-conversation fan-out. Three-layer forced marker tests verify zero cross-conversation leakage: (1) API-level marker present in the correct conversation only; (2) red marker visible in origin group but absent in cross-group; (3) dual-group cross-injection attempt denied.

**Blocked by:** 24 — Origin binding module and ContextVar

**Status:** ready-for-agent

- [ ] Reply-chain traversal using backwardLink pagination for full conversation history
- [ ] Sliding-window recent messages as supplementary context
- [ ] No mechanical pre-filter — LLM judges relevance of each retrieved message
- [ ] Attachments as inline previews; full content via two-phase broker fetch
- [ ] No redaction of retrieved content
- [ ] History injected as standalone user message with assistant ack separator for role alternation
- [ ] Retrieval identity bound to exact `conv_id` — no cross-conversation fan-out
- [ ] Forced marker test layer 1: API-level — marker present in correct conversation only
- [ ] Forced marker test layer 2: red marker — visible in origin group, absent in cross-group
- [ ] Forced marker test layer 3: dual-group cross-injection attempt → DENY
