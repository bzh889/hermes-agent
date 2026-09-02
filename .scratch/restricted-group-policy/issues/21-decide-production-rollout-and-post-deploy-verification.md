# Decide production rollout and post-deploy verification plan

Type: grilling
Status: closed
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: (none)

## Question

After implementation and adversarial E2E pass, what is the exact production rollout plan: which existing Teams group becomes the production Monitor Group, what harmless post-opening probe data verifies each enforcement seam in production, what compensation triggers fire on violation, and what is the post-deploy observation window duration and exit criteria? Also decide any remaining non-egress adversarial E2E matrix rows not covered by the egress escape matrix (ticket 18), and whether the non-egress matrix needs its own fixture set or reuses egress fixtures.

## Comments

### Resolution — 2026-09-01

**Decisions (6 items):**

1. **Production Monitor Group** — Use the existing test group `19:cbdcf6224c48469ea048147752ed92d9@thread.v2` directly as the production Monitor Group. No new group is created; the test group transitions to production status.

2. **Post-opening probe design** — Each enforcement seam gets its own dedicated probe:
   - Origin binding: send a message with a mismatched group ID; assert the operation is denied.
   - Egress Broker: attempt a send without a valid permit; assert denial.
   - Adapter wiring: attempt a cross-group destination send; assert the message does not arrive at the wrong destination.
   - CQ Read Broker: attempt a write/mutation operation through the read-only broker; assert rejection.
   Each probe is independent and targets one seam — no shared probe script.

3. **Compensation trigger** — On violation detection, the triggering operation is automatically held (paused, not denied), and the owner receives a notification. The policy continues running — only the violating operation is held. The owner decides whether to resume, stop, or rollback.

4. **Observation window** — No fixed duration. The post-deploy observation window ends when 30 consecutive operations complete without any violation. Each operation counts only if it exercises at least one enforcement seam.

5. **Non-egress adversarial E2E matrix** — A new ticket (22) will be created to define the non-egress adversarial matrix, parallel to the egress escape matrix (ticket 18). It covers: CQ broker unauthorized write attempts, cross-group capability leakage, model-routing gate bypass attempts, and capability descriptor spoofing. This ticket's resolution creates ticket 22 as a child of the map.

6. **Non-egress matrix fixtures** — Reuse ticket 18's contract-test adapter approach: paths that can't be exercised with real systems use contract-test adapters that simulate the unsupported dimension. This gives the non-egress matrix the same fixture discipline as the egress matrix without requiring every real system to be present.

**Newly surfaced ticket:** 22 — Define non-egress adversarial E2E matrix fixtures (created by this resolution).
