# ADR 0004: Core executes deterministic contracted transitions

## Status

Accepted

## Context

A Contracted Strategy describes a capability whose states are finite and whose next action is unique or ends in an explicit handoff. Leaving the model in the loop between such states adds latency, cost, and nondeterminism without adding a legitimate decision.

The `bug-brief` authentication-expiry path is the motivating example. If the provider reports `AUTH_EXPIRED` and the contract declares re-authentication followed by one retry as the only legal recovery, asking the model what to do next can only reproduce that transition or violate the contract.

An external YAML file would not make this behavior executable by itself. If it is only injected into the prompt, the model may ignore, reinterpret, or route around it. Responsibility for advancing deterministic transitions must therefore be explicit.

## Decision

The Hermes Core owns a generic **Contract Executor** for Contracted Strategy nodes.

When a contracted capability starts:

1. The model selects the capability and supplies its initial inputs.
2. The Contract Executor invokes the operation declared for the current state.
3. The Capability Provider returns a normalized structured outcome.
4. The Contract Executor selects the single transition declared for that `(state, outcome)` pair.
5. It continues without another model call until it reaches success, a declared terminal failure, a budget limit, or an explicit human/model handoff.

The model does not choose among recovery routes inside a contracted node and cannot override its transition table. A transition requiring semantic judgment must be represented as an explicit handoff or as an Adaptive Strategy node rather than hidden inside the contracted node.

The Contract Executor is domain-neutral. It interprets versioned strategy data and observable provider outcomes; it must not contain branches for Buganizer, CorpSSO, Teams, or any other individual provider.

Capability Providers continue to own credentials, sessions, and execution. They expose declared operations and normalize their results into outcomes usable by the Contract Executor.

Adaptive Strategy nodes remain model-driven, bounded by Core guardrails. A Hybrid Strategy may therefore move deliberately between deterministic execution and explicit model handoffs.

## Consequences

### Positive

- Unique recovery routes execute without extra model latency or cost.
- Contracted behavior is enforced rather than dependent on prompt obedience.
- The same interpreter can run contracts for unrelated providers.
- Execution traces expose exact states, outcomes, transitions, and handoffs.

### Negative

- Providers used by contracted nodes must return stable normalized outcomes.
- Strategy contracts require schema validation and versioning.
- A malformed or incomplete transition table needs an explicit runtime policy.
- Some existing skill prose must be separated into deterministic and adaptive nodes.

## Rejected alternatives

### Model proposes every transition and Core validates it

Rejected because the model call cannot add a legitimate choice when the contract permits only one next transition. It adds latency while preserving a new failure mode.

### Provider script owns the whole state machine

Rejected because it duplicates orchestration across providers and hides cross-provider execution budgets and handoffs from Core guardrails.

### YAML is injected as model instructions only

Rejected because advisory text is not an executable contract and cannot guarantee the closed-provider or unique-recovery rules.
