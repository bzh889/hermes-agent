# 02 — Native quoted reply supplies exact full source context

**What to build:** When a Teams user revises a request by sending a native reply to a long source message, Hermes must resolve the exact related message and receive the complete source plus the new reply body through the existing normalized reply context. A truncated display quote must never masquerade as the complete source.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Source of truth

This ticket implements only the inbound native-reply context vertical slice defined by the existing OpenSpec change:

- [Proposal](../../../openspec/changes/teams-mtk-hermes-native-parity/proposal.md)
- [Design §12](../../../openspec/changes/teams-mtk-hermes-native-parity/design.md)
- [Formal specification](../../../openspec/changes/teams-mtk-hermes-native-parity/specs/teams-mtk-native-parity/spec.md)
- [Research](../../../openspec/changes/teams-mtk-hermes-native-parity/research.md)
- [E2E registry](../../../openspec/changes/teams-mtk-hermes-native-parity/e2e_test_registry.md)

Do not create or reinterpret a second specification in this ticket.

## Acceptance criteria

- [ ] SDK normalization retains native reply relation metadata and safely accepts raw properties represented as either an object or a JSON string, plus quoted-message relations represented as either a list or an encoded list.
- [ ] Normalization and relation parsing do not rewrite or discard the user-visible reply body.
- [ ] Source selection prefers `replyChainMessageId` and corroborates it against `qtdMsgs` message relations and the blockquote relation when present.
- [ ] Relation disagreements produce sanitized diagnostics and never authorize selecting an unrelated source message.
- [ ] A known source identity is retrieved through the existing authenticated conversation-message transport using the exact conversation and source-message identity.
- [ ] On successful exact retrieval, the existing normalized MessageEvent reply context contains the source identity and complete canonical source text while preserving the new reply body as the current user request.
- [ ] A shorter display quote remains presentation-only and is never promoted as complete reply context.
- [ ] If exact retrieval fails, the relation identity may remain available, but complete reply text stays unavailable or explicitly partial; the adapter does not fabricate full context from the preview.
- [ ] Deterministic tests cover compatible metadata shapes, relation corroboration/disagreement, exact-fetch success/failure, and the resulting public MessageEvent context.
- [ ] The named real-gateway E2E `quoted-reply-full-context-revises-query` creates and canonically reads back a human-originated source longer than the display preview, with a terminal sentinel outside that preview, then submits a native human reply containing the revised request.
- [ ] That E2E independently proves an exact relation match, direct-fetch full-source hash match, use of both the terminal sentinel and revised reply body by the gateway/agent result, `preview-only = false`, and cleanup residue `= 0`.
- [ ] Every remote side effect is cleaned in `finally` by exact returned identity or a unique marker; malformed send results trigger discovery cleanup, and cleanup failure fails this E2E item.
- [ ] Logs and retained test evidence contain only sanitized status, structural aliases, lengths, and hashes—never organization identities, message bodies, tenant hosts, or credentials.

## Out of scope

- Same-ID edit revision tracking and exactly-once dispatch; issue 01 owns that slice.
- Outbound Hermes `reply_to` native delivery; issue 03 owns that slice.
- Making Graph `replyToId`, Graph subscriptions, or a public callback endpoint a required dependency.
- Claiming that the private Skype reply envelope is stable across tenants or guaranteed by Microsoft.

## P0 completion note

Completing this ticket does not by itself complete Query Revision and Native Reply P0. Overall completion still requires all three named E2E verdicts to remain independent, the complete named real-gateway suite to pass, and the canonical repository test wrapper to pass on the final tree.
