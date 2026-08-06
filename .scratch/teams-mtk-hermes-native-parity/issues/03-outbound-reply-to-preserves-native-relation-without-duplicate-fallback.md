# 03 — Outbound reply_to preserves native relation without duplicate fallback

**What to build:** When Hermes' normal delivery path receives a reply target, the resulting Teams message must use the SDK's native reply operation and remain attached to that target. A flat send is allowed only when native reply is known to be unavailable before any remote side effect begins; an indeterminate native outcome must never trigger a duplicate flat reply.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

## Source of truth

This ticket implements only the outbound native-reply vertical slice defined by the existing OpenSpec change:

- [Proposal](../../../openspec/changes/teams-mtk-hermes-native-parity/proposal.md)
- [Design §12](../../../openspec/changes/teams-mtk-hermes-native-parity/design.md)
- [Formal specification](../../../openspec/changes/teams-mtk-hermes-native-parity/specs/teams-mtk-native-parity/spec.md)
- [Research](../../../openspec/changes/teams-mtk-hermes-native-parity/research.md)
- [E2E registry](../../../openspec/changes/teams-mtk-hermes-native-parity/e2e_test_registry.md)

Do not create or reinterpret a second specification in this ticket.

## Acceptance criteria

- [x] When `reply_to` is supplied, the normal adapter delivery path delegates to the SDK native reply operation instead of discarding the target and using a normal send.
- [x] A successful native reply recovers the remote message identity, including a response that supplies `OriginalArrivalTime` without `id`, and records exact conversation-scoped outbound ownership.
- [x] Canonical service read-back of a successful native reply contains reply-chain, quoted-message, or equivalent native relation data that points to the requested target.
- [x] A flat send is attempted at most once and only when the SDK/native reply operation is unavailable or explicitly unsupported before a remote side effect can begin.
- [x] A permitted flat degradation returns an observable sanitized result and log signal stating that the native relation was not preserved.
- [x] If timeout, exception, or another failure occurs after native delivery may have reached the remote service, the adapter reports delivery uncertainty and does not issue a second flat send.
- [x] Deterministic tests independently cover native success, explicit pre-send unavailability, and post-start indeterminate outcome, including send counts and ownership behavior.
- [x] The named real-gateway E2E `reply-to-native-thread-roundtrip` creates and canonically reads back a controlled target, invokes the formal Hermes delivery path with `reply_to`, and proves the resulting native relation points to that target.
- [x] The same named E2E includes an explicitly forced pre-send-unavailable case and proves exactly one flat message plus a matching sanitized degradation signal.
- [x] The E2E also proves that an indeterminate native outcome does not produce a second flat send, reports duplicate `= 0`, and finishes with cleanup residue `= 0`.
- [x] Every remote side effect is cleaned in `finally` by exact returned identity or a unique marker; malformed send results trigger discovery cleanup, and cleanup failure fails this E2E item.
- [x] Logs and retained test evidence contain only sanitized status, structural aliases, lengths, and hashes—never organization identities, message bodies, tenant hosts, or credentials.

## Verification evidence

- 2026-08-06: targeted real-gateway `reply-to-native-thread-roundtrip` passed with `native_relation=1`, `flat_count=1`, observable degradation, delivery uncertainty, duplicate `= 0`, and cleanup residue `= 0`.
- 2026-08-06: deterministic E2E-contract tests passed `52/52`; media transport tests passed `17/17` after duplicate-safe adaptive-card transport hardening.
- 2026-08-06: the canonical repository wrapper passed all seven directly impacted P0 files, `260/260`; the separately modified reliability file then passed `48/48`, for `308/308` final impacted tests.
- 2026-08-06: the complete sequential named real-gateway suite passed `29/29` without `--only`; native success, pre-send degradation, and indeterminate outcome remained separately observable.
- 2026-08-06: a full-repository wrapper attempt is independently blocked by isolated, out-of-diff Windows image-path failures in `tests/agent/test_image_routing.py` (`7 failed, 98 passed, 1 skipped`); no full-repository-green claim is made.
- 2026-08-06: final gateway restart/read-back started PID 19312 after the production source mtimes; 104 fresh startup lines contained Teams connect/poll and API/gateway readiness events with zero ERROR/CRITICAL/Traceback lines.

## Out of scope

- Inbound same-ID revision dispatch; issue 01 owns that slice.
- Inbound exact-source reply context; issue 02 owns that slice.
- Treating every general send failure as authorization to issue a flat fallback.
- Bot Framework migration, a public callback endpoint, Graph reply replacement, native audio/video, capability-command dispatch, forwarding authorization, or WebSocket soak-policy work.

## P0 completion note

Completing this ticket does not by itself complete Query Revision and Native Reply P0. Overall completion still requires all three named E2E verdicts to remain independent, the complete named real-gateway suite to pass, and the canonical repository test wrapper to pass on the final tree.
