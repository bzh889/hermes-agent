# 29 — Egress escape matrix adversarial tests (17 rows)

**What to build:** The 17-row egress escape matrix defined in ticket 18 is implemented as executable adversarial tests. Each row tests one emitter path with its policy-defined outcome (ALLOW or DENY) and verifies: safe pre-gate reachability (adapter can connect), policy-defined exact-origin outcome, forced cross-group/DM denial before adapter invocation, independent source-and-target readback with unique `EGRESS-TEST-{uuid}:` markers, restart and indeterminate-result reconciliation, same-identity retry only after confirmed absence, and cleanup. Contract-test adapters simulate unsupported dimensions (alternate platform, alternate account, webhook). Test messages contain only public markers — no PII, NDA, credentials, or CQ content.

**Blocked by:** 28 — Wire all emitter paths through the Egress Broker

**Status:** ready-for-agent

- [ ] Row 1: final reply — exact origin ALLOW (readback confirms delivery)
- [ ] Row 2: streamed commentary — exact origin ALLOW
- [ ] Row 3: send_message text — exact origin ALLOW
- [ ] Row 4: send_message media — exact origin ALLOW
- [ ] Row 5: reaction — DENY (no side effect)
- [ ] Row 6: loop mutation — DENY
- [ ] Row 7: native route — exact origin ALLOW
- [ ] Row 8: relay route — exact origin ALLOW
- [ ] Row 9: automatic MEDIA delivery — exact origin ALLOW
- [ ] Row 10: TTS — exact origin ALLOW
- [ ] Row 11: document delivery — exact origin ALLOW
- [ ] Row 12: cron fan-out — cross-group DENY (no message at deny target)
- [ ] Row 13: cron mirroring — cross-group DENY
- [ ] Row 14: delegated/background completion — DENY (must return through Broker)
- [ ] Row 15: Kanban notification — cross-group DENY
- [ ] Row 16: plugin/webhook/API emitter — per policy
- [ ] Row 17: future registered adapter — per policy
- [ ] Each DENY row verified by independent target readback (no message delivered)
- [ ] Each ALLOW row verified by source readback (message delivered with unique marker)
- [ ] Contract-test adapters for unsupported dimensions (alternate platform, account, webhook)
- [ ] No protected content in any test message
