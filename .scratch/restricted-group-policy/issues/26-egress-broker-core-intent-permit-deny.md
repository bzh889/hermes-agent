# 26 — Egress Broker core: intent, permit, deny

**What to build:** A Core-owned Egress Broker module that sits between every outbound emitter and the adapter edge. When a restricted task attempts an outbound operation, the Broker validates: delivery purpose (must be a Restricted Logical Delivery purpose — reply, stream, edit, send_message text/media, derived media), origin equality (destination matches the OriginEgressBinding), and policy revision (must match current). Valid calls receive a one-use permit bound to the exact operation, destination, route, payload fingerprint, and policy revision. Invalid calls are denied with a structured reason. The Broker persists an `EgressIntent` record before any side effect. Unit tests prove permit one-use enforcement, stale-revision denial, origin-mismatch denial, and delivery-purpose classification.

**Blocked by:** 25 — Restricted Group policy config and activation gate

**Status:** ready-for-agent

- [ ] Egress Broker module with `request_permit(operation, destination, route, payload, binding)` interface
- [ ] Delivery purpose classifier: Restricted Logical Delivery purposes ALLOW; reactions, loop mutations, cron fan-out, Kanban notifications DENY
- [ ] Origin equality check: destination must match binding's conversation/thread
- [ ] Policy revision check: stale revision fails closed
- [ ] One-use permit: second use of the same permit is denied
- [ ] Permit binds exact operation, destination, route, payload fingerprint, and policy revision
- [ ] EgressIntent persisted to audit DB before the adapter is invoked
- [ ] Unit test: valid permit → ALLOW
- [ ] Unit test: permit reuse → DENY
- [ ] Unit test: stale revision → DENY
- [ ] Unit test: origin mismatch (cross-group destination) → DENY
- [ ] Unit test: denied delivery purpose (reaction) → DENY
