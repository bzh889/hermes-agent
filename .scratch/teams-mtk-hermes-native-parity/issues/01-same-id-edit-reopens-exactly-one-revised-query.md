# 01 — Same-ID edit reopens exactly one revised Query

**What to build:** When a Teams user edits an already-processed query without changing its remote message identity, Hermes must process the complete corrected body as exactly one revised agent turn. Unchanged poll repeats stay silent, and overlapping poll/WebSocket fetches must not create duplicate answers.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

## Source of truth

This ticket implements only the inbound-edit vertical slice defined by the existing OpenSpec change:

- [Proposal](../../../openspec/changes/teams-mtk-hermes-native-parity/proposal.md)
- [Design §12](../../../openspec/changes/teams-mtk-hermes-native-parity/design.md)
- [Formal specification](../../../openspec/changes/teams-mtk-hermes-native-parity/specs/teams-mtk-native-parity/spec.md)
- [Research](../../../openspec/changes/teams-mtk-hermes-native-parity/research.md)
- [E2E registry](../../../openspec/changes/teams-mtk-hermes-native-parity/e2e_test_registry.md)

Do not create or reinterpret a second specification in this ticket.

## Acceptance criteria

- [x] The SDK-normalized representation retains the raw message identity, content, properties, explicit version, and edit-time candidate without discarding their original value types.
- [x] Revision state is bounded and isolated by the exact conversation/message identity pair. It records a normalized explicit revision candidate when available and a deterministic hash of canonical content.
- [x] An unseen identity follows the normal new-message path; an unchanged revision/hash repeat starts no turn; a changed explicit revision candidate or canonical-content hash dispatches one complete revised body.
- [x] The new revision state is recorded atomically before dispatch, so overlapping polling and WebSocket catch-up cannot dispatch the same revision twice.
- [x] Equal message IDs in different conversations cannot share revision state or suppress one another.
- [x] Existing authorization, outbound ownership, mention, blocked-keyword, and other inbound policy gates still apply before revision dispatch.
- [x] If an edited bot-owned message loses its sender property, conversation-scoped outbound ownership or authoritative sender metadata still prevents it from becoming a human revision echo.
- [x] Deterministic tests assert public normalized output and observed dispatch behavior rather than helper existence, source text, or an attempted HTTP call.
- [x] The named real-gateway E2E `inbound-edit-revision-reopens-query` uses a real human-originated message, waits for the initial completed turn, edits the same remote identity, and performs canonical service read-back after the poll/WebSocket overlap window.
- [x] That E2E independently proves revision dispatch `= 1`, duplicate `= 0`, complete edited-body match, no replay of the original body, and cleanup residue `= 0`.
- [x] Every remote side effect is cleaned in `finally` by exact returned identity or a unique marker; malformed send results trigger discovery cleanup, and cleanup failure fails this E2E item.
- [x] Logs and retained test evidence contain only sanitized status, structural aliases, lengths, and hashes—never organization identities, message bodies, tenant hosts, or credentials.

## Out of scope

- Exact native quoted-reply source retrieval and normalized reply context; issue 02 owns that slice.
- Outbound `reply_to` native delivery and duplicate-safe degradation; issue 03 owns that slice.
- Graph change notifications, a second inbound source, Bot Framework migration, or WebSocket soak-policy work.
- Persisting raw conversation, message, or user identities in repository artifacts.

## P0 completion note

Completing this ticket does not by itself complete Query Revision and Native Reply P0. Overall completion still requires all three named E2E verdicts to remain independent, the complete named real-gateway suite to pass, and the canonical repository test wrapper to pass on the final tree.
