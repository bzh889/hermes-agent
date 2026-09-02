# 27 — Audit chain: HMAC-linked intent/outcome records

**What to build:** Every Egress Broker decision writes an HMAC-SHA256-chained record to a SQLite WAL database. An `intent` phase record is committed before any restricted side effect; an `outcome` phase record after. Each record stores: sequence number, previous record HMAC, phase, decision (allow/deny), reason, operation type, destination fingerprint, content fingerprint, policy revision, and timestamp. No raw prompts, CQ content, attachments, generated code, or credentials are stored — fingerprints only. On restart, unmatched intent records (no corresponding outcome) are marked `indeterminate`. Unit tests prove chain integrity (each record's HMAC chains to the previous), tamper detection (a modified record breaks the chain), and indeterminate reconciliation (unmatched intent after restart → `indeterminate`).

**Blocked by:** 26 — Egress Broker core: intent, permit, deny

**Status:** ready-for-agent

- [ ] SQLite WAL audit DB under `get_hermes_home() / "audit" / "restricted_group.db"`
- [ ] Append-only schema: sequence, prev_hmac, hmac, phase, decision, reason, operation_type, destination_fingerprint, content_fingerprint, policy_revision, timestamp
- [ ] HMAC-SHA256 chain: each record's HMAC includes the previous record's HMAC
- [ ] Intent phase record committed before the side effect
- [ ] Outcome phase record committed after the side effect
- [ ] No raw content stored — fingerprints only
- [ ] Restart reconciliation: unmatched intents → `indeterminate`
- [ ] Unit test: chain integrity — each record links to the previous
- [ ] Unit test: tamper detection — modifying a record breaks the chain
- [ ] Unit test: indeterminate reconciliation — unmatched intent after simulated restart → `indeterminate`
- [ ] Unit test: no raw content in any record
