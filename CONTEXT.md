# Core Context

Hermes Core coordinates conversations and capabilities while keeping domain-specific execution at the system edges. This glossary names the responsibility boundaries shared by skills, capability providers, and the agent core.

## Language

**Capability Strategy**:
The skill-owned decision about when a capability applies and which execution and recovery routes are legitimate.
_Avoid_: Tool suggestion, prompt hint

**Strategy Activation**:
An explicit skill load that associates its declared Capability Strategy with the current Intent Thread. Skill visibility, indexing, and direct provider availability do not activate a strategy.
_Avoid_: Skill discovery, provider permission, session-wide flag, time-limited lease

**Intent Thread**:
A semantic unit of user work that may span widely separated messages and multiple capability runs. Its continuity is determined from meaning and conversation evidence, not elapsed time or chat/session identity.
_Avoid_: Teams conversation, session ID, recent-message window, timeout bucket

**Intent Relation**:
The model-classified relationship of a new user message to prior work: `new`, `follow_up`, or `correction`. Follow-up and correction preserve the prior Intent Thread's Strategy Activation; new work starts without inheriting it.
_Avoid_: Time-gap heuristic, reply-ID equivalence, same-chat assumption

**Intent Reference**:
A stable runtime identifier selected with an Intent Relation to name the prior Intent Thread being followed up or corrected. It is provenance for strategy continuity, not authorization.
_Avoid_: Teams message ID, session ID, current-topic flag

**Contracted Strategy**:
A Capability Strategy with a proven, repeatable route whose provider sequence, recovery routes, and stopping conditions are executed directly by the Core without a model call between uniquely determined transitions.
_Avoid_: Hard-coded prompt, preferred suggestion, model-guided checklist

**Adaptive Strategy**:
A Capability Strategy used when no repeatable best route is known, allowing model-led planning within explicit credential, provider, and failure boundaries.
_Avoid_: Unrestricted exploration, fallback to anything

**Contract Executor**:
The generic Core interpreter that advances a Contracted Strategy from structured provider outcomes until it reaches success, an explicit human/model handoff, or a declared terminal failure. It contains no provider-specific domain logic.
_Avoid_: Agent reasoning loop, provider script, workflow-specific Core branch

**Contractible Capability**:
A capability whose expected states can be finitely enumerated and whose every state has one legitimate next transition or an explicit handoff to a person.
_Avoid_: Familiar workflow, commonly successful task

**Strategy Node**:
One independently classified step in a Capability Strategy, designated as either contracted or adaptive.
_Avoid_: Entire skill, arbitrary tool call

**Hybrid Strategy**:
A Capability Strategy that composes contracted Strategy Nodes with explicitly bounded Adaptive Strategy Nodes.
_Avoid_: Partially documented workflow, unrestricted mixed mode

**Capability Provider**:
The executable boundary that performs one declared operation, owns its credential and session lifecycle, and returns a normalized outcome that a Contract Executor can evaluate.
_Avoid_: Skill script, authentication helper

**Execution Guardrail**:
A core-owned enforcement rule that prevents an agent from leaving an active Capability Strategy, exceeding its failure budget, or inventing alternative providers without authorization. It does not replace provider authentication or authorization.
_Avoid_: Provider logic, Buganizer special case

**Execution Authority**:
The per-turn upper bound on operations and side effects derived from the current execution surface, conversation, and immutable sender identity. A strategy may narrow this authority but can never expand or semantically inherit it.
_Avoid_: Skill permission, Intent Thread trust, cached session role

**Restricted Group Policy**:
A reusable, fail-closed authorization contract bound to an exact group conversation that narrows every member's turn authority across tools, providers, data sources, execution environments, and outbound destinations. Mention gating or a toolset blocklist alone is not a Restricted Group Policy.
_Avoid_: Group whitelist, blocked toolsets, prompt rule

**CQ Read Broker**:
The credential-owning Capability Provider that exposes only non-mutating ALPS and MOLY operations authorized by a Restricted Group Policy. It never delegates the owner's credential, cookie, arbitrary URL access, or a general command surface to the agent or its sandbox.
_Avoid_: crtool shell access, browser login, CQ skill instructions

**Ephemeral Task Sandbox**:
A disposable execution boundary created for one restricted task, without access to host files or owner credentials, whose only durable outputs are policy-authorized results and whose filesystem is destroyed at task termination.
_Avoid_: Working directory, temporary filename, project workspace

**Origin-Bound Egress**:
An outbound authority that permits delivery only back to the exact conversation origin of the current restricted turn. A configured or otherwise trusted Teams destination does not widen this authority.
_Avoid_: Forward allowlist, home channel, messaging prompt rule

**Contract Gap**:
A fail-closed condition in which a Contracted Strategy cannot determine one legal next transition because its contract is missing, invalid, unsupported, or does not define the observed provider outcome.
_Avoid_: Adaptive fallback opportunity, provider failure by default, model recovery prompt

**Contract Repair Task**:
A durable, de-duplicated Kanban triage item created from evidence of a Contract Gap so a Foreground Agent can determine whether the contract or provider boundary must change.
_Avoid_: Automatic contract rewrite, session TODO, Provider Repair Task without triage

**Skill Authorship**:
The historical fact of who produced a skill's content. Authorship does not by itself grant autonomous maintenance permission.
_Avoid_: Skill ownership, write authority

**Skill Ownership**:
The external or human control relationship associated with a skill's source. Skill Ownership does not restrict non-destructive updates by a Hermes Agent that can use the skill.
_Avoid_: Human-authored skill, creator identity

**Skill Write Authority**:
An ephemeral execution capability permitting creation or non-destructive maintenance within the visible skill write surface. Skill visibility determines eligible targets; trusted ingress provenance determines whether the current turn holds this authority.
_Avoid_: Curator ownership, agent-created skill, permanent session privilege

**Teams Control Channel**:
The exact Teams MTK conversation and owner-identity boundary whose inbound turns may receive Skill Write Authority. A user allowlist, group role, mention, or prior authorized turn does not make another conversation a control channel.
_Avoid_: Home destination alone, authorized user in any chat, trusted display name

**Turn Capability**:
A non-persisted authorization computed from the current inbound source and inherited only by work spawned from that turn. It must not survive through a cached Agent, shared group session, transcript, model argument, or later turn.
_Avoid_: Session flag, prompt instruction, persisted provenance marker

**Destructive Curation Consent**:
Separate authorization required before unattended deletion or archival of a skill. Skill Write Authority does not imply Destructive Curation Consent.
_Avoid_: Patch permission, normal skill maintenance

**Provider Repair Task**:
A durable Kanban triage item created from observed evidence that a Capability Provider failed on the skill-selected route, preserving the reproduction context for a Foreground Agent to repair with TDD.
_Avoid_: Background code change, speculative root cause, session TODO
