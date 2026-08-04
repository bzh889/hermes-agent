# 03 — Close non-control skill-mutation escape paths

**What to build:** Make the owner-control boundary authoritative across every capability that could indirectly mutate a skill. A denied Gateway turn cannot obtain the same side effect through a lower-level file, shell, code, delegation, schedule, desktop, background-review, or symlink route, while authorized TUI and control-conversation workflows continue to work.

**Blocked by:** 02 — Establish per-turn owner Execution Authority through skill maintenance.

**Status:** ready-for-agent

- [ ] Non-control Gateway turns are denied before a protected skill path is mutated through public file write or patch operations.
- [ ] Path resolution protects local, external, and symlinked skill targets without relying on a hard-coded home-directory prefix.
- [ ] A denied turn cannot bypass the boundary through terminal commands, programmatic tool execution, delegation, scheduled work, or desktop control when those surfaces could reach a protected skill target.
- [ ] Background Review and delegated descendants inherit no more authority than the commissioning turn and cannot self-upgrade through their prompts or tool arguments.
- [ ] Scheduled or redirected work requires its own trusted execution origin and cannot cite an older owner turn as authority.
- [ ] Authorized TUI and exact owner-control-conversation operations retain their normal behavior, approvals, and exact-target read-before-write checks.
- [ ] Attempts to delete or archive still route through Destructive Curation Consent rather than a generic write escape hatch.
- [ ] Denials identify the protected boundary without revealing secrets, raw immutable identities, or sensitive local paths.
- [ ] High-level Gateway tests exercise real dispatch and path enforcement instead of source-text assertions or mocks of the guard itself.
- [ ] Concurrent denied and allowed turns prove no ContextVar, worker-thread, or cached-Agent authority leak.
