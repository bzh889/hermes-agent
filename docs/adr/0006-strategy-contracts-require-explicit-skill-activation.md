# ADR 0006: Strategy contracts require explicit skill activation

## Status

Accepted

## Context

A Capability Provider may be useful outside a skill-prescribed workflow. The same operation can be invoked after loading a skill with a proven route or directly by a model that needs adaptive planning.

Making every provider operation globally contract-required would turn a skill-authored strategy into a provider-wide policy. It would also prevent legitimate direct use whenever no contract is active.

Conversely, once a strategy has been explicitly activated, allowing a direct operation to bypass it would make the contracted execution internally inconsistent.

## Decision

A Capability Strategy governs execution only after an explicit **Strategy Activation** caused by loading the skill that owns it.

When a matching strategy is active, its Contracted Strategy nodes are enforced by the Core Contract Executor according to ADR 0004. The model cannot bypass the active contract by issuing the underlying provider operation directly.

When no matching skill strategy is active, a direct provider or tool call remains legal and is treated as Adaptive Strategy execution. The provider does not supply a hidden default contract, and the Core does not search for and activate a matching skill automatically.

Merely seeing a skill in the system-prompt index or `skills_list` is not Strategy Activation. An explicit load associates the strategy with the current semantic Intent Thread.

Strategy Activation has no TTL and is not scoped mechanically to a turn, chat, or session. For every later user message, the model reviews the relevant prior user/assistant exchange and classifies the **Intent Relation** as:

- `new` — start a new Intent Thread without inheriting the previous activation;
- `follow_up` — continue the previous Intent Thread and its strategy; or
- `correction` — amend the previous request while preserving its strategy and start a corrected execution without rewriting past messages.

Elapsed time is not evidence that an intent ended. A reply after a long delay may be a follow-up or correction, while an immediately adjacent message may begin unrelated work. Teams reply metadata and message references are useful evidence but do not replace semantic classification.

The Strategy Activation remains associated with its Intent Thread after a capability run reaches a terminal state, so a later semantic follow-up can start another run under the same strategy without requiring the skill to be loaded again. A message classified as new does not inherit that strategy even when it arrives in the same cached Agent or Teams conversation.

Strategy contracts are not security or authentication mechanisms. Provider credential handling, authorization, platform policy, skill-write authority, and other security guardrails apply regardless of whether execution is contracted or adaptive.

## Consequences

### Positive

- Skill authors retain ownership of strategy without taking over the provider globally.
- Direct provider use remains available for genuinely adaptive work.
- Contract activation is observable and traceable rather than inferred from subject matter.
- Security enforcement remains in Provider and Core layers where it cannot be bypassed by omitting a skill.

### Negative

- The same provider operation may behave deterministically or adaptively depending on explicit skill activation.
- Traces and user-facing diagnostics must identify the active execution mode and Intent Relation.
- The runtime needs access to sufficient prior user and assistant messages for semantic continuity classification.
- Agents that fail to load a relevant skill may take an adaptive route; this is intentional rather than treated as a security violation.
- Semantic misclassification can incorrectly inherit or drop a strategy, so ambiguous relations need an explicit policy.

## Rejected alternatives

### Every matching provider operation requires a contract

Rejected because this makes a skill strategy a global provider policy and removes legitimate adaptive use.

### Core auto-discovers a contract from the provider call

Rejected because implicit activation can select the wrong skill when several strategies use the same provider and obscures which strategy owns the run.

### Provider owns a default contract

Rejected because provider ownership is limited to authentication, execution, and normalized outcomes; strategy remains skill-owned.
