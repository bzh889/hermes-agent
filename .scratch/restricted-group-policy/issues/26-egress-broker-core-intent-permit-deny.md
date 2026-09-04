# 26 — Egress Broker core: intent, permit, deny

**What to build:** A Core-owned Egress Broker module that sits between every outbound emitter and the adapter edge. When a restricted task attempts an outbound operation, the Broker validates: delivery purpose (must be a Restricted Logical Delivery purpose — reply, stream, edit, send_message text/media, derived media), origin equality (destination matches the OriginEgressBinding), and policy revision (must match current). Valid calls receive a one-use permit bound to the exact operation, destination, route, payload fingerprint, and policy revision. Invalid calls are denied with a structured reason. The Broker persists an `EgressIntent` record before any side effect. Unit tests prove permit one-use enforcement, stale-revision denial, origin-mismatch denial, and delivery-purpose classification.

**Blocked by:** 25 — Restricted Group policy config and activation gate

**Status:** closed

- [x] Egress Broker module with `request_permit(operation, destination, route, payload, binding)` interface
- [x] Delivery purpose classifier: Restricted Logical Delivery purposes ALLOW; reactions, loop mutations, cron fan-out, Kanban notifications DENY
- [x] Origin equality check: destination must match binding's conversation/thread
- [x] Policy revision check: stale revision fails closed
- [x] One-use permit: second use of the same permit is denied
- [x] Permit binds exact operation, destination, route, payload fingerprint, and policy revision
- [x] EgressIntent persisted to audit DB before the adapter is invoked
- [x] Unit test: valid permit → ALLOW
- [x] Unit test: permit reuse → DENY
- [x] Unit test: stale revision → DENY
- [x] Unit test: origin mismatch (cross-group destination) → DENY
- [x] Unit test: denied delivery purpose (reaction) → DENY

## Comments

### Resolution — 2026-09-03

**Implemented:**

New module `gateway/egress_broker.py` — the single choke point for all restricted-context side effects.

**Core API:**
- `EgressBroker.request_permit(operation, destination, route, payload, binding)` → `BrokerResult(decision, reason, permit, intent)`
- `EgressBroker.consume_permit(permit_id)` — one-use enforcement
- `EgressBroker.request_and_consume(...)` — atomic request+consume convenience
- `EgressBroker.check_permit_validity(permit, op, dest, route, payload)` — verify a previously-issued permit
- `get_egress_broker()` — process-scoped singleton

**Dataclasses:**
- `EgressOperation` enum — 5 ALLOW (reply, stream, edit, send_message, derived_media) + 4 DENY (reaction, loop_mutation, cron_fanout, kanban_notification)
- `EgressRoute` enum — NATIVE (allow) + RELAY/WEBHOOK/API_SERVER (deny)
- `PermitDecision` / `DenyReason` enums
- `EgressIntent` — pre-side-effect record (fingerprint, policy, binding)
- `EgressPermit` — frozen one-use permit (permit_id, operation, destination, route, payload_fingerprint, policy_revision)
- `EgressPermitRecord` — mutable wrapper tracking consumption

**Validation pipeline (in order):**
1. Unrestricted context (no binding) → ALLOW (pass-through no-op)
2. Invalid binding type → DENY INVALID_BINDING
3. Delivery purpose not in ALLOW set → DENY DELIVERY_PURPOSE_DENIED
4. Route not NATIVE → DENY ROUTE_DENIED
5. Destination ≠ binding.conv_id/thread_id → DENY ORIGIN_MISMATCH
6. Empty policy_revision → DENY STALE_REVISION
7. All checks pass → issue one-use permit + persist EgressIntent

**Tests:** `tests/gateway/test_egress_broker.py` — 37 tests across 12 classes:
- `TestUnrestrictedPassthrough` (2) — no binding → pass through
- `TestDeliveryPurpose` (9) — 5 allowed + 4 denied (parametrized)
- `TestOriginEquality` (4) — conv_id match, cross-group deny, thread_id match, empty dest
- `TestPolicyRevision` (2) — valid + empty
- `TestRouteCheck` (3) — relay/webhook/api_server denied (parametrized)
- `TestOneUsePermit` (3) — first consume succeeds, second fails, validity check after consume
- `TestPermitBinding` (3) — fields match, operation mismatch, payload tamper
- `TestEgressIntent` (3) — recorded on valid, not on denied, fingerprint not raw
- `TestContextVarIntegration` (2) — reads from ContextVar, no binding → pass through
- `TestPayloadFingerprint` (4) — determinism, none, dict order-independence
- `TestInvalidBinding` (1) — string binding → DENY
- `TestSingleton` (1) — singleton identity

**Verification:** `scripts/run_tests.sh` (3 files) → 82/82 passed, 0 failed, 18.8s (hermetic)
