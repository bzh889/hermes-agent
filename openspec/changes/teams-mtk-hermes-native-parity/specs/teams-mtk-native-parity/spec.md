## ADDED Requirements

### Requirement: Complete Hermes Platform Integration
The Teams MTK platform SHALL participate in the same Hermes integration surfaces as other configured messaging platforms, including status reporting, prompt hints, cron delivery, target parsing, session identity, and configuration-based authorization.

#### Scenario: Configured platform is discoverable
- **WHEN** a valid Teams MTK conversation is configured
- **THEN** Hermes reports the platform as configured and can route an explicit Teams MTK delivery target without requiring a new model tool

#### Scenario: Scheduled delivery uses the platform registry
- **WHEN** a cron job targets `teams_mtk` and no live gateway adapter reference is available
- **THEN** the registered standalone sender delivers through the same authenticated transport and returns a truthful structured result

### Requirement: SDK-First Transport with Graceful Fallback
The adapter SHALL use `teams_skype_sdk` for supported Skype and Graph operations when the SDK is available, and MUST retain behaviorally equivalent raw HTTP fallbacks for unavailable or unsupported SDK paths.

#### Scenario: SDK operation succeeds
- **WHEN** the SDK is installed and a supported operation succeeds
- **THEN** the adapter returns the SDK result without invoking the raw fallback

#### Scenario: SDK path is unavailable
- **WHEN** the SDK cannot be imported or a supported SDK operation fails before producing a remote side effect
- **THEN** the adapter invokes the raw HTTP fallback and reports which path produced the result

#### Scenario: Send result identifies the remote message
- **WHEN** the Skype send endpoint returns `OriginalArrivalTime` without an `id`
- **THEN** the adapter treats `OriginalArrivalTime` as the message ID for edit, ownership, cleanup, and read-back operations

### Requirement: WebSocket Acceleration with Poll Catch-Up
The adapter SHALL use Trouter WebSocket events to reduce inbound latency while retaining HTTP polling as the authoritative catch-up path.

#### Scenario: Healthy WebSocket event arrives
- **WHEN** a healthy Trouter connection emits an event for a configured conversation
- **THEN** the adapter immediately fetches the authoritative message representation and processes it through the normal inbound pipeline

#### Scenario: WebSocket disconnects or misses an event
- **WHEN** the WebSocket is unhealthy, reconnecting, or has missed an inbound event
- **THEN** HTTP polling continues and eventually processes every message newer than the persisted conversation watermark

#### Scenario: Gateway restarts
- **WHEN** the gateway restarts after previously sending or processing messages
- **THEN** catch-up seeding prevents old messages from being replayed as new agent turns

### Requirement: Native Message and Media Delivery
The adapter SHALL deliver text, edits, images, documents, Adaptive Cards, typing signals, reactions, and supported deletion operations using Teams-compatible payloads and authentication.

#### Scenario: Rich content is delivered
- **WHEN** Hermes sends mixed Markdown and HTML content
- **THEN** the Teams read-back contains rendered HTML without residual supported Markdown syntax or duplicate final messages

#### Scenario: Media is delivered
- **WHEN** Hermes sends an image or document
- **THEN** the remote message contains a usable hosted image or file reference and the acceptance check reads back that remote effect

#### Scenario: Reaction round trip
- **WHEN** Hermes adds and then removes a supported reaction
- **THEN** API read-back observes the reaction after add and its absence after remove

### Requirement: Conversation-Scoped Outbound Ownership
Outbound message ownership SHALL be recorded only after a successful send as a bounded TTL entry keyed by the exact `(conversation_id, message_id)` pair. Inbound ownership checks MUST be read-only.

#### Scenario: Tracked outbound message is polled back
- **WHEN** an inbound poll returns a message whose exact conversation and message ID were registered by an outbound send
- **THEN** the adapter suppresses that message as its own echo without starting an agent turn

#### Scenario: Same message ID appears in another conversation
- **WHEN** an untracked conversation contains the same message ID as a tracked outbound message in another conversation
- **THEN** the adapter treats the untracked pair as foreign and does not suppress or authorize it

#### Scenario: Foreign message contains Hermes presentation HTML
- **WHEN** a user quotes or forwards content containing Hermes HTML styling or signature text
- **THEN** the adapter treats presentation markup as non-authoritative and dispatches the foreign inbound message normally

#### Scenario: Foreign inbound is inspected
- **WHEN** the adapter checks an unseen inbound message against outbound ownership
- **THEN** the check does not register, remember, or otherwise mutate outbound ownership state

