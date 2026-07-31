# Core Context

Hermes Core coordinates conversations and capabilities while keeping domain-specific execution at the system edges. This glossary names the responsibility boundaries shared by skills, capability providers, and the agent core.

## Language

**Capability Strategy**:
The skill-owned decision about when a capability applies and which execution and recovery routes are legitimate.
_Avoid_: Tool suggestion, prompt hint

**Contracted Strategy**:
A Capability Strategy with a proven, repeatable route whose provider sequence, recovery routes, and stopping conditions are fixed so model choice does not materially change execution.
_Avoid_: Hard-coded prompt, preferred suggestion

**Adaptive Strategy**:
A Capability Strategy used when no repeatable best route is known, allowing model-led planning within explicit credential, provider, and failure boundaries.
_Avoid_: Unrestricted exploration, fallback to anything

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
The executable boundary that performs a capability and owns its credential and session lifecycle.
_Avoid_: Skill script, authentication helper

**Execution Guardrail**:
A core-owned enforcement rule that prevents an agent from leaving the declared Capability Strategy, exceeding its failure budget, or inventing alternative providers without authorization.
_Avoid_: Provider logic, Buganizer special case

**Skill Authorship**:
The historical fact of who produced a skill's content. Authorship does not by itself grant autonomous maintenance permission.
_Avoid_: Skill ownership, write authority

**Skill Ownership**:
The external or human control relationship associated with a skill's source. Skill Ownership does not restrict non-destructive updates by a Hermes Agent that can use the skill.
_Avoid_: Human-authored skill, creator identity

**Skill Write Authority**:
Permission for a Hermes Agent to patch, edit, or update supporting files of every skill it can resolve, load, and use, including symlink targets, regardless of Skill Authorship or Skill Ownership.
_Avoid_: Curator ownership, agent-created skill

**Destructive Curation Consent**:
Separate authorization required before unattended deletion or archival of a skill. Skill Write Authority does not imply Destructive Curation Consent.
_Avoid_: Patch permission, normal skill maintenance

**Provider Repair Task**:
A durable Kanban triage item created from observed evidence that a Capability Provider failed on the skill-selected route, preserving the reproduction context for a Foreground Agent to repair with TDD.
_Avoid_: Background code change, speculative root cause, session TODO
