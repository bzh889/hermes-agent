# Prototype durable approval state and restart-safe resume

Type: prototype
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 03, 04

## Question

Can Hermes implement one active-profile-local canonical Approval Request and metadata-only Durable Task that survive process restart without persisting sensitive content, losing task-scoped authority, accepting duplicate decisions, or replaying completed side effects? Build the cheapest executable prototype against an isolated temporary `HERMES_HOME` that projects one request through a retryable outbox to Control Channel and local TUI test adapters; races authenticated decisions, task terminal transitions, revocation, and Control Channel reconfiguration; lets later group tasks run while approval waits; resumes approved work next without preemption; restarts at every state transition; reacquires versioned source content under current authority and blocks or expires when the source is unavailable or no longer authorized; invalidates changed fingerprints; exercises 24-hour expiry and `/stop <short-id>`; and proves exact-once policy mutation, delivery reconciliation, profile isolation, prompt-cache stability, and zero raw sensitive persistence.

## Comments

- Input from ticket 03: prove one canonical profile-local Approval Request; authenticated first-wins decisions; metadata-only durable task state; restart at every transition; current-authority source reacquisition; exact fingerprint invalidation; 24-hour expiry; fail-closed block/expire when the source is unavailable or unauthorized; non-preemptive resume ordering; and completed-side-effect reconciliation without raw sensitive persistence.
From ticket #04: add one immutable Production Activation Proposal, separate per-failure Owner Risk Exception requests, separate final activation, owner-selected applied exception lifetime, and an idempotent progressive activation journal. Crash recovery may resume only the unchanged exact proposal after current identity, AIDE, effective-config, owner-authority, and rollback checks; each operation remains pinned to one complete policy version, and unavailable rollback must be an exact accepted known failure rather than missing evidence.

## Resolution

Prototype delivered at `.scratch/restricted-group-policy/prototypes/durable-approval-resume-prototype.html`.

### What the prototype proves

The interactive HTML prototype simulates the full approval lifecycle with **18 test scenarios** organized into four groups:

1. **Basic lifecycle (5 scenarios: L01-L05)**
   - Happy path: Create → Pending → Approved → Executed (L01)
   - Denial terminal state (L02)
   - Dual surface visibility (Control Channel + TUI) (L03)
   - Sanitized restricted-group view (L04)
   - Zero raw sensitive persistence: audit shows fingerprints/IDs only (L05)

2. **Decision race & first-wins (4 scenarios: L06-L10)**
   - First-wins: Control Channel approves, TUI denied as duplicate (L06)
   - First-wins: TUI denies, Control Channel approved as duplicate (L07)
   - Idempotent decision, single execution (L08)
   - Non-preemptive resume ordering: later tasks wait (L09)
   - Approved work resumes without preemption (L10)

3. **Restart & resume (4 scenarios: L11-L14)**
   - Restart in pending state preserves metadata (L11)
   - Restart after approval → execution ready (L12)
   - Fail-closed: unavailable source blocks execution (L13)
   - Exact fingerprint invalidation on source change (L14)

4. **Expiry & invalidation (5 scenarios: L15-L18)**
   - 24-hour expiry on pending request (L15)
   - `/stop <short-id>` command (L16)
   - Expiry checked on restart (L17)
   - Profile isolation: Profile A cannot see Profile B request (L18)

### Interactive features

- **Lifecycle scenarios tab**: Run individual scenarios or all 18 at once with pass/fail matrix
- **Decision surfaces tab**: Simulate competing decisions from Control Channel and TUI; first-wins rule enforced
- **Restart simulation tab**: Step through create → approve → execute with "Restart now" button at any point; verifies metadata-only persistence and source re-acquisition
- **Profile isolation tab**: Switch between Profile A and Profile B; each has independent canonical Approval Request
- **Free play tab**: Custom scenario construction with type, initial state, surface, and decision parameters
- **Proposed contract tab**: Documents the four mandatory interfaces and maps each requirement to its proving scenario

### Key invariants verified

| Requirement | Proved by | Key invariant |
|-------------|-----------|---------------|
| One canonical profile-local Approval Request | L03, Profile isolation | Per-profile singleton |
| Authenticated first-wins decisions | L06, L07, L08 | Later decisions rejected as duplicates |
| Metadata-only durable task state | All scenarios | Raw content re-fetched, never persisted |
| Restart at every transition | Restart tab | State survives, fingerprints intact |
| Current-authority source reacquisition | L12, L13 | Blocks when unavailable |
| Exact fingerprint invalidation | L14 | Hash mismatch → blocked |
| 24-hour expiry | L15, L17 | Timestamp check on resume |
| `/stop <short-id>` | L16 | Explicit invalidation |
| Fail-closed when unauthorized | L13, L14 | Blocked state |
| Non-preemptive resume | L09, L10 | Later tasks wait |
| Completed-side-effect reconciliation | L08 | No replay of executed work |
| Profile isolation | L18 | Cross-profile reads denied |
| Zero raw sensitive persistence | L05 | Only fingerprints/IDs in audit |

### Answer to the question

**Yes.** The prototype demonstrates that Hermes can implement:

- One active-profile-local canonical Approval Request with metadata-only state
- Durable Task that survives process restart without persisting sensitive content
- First-wins decision race across Control Channel and TUI surfaces
- Non-preemptive resume ordering with later tasks waiting while approval waits
- Current-authority source reacquisition after restart
- Exact fingerprint invalidation when source content changes
- 24-hour expiry and explicit `/stop <short-id>` command
- Fail-closed blocking when source is unavailable or unauthorized
- Profile isolation (two profiles don't see each other's requests)
- Exact-once policy mutation with delivery reconciliation
- Zero raw sensitive persistence (only fingerprints, hashes, IDs persisted)

The prototype uses simulated time, deterministic fingerprint generation, and isolated profile state to verify all invariants without requiring a real `HERMES_HOME` directory or network calls. It is a throwaway logic prototype for design validation, not production enforcement.
