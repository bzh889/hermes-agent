## ADDED Requirements

### Requirement: Group whitelist authorization
The system SHALL authorize any sender within a Teams group conversation whose `chat_id` is present in `gateway.teams_mtk.groups` (config.yaml), without requiring that sender's individual OID to appear in `GATEWAY_ALLOWED_USERS`.

#### Scenario: Whitelisted group member sends a message
- **WHEN** a user who is not in `GATEWAY_ALLOWED_USERS` sends a message in a Teams group conversation whose `chat_id` exists under `gateway.teams_mtk.groups`
- **THEN** the message is authorized and forwarded to the agent pipeline

#### Scenario: Non-whitelisted group is unaffected
- **WHEN** a user sends a message in a Teams group conversation whose `chat_id` does NOT exist under `gateway.teams_mtk.groups`
- **THEN** the existing individual-allowlist (`GATEWAY_ALLOWED_USERS`) check applies unchanged, and the message is denied if the sender is not individually allowlisted

#### Scenario: DM conversations unaffected
- **WHEN** a message arrives via a 1-1 Teams conversation (`chat_type == "dm"`)
- **THEN** the group whitelist path is not consulted; authorization continues to use `GATEWAY_ALLOWED_USERS` as before

### Requirement: Per-group mention exemption
The system SHALL allow each whitelisted group to independently override whether `@hermes` mention is required, via `gateway.teams_mtk.groups.<id>.require_mention`, defaulting to `false` when a group is added via the CLI.

#### Scenario: Group added with default mention policy
- **WHEN** an operator runs `hermes teams-mtk group add <conv_id>` without `--require-mention`
- **THEN** the group's `require_mention` is set to `false`, and messages in that group are processed without needing `@hermes`

#### Scenario: Group explicitly requires mention
- **WHEN** a group's config has `require_mention: true`
- **THEN** messages in that group are ignored unless they contain the `@hermes` mention tag (case-insensitive), matching existing global mention-gating behavior

#### Scenario: Fallback to global mention policy for un-configured groups
- **WHEN** a group conversation's `chat_id` is not present in `gateway.teams_mtk.groups`
- **THEN** mention gating falls back to the existing global `TEAMS_MTK_REQUIRE_MENTION` env var / default `true`

### Requirement: Per-group and per-user toolset restriction
The system SHALL support restricting which toolsets are available to the agent when responding in a given group, via `gateway.teams_mtk.groups.<id>.blocked_toolsets` and `gateway.teams_mtk.groups.<id>.per_user.<user_id>.blocked_toolsets`, with the two sets unioned before being passed to the agent as `disabled_toolsets`.

#### Scenario: Group-level toolset block
- **WHEN** a group has `blocked_toolsets: [terminal, code_execution, browser]`
- **THEN** any agent invocation for a message from that group is constructed with those toolsets disabled, regardless of sender

#### Scenario: Per-user toolset block within an otherwise unrestricted group
- **WHEN** a group has no `blocked_toolsets` but `per_user.<oid>.blocked_toolsets: [web]` for a specific sender
- **THEN** only that sender's messages are processed with `web` disabled; other senders in the same group are unaffected

#### Scenario: Group and per-user restrictions combine
- **WHEN** a group has `blocked_toolsets: [terminal]` AND the sending user has `per_user.<oid>.blocked_toolsets: [web]`
- **THEN** the agent invocation for that sender's message has both `terminal` and `web` disabled (set union)

### Requirement: Bidirectional keyword blocking
The system SHALL block message processing (inbound) and reply delivery (outbound) when text matches any regex pattern in `gateway.teams_mtk.groups.<id>.blocked_keywords` (case-insensitive), replacing the blocked content with a fixed notice instead of forwarding it.

#### Scenario: Inbound message matches a blocked keyword
- **WHEN** an incoming group message (after mention-tag stripping) matches any pattern in that group's `blocked_keywords`
- **THEN** the message is NOT forwarded to the agent; a fixed refusal notice is sent back to the conversation instead, and the match is logged

#### Scenario: Outbound reply matches a blocked keyword
- **WHEN** the agent's composed reply for a message in a keyword-restricted group matches any pattern in that group's `blocked_keywords`
- **THEN** the reply is NOT delivered; a fixed refusal notice is sent instead, and the match is logged

#### Scenario: No keyword restrictions configured
- **WHEN** a group's `blocked_keywords` is empty or absent
- **THEN** no keyword filtering is applied to inbound or outbound content for that group

### Requirement: CLI group management
The system SHALL provide `hermes teams-mtk group add|list|set|remove` commands that read and write `gateway.teams_mtk.groups` in config.yaml without requiring manual YAML editing.

#### Scenario: Adding a new group
- **WHEN** an operator runs `hermes teams-mtk group add <conv_id> --name "<label>"`
- **THEN** a new entry is created under `gateway.teams_mtk.groups.<conv_id>` with `name` set and `require_mention: false`, and the operator is shown a reminder that a gateway restart is required for the change to take effect

#### Scenario: Listing configured groups
- **WHEN** an operator runs `hermes teams-mtk group list`
- **THEN** all configured groups are printed showing their `name`, effective `require_mention` value (including which source it came from — group override vs. global default), `blocked_toolsets`, and `blocked_keywords`

#### Scenario: Updating a group's restrictions
- **WHEN** an operator runs `hermes teams-mtk group set <conv_id> --block-toolset <name> --block-keyword <pattern>`
- **THEN** the specified toolset/keyword is appended to that group's `blocked_toolsets`/`blocked_keywords` lists in config.yaml (deduplicated), and a restart reminder is shown

#### Scenario: Removing a group from the whitelist
- **WHEN** an operator runs `hermes teams-mtk group remove <conv_id>`
- **THEN** the entry is deleted from `gateway.teams_mtk.groups`, and the group reverts to being denied by default (unless individually allowlisted senders exist in `GATEWAY_ALLOWED_USERS`)
