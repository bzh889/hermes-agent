# Tasks — Restricted Group Policy

## Phase 1 — Origin Binding

- [ ] 24 — Origin binding module and ContextVar (no blockers)
- [ ] 25 — Restricted Group policy config and activation gate (blocked by 24)

## Phase 2 — Egress Broker Core

- [ ] 26 — Egress Broker core: intent, permit, deny (blocked by 25)
- [ ] 27 — Audit chain: HMAC-linked intent/outcome records (blocked by 26)

## Phase 3 — Adapter Wiring (E2E)

- [ ] 28 — Wire all emitter paths through the Egress Broker (blocked by 27)
- [ ] 29 — Egress escape matrix adversarial tests, 17 rows (blocked by 28)

## Phase 4 — CQ Read Broker + Sandbox

- [ ] 30 — CQ Read Broker: seven read-only operations (blocked by 28)
- [ ] 31 — Disposable per-group execution sandbox (blocked by 25)

## Phase 5 — Policy, Approval, History, Learning, Triage (E2E)

- [ ] 32 — Model-routing gate: AIDE-only authorizeAndInvoke (blocked by 26)
- [ ] 33 — Durable approval state and restart-safe resume (blocked by 27, 31)
- [ ] 34 — Exact-group semantic history retrieval (blocked by 24)
- [ ] 35 — Confidence-gated triage, learning, CQ export consistency, and production rollout (blocked by 29, 30, 32, 33, 34)

## Dependency graph

```
24 ──┬── 25 ──┬── 26 ──┬── 27 ── 28 ──┬── 29 ──┐
     │         │        │              │         │
     │         │        ├── 32 ───────┤         ├── 35
     │         │        │              │         │
     │         └── 31 ──┼── 33 ───────┤         │
     │                  │                        │
     └── 34 ────────────┴────────────────────────┘
     │                                           │
     └───────────────────────────────────────────┘
                                30 ──────────────┘
```

Frontier (unblocked, ready-for-agent): **24**
