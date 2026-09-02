# Decide implementation sequence and behavioral test architecture

Type: grilling
Status: closed
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: (none)

## Question

Given all 17 closed design/prototype decisions (capability taxonomy, owner approval, CQ read broker, disposable execution, origin-bound egress, model-routing gate, audit, learning, durable resume, confidence-gated triage, CQ export consistency, egress matrix fixtures, semantic history), what is the correct implementation sequence across the codebase, and what behavioral test architecture (unit, integration, adversarial, E2E layers) will prove each enforcement seam before production activation? Decide build order dependencies, which existing files/modules change first, where the new enforcement boundary code lives, how behavioral tests are layered, and what the coverage gates are before moving from one implementation phase to the next.

## Comments

### Resolution — 2026-09-01

**Decisions (7 items):**

1. **Implementation start point** — Begin with origin identity binding (SessionSource / ContextVar). Without correct origin identity, the broker cannot verify and adapter wiring has no meaning. Build order: identity binding → broker core → adapter wiring.

2. **Module placement** — Create a new module `gateway/restricted_origin.py` for `OriginEgressBinding` and related classes. This lives at the gateway layer alongside `session_context.py` because the binding action occurs at gateway ingress (when a message arrives from Teams).

3. **Test layering** — Four layers: (1) unit — pure logic tests; (2) integration — multi-module assembly tests; (3) adversarial — cross-conversation/cross-group/cross-route escape attempt tests; (4) live E2E — real Teams group send/receive tests.

4. **Phase gate** — Strict layered progression: unit all-pass → integration all-pass → adversarial all-pass → E2E. No phase skips until the current layer is fully green.

5. **Implementation phases** — Five phases:
   - **Phase 1**: Origin binding (`gateway/restricted_origin.py`, `OriginEgressBinding`, ContextVar integration with `session_context.py`)
   - **Phase 2**: Egress Broker core (intent persistence, permit issuance, one-use consumption, policy recheck)
   - **Phase 3**: Adapter wiring (all emitter paths: reply, stream/progress, edit, send_message, reaction, TTS/media, cron, delegation, Kanban, webhook/API)
   - **Phase 4**: CQ Read Broker + disposable execution sandbox
   - **Phase 5**: Approval, audit, durable resume, learning, confidence-gated triage, semantic history injection

6. **E2E placement** — E2E runs only at Phase 3 (adapter wiring — verify each emitter path against real Teams) and Phase 5 (full integration — verify end-to-end policy enforcement). Phases 1, 2, 4 run unit + integration + adversarial only. This aligns with ticket 18's egress escape matrix fixtures (Phase 3) and ticket 19's full E2E (Phase 5).

7. **Coverage gate** — Each phase must pass all four test layers (where applicable) before advancing to the next phase. The gate is per-layer, not per-feature: all unit tests for the phase must pass before integration tests begin, all integration before adversarial, all adversarial before E2E.
