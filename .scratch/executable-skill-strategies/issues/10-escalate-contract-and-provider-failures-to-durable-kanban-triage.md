# 10 — Escalate contract and provider failures to durable Kanban triage

**What to build:** Convert observed execution failures into durable, correctly owned, de-duplicated repair work. Contract Gaps create Contract Repair Tasks, provider/tool defects create Provider Repair Tasks, and Background Review may improve an authorized skill contract but may not directly patch arbitrary provider source or auto-dispatch speculative work.

**Blocked by:** 02 — Establish per-turn owner Execution Authority through skill maintenance; 06 — Run deterministic recovery and fail closed on Contract Gaps.

**Status:** ready-for-agent

- [ ] Contract Gaps and evidenced provider/tool failures are classified separately from authorization denial, operation unavailability, budget exhaustion, and human/model handoff.
- [ ] The first qualifying Contract Gap creates one durable Contract Repair Task in existing Kanban `triage`.
- [ ] The first qualifying provider/tool failure creates one durable Provider Repair Task in existing Kanban `triage`.
- [ ] Repair evidence includes the owning-layer candidates, skill/capability, operation, normalized outcome/error class, expected behavior, manifest version/digest, trace reference, source session, and observed timestamps without credentials or raw PII.
- [ ] A stable idempotency fingerprint appends equivalent recurrences to the existing open task instead of creating duplicates.
- [ ] Repair tasks are not automatically promoted, assigned, or dispatched; a Foreground Agent must reproduce and confirm ownership before a TDD repair.
- [ ] Background Review with inherited Skill Write Authority may non-destructively repair a verified contract defect in the exact skill target.
- [ ] Background Review escalates provider defects and does not directly modify arbitrary provider or project source, encode speculative root cause as fact, or store an unverified workaround as permanent strategy.
- [ ] Failure to create or update the Kanban task is reported separately and never replaces the original execution failure.
- [ ] High-level tests read Kanban state back after first and repeated failures to prove task class, status, redaction, deduplication, evidence accumulation, and no auto-dispatch.
