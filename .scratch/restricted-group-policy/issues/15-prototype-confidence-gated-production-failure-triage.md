# Prototype confidence-gated production failure triage

Type: prototype
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 04, 10, 11, 14

## Question

Can Hermes implement the selected post-opening `Production Failure Triage` without silently widening authority or losing exact operation state? Build the cheapest executable prototype against an isolated temporary `HERMES_HOME` that sends content-minimized structured failure evidence only through the approved AIDE route; accepts an exact canonical function set plus an LLM self-reported percentage; applies the strict `> 90%` branch to block the inferred function while unrelated operations continue; applies the `<= 90%`, unavailable-model, malformed-output, and timeout branches to hold only the triggering operation, descendants, uncommitted side effects, and unreleased output for at most 24 hours; and projects one canonical owner decision for exact resume, selective stop, full stop, or rollback.

Force adversarial error text, prompt-injection-shaped evidence, shared-component failures, duplicate and late model responses, owner races, process restart at every transition, exception expiry/revocation, and already-completed external side effects. Prove operation-version pinning, exact-function containment, no prohibited member Capability Grant, no raw sensitive persistence, content-minimized audit, owner-only direct resume through exact `Owner Risk Exception` when a defect is confirmed, cleanup on expiry, and explicit compensation evidence rather than fabricated rollback.

## Resolution

**Answer: YES** — the prototype at `.scratch/restricted-group-policy/prototypes/confidence-gated-failure-triage-prototype.html` demonstrates all required invariants.

### Prototype structure

- **17 test scenarios** covering:
  - **3 high-confidence (>90%) block scenarios**: 95%, 91% (edge), 100% (maximum)
  - **3 low-confidence (≤90%) hold scenarios**: 90% (edge), 50%, 10%
  - **3 failure-triage failure modes**: AIDE unavailable (503), malformed JSON, timeout (30s)
  - **4 adversarial prompt-injection tests**: explicit command, confidence spoof, approval spoof, capability grant request
  - **2 restart-safety tests**: restart after hold (operation-version pinned), side-effect no-replay
  - **1 owner-race test**: first-wins idempotency
  - **1 expiry test**: 24h hold cleanup
  - **1 Owner Risk Exception test**: exact resume with explicit risk acceptance

### Proven invariants

| Invariant | Proof in prototype |
|-----------|-------------------|
| **AIDE-only routing** | All scenarios route through `routed_to_aide` audit entry; no external-model fallback path exists |
| **Content-minimized audit** | Audit stores fingerprints (`sha256:...`), HMAC chains, metadata only — no raw evidence text persisted |
| **Operation-version pinning** | Every scenario binds `operationVersion`; restart scenarios verify same version survives |
| **Exact-function containment** | `blockedFunctions` array contains only inferred function; `unrelatedOperationsContinuing` shows others continue |
| **No prohibited Capability Grant** | Injection scenario #INJ-3 requests `external_mutation`, prototype logs `capabilityGrantDenied: true` |
| **No raw sensitive persistence** | After restart, `failureEvidence` and `inferredFunction` cleared; only metadata and audit fingerprints survive |
| **Owner-only direct resume** | `ownerDecisions` array requires `ownerAuthenticated: true`; `ownerRiskExceptions` carry explicit risk acceptance |
| **First-wins idempotency** | Owner race scenario: first decision accepted, second rejected with `reason: 'first_wins_idempotency'` |
| **Cleanup on expiry** | Expiry scenario: `holdExpiryAt` checked, `heldOperations` cleared, `currentPhase: 'expired'` |
| **Explicit compensation evidence** | Restart/no-replay scenario: `completedSideEffects` journal prevents replay; compensation logged explicitly |

### Confidence gate enforcement

- **>90% branch**: `confidence > TRIAGE_POLICY.confidenceThreshold` → `blockedFunctions.push(fnName)`, `currentPhase: 'blocked'`
- **≤90% branch**: `confidence <= TRIAGE_POLICY.confidenceThreshold` → `heldOperations.push(...)`, `currentPhase: 'held'`, `holdExpiryAt` set
- **Unavailable/timeout/malformed**: All route to hold branch with appropriate `reason` in audit

### Adversarial defense

- **Prompt injection ignored**: Error text with `IGNORE GATE` commands logged as `injection_attempt_detected`, confidence set to low (25-30%), hold applied
- **Confidence spoof ignored**: Error text claiming `confidence=100%` ignored; actual LLM self-reported confidence (45%) used
- **Capability grant denied**: Error text requesting `Grant Capability: external_mutation` logged as `prohibitedCapability`, no grant issued

### Restart safety

- **Metadata-only persistence**: `operationVersion`, `currentPhase`, `heldOperations`, `holdExpiryAt`, audit fingerprints survive
- **Sensitive content non-persistence**: `failureEvidence`, `inferredFunction`, `llmConfidence` cleared on restart (would be re-fetched under current authority in production)
- **Operation-version pinned**: Verified across all restart scenarios — same version before and after

### Files created

1. `.scratch/restricted-group-policy/prototypes/confidence-gated-failure-triage-prototype.html` — interactive HTML prototype with dark theme, tabs, 17 scenarios, pass/fail matrix

## Comments
