# 33 — Durable approval state and restart-safe resume

**What to build:** Owner approval creates a metadata-only Durable Task — no raw sensitive content is persisted, only fingerprints and metadata. First-wins: the first owner decision is immutable; subsequent decisions for the same task are rejected. On restart, the system reconciles by matching intent/outcome records from the audit chain, not by replaying the approval flow. An integration test proves that an interrupted approval flow resumes correctly after a simulated restart — the first decision is honored, the second is rejected, and no sensitive content is recovered from disk.

**Blocked by:** 27 — Audit chain: HMAC-linked intent/outcome records, 31 — Disposable per-group execution sandbox

**Status:** closed

- [ ] Approval request creates a metadata-only Durable Task (fingerprints, no raw content)
- [ ] First-wins: first owner decision is immutable; second decision rejected
- [ ] Zero raw sensitive persistence — only fingerprints and metadata stored
- [ ] Restart reconciliation: match intent/outcome records, not replay
- [ ] Integration test: first decision honored, second decision rejected
- [ ] Integration test: interrupted approval flow resumes correctly after simulated restart
- [ ] Integration test: no raw sensitive content recoverable from disk after restart
