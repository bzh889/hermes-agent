# Define the content-minimized audit contract

Type: grilling
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02, 03, 04

## Question

What append-only audit schema, storage boundary, retention, access control, and evidence-query interface proves Restricted Group decisions without storing sensitive content? Decide immutable/fingerprinted principal and origin, policy/version, operation and CQ/query fingerprints, decision/reason, data volume, provider/model, approval correlation, cleanup and egress verdicts; define explicit exclusions for credentials, prompts, CQ content, attachments, generated code, and private-source markers; and specify tamper, concurrency, restart, redaction, and forced-secret tests.

## Comments

- Input from ticket 03: cover canonical request/decision/task IDs and fingerprints, immutable state transitions and CAS version, owner/origin/surface/config revisions, outbox delivery, deadlines, rationale or rationale fingerprint, policy/descriptor/source/payload revisions, operation/idempotency journal, resume/restart/reconfiguration, revoke, expiry/cancel/merge, race outcome, egress, and cleanup without raw sensitive content.
- Input from [Decide the production go-live gate](04-decide-production-go-live-gate.md): cover Activation Evidence Manifest identity, per-failure Owner Risk Exception and applied lifetime, final activation, progressive per-capability version visibility, operation-version pinning, production probe evidence, LLM-inferred function and self-reported percentage, high/low-confidence branch, held-operation expiry, direct resume, owner rollback, unavailable rollback disclosure, completed-side-effect read-back, and compensation outcome without persisting raw failure content or secrets.

## Resolution

### Audit schema — immutable append-only record

Each audit record contains exactly these fields, never raw sensitive content:

| Field | Source | Example | Why |
|-------|--------|---------|-----|
| `audit_id` | monotonic sequence + UUID | `audit:000123:uuid` | Tamper-evident unique ID |
| `timestamp` | server clock (UTC) | `2026-08-21T...Z` | Chronological ordering |
| `phase` | write-before-execute phase | `intent` / `outcome` / `indeterminate` | Restart safety: intent written before operation, outcome after |
| `principal` | authenticated identity fingerprint | `sha256:MTK12265...` | Who triggered, never raw name |
| `origin` | exact group/conversation fingerprint | `sha256:teams_mtk:group:19:...` | Which group |
| `policy_id` | current policy at decision time | `restricted-group-policy` | Which policy |
| `policy_revision` | current revision at decision time | `7` | Which version |
| `operation_id` | Durable Task operation identity | `op-001` | Which operation |
| `attempt_id` | attempt within operation | `attempt-001` | Which attempt |
| `capability_descriptor` | descriptor fingerprint | `sha256:cq.read.alps...` | Operation classification |
| `cq_target` | CQ system identifier | `ALPS` or `MOLY` | Which system |
| `query_fingerprint` | query hash | `sha256:SELECT...` | What was queried, not query text |
| `decision` | gate outcome | `allowed` / `denied` / `held` | Result |
| `reason` | gate reason code | `exact current-revision route grant` | Why |
| `data_volume` | bytes/rows returned | `127KB / 42 rows` | Magnitude only |
| `provider` | model route provider | `aide` | Which provider |
| `model` | model identifier | `mtk/qwen3-5-397b-...` | Which model |
| `route_class` | model route class | `main` / `fallback` / `vision` | Which route type |
| `cleanup_verdict` | sandbox cleanup outcome | `deleted` / `skipped-active` | Cleanup result |
| `egress_verdict` | origin-bound egress outcome | `delivered` / `denied` / `held` | Egress result |
| `approval_correlation` | linked Approval Request ID | `approval:req-abc123` | Related approval, if any |
| `implementation_fingerprint` | code/version digest | `sha256:plugin:v1.2.3...` | Bound implementation version |
| `prev_audit_hmac` | HMAC-SHA256 of previous record | `sha256:...` | Tamper-evident chain |
| `record_hmac` | HMAC-SHA256 of this record | `sha256:...` | Tamper-evident self |

### Explicit exclusions (never recorded)

- Credentials, tokens, passwords, cookies
- Full prompts (system/user/assistant messages)
- Full CQ content (query results, comment text)
- Attachments
- Generated code
- Raw approval payload (PII/NDA content)
- Private source markers (other conversations, DMs, email, etc.)

### Storage boundary

- **Engine**: SQLite WAL mode, profile-local, under `get_hermes_home() / "audit" / "restricted_group.db"`
- **Append-only**: no UPDATE or DELETE — records are INSERT only
- **Tamper protection**: HMAC-SHA256 chain — each record includes `prev_audit_hmac` (HMAC of the previous record's full content including its own `record_hmac`); a broken chain signals tampering
- **Retention**: permanent; no automatic deletion; owner may manually export and archive

### Access control

- **Owner-only**: only the authenticated owner (mtk12265) may query audit records, through local TUI/CLI
- **Groups never see audit**: group members have zero access to audit content, not even aggregate counts
- **No remote query**: audit is not exposed through any messaging gateway, API server, or plugin IPC

### Restart safety (write-before-execute)

1. Before any restricted operation executes, an `intent` phase audit record is written and committed to WAL
2. The operation executes only after the WAL commit succeeds
3. After the operation completes (success, failure, or hold), an `outcome` phase record is written
4. On restart: replay scans for `intent` records without a matching `outcome` → marks them as `indeterminate` with a new audit record explaining the gap
5. This proves no operation executes without first being logged, and no crash can lose evidence of what was attempted

### Evidence query interface

- **Fixed reports**: CLI command `hermes audit report` with predefined report types (daily summary, per-group, per-policy, per-operation-type, denied-operations, egress-verdicts)
- **Date range filter**: `--from YYYY-MM-DD --to YYYY-MM-DD`
- **No flexible SQL**: no arbitrary query interface — fixed reports only, to minimize information leakage risk
- **JSON export**: each report can be exported as JSON for offline analysis

### Required tests

- **Tamper test**: corrupt one record → chain verification detects the break and reports all subsequent records as suspect
- **Concurrency test**: concurrent operations produce interleaved but correctly chained records with no gaps or duplicates
- **Restart test**: kill process between intent and outcome → restart marks record as indeterminate
- **Redaction test**: verify no excluded field (credentials, prompts, CQ content, attachments, code) appears in any record
- **Forced-secret test**: attempt operations that could leak secrets (credential_use, secret_exposure) → verify audit records contain only fingerprints, never raw values
