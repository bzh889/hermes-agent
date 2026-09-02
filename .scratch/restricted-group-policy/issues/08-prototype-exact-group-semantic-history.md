# Prototype exact-group semantic history retrieval

Type: prototype
Status: closed
Assigned: dev
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

How should Restricted Group follow-up context retrieve semantically relevant original Teams messages from only the exact bound conversation, with no time limit and no Hermes memory, Mem0, PKB, private session history, or cross-group content? Prototype retrieval over real-shaped long-history fixtures using the existing Teams MTK exact-conversation fetch primitive, then decide identity binding, pagination, attachment treatment, redaction, relevance thresholds, prompt-cache-safe injection, and forced marker tests that prove zero cross-conversation leakage.

## Comments

### Resolution — 2026-09-01

**Decisions (7 items):**

1. **Retrieval scope** — Combine reply-chain traversal (follow the current message's reply chain upward) with a sliding window of the most recent N messages. If the reply chain + recent window don't cover what the question needs, paginate further back via `_fetch_messages(conv_id, limit=None)` backwardLink pagination. No hard time limit. Start small (reply chain + recent ~100), expand only when needed.

2. **Relevance selection** — No mechanical pre-filtering (no keyword/regex/embedding pre-screen). Deliver the raw retried messages to the LLM and let the LLM itself judge which are relevant to the current question. Rationale: the group's history is in-scope content; mechanical filtering risks dropping relevant context.

3. **Attachment treatment** — Two-phase: (a) attachments are included with the message as inline text representation (preview/filename/metadata). (b) If the LLM judges that it needs the full attachment content, it requests the content through the existing CQ Read Broker (ticket 06) — the same credential-owning broker, not direct URL access. No raw SharePoint URLs are given to the LLM; the broker owns the URL and returns content.

4. **Redaction** — No redaction. History is from the same Restricted Group the current speaker is in; members already see this content. No masking of names, CR IDs, or other content.

5. **Prompt-cache-safe injection** — Inject history as a standalone user message placed *before* the current user message, with a one-line assistant ack message ("以下是歷史上下文") between them to preserve strict role alternation. Sequence per turn:
   - `user`: `[歷史上下文] <retrieved messages>`
   - `assistant`: `以下是歷史上下文。`
   - `user`: `<current message>`
   This preserves prompt cache because the system prompt is byte-stable; the history is injected into the turn-specific message sequence, not the system prompt.

6. **Identity binding** — History fetch is bound to the exact `conversation_id` of the incoming message. The adapter's existing `_fetch_messages(conv_id, limit)` / `_fetch_messages_by_date(conv_id, ...)` / `_fetch_exact_reply_source(conversation_id, message_id)` already take an explicit `conv_id` — no global search, no multiple-conversation fan-out. `search_all_conversations()` (which iterates all `_conv_ids`) is NOT used for restricted-group history.

7. **Forced marker tests (zero cross-conversation leakage)** — Three layers:
   - **API-level**: Assert `_fetch_messages` only accepts the bound `conv_id`; passing a different `conv_id` must not return data from the wrong conversation.
   - **Red marker**: Insert a unique UUID-tagged message into group A; query from group B; assert the UUID does not appear in the response.
   - **Dual-group cross**: Set up two restricted group fixtures, inject distinct keywords into each, and verify each group's response only contains its own keywords.
   All tests must fail-closed: no leakage, no cross-contamination.

**Prototype assets:** This is a decision-only resolution (no code artifact committed). The prototype design is documented above for implementation tickets to follow.