### Requirement: Delete Only Proven Bot-Owned Messages
Safe deletion SHALL allow only messages proven to be bot-owned by the exact conversation-scoped outbound registry or authoritative sender metadata. Presentation HTML and inbound deduplication MUST NOT grant deletion authority.

#### Scenario: Owned message is deleted
- **WHEN** safe deletion targets a registered outbound `(conversation_id, message_id)` pair
- **THEN** the adapter deletes it and API read-back observes the remote tombstone

#### Scenario: Foreign message is protected
- **WHEN** the same adapter instance first processes a controlled foreign inbound message and then receives a safe-delete request for that pair
- **THEN** deletion is refused and API read-back confirms the foreign content is unchanged

### Requirement: Safe Contact Resolution and Directory Fallback
Contact targets SHALL resolve existing conversations by display name before consulting the organization directory. Directory results MAY improve canonical naming and error guidance but MUST NOT create a new chat without the required external scope and authorization gate.

#### Scenario: Existing conversation matches directly
- **WHEN** a requested contact name matches an existing conversation title
- **THEN** the adapter returns that conversation without invoking directory search

#### Scenario: Directory resolves a canonical name but no chat exists
- **WHEN** direct lookup misses and directory search returns a canonical user identity whose conversation still cannot be resolved
- **THEN** the adapter returns an actionable error naming only the sanitized canonical display name and instructing the user to open a Teams conversation first

#### Scenario: Directory lookup fails
- **WHEN** direct lookup and directory search both fail
- **THEN** the adapter returns a truthful not-found result without creating or sending to an unauthorized conversation

### Requirement: Authorization and Identity Privacy
The platform SHALL preserve configured conversation and user authorization boundaries, and MUST redact stable organization identifiers from logs and failure evidence.

#### Scenario: Unauthorized conversation sends a message
- **WHEN** an inbound message originates outside configured authorization policy
- **THEN** the adapter refuses agent dispatch and does not expose additional tool access

#### Scenario: Diagnostic evidence is emitted
- **WHEN** the adapter logs an AAD object identifier or an E2E failure
- **THEN** stable identifiers, tokens, message bodies, and other sensitive values are redacted or represented only by sanitized status, length, and hash metadata

### Requirement: Honest Real-Gateway Acceptance
Every live capability marked complete SHALL have a named sequential E2E test that exercises the real transport and verifies the delivered effect through logs or API read-back appropriate to that effect.

#### Scenario: Delivered content is under test
- **WHEN** a test claims message, media, reaction, edit, delete, or contact-routing success
- **THEN** it verifies the resulting remote state rather than method existence, an attempted call, or a permissive success-or-failure log pattern

#### Scenario: Test selection is invalid or empty
- **WHEN** the E2E runner receives an unknown name or selects zero tests
- **THEN** it exits non-zero and does not report a passing suite

#### Scenario: A test creates a remote side effect
- **WHEN** a test sends or mutates a remote message, including a send that returns failure or a malformed result
- **THEN** cleanup runs in `finally`, discovers the side effect by returned ID or unique marker, and surfaces cleanup failure as a test error

#### Scenario: Full acceptance is claimed
- **WHEN** changes to the adapter or E2E assertions are ready for completion
- **THEN** the complete named real-gateway suite and the canonical repository test wrapper both pass on the final tree

#### Scenario: Edited inbound query is accepted
- **WHEN** `inbound-edit-revision-reopens-query` edits a human-originated query under the same remote message identity
- **THEN** the real gateway emits exactly one revised turn containing the complete edited body, does not replay the original body, reads back the canonical edited object, and confirms cleanup

#### Scenario: Long quoted reply is accepted
- **WHEN** `quoted-reply-full-context-revises-query` replies to a source whose complete body exceeds the display quote preview
- **THEN** the real gateway promotes the exact source identity and complete fetched source content, combines it with the reply body, and never labels the preview as complete context

#### Scenario: Native outbound reply is accepted
- **WHEN** `reply-to-native-thread-roundtrip` sends a Hermes response with a reply target
- **THEN** canonical service read-back contains the native relation to that target, or an explicitly forced pre-send-unavailable case produces one flat send with a sanitized degradation signal

#### Scenario: Revision and reply verdicts remain independent
- **WHEN** the edit, inbound-reply, and outbound-reply acceptance items run in one suite
- **THEN** each reports its own functional, read-back, and cleanup result and no passing item masks another item's failure

