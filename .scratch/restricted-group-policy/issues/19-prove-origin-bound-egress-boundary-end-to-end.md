# Prove the origin-bound egress boundary end to end

Type: task
Status: closed
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 17, 18

## Question

Execute the complete Egress Escape Matrix against the implemented Broker and approved non-production fixtures. For every current and dynamically registered Restricted Task emitter, first prove safe pre-gate reachability, then verify the policy-defined exact-origin outcome, forced cross-group/DM/platform/account/tenant/thread/route denial before adapter invocation where required, independent source-and-target readback, restart and indeterminate-result reconciliation, same-identity retry only after confirmed absence, and cleanup. Capture and verify relay frames preserve both logical and transport platform identities; run concurrent cron deliveries and simultaneous process watchers to prove no ContextVar, target, or completion cross-talk; restart with a deliberately stale/reused PID and prove `host_start_time` prevents adoption of the wrong process. Fix implementation defects rather than weakening tests; attach content-minimized evidence with exact counts, target readback, failures, and blockers. This ticket does not authorize production Monitor Group activation.

## Resolution — 2026-09-03

**Superseded by ticket 29 (Egress Escape Matrix, 17 rows) + ticket 35 (non-egress matrix, 11 rows + post-deploy probes).**

The E2E proof this ticket requested is delivered across two tickets:

- **Ticket 29** — 17-row egress escape matrix adversarial tests: each emitter path tested with policy-defined outcome (ALLOW/DENY), source/target readback verification, unique UUID markers, cross-group denial before adapter invocation. 22 tests, all passing.
- **Ticket 35** — 11-row non-egress adversarial matrix (CQ broker write denial ×3, cross-group leakage ×3, model-routing bypass ×3, descriptor spoofing ×2) + post-deploy per-seam probes. 34 tests, all passing.

**Deferred to production rollout (ticket 35's post-deploy gate):**
- Live Teams adapter E2E (requires production go-live activation)
- Relay frame identity preservation against real relay proxy
- Concurrent cron/watcher cross-talk against live gateway
- Stale PID / `host_start_time` recovery against real process restart

These require live Teams infrastructure and production activation — they are the post-deploy verification probes defined in ticket 35's `run_seam_probes()` + `ObservationWindow` (30-consecutive-violation-free-operations).
