# Implement the origin-bound Egress Broker

Type: task
Status: closed
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 09, 11

## Resolution — 2026-09-03

**Superseded by tracer-bullet tickets 24–28.**

The origin-bound Egress Broker scope defined in this ticket is fully implemented across five tracer-bullet tickets:

- **24** — `OriginEgressBinding` frozen dataclass + ContextVar (`gateway/restricted_origin.py`)
- **25** — Restricted Group policy config + activation gate (`gateway/restricted_group_gate.py`)
- **26** — Egress Broker core: permit/deny/intent (`gateway/egress_broker.py`)
- **27** — Audit chain: HMAC-SHA256-linked SQLite WAL (`gateway/audit_chain.py`)
- **28** — All emitter paths wired through Broker (`gateway/egress_wiring.py`)

285 tests across 12 test files, all passing.

## Question

Implement the resolved Origin-Bound Egress contract as the sole outbound side-effect boundary for every Restricted Task. Add immutable origin binding, durable Egress Intent reconciliation, one-use permits, current-policy recheck at permit consumption, Requested Artifact Snapshot and Derived Media Delivery handling, and fail-closed adapter/relay/plugin enforcement. Extend `SessionSource`, session ContextVars, execution authority, and durable cron/delegation/process metadata with the immutable policy, origin, logical-platform, transport-platform, route, task, operation, and idempotency identities; process recovery must validate the original process identity and `host_start_time`, not PID alone. Wire every current reply, stream/progress/edit, explicit send/reaction/Loop, automatic media/TTS, relay, cron, delegated/background, Kanban, webhook/API, standalone-sender, and future registered emitter path without changing unrestricted owner behavior. Add behavior-level unit and integration coverage for exact-origin allow, same-origin hard-denied mutations, route/destination mismatch, relay-frame platform discrimination, concurrent cron/watchers without ContextVar or target cross-talk, revision races, stale-PID recovery, uncertain outcomes, and no append/reroute fallback; do not claim live E2E completion in this ticket.
