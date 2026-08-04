# ADR 0005: Contract gaps fail closed and escalate to Kanban

## Status

Accepted

## Context

ADR 0004 assigns deterministic contracted transitions to a Core Contract Executor. The executor can continue only when the active contract is valid and maps the current state plus normalized provider outcome to one legal transition.

A contract can fail before or during execution: its schema may be malformed, its version unsupported, a required operation missing, a state unreachable, or a provider may return an outcome the contract does not define. These cases do not establish that an alternative provider or model-selected recovery is legitimate.

Silently handing such a failure back to the model would make Contracted Strategy degrade into Adaptive Strategy at exactly the point where its boundary is uncertain.

## Decision

A missing, invalid, unsupported, incomplete, or non-matching contracted strategy is a **Contract Gap** and fails closed.

The Contract Executor must:

1. validate the contract before the first side effect where possible;
2. stop immediately when no declared transition matches the observed state and outcome;
3. return an explicit terminal result identifying the gap rather than presenting it as an ordinary provider failure;
4. never switch to Adaptive Strategy, another provider, provider-default fallback, or model exploration automatically; and
5. create or update a de-duplicated **Contract Repair Task** in Kanban triage with the structured execution evidence.

The repair evidence must identify at least the skill and capability, contract schema version, strategy node and state, normalized outcome, applicable budget counters, and execution trace. Raw credentials and secret payloads must not be attached.

Triage, not the Background Review, determines whether the lasting defect belongs to the strategy contract, the Capability Provider's normalization, or both. The Foreground Agent then repairs the owning layer with TDD.

A repeated occurrence updates the existing open repair task instead of creating an unbounded series of duplicates. Exact fingerprinting and retention mechanics are reversible implementation details.

## Consequences

### Positive

- Closed contracts remain closed during failure.
- Unknown provider behavior cannot silently broaden execution authority.
- The user receives an honest, specific failure instead of model improvisation.
- Repair evidence survives the current session and reaches the correct owner through triage.

### Negative

- Newly introduced provider outcomes may stop contracted workflows until the contract is updated.
- Contract validation and clear user-facing diagnostics become mandatory.
- Kanban availability must not be allowed to hide the original Contract Gap; task-creation failure must be reported separately.

## Relationship to ADR 0002

ADR 0002 covers structured evidence of a Capability Provider defect. This ADR covers an execution contract that cannot select a legal transition. Both use the same Kanban triage system, but neither pre-classifies the other as the root cause.

## Rejected alternatives

### Fall back to model planning with the same provider

Rejected because same-provider restriction does not make an undefined transition legitimate.

### Allow unrestricted model or provider fallback

Rejected because it violates the closed-provider and unique-recovery properties of a Contracted Strategy.
