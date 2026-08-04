# 07 — Resume Hybrid Strategies through bounded Adaptive handoffs

**What to build:** Allow a Hybrid Strategy to leave deterministic execution only at an explicitly declared Adaptive node, give the model a bounded decision context, and resume the same contracted run after the model supplies the required judgment without expanding tools, providers, budgets, or authority.

**Blocked by:** 04 — Execute one local Contracted Strategy end to end.

**Status:** ready-for-agent

- [ ] A manifest can compose contracted and adaptive nodes while declaring every handoff and resume edge explicitly.
- [ ] Entering an Adaptive node returns the model only the objective, relevant normalized evidence, allowed operations/providers, remaining budgets, Intent Reference, and resume point required for that decision.
- [ ] The handoff does not rebuild the system prompt, mutate prior context, or dynamically widen the session tool schema.
- [ ] The model can return a bounded decision that resumes the same manifest snapshot at one declared continuation.
- [ ] An out-of-scope operation, provider, transition, or budget request is rejected before side effects rather than treated as permission to explore.
- [ ] Existing Execution Authority, approval, credential, and dangerous-action controls remain active during the Adaptive node.
- [ ] A semantic condition cannot masquerade as a contracted expression; it must appear as an Adaptive node or explicit human handoff.
- [ ] Traces clearly distinguish contracted transitions, model handoffs, model decisions, resume points, and terminal outcomes.
- [ ] A high-level Hybrid fixture proves one bounded model decision occurs at the Adaptive node and no additional model decision occurs during surrounding deterministic transitions.
- [ ] Invalid, missing, repeated, or stale resume references fail safely without starting a second capability run.
