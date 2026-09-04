# 34 — Exact-group semantic history retrieval

**What to build:** History retrieval for a restricted group conversation uses reply-chain traversal (backwardLink pagination) first, then sliding-window recent messages, to gather context. There is no mechanical pre-filter — the LLM judges the relevance of each retrieved message. Attachments appear as inline previews; full content requires a two-phase broker fetch (preview → broker). No redaction is applied. History is injected as a standalone user message followed by an assistant ack separator, preserving role alternation and prompt caching. The retrieval identity is bound to the exact `conv_id` from the OriginEgressBinding — no cross-conversation fan-out. Three-layer forced marker tests verify zero cross-conversation leakage: (1) API-level marker present in the correct conversation only; (2) red marker visible in origin group but absent in cross-group; (3) dual-group cross-injection attempt denied.

**Blocked by:** 24 — Origin binding module and ContextVar

**Status:** closed

- [x] Reply-chain traversal using backwardLink pagination for full conversation history
- [x] Sliding-window recent messages as supplementary context
- [x] No mechanical pre-filter — LLM judges relevance of each retrieved message
- [x] Attachments as inline previews; full content via two-phase broker fetch
- [x] No redaction of retrieved content
- [x] History injected as standalone user message with assistant ack separator for role alternation
- [x] Retrieval identity bound to exact `conv_id` — no cross-conversation fan-out
- [x] Forced marker test layer 1: API-level — marker present in correct conversation only
- [x] Forced marker test layer 2: red marker — visible in origin group, absent in cross-group
- [x] Forced marker test layer 3: dual-group cross-injection attempt → DENY

## Comments

### Resolution — 2026-09-03

**Implemented:** `gateway/restricted_history.py` — exact-group semantic history retrieval.
- `HistoryMessage`, `HistoryResult` dataclasses
- `retrieve_history(fetch_fn, conv_id, binding)` — two-stage: reply-chain traversal (backwardLink) → sliding-window supplement
- `CrossConversationError` — guards conv_id mismatch
- `format_history_for_injection(result)` → `(user_message, assistant_ack)` for role-alternation-safe injection
- No redaction, no pre-filter — all messages returned for LLM relevance judgment

**Tests:** `tests/gateway/test_restricted_history.py` — 14 tests, 3.34s
- Reply-chain traversal, sliding-window, cross-conversation guard, no redaction, no pre-filter, format injection, 3-layer forced marker tests
**Verification:** 14/14 passed, 0 failed
