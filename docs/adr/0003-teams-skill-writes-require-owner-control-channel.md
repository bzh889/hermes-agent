# ADR 0003: Teams skill writes require the owner's control channel

## Status

Accepted

## Context

The Teams MTK gateway serves more than one conversation and can accept questions from users other than the Hermes owner. These users must be able to read and use available skills without gaining permission to change the shared skill library.

`GATEWAY_ALLOWED_USERS` and group authorization answer whether a message may reach Hermes. They do not answer whether that message may mutate persistent procedural knowledge. Sender authorization alone is also insufficient: the owner speaking in another Teams conversation must not silently turn that conversation into a control surface.

The live deployment already distinguishes a Teams home/control conversation from monitored group conversations. `SessionSource` carries immutable `platform`, `chat_id`, and `user_id` values into the gateway runner. However, Background Review currently inherits only the parent Agent's platform and the Agent itself is cached across turns, so write permission cannot safely be represented as a persistent Agent or session flag.

ADR 0001 defines every resolvable skill, including external and symlinked skills, as part of the eligible non-destructive write surface. This ADR defines which Teams turns may exercise that authority.

## Decision

Only a Teams MTK turn satisfying both of these conditions may hold Skill Write Authority:

1. Its exact `SessionSource.chat_id` is configured as an owner control channel.
2. Its immutable `SessionSource.user_id` matches the configured owner identity.

The canonical non-secret configuration lives in `config.yaml` under a shared `gateway.teams_mtk.control_conversations` policy. This same exact-conversation boundary is used by the broader owner-equivalent Execution Authority defined in ADR 0007; skill writes must not maintain a second, drifting allowlist. The existing `TEAMS_MTK_HOME_CHANNEL` value may seed the initial migration, but home-channel delivery and control authorization remain distinct concepts after migration.

The authorization is a non-persisted Turn Capability:

- Compute it from the current authenticated inbound `SessionSource` on every turn.
- Assign it after platform authorization and before model/tool execution.
- Never derive it from display names, message text, model arguments, a skill's `created_by` marker, or a previous turn.
- Never persist it in the transcript, session DB, prompt, cached Agent identity, or user-editable tool arguments.
- A Background Review fork may inherit it only from the exact turn that triggered the review.
- Delegations, scheduled work, and other descendants must not gain it unless their trusted execution contract explicitly propagates the same capability.

Teams MTK turns without this capability may load and follow skills but may not create, patch, edit, write supporting files, remove files, delete, or archive any skill. This applies even when the sender is otherwise allowed to use the gateway.

Enforcement is defense in depth:

1. **Schema gate:** hide skill mutation actions from unauthorized Teams turns to prevent useless model attempts.
2. **Dispatch gate:** reject unauthorized mutations at the trusted write boundary even if a model, plugin, or Background Review reaches it.
3. **Escape-hatch gate:** direct file tools must treat every resolved skill root and symlink target as protected. Unsandboxed tools that can bypass path checks, including terminal, code execution, desktop control, delegation, or cron creation, must be unavailable to unauthorized Teams turns or inherit an equivalent hard deny.

Because group sessions and Agents can be cached across participants, the capability is reset and recomputed for each inbound message. An owner interaction must never bless the next participant's turn.

Delete and archive remain subject to the separate Destructive Curation Consent from ADR 0001 even inside the control channel.

Local CLI/TUI owner sessions are outside this Teams-specific ingress restriction and retain their normal trusted-local policy.

## Consequences

### Positive

- Questions from other Teams users cannot modify shared procedural knowledge directly or through Background Review.
- The owner's control channel can still drive automatic skill improvement, including external and symlinked skills.
- Authorization depends on immutable platform identities rather than model judgment or prompt wording.
- Cached group Agents cannot leak owner privilege across participants.

### Negative

- Unauthorized Teams turns cannot receive unsandboxed terminal or code-execution access until those tools can enforce protected skill roots transitively.
- A moved or replaced control conversation requires a configuration update.
- Home-channel migration needs care so delivery configuration is not permanently overloaded as an authorization primitive.

### Verification requirements

- A control-channel owner turn can patch a loaded skill and its Background Review inherits that permission.
- The same owner in another Teams conversation is denied.
- Another user in a monitored group is denied, including after an authorized owner turn reused the same cached Agent.
- A denied turn cannot bypass the guard through direct file tools, symlink targets, Background Review, delegation, cron, code execution, terminal, or desktop control.
- Read-only skill discovery and execution continue to work for denied turns.
- Local CLI/TUI behavior remains unchanged.