### Requirement: External SDK Polling Ownership Parity
The separately versioned `teams_skype_sdk` polling runner SHALL apply the same conversation-scoped ownership and read-only inbound lookup contract as the gateway.

#### Scenario: SDK polling sees a foreign quoted reply
- **WHEN** a foreign inbound message contains quoted Hermes HTML
- **THEN** the polling runner dispatches it and does not classify it as bot-owned from its content

#### Scenario: SDK polling sees cross-chat ID collision
- **WHEN** two conversations contain the same message ID and only one pair was sent by the bot
- **THEN** the runner suppresses only the registered conversation/message pair

#### Scenario: SDK polling inspects unseen inbound ID
- **WHEN** an inbound message is absent from the outbound registry
- **THEN** the membership check leaves the registry unchanged

### Requirement: Same-Identity Message Revision Dispatch
The Teams MTK adapter SHALL maintain bounded conversation-scoped revision state so a changed representation of an existing message identity is dispatched exactly once without weakening authorization or outbound ownership checks.

#### Scenario: First representation is processed
- **WHEN** an authorized inbound message identity has not been observed in its conversation
- **THEN** the adapter dispatches it through the normal inbound pipeline and records its explicit revision candidate and deterministic canonical-content hash

#### Scenario: Unchanged representation is polled again
- **WHEN** polling or WebSocket catch-up returns the same conversation, message identity, revision candidate, and canonical-content hash
- **THEN** the adapter treats it as old and does not start another agent turn

#### Scenario: Same identity contains a new revision
- **WHEN** an authorized inbound message keeps its message identity but its explicit revision candidate or canonical-content hash changes
- **THEN** the adapter dispatches exactly one revision event containing the complete current body and atomically records the new revision before overlapping fetch paths can replay it

#### Scenario: Tenant omits explicit revision fields
- **WHEN** a message envelope does not expose a usable version or edit-time candidate
- **THEN** the deterministic canonical-content hash remains the revision detector and duplicate suppressor

#### Scenario: Sender property disappears after edit
- **WHEN** an edited outbound message no longer carries the sender property that was present on create
- **THEN** the adapter continues to determine ownership from the conversation-scoped outbound registry or authoritative sender metadata and does not dispatch an echo solely because that property disappeared

### Requirement: Structured Native Reply Context
The Teams MTK transport SHALL preserve native reply relations, retrieve the exact source message by relation identity, and populate the existing normalized reply context with complete source content when retrieval succeeds.

#### Scenario: Raw reply properties are represented differently
- **WHEN** raw reply properties arrive as an object or a JSON string and quoted-message relations arrive as a list or encoded list
- **THEN** the adapter parses them safely without discarding relation identity or changing the user-visible reply body

#### Scenario: Reply relation is corroborated
- **WHEN** a reply-chain relation is present with quoted-message or blockquote relation fields
- **THEN** the adapter prefers the reply-chain identity, corroborates equivalent relation fields when present, and records sanitized disagreement without selecting an unrelated source

#### Scenario: Complete source is retrievable
- **WHEN** the exact source message can be fetched from the authenticated conversation message resource
- **THEN** the normalized event contains the source message identity and complete canonical source text in its reply context

#### Scenario: Display preview is truncated
- **WHEN** the blockquote preview is shorter than the fetched source
- **THEN** the adapter treats the preview as presentation-only and never promotes it as the complete reply source

#### Scenario: Exact source retrieval fails
- **WHEN** a reply relation identity is known but the exact source cannot be fetched
- **THEN** the event may preserve the relation identity but leaves complete reply text unavailable or explicitly partial rather than fabricating full context

### Requirement: Native Outbound Reply Delivery
When a reply target is supplied, the Teams MTK adapter SHALL use the SDK's native reply operation and SHALL make any relation-losing degradation explicit and duplicate-safe.

#### Scenario: Native reply succeeds
- **WHEN** the SDK supports native reply and the remote operation succeeds
- **THEN** the adapter returns the new message identity, records conversation-scoped ownership, and canonical read-back links the new message to the requested target

#### Scenario: Native reply is unavailable before send
- **WHEN** the SDK or native reply operation is unavailable or explicitly unsupported before a remote side effect can begin
- **THEN** the adapter may send one flat message and returns an observable sanitized degradation signal that the native relation was not preserved

#### Scenario: Native reply outcome is indeterminate
- **WHEN** an exception occurs after the native reply operation may have reached the remote service
- **THEN** the adapter reports delivery uncertainty and does not issue a second flat send
