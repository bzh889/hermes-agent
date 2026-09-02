# Define privacy-preserving learning and knowledge promotion

Type: grilling
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02, 03

## Question

What exact contract lets multiple independent Restricted Groups improve Hermes from real usage without automatically retaining raw prompts, Teams/CQ content, PII, NDA text, attachments, or credentials? Define the de-identified Optimization Record schema, per-group versus aggregate identifiers, retention/deletion, owner inspection, repair/skill-review trigger, and proof that group turns cannot write skills, provider source, PKB, or declassify data. Separately define Shared Knowledge Candidate creation, provenance and sensitivity retention, duplicate handling, owner-only review through the Control Channel/TUI protocol, approved PKB destination and attribution, rejection/deletion, cross-group isolation, and forced-PII/NDA/secret tests.

## Comments

- Input from ticket 03: Shared Knowledge promotion displays the exact candidate/provenance/destination on both Approval Surfaces and authorizes one idempotent promotion. The canonical request persists metadata/fingerprints but not raw sensitive content; this ticket must decide candidate source retention/reacquisition, expiry, duplicate handling, rejection deletion, and audit under that constraint.

## Resolution

### Two separate systems

**1. Optimization Record** — de-identified structured usage telemetry from restricted-group operations.
**2. Shared Knowledge Candidate** — content-bearing proposal derived from restricted-group work for owner review before PKB admission.

Both systems are per-group isolated: no cross-group leakage, no automatic PKB ingest, no skill/provider source writes from group turns.

### Optimization Record schema

| Field | Description | Example |
|-------|-------------|---------|
| `record_id` | UUID | `opt-uuid` |
| `group_hash` | SHA-256 of group conversation ID (never raw ID) | `sha256:group-19` |
| `operation_type` | Type of operation | `cq_read` / `model_call` / `skill_use` |
| `capability_descriptor_hash` | Descriptor fingerprint | `sha256:...` |
| `outcome` | Result | `success` / `failure` / `corrected` |
| `failure_reason` | Failure reason code (if failed) | `timeout` / `denied` / `provider_error` |
| `correction_type` | User correction type (if corrected) | `re-phrased` / `retry` / `manual_override` |
| `timestamp` | UTC timestamp | `2026-08-21T...Z` |
| `skill_name` | Skill invoked (if any) | `cr-access` |
| `provider` / `model` | Model route used | `aide` / `qwen3-5` |

Explicit exclusions: raw prompts, response content, CQ query text, CQ results, attachments, PII, NDA text, credentials.

### Optimization Record properties

- **Retention**: permanent; no automatic deletion
- **Storage**: profile-local SQLite, per-group partitioned by `group_hash`
- **Access**: owner-only via local TUI/CLI; group members have zero access
- **Skill review trigger**: when the same `skill_name` records consecutive failures (any failure reason), the system automatically creates a Kanban triage item for skill review. The system does NOT auto-modify the skill — it creates the triage item only.
- **Repair trigger**: triage item follows the existing Provider Repair Task / Contract Repair Task flow from CONTEXT.md
- **Group turns cannot write**: skills, provider source code, PKB, or declassify data. Creating an Optimization Record does not grant the originating group turn write authority over any of these.

### Shared Knowledge Candidate schema

| Field | Description |
|-------|-------------|
| `candidate_id` | UUID |
| `source_group_hash` | SHA-256 of source group conversation ID |
| `content_fingerprint` | SHA-256 of candidate content (not stored) |
| `provenance_labels` | Data Provenance Labels: `origin_group`, `task_generated`, plus `pii`/`nda_confidential`/`secret` flags if detected |
| `sensitivity_flags` | Detected sensitivity (inherited from inputs) |
| `proposed_pkb_destination` | Suggested PKB path |
| `attribution` | Source group hash (not raw ID) |
| `created_at` / `expires_at` | Creation / expiry timestamp |
| `status` | `pending` / `approved` / `rejected` / `expired` |
| `fingerprint_bound` | Implementation fingerprint of the producer that created this candidate |

### Shared Knowledge Candidate properties

- **Retention**: pending candidates have 30-day expiry; approved candidates are permanently admitted to PKB
- **Owner review**: through Control Channel or local TUI (both are Approval Surfaces per CONTEXT.md); exact candidate/provenance/destination displayed on both surfaces
- **Promotion is idempotent**: one authenticated owner decision; first terminal decision wins
- **Duplicate handling**: same `content_fingerprint` from different groups → latest candidate retained, earlier duplicates auto-rejected with `DUPLICATE_CONTENT_FINGERPRINT` reason
- **Rejection**: rejected candidates are deleted (content), but the rejection decision is recorded in audit (metadata/fingerprint only, per #11 audit contract)
- **PKB destination**: approved candidate goes to the owner-designated PKB path with attribution to `source_group_hash` (not raw group identity)
- **Cross-group isolation**: candidates from group A are never visible to group B; only the owner sees candidates from all groups
- **Source reacquisition**: if the source content is no longer available or no longer authorized at promotion time, the candidate is blocked with `SOURCE_UNAVAILABLE`
- **Fingerprint invalidation**: if the producer's implementation fingerprint has changed since candidate creation, the candidate is invalidated and a new one must be created

### Required tests

- **Forced-PII test**: attempt to create an Optimization Record or Candidate containing PII → verify the record/candidate is not created or has PII stripped to fingerprint only
- **Forced-NDA test**: attempt to create a Candidate containing NDA text → verify sensitivity flag is set and content is not persisted
- **Forced-secret test**: attempt to create a Record or Candidate containing credentials → verify creation fails closed
- **Cross-group isolation test**: candidate from group A is not visible in group B's context
- **No-write-authority test**: verify that creating an Optimization Record does not modify any skill, provider source, PKB entry, or data classification
- **Skill-review trigger test**: same skill fails 3+ times → verify Kanban triage item created but skill not modified
- **Duplicate candidate test**: two candidates with same content fingerprint → older auto-rejected
- **PKB promotion test**: approved candidate appears in PKB with correct attribution and provenance labels
