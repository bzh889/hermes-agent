# 06 — Run deterministic recovery and fail closed on Contract Gaps

**What to build:** Extend the minimal executor into a finite deterministic state machine that can consume normalized provider outcomes, perform declared recovery such as authentication refresh and retry, enforce budgets and stopping conditions, and fail closed whenever the contract cannot select exactly one legal transition.

**Blocked by:** 04 — Execute one local Contracted Strategy end to end.

**Status:** ready-for-agent

- [ ] Contract-capable operations expose stable operation identities and normalized outcome vocabularies without moving credential or session ownership into the skill.
- [ ] Manifest validation rejects duplicate outcomes, ambiguous transitions, unreachable states, missing terminals, undeclared operations, and unbounded cycles before side effects.
- [ ] A fixture sequence that observes `auth_expired`, runs the declared refresh operation, retries, and succeeds executes in exact order.
- [ ] Exactly zero model decisions occur between uniquely determined contracted transitions in that recovery sequence.
- [ ] Core enforces operation, retry, transition, and total-run budgets independently of model intent.
- [ ] Unknown outcomes, unsupported schema versions, missing operation registrations, invalid graphs, and exhausted budgets produce distinct Contract Gap or budget terminal results.
- [ ] Contract Gaps never auto-select another provider, direct provider call, model exploration, or Adaptive fallback.
- [ ] Authorization denial and operation unavailability remain distinct from Contract Gap so policy is not misdiagnosed as a broken strategy.
- [ ] Execution traces preserve each node, operation, normalized outcome, transition, budget consumption, failure classification, and immutable manifest digest without secrets.
- [ ] Table-driven validator tests and high-level executor tests assert behavior and model-call/side-effect counts rather than implementation source or catalog snapshots.
