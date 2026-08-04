# 04 — Execute one local Contracted Strategy end to end

**What to build:** Let a TUI owner explicitly load a fixture skill whose compact frontmatter index points to a lazy data-only strategy manifest, invoke a service-gated strategy execution interface, dispatch one real normalized read-only operation through the existing tool registry, and receive a successful result with a persisted execution trace.

**Blocked by:** 02 — Establish per-turn owner Execution Authority through skill maintenance.

**Status:** ready-for-agent

- [ ] Skill discovery reads only the compact versioned capability index and does not eagerly inject the full strategy manifest.
- [ ] Explicit skill loading resolves the referenced manifest within the exact skill root and rejects traversal outside that root.
- [ ] A minimal versioned manifest with one contracted node validates before its first operation runs.
- [ ] `strategy_execute` is service-gated and present at Agent construction only when executable strategies are available to that eligible session.
- [ ] The Contract Executor dispatches the declared operation through the real registry and consumes a stable normalized success outcome.
- [ ] No additional model decision occurs between dispatching the single contracted operation and selecting its sole terminal transition.
- [ ] The user receives the operation result and a trace records capability, execution mode, node, normalized outcome, terminal state, budget, and manifest digest.
- [ ] Existing skills without strategy metadata and direct tools without normalized contract operations continue unchanged in Adaptive mode.
- [ ] The implementation remains provider-neutral and contains no fixture- or product-specific branch in Core.
- [ ] A high-level `AIAgent.run_conversation` test uses an isolated Hermes home, real skill loading, real registry dispatch, real persistence, and a deterministic fake provider while leaving the executor unmocked.
