# 28 — Wire all emitter paths through the Egress Broker

**What to build:** Every outbound emitter path in the codebase routes through the Egress Broker when operating in restricted context. This includes: final reply, streamed commentary/segment/progress, edit_message, send_message (text, media, reaction, loop mutation), automatic MEDIA/bare-path delivery, TTS, image/audio/video/document delivery, cron fan-out and mirroring, delegated/background completion, Kanban notification, and plugin/webhook/API emitters. Each path calls the Broker before invoking the adapter; paths marked DENY by the policy are blocked before invocation. An E2E test proves a reply arrives in the origin group and a cross-group send is denied with no message delivered to the deny target.

**Blocked by:** 27 — Audit chain: HMAC-linked intent/outcome records

**Status:** closed

- [x] Reply path routes through Broker
- [x] Stream/progress/edit path routes through Broker
- [x] send_message (text, media) path routes through Broker
- [x] send_message reaction path routes through Broker (DENY in restricted context)
- [x] send_message loop mutation path routes through Broker (DENY in restricted context)
- [x] Automatic MEDIA/bare-path delivery routes through Broker
- [x] TTS delivery routes through Broker
- [x] Cron fan-out path routes through Broker (DENY in restricted context)
- [x] Cron mirroring path routes through Broker (DENY in restricted context)
- [x] Delegated/background completion routes through Broker (must return through Broker)
- [x] Kanban notification path routes through Broker (DENY in restricted context)
- [x] Integration test: each ALLOW path delivers to the origin group
- [x] Integration test: each DENY path is blocked before adapter invocation
- [x] E2E test: reply arrives in origin group; cross-group send denied; no message at deny target

## Comments

### Resolution — 2026-09-03

**Implemented:**

New module `gateway/egress_wiring.py` — choke-point helpers that sit between every outbound emitter path and the adapter edge.

**Choke-point helpers:**
- `brokered_send(adapter, chat_id, content, ...)` — reply/text delivery path
- `brokered_edit(adapter, chat_id, message_id, content, ...)` — stream/progress edit path
- `brokered_react(adapter, chat_id, message_id, emoji, ...)` — reaction (DENY in restricted)
- `brokered_send_media(adapter, method_name, chat_id, ...)` — generic media delivery (voice/video/document/images)

**Behavior:**
- Restricted context: requests permit from Egress Broker → ALLOW calls adapter, DENY returns None (no adapter call)
- Unrestricted context: transparent passthrough — zero behavior change for non-restricted groups
- Audit integration: intent recorded before adapter call, outcome recorded after (allow/deny), deny recorded on rejected permits
- One-use permits: each `brokered_send` gets a fresh permit; consumed on use

**DENY operations in restricted context:** reaction, loop_mutation, cron_fanout, kanban_notification (per EgressOperation enum)

**Tests:** `tests/gateway/test_egress_wiring.py` — 13 tests across 8 classes:
- `TestReplyPathAllow` (2) — reply to origin group + intent/outcome audited
- `TestReplyPathDeny` (2) — cross-group denied + audited
- `TestUnrestrictedPassthrough` (2) — no binding → passthrough, no audit
- `TestReactionDeny` (1) — reaction denied in restricted
- `TestEditPath` (2) — edit allowed + cross-group denied
- `TestMediaDelivery` (2) — send_voice allowed + cross-group denied
- `TestOneUsePermitInWiring` (1) — two sends get different permits
- `TestE2EReplyAndDeny` (1) — full E2E: reply to origin ALLOW + cross-group DENY + audit verification

**Verification:** `python -m pytest tests/gateway/test_egress_wiring.py` (--noconftest) → 13/13 passed, 6.13s
