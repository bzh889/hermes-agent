# 11 — Validate executable strategy packages before activation

**What to build:** Give skill authors and operators a public validation surface that proves an executable strategy package is safe, structurally deterministic where claimed, compatible with its registered operations, and consistent enough to activate before any provider side effect occurs.

**Blocked by:** 06 — Run deterministic recovery and fail closed on Contract Gaps; 07 — Resume Hybrid Strategies through bounded Adaptive handoffs; 09 — Preserve semantic continuity across compression and strategy versions.

**Status:** ready-for-agent

- [ ] Validation works through normal skill resolution for local, bundled, Hub-installed, external, plugin-provided, and symlinked packages.
- [ ] Frontmatter indexes are compact, versioned, and checked for unique capability IDs and path-contained manifest references.
- [ ] Full manifests are loaded lazily and rejected when their schema version is unsupported or their data contains scripts, executable expressions, credentials, or unsafe path references.
- [ ] Contracted graph validation covers operation registration, normalized outcome vocabulary, unique transitions, reachability, terminals, handoffs, finite cycles, and budgets.
- [ ] Hybrid validation covers declared Adaptive objectives, allowed operation/provider scope, resume points, and stale or ambiguous continuation references.
- [ ] Validation detects actionable prose/manifest drift where the skill declares behavior that cannot be reconciled with its executable index or contract.
- [ ] Validation completes before any provider operation, credential flow, repair task, or other side effect is invoked.
- [ ] Diagnostics identify the skill, capability, schema/version, invalid invariant, and safe next action without leaking secrets or internal identities.
- [ ] Valid strategy fixtures from every supported source class pass; malformed path, graph, outcome, version, and handoff fixtures fail behaviorally.
- [ ] User-facing authoring guidance documents the responsibility boundary, validation workflow, activation semantics, authority rules, fail-closed behavior, and backward-compatible Adaptive default.
