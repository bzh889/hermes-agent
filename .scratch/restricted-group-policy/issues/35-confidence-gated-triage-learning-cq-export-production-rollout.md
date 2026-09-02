# 35 — Confidence-gated triage, learning, CQ export consistency, and production rollout

**What to build:** The final phase delivers five capabilities and the production rollout verification. (1) **Confidence-gated triage**: >90% confidence that a production failure is in the inferred function → block that function while unrelated operations continue; ≤90% → hold the triggering operation for 24h; adversarial error text cannot escalate authority. (2) **Privacy-preserving learning**: de-identified Optimization Records and Shared Knowledge Candidates with 30-day expiry; owner-approved PKB promotion. (3) **CQ export consistency**: stable sort + duplicate/gap detection + 8 fail-closed conditions → `INCOMPLETE_RESULT`. (4) **Production go-live gate**: exact owner activation; progressive per-capability version visibility. (5) **Post-deploy verification**: per-seam independent probes; auto-hold on violation with owner notification; 30-consecutive-violation-free-operations observation window. The 11-row non-egress adversarial matrix (CQ broker write denial ×3, cross-group capability leakage ×3, model-routing gate bypass ×3, descriptor spoofing ×2) is executed as adversarial tests using the existing test group as origin and contract-test adapters for unsupported dimensions.

**Blocked by:** 29 — Egress escape matrix adversarial tests, 30 — CQ Read Broker, 32 — Model-routing gate, 33 — Durable approval state, 34 — Semantic history retrieval

**Status:** ready-for-agent

- [ ] Confidence-gated triage: >90% blocks inferred function, ≤90% holds 24h
- [ ] Adversarial error text cannot escalate authority (treated as untrusted input)
- [ ] De-identified Optimization Records (no member identities or raw content)
- [ ] Shared Knowledge Candidates with 30-day expiry
- [ ] Owner-approved PKB promotion (no auto-ingestion)
- [ ] CQ export: stable sort + duplicate detection + gap detection
- [ ] CQ export: 8 fail-closed conditions → `INCOMPLETE_RESULT` with diagnostic metadata
- [ ] Production activation gate: exact owner activation required
- [ ] Post-deploy probes: per-seam independent probes verify each enforcement seam
- [ ] Compensation trigger: auto-hold violating operation + owner notification
- [ ] Observation window: 30 consecutive violation-free operations as exit criteria
- [ ] Non-egress adversarial matrix row 1: CQ broker INSERT → DENY
- [ ] Non-egress adversarial matrix row 2: CQ broker UPDATE → DENY
- [ ] Non-egress adversarial matrix row 3: CQ broker DELETE → DENY
- [ ] Non-egress adversarial matrix row 4: Group A operation affects Group B → DENY
- [ ] Non-egress adversarial matrix row 5: Group A history injected into Group B → DENY
- [ ] Non-egress adversarial matrix row 6: Group A descriptor read by Group B → DENY
- [ ] Non-egress adversarial matrix row 7: Forged route identity → DENY
- [ ] Non-egress adversarial matrix row 8: Stale policy revision → DENY
- [ ] Non-egress adversarial matrix row 9: Gate-check-and-switch race → DENY
- [ ] Non-egress adversarial matrix row 10: Forged descriptor capability → DENY
- [ ] Non-egress adversarial matrix row 11: Tampered descriptor fingerprint → DENY
