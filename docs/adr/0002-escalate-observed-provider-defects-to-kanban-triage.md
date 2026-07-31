# ADR 0002: Escalate observed provider defects to Kanban triage

## Status

Accepted

## Context

Hermes Background Review can improve procedural guidance in a skill, but its autonomous write surface does not extend to arbitrary provider or project source code. When a task exposes a defect in a provider outside the skill directory, recording only a workaround in `SKILL.md` leaves the underlying defect in place. Allowing an unattended background reviewer to patch arbitrary repositories would instead create an unsafe and difficult-to-audit code execution path.

Hermes already has a durable, SQLite-backed Kanban board with task history, workspace routing, human-in-the-loop states, and worker handoff. A separate repair queue would duplicate this capability. Session TODOs and in-process delegation are not durable enough.

## Decision

When Background Review observes evidence that the skill-selected Capability Provider failed, it may create or update a **Provider Repair Task** in the existing Hermes Kanban system.

Provider Repair Tasks:

- start in `triage` and are never dispatched automatically;
- preserve the source skill, provider identity and repository/path when known, operation, exact observed failure evidence, source session, attempted official route, and expected behavior;
- describe the finding as a suspected provider defect rather than claiming an unverified root cause;
- are taken over by a Foreground Agent and repaired using TDD;
- may point at the provider repository through Kanban's existing `workdir` support.

Background Review may still apply a non-destructive skill improvement in the same review. That update must describe the legitimate route or stopping condition and must not encode an unverified workaround as the permanent provider contract.

Operational choices such as occurrence thresholds, error normalization, confidence scoring, and deduplication are reversible Agent optimization policy rather than user-level architecture decisions. The initial policy is:

- require an actual tool/provider failure in the transcript;
- create on the first evidenced occurrence because `triage` has no automatic code side effect;
- use an idempotency key derived from provider identity, operation, and normalized error class;
- append later occurrences and session evidence to the existing open task instead of creating duplicates;
- do not create a task from speculation without a failed provider invocation.

## Consequences

### Positive

- Provider defects survive session compression and process restarts.
- Background learning no longer degrades into accumulating workarounds in skills.
- Source modification remains in a foreground, reviewable TDD workflow.
- Hermes reuses its existing durable queue and audit trail.

### Negative

- Kanban triage may accumulate false positives or low-value failures.
- Foreground work must include a triage step before implementation.
- Background Review needs a narrow path to create or update Kanban tasks despite its otherwise restricted tool surface.

### Mitigations

- Require observed provider/tool evidence and retain exact source context.
- Deduplicate repeated failures and append occurrences to the existing task.
- Keep tasks in `triage`; no dispatcher worker runs until a foreground decision promotes the task.
- Treat root-cause text from Background Review as a hypothesis until the TDD repair reproduces it.
