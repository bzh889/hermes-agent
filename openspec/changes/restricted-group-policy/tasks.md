# Tasks — Restricted Group Policy

## Phase 1 — Origin Binding

- [x] 24 — Origin binding module and ContextVar
- [x] 25 — Restricted Group policy config and activation gate

## Phase 2 — Egress Broker

- [x] 26 — Egress Broker core: intent, permit, deny
- [x] 27 — Audit chain: HMAC-linked intent/outcome records

## Phase 3 — Adapter Wiring

- [x] 28 — Wire all emitter paths through the Egress Broker
- [x] 29 — Egress escape matrix adversarial tests (17 rows)

## Phase 4 — CQ Broker + Sandbox

- [x] 30 — CQ Read Broker: seven read-only operations
- [x] 31 — Disposable per-group execution sandbox

## Phase 5 — Routing Gate + Approval + History + Rollout

- [x] 32 — Model-routing gate: AIDE-only authorizeAndInvoke
- [x] 33 — Durable approval state and restart-safe resume
- [x] 34 — Exact-group semantic history retrieval
- [x] 35 — Confidence-gated triage, learning, CQ export, production rollout
