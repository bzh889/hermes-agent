# ADR 0009: The main model declares semantic intent continuity

## Status

Accepted

## Context

ADR 0006 binds Strategy Activation to a semantic Intent Thread rather than a TTL, turn, chat, or session. A later message may follow up or correct old work after a long delay, while an immediately adjacent message may start unrelated work.

The Contract Executor needs an explicit runtime signal identifying which prior Intent Thread, if any, owns the strategy. A boolean `is_follow_up` is insufficient because a Teams conversation can contain several old work threads. Core heuristics based on time or reply IDs cannot make the semantic judgment the user requires.

A separate classifier call before every message would add latency and cost. Asking the model to remember the classification only in prose would not give the Contract Executor structured input.

## Decision

The main conversational model classifies each relevant inbound user message as `new`, `follow_up`, or `correction` while processing its normal turn. For follow-up and correction, it also selects a stable **Intent Reference** identifying the prior Intent Thread.

The model must review the relevant prior user and assistant exchanges before classifying. Evidence resolution follows this order without imposing a time limit:

1. an explicit platform reply or message reference supplies a strong candidate anchor;
2. retained conversation history and compression summaries supply nearby context; and
3. when the referenced work is no longer in active context, same-conversation history retrieval supplies the older exchange.

A platform reply ID identifies evidence; it does not force the semantic result. Unrelated content may still start a new Intent Thread. Conversely, a message without reply metadata may semantically continue old work.

For an executable strategy, the model submits the Intent Relation, Intent Reference when required, capability ID, and normalized user inputs through a service-gated `strategy_execute` interface. The Core then validates the reference, resolves Strategy Activation, recomputes current-turn Execution Authority, loads the manifest, and runs deterministic transitions.

`strategy_execute` is exposed only in sessions whose frozen initial toolset has executable strategy support. It is not added or removed mid-conversation. Skill installation or strategy-schema changes therefore take effect in a later session by default, preserving prompt caching.

No auxiliary classifier call is required. Core validates structural facts—whether the referenced intent exists, whether it owns the capability strategy, and whether the current principal may execute—but does not replace the model's semantic judgment with a time heuristic.

A `new` relation creates a new Intent Thread. A `follow_up` resumes the prior strategy context. A `correction` creates an amended execution under the same strategy without deleting or rewriting prior messages or traces.

When the relation is genuinely ambiguous and selecting the wrong Intent Thread would authorize a side effect or alter durable state, the model asks the user to identify the intended prior work. For read-only work with no durable consequence, the model may proceed with its best semantic judgment and report the interpreted context.

## Consequences

### Positive

- There is no TTL or same-chat shortcut.
- Several old work topics can coexist in one Teams conversation.
- Classification reuses the main model call instead of adding a mandatory classifier round trip.
- Core receives a structured continuation signal without interpreting natural language itself.
- Corrections preserve append-only history and prompt-cache invariants.

### Negative

- The model can misclassify semantic continuity.
- Intent identifiers and compact summaries must survive compression and session persistence.
- Older same-conversation exchanges must remain retrievable even when absent from active context.
- A service-gated strategy tool adds schema footprint to sessions that enable executable contracts.

## Rejected alternatives

### Expire strategy after a turn, run, session, or TTL

Rejected because elapsed time and transport boundaries do not determine semantic continuity.

### Treat every platform reply as a follow-up

Rejected because reply metadata is an anchor, not proof that the content continues the referenced task.

### Run an auxiliary classifier before every turn

Rejected as the default because it adds an avoidable model request to Gateway latency.

### Let Core infer continuity from tool names

Rejected because identical tools can serve unrelated intents and direct provider calls are legitimately Adaptive.
