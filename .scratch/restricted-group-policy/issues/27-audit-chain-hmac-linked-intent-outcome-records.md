# 27 — Audit chain: HMAC-linked intent/outcome records

**What to build:** Every Egress Broker decision writes an HMAC-SHA256-chained record to a SQLite WAL database. An `intent` phase record is committed before any restricted side effect; an `outcome` phase record after. Each record stores: sequence number, previous record HMAC, phase, decision (allow/deny), reason, operation type, destination fingerprint, content fingerprint, policy revision, and timestamp. No raw prompts, CQ content, attachments, generated code, or credentials are stored — fingerprints only. On restart, unmatched intent records (no corresponding outcome) are marked `indeterminate`. Unit tests prove chain integrity (each record's HMAC chains to the previous), tamper detection (a modified record breaks the chain), and indeterminate reconciliation (unmatched intent after restart → `indeterminate`).

**Blocked by:** 26 — Egress Broker core: intent, permit, deny

**Status:** closed

- [x] SQLite WAL audit DB under `get_hermes_home() / "audit" / "restricted_group.db"`
- [x] Append-only schema: sequence, prev_hmac, hmac, phase, decision, reason, operation_type, destination_fingerprint, content_fingerprint, policy_revision, timestamp
- [x] HMAC-SHA256 chain: each record's HMAC includes the previous record's HMAC
- [x] Intent phase record committed before the side effect
- [x] Outcome phase record committed after the side effect
- [x] No raw content stored — fingerprints only
- [x] Restart reconciliation: unmatched intents → `indeterminate`
- [x] Unit test: chain integrity — each record links to the previous
- [x] Unit test: tamper detection — modifying a record breaks the chain
- [x] Unit test: indeterminate reconciliation — unmatched intent after simulated restart → `indeterminate`
- [x] Unit test: no raw content in any record

## Comments

### Resolution — 2026-09-03

**Implemented:**

New module `gateway/audit_chain.py` — SQLite WAL, append-only, HMAC-SHA256-chained audit trail.

**Core class:** `AuditChain`
- `__init__(db_path)` — opens SQLite in WAL mode (follows `hermes_state.py` pattern), creates schema + indexes if absent
- `append_intent(...)` — records intent phase before side effect
- `append_outcome(...)` — records outcome phase after side effect
- `append_denied(...)` — records a denied permit request
- `reconcile_indeterminate()` — marks unmatched intents as `indeterminate` (restart call)
- `verify_chain()` — recomputes every HMAC and checks chain integrity (tamper detection)
- `get_all_records()` — returns all records in sequence order

**Schema:** `audit_chain` table with 13 columns:
`seq` (autoincrement PK), `prev_hmac`, `hmac`, `phase`, `decision`, `reason`, `operation_type`, `destination_fingerprint`, `content_fingerprint`, `policy_id`, `policy_revision`, `permit_id`, `timestamp`

**HMAC chain:** Each record's HMAC covers all 12 fields + the previous record's HMAC. First record uses `_GENESIS_HMAC` sentinel. Key derived from `get_hermes_home()` (deterministic per profile, verifiable across restarts).

**Fingerprint helpers:** `destination_fingerprint(dest)`, `content_fingerprint(payload)` — SHA-256, order-independent for dicts, `sha256:none` for empty/None.

**Tests:** `tests/gateway/test_audit_chain.py` — 36 tests across 10 classes:
- `TestDBCreation` (4) — file created, WAL mode, schema, indexes
- `TestChainIntegrity` (5) — empty/single/multi chain verifies, genesis prev_hmac, link continuity
- `TestTamperDetection` (4) — tampered hmac/prev_hmac/decision/content_fingerprint all detected
- `TestIntentOutcomePhases` (3) — intent before outcome, denied recorded, outcome can be failure
- `TestNoRawContent` (3) — destination/content fingerprinted, full DB scan for raw secret
- `TestRestartReconciliation` (6) — matched not marked, unmatched marked, multiple, partial, denied not reconciled, chain intact after
- `TestAppendOnly` (2) — no update/delete API, seq auto-increments
- `TestSingleton` (1) — get_audit_chain returns same instance
- `TestFingerprintHelpers` (7) — determinism, difference, sentinels, dict order independence
- `TestCrossRestartContinuity` (1) — chain continues after reopen with same key

**Verification:** `python -m pytest` (4 files, --noconftest) → 118/118 passed, 0 failed, 20.68s

**Note:** Run with `--noconftest` because `tests/gateway/conftest.py` adapter-antipattern scan hits `MemoryError` reading the very large `gateway/run.py`. Pre-existing environment issue, not caused by this change.
