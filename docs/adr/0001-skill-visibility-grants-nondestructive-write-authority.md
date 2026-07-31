# ADR 0001: Skill visibility grants non-destructive write authority

## Status

Accepted

## Context

Hermes currently uses the legacy `created_by: agent` usage marker as a Curator-management opt-in. Background Review may patch a skill only when that marker is present. Foreground-created, copied, Hub-installed, bundled, external-directory, and symlinked skills can therefore be readable and usable by an agent while remaining protected from unattended maintenance.

This policy blocked a real self-improvement attempt: Background Review loaded and selected `bug-brief`, then `skill_manage(patch)` was refused because its usage record had `created_by: null`. The field name is also misleading because the implementation treats it as management consent rather than reliable authorship provenance.

The intended operating model is different: a skill exposed to Hermes is part of the agent's procedural capability and should remain improvable by the same agent. Authorship and source ownership do not determine non-destructive maintenance permission.

Deleting or archiving a skill has materially different consequences from improving its instructions or supporting files and therefore requires a separate authority decision.

## Decision

A Hermes Agent has non-destructive write authority over every skill it can resolve, load, and use, regardless of:

- who authored it;
- whether it is local, bundled, Hub-installed, or discovered through `skills.external_dirs`;
- whether its resolved path is reached through a symlink or junction;
- whether its usage record contains `created_by: agent`.

Non-destructive write authority covers:

- patching or editing `SKILL.md`;
- writing, patching, or removing supporting files when that action does not remove the skill itself;
- equivalent foreground and unattended Background Review maintenance.

Before writing, the actor must resolve the exact skill target and load the current target content in the same review context. Ambiguous skill names do not confer authority until resolution succeeds.

Deletion and archival are excluded. They require separate destructive curation consent and retain their existing protection, approval, and pinning rules.

The legacy `created_by` marker may remain for backward-compatible telemetry or destructive lifecycle policy, but it must not gate non-destructive skill maintenance.

## Consequences

### Positive

- Background Review can apply lessons to the skill that produced or contributed to the current task.
- Self-improvement no longer silently fails because authorship provenance is absent or misleading.
- Symlinked and externally discovered skills behave consistently with the capability the Agent actually loaded.
- Authorship, source ownership, non-destructive maintenance, and destructive lifecycle authority become separate concepts.

### Negative

- Updating a symlinked or external skill mutates its resolved upstream target and can affect other consumers.
- Hub or bundled updates may later overwrite Agent changes, or Agent changes may produce a dirty source checkout.
- A faulty Background Review can modify a wider set of skills.

### Mitigations

- Preserve exact-target resolution and same-review read-before-write enforcement.
- Keep patch operations targeted and auditable through existing skill usage telemetry.
- Preserve explicit approval and pinning protections for deletion and archival.
- Surface write failures and applied changes rather than leaving them only in debug logs.
