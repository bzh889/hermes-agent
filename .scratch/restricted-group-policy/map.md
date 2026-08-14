# Design and launch reusable Restricted Group Policy

Labels: wayfinder:map

## Destination

Build, deploy, and live-verify a reusable, fail-closed Teams MTK Restricted Group Policy framework. Its first production policy lets every member of a designated Monitor Group query and export ALPS/MOLY through the owner's account while enforcing global read-only behavior, private-source isolation, per-group temporary storage, origin-bound Teams egress, MTK-internal model routing, privacy-preserving optimization capture, and owner-approved promotion of shared knowledge into the owner's PKB.

The map includes implementation, adversarial E2E, TestGroup rollout, production canary, rollback readiness, and post-deploy verification; it does not stop at a specification.

## Notes

- Use `grilling`, `domain-modeling`, `research`, `prototype`, `tdd`, `implement`, and the Teams MTK E2E skills where their ticket type requires them.
- Existing spec ownership is preserved rather than duplicated: [`teams-mtk-group-whitelist`](../../openspec/changes/teams-mtk-group-whitelist/) is the completed admission/mention/config/toolset/keyword baseline; [`teams-mtk-hermes-native-parity`](../../openspec/changes/teams-mtk-hermes-native-parity/) owns Teams transport, streaming/reply/file/forward behavior and named real E2E; [`Executable Skill Strategies`](../executable-skill-strategies/spec.md) owns the generic Execution Authority, Capability Provider, Core guardrail, descendant-authority, and fail-closed vocabulary that Restricted Group Policy extends.
- Do not append unresolved Restricted Group Policy requirements to either existing Teams change. Once the Wayfinder decision/prototype frontier and remaining fog are clear, run `/to-spec` to synthesize a new cross-cutting `restricted-group-policy` OpenSpec change that cites those baselines, then `/to-tickets` before implementation. The new spec must preserve group-whitelist admission while replacing toolset/keyword-only restriction as the security model with per-operation capability authority.
- General group requests require `@hermes`; known control commands such as `/stop` bypass the mention gate.
- Every group member is authorized to query ALPS/MOLY, list/download attachments, and request export. CQ comment, update, assign, and every other CQ mutation are forbidden.
- The policy is globally read-only across external systems. The only write exceptions are replies to the exact origin group, explicitly requested artifact upload to that group, CQ export generation, audit records, and computation inside the group's temporary area.
- Deny all owner-private sources: other Teams conversations and DMs, email, local/network files, Workflow, Webex, calendar/meetings, OneNote, Hermes memory/Mem0/PKB/session history/skills/config/logs/credentials, and browser-cookie or owner-session bypasses. ALPS/MOLY is the explicit account-backed read exception.
- Allow other classified read capabilities unless denied. An unknown or unclassified capability pauses the task and asks the owner through both the exact owner control conversation and local TUI. Owner approval binds one explicit function and normalized resource scope to the requesting group's exact policy, persists until revoked, and resumes the paused task; it never approves a whole plugin, another group, another profile, or global Hermes.
- Policy approvals and revocations take effect immediately. Every operation in an in-flight task must re-check current authority; revocation blocks the next affected operation.
- Only the owner may create, bind, modify, approve, revoke, deploy, or disable a policy. There is no per-user privilege expansion inside a restricted group.
- All main-model, fallback, auxiliary, vision, OCR, embedding, title-generation, and delegated-agent routes must use approved MTK internal AIDE routes; unavailable routes fail closed.
- Each group has an isolated temporary root. Its whole root is cleaned daily at 03:00. If a task is active then, that group's sweep is skipped and the active task directory is deleted immediately when the task ends. `/stop` also deletes the current task directory.
- Each group runs one task at a time. Additional messages use the existing queue. Any group member may `/stop` the current task; queued messages remain and continue afterward.
- Same-group follow-up context has no time limit, but comes only from semantically relevant original Teams history in that exact group. Do not create Hermes memory, Mem0, PKB, or cross-group history for it.
- Restricted-group use may automatically emit de-identified Optimization Records containing capability, outcome, failure, correction, and feedback evidence, but no raw prompts, Teams/CQ content, PII, NDA text, or attachments. Content-bearing Shared Knowledge Candidates retain their provenance and enter the owner's PKB only after explicit owner approval; group turns never receive skill-write, provider-source-write, PKB-write, or declassification authority.
- Artifacts successfully uploaded to the origin group are no longer access-restricted by Hermes. Local staging copies remain subject to cleanup.
- There is no business quota for time, rows, attachment size, export size, or sandbox storage.
- Audit is mandatory and content-minimized: record immutable/fingerprinted principal and origin, policy/version, operation, CQ target/query fingerprint, decision/reason, data volume, provider/model, cleanup verdict, and origin-egress verdict; never record credentials, full prompts, full CQ content, attachments, or generated code.
- Rollout is TestGroup adversarial E2E first, then a production harmless canary and deny-path probes with API read-back, audit evidence, disk cleanup evidence, and verified zero cross-group side effects.
- Do not commit, push, or deploy merely by working a planning/decision ticket. Execution tickets must preserve unrelated dirty work in the checkout.

## Decisions so far

<!-- Resolved child tickets are indexed here by linked title and one-line gist. -->

- [Discover reusable enforcement seams and bypass paths](issues/01-discover-reusable-enforcement-seams.md) — Extend trusted turn context, authority, middleware, approval transport, Teams history, and registry routing; add explicit policy gates for cross-domain execution, CQ reads, model routing, origin egress, isolated storage, durable approval, and audit.

## Not yet specified

- The implementation sequence and behavioral test architecture after the enforcement design is known.
- The complete adversarial E2E matrix, TestGroup identity, production Monitor Group identity, canary data, rollback trigger, and post-deploy observation window.

## Out of scope

- Granting Monitor Group members any CQ mutation or any external-system write beyond the explicit origin reply/artifact and ephemeral-compute exceptions.
- Exposing owner credentials, cookies, tokens, login secrets, credential paths, or raw authentication failures to the model, sandbox, audit, or group.
- Changing owner authority in local CLI/TUI or the exact owner control conversation, except where those surfaces manage Restricted Group Policies.
- Automatically ingesting Monitor Group content into the owner's PKB, Mem0, or other private knowledge stores.
