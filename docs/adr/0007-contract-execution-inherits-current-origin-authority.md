# ADR 0007: Contract execution inherits current origin authority

## Status

Accepted

## Context

A Contracted Strategy can invoke operations without another model decision. This raises a separate question from whether the transition is deterministic: which operations the current caller is authorized to execute.

A fixed global allowlist of `contract-safe` operations would unnecessarily restrict the owner's trusted local workflow. Allowing every explicitly loaded skill to invoke every operation would instead let an untrusted Gateway question or third-party skill expand its caller's authority.

Intent continuity cannot solve authorization. A semantic follow-up may continue work after a long delay or from retained history, but trust must come from the current inbound principal rather than from the previous Intent Thread.

## Decision

A strategy never grants execution authority. It executes inside the **Execution Authority** of the current turn and may only narrow it.

The trusted owner surfaces are:

- the local TUI; and
- Teams MTK turns from the configured control conversation when the immutable sender identity is also the owner.

Those surfaces may execute Contracted Strategy operations using any tool or provider operation currently enabled for the same principal, subject to all normal approval, credential, destructive-action, availability, and platform safety checks. Explicit skill activation does not bypass any of those checks.

Other Gateway conversations and users may read or use skill instructions under their normal Gateway policy, but they cannot execute operations through the Contract Executor. A contract invocation from those origins fails with an authorization result; it does not fall back to adaptive execution automatically.

Execution Authority is recomputed for every inbound turn from trusted runtime metadata. It is not persisted in the model prompt, session history, cached Agent, strategy state, or Intent Thread. A follow-up or correction may inherit Strategy Activation while still receiving a different or denied Execution Authority.

Delegated, background, scheduled, or redirected work spawned from a turn may inherit no more authority than that turn. It cannot upgrade itself by changing tool arguments, selecting another skill, or referring to a prior trusted message.

An operation named by a contract but unavailable under the current principal is an authorization or availability failure, not a Contract Gap. A nonexistent operation or invalid contract reference remains a Contract Gap under ADR 0005.

## Consequences

### Positive

- The owner retains full TUI and control-channel capability.
- Other Gateway users cannot turn deterministic skill execution into privilege escalation.
- Semantic continuity and security provenance remain independent.
- Existing approval and destructive-action policies stay authoritative.

### Negative

- The same active strategy may execute on one surface and be denied on another.
- Gateway and background execution must carry immutable origin authority outside model-controlled context.
- Tests must cover cached/shared sessions so a trusted turn cannot bless a later untrusted turn.

## Rejected alternatives

### Only provider-declared `contract-safe` operations

Rejected as the sole policy because it needlessly limits trusted owner surfaces and duplicates the existing tool/approval policy.

### Any operation named by an explicitly loaded skill

Rejected because skill activation is strategy selection, not authorization.

### Inherit authority with the Intent Thread

Rejected because semantic continuity is not proof of the current sender or conversation's trust level.
