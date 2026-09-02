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

**Capability Descriptor**:
The registration-time semantic declaration that names and versions an operation and supplies the fixed Core policy dimensions: action, resource class, data/sensitivity class, effect class, normalized target scope, and execution or egress authority domain. A descriptor may add namespaced typed attributes, but extensions cannot omit or redefine the Core envelope and policy selectors may match only registered, validated fields.
_Avoid_: Tool name, toolset membership, free-form permission label, policy rule

**Implementation Fingerprint**:
A stable digest and version identity for the exact executable operation and its classification evidence, including the validated schema, manifest/provider identity, and relevant implementation source. Capability Grants and approved inferred classifications bind this fingerprint; any relevant change invalidates that authority before the next execution. The fingerprint contains no source text, credentials, or sensitive payload.
_Avoid_: Tool display name, package label alone, model-authored hash, whole-plugin permission

**Inferred Capability Proposal**:
A non-authoritative classification Hermes derives for an operation that lacks a valid Capability Descriptor, using available schema, description, manifest/source evidence, and argument shape. The task remains paused until the owner approves the exact function and resource scope for one group; approval binds the implementation/version fingerprint, and any change invalidates it for reclassification.
_Avoid_: Automatic permission, trusted documentation, whole-plugin approval, default read-only classification

**Capability Request**:
The structured, per-operation authorization fact produced from a Capability Descriptor, normalized target and typed runtime attributes, and trusted policy, origin, principal, task, and parent-operation context. A Restricted Group Policy matches selectors against this request before the operation can execute; tool and provider names are evidence, not the authorization vocabulary.
_Avoid_: Tool call, model-supplied permission, session-wide grant, opaque capability string

**Authority Chain**:
The per-operation lineage in which every direct or indirect executable boundary recomputes effective authority as the intersection of its parent authority, current policy revision, matching grant or elevation, and Core guards. A child operation may preserve or narrow authority but never widen it.
_Avoid_: Top-level request approval, trusted plugin internals, inherited blanket permission

**Capability Grant**:
An owner-approved policy entry that permits a declared operation and resource scope only for one exact Restricted Group Policy and its bound Teams group. A grant never applies to another group, policy, profile, or the global Hermes installation.
_Avoid_: Global tool enablement, plugin approval, user role, session permission

**Persistent Denial**:
An owner-confirmed policy entry that rejects one explicit reusable selector for one exact Restricted Group Policy until owner revocation. It may be created only through a Deny-always scope proposal and second confirmation; it never expands from an exact request into an inferred class of similar requests.
_Avoid_: Deny once, fuzzy similarity block, global tool disablement, hidden deny rule

**Temporary Elevation**:
An owner-issued increase in authority for one exact durable task, restricted group, function, and resource scope, requested and approved through an authoritative Approval Surface. It does not rewrite the group's persistent Capability Grants or baseline policy, survives process restart with that task, and expires only when the task completes, aborts, or merges, or when the owner revokes it. It never transfers to a merged target, queued, or subsequent task. It may permit a scoped private-data read, but never credential or secret exposure, and all resulting data retains provenance, origin-bound egress, and audit constraints.
_Avoid_: Permanent grant, global override, owner impersonation, credential sharing

**Control Channel**:
An owner-designated exact Teams conversation outside Restricted Group Policy. Authenticated owner requests have full owner authority in every channel; non-owner Control Channel members receive full operational authority but not owner identity or owner-only governance. Ordinary owner-private PII/NDA content requires owner release before multi-member egress, while a pending approval request may show its exact sensitive decision payload there as an owner-designated management exception. Plaintext credential/auth output is never allowed in a multi-member Teams conversation.
_Avoid_: Restricted Group, owner impersonation, global policy approval surface, credential-sharing channel

**Approval Surface**:
One of the two owner-authorized policy-management entry points: the exact owner-designated Control Channel or the local TUI. Both may display the type-specific exact decision payload, including PII, NDA, or owner-private content but never plaintext credentials or auth secrets, and may decide the same request. Only an authenticated owner decision is valid, the first accepted terminal decision wins, and every other surface becomes a resolved mirror. Other conversations may carry owner operational requests but cannot submit Approval Request or revocation decisions.
_Avoid_: Any owner conversation, restricted-group reply, non-owner Control Channel vote, duplicate approval queue

**Approval Request**:
The single durable, active-profile-local record of one owner decision needed by a suspended operation or governance action. It has one opaque identity, exact requesting group/principal/task and approval type, fingerprints for the type-specific decision payload and proposed scope/lifetime, bound policy/descriptor/source revisions, and one lifecycle state. Raw sensitive payloads are not persisted and are re-fetched after restart. Control Channel, local TUI, and the sanitized originating-group status are projections of this record, not independent requests.
_Avoid_: Chat notification, duplicate per-surface request, raw context bundle, model-authored permission

**Activation Evidence Manifest**:
The itemized, fingerprinted proof bundle for one exact production activation proposal. It records real allow-path, deny-path, restart/isolation, side-effect, audit, cleanup, and rollback results plus independent read-back; a skipped, zero-case, missing, or unreadable required result is unknown and ineligible. Complete evidence does not age by time alone, but any bound program, policy, configuration, profile, test-definition, or test-environment change invalidates it.
_Avoid_: CI badge, mutable release checklist, stale test summary, owner guess

**Production Activation Proposal**:
An immutable active-profile-local governance proposal binding one exact program and policy version, implementation, effective configuration, Activation Evidence Manifest, production group fingerprint, verified rollback target or exact accepted rollback-readiness failure, and accepted Owner Risk Exceptions. Automation may create it but only the authenticated owner may activate it through an Approval Surface; any bound change supersedes it.
_Avoid_: Automated deployment permission, reusable approval, group template, mutable candidate

**Owner Risk Exception**:
An authenticated owner governance decision accepting one fully evidenced implementation-defect risk for one exact profile, production group, policy/build version, function, failure, consequence set, and owner-selected expiry no later than that version's retirement. It may permit first activation or direct resume despite a confirmed runtime violation, but never covers missing evidence or a new failure, never transfers scope, remains audited and revocable, and does not grant Monitor Group members a prohibited capability.
_Avoid_: Capability Grant, unknown-risk waiver, blanket approval, member permission, unauthenticated override

**Progressive Production Activation**:
An owner-approved rollout in which capability slices become member-visible after each slice is durably installed and read back, while every admitted operation remains pinned to one complete policy version. Restart may continue only the unchanged, idempotent activation journal; a single operation never mixes old and new policy versions.
_Avoid_: Atomic whole-policy cutover, mixed-version operation, locked production canary, blind restart retry

**Production Failure Triage**:
The post-opening control path that blocks a demonstrated failed function, or asks an approved AIDE-routed LLM to infer the most likely function when scope is uncertain. A self-reported confidence strictly above 90 percent blocks the inferred function; lower confidence holds only the triggering operation for owner decision while other work continues. It is failure containment, not request authorization or a Capability Grant.
_Avoid_: Deterministic authorization, whole-service auto-rollback, silent fail-open, capability classification

**Owner Decision**:
The first authenticated-owner terminal answer accepted for one pending Approval Request. It is immutable and idempotent under exact retry; a later opposite owner intent creates a new governance request against current authority rather than rewriting the earlier decision or its side effects.
_Avoid_: Last-write-wins history, mutable approval card, non-owner vote, retroactive rollback

**Capability Effect**:
One security-relevant consequence of a Capability Request. Core effects are `read`, `compute`, `ephemeral_write`, `durable_internal_write`, `external_mutation`, `egress`, `authority_spawn`, `credential_use`, `credential_maintenance`, `policy_admin`, and `secret_exposure`. Effects are orthogonal and composable: every effect on a request must be authorized, any denied effect denies the operation, and any unclassified effect makes the request unknown rather than allowing a primary read or low-risk label to mask it. Secret exposure is never grantable, while policy administration always requires owner authority.
_Avoid_: Primary effect, linear risk score, tool risk level

**Data Provenance Label**:
A source label carried by runtime values and artifacts: `public`, exact `origin_group`, scoped `brokered_policy_data`, scoped `owner_private`, `policy_control`, `task_generated`, or `unknown`, plus orthogonal `pii`, `nda_confidential`, and `secret` sensitivity flags. Outputs inherit the union of every input label plus producer labels; no model reasoning, summary, transform, tool, or format conversion lowers classification implicitly. Label removal requires a separately registered and authorized declassifier, and the first Restricted Group Policy version provides none.
_Avoid_: Single highest-risk label, resource-only classification, model-decided declassification

**Optimization Record**:
A de-identified structured record of restricted-group capability use, outcome, failure, correction, or feedback that can inform later skill and provider improvement without retaining raw prompts, Teams or CQ content, PII, NDA text, credentials, or attachments. Creating a record does not grant the originating group turn write authority over skills, source code, providers, or the owner's PKB.
_Avoid_: Conversation transcript, automatic skill edit, content archive, user telemetry dump

**Shared Knowledge Candidate**:
A content-bearing, provenance-preserving proposal derived from restricted-group work for explicit owner review. It is not part of the owner's PKB until the owner approves that exact candidate through an owner-authorized surface.
_Avoid_: Automatic PKB ingest, de-identified optimization record, group memory

**Restricted Group Policy**:
A reusable, fail-closed authorization contract bound to one exact group conversation that narrows non-owner turn authority across tools, providers, data sources, execution environments, and outbound destinations. Multiple Restricted Groups coexist with independent effective policies, grants, elevations, storage, history scopes, and audit streams; no approval or modification propagates between groups implicitly. Mention gating or a toolset blocklist alone is not a Restricted Group Policy.
_Avoid_: Group whitelist, blocked toolsets, prompt rule

**CQ Read Broker**:
The credential-owning Capability Provider that exposes only non-mutating ALPS and MOLY operations authorized by a Restricted Group Policy. It never delegates the owner's credential, cookie, arbitrary URL access, or a general command surface to the agent or its sandbox.
_Avoid_: crtool shell access, browser login, CQ skill instructions

**Durable Task**:
A stable restricted-work identity and metadata state that spans process restarts from creation until the task completes, aborts, or explicitly merges into another task. Approval Requests, content fingerprints, operation journals, and Temporary Elevations bind to this identity, while raw sensitive content is re-fetched under current authority; a merge terminates the source task and never transfers its elevation to the target.
_Avoid_: Process, agent loop, queue message, resumable session without task identity

**Ephemeral Task Sandbox**:
A disposable execution boundary created for one restricted task, without access to host files or owner credentials, whose only durable outputs are policy-authorized results and whose filesystem is destroyed at task termination.
_Avoid_: Working directory, temporary filename, project workspace

**Origin-Bound Egress**:
An outbound authority bound at restricted ingress to the active profile, Restricted Group Policy identity, exact native-or-relay transport route, platform adapter/account/tenant, exact chat or conversation, normalized thread/topic (or an explicit none value), and Durable Task. Every outbound side effect must prove exact route and destination equality and re-authorize against the current policy revision immediately before delivery; the ingress revision is audit evidence, not frozen authority. If Hermes cannot prove the origin, route, or destination identity, delivery fails closed, and a failed native or relay route never falls back to another route automatically.
_Avoid_: Group-only binding, transport failover, frozen ingress permission, forward allowlist, home channel, messaging prompt rule

**Restricted Logical Delivery**:
One policy-authorized outbound purpose from a Durable Task: its Primary Reply, one Requested Artifact bound by task and content fingerprint, one policy-authorized Derived Media Delivery, or a Minimal Status Notice that contains no protected source content. A Primary Reply has one remote text-message identity: reliable progress/edit/final operations update that handle; a platform without reliable edit sends only final, and an uncertain edit is reconciled rather than replaced by a new message. Derived media is a child delivery with its own Egress Intent and remote handle, not an edit fallback. `send_message`, relay, cron, delegated work, background completion, media extraction, and TTS are emitters or producers, not independent delivery authority; they must return through the task's Origin-Bound Egress gate, and delayed output is ineligible after the task terminates.
_Avoid_: Code-path permission, append-as-edit fallback, arbitrary same-group send, direct subagent delivery, post-task cron result, unjournaled media child

**Minimal Status Notice**:
A fixed, content-free originating-group message that reports only that a restricted operation paused, was denied, failed, or has an indeterminate delivery, plus an opaque correlation reference. It never names another destination, exposes protected labels or payload, or retries when the exact origin route itself is unavailable; the detailed reason, policy revisions, fingerprints, adapter-invocation verdict, and confirmed-absence evidence belong only in the content-minimized immutable audit.
_Avoid_: Error dump, blocked target disclosure, sensitive classification disclosure, status-route fallback

**Egress Intent**:
The durable pre-side-effect record for one Restricted Logical Delivery. It binds the delivery purpose, Durable Task, exact origin, operation, payload/provenance/artifact fingerprints, current policy revision, and one idempotency identity, then records the real remote message or file handle. After timeout or restart, Hermes reconciles the intent through independent exact-origin platform read-back; a confirmed existing delivery is adopted, a proven absent delivery may be retried with the same identity, and an indeterminate outcome is never resent or rerouted automatically.
_Avoid_: Send-first journal, blind restart replay, new retry identity, adapter fallback after uncertain outcome

**Egress Broker**:
The Core-owned sole outbound side-effect boundary for a Restricted Task. Producers submit a Restricted Egress Candidate; the broker reloads current authority, validates the exact Origin-Bound Egress identity and delivery purpose, persists the Egress Intent, and issues a one-use permit for the exact adapter operation, destination, and payload fingerprint. Restricted adapters, relays, uploads, edits, and network emitters deny calls without that permit and return structured outcome plus the actual remote handle; plugins and code paths never make their own policy decision.
_Avoid_: Per-adapter policy, reusable permit, final-reply-only check, direct restricted network send

**Egress Escape Matrix**:
The production-acceptance proof covering every real final reply; streamed commentary, segment, progress/edit, and typing/activity operation; explicit `send_message` text/media/reaction/unreaction/Loop operation; native/relay transport; automatic `MEDIA:`/bare-path/TTS/image/audio/video/document delivery; cron fan-out and mirroring; delegated or terminal-background completion; Kanban notification/artifact; and any plugin, webhook, API, or future adapter emitter reachable from a Restricted Task. Each path is tested for its policy-defined exact-origin outcome plus attempted cross-group, DM, platform, thread/topic, and native/relay-route escape: the four Restricted Logical Delivery purposes may succeed, while arbitrary sends, reactions, Loop mutations, fan-out, and post-task output remain denied even at exact origin. Every row proves safe pre-gate reachability, denial before adapter invocation where denial is expected, independent source-and-target read-back with unique markers, uncertain-outcome/restart idempotency, and cleanup; shared-broker tests, mocks, logs, or sampled paths cannot substitute for a row.
_Avoid_: Representative-only E2E, log-only denial, unverified target, stale PASS, mock-only escape proof

**Requested Artifact Snapshot**:
The immutable exact bytes used by a Requested Artifact or Derived Media Delivery, sealed inside the active Ephemeral Task Sandbox before upload with content hash, detected media type, size, and complete Data Provenance Labels. Egress authorizes that snapshot—not a mutable path—against the current policy and exact origin; symlinks, junctions, external files, later byte changes, and unknown provenance fail closed. A successful upload records the remote file handle, while local staging remains cleanup-bound to the Durable Task.
_Avoid_: Upload by live path, host-file attachment, post-check mutation, provenance-free export

**Derived Media Delivery**:
A policy-authorized exact-origin child of a Primary Reply created automatically from a `MEDIA:` directive, a task-sandbox path, TTS, or another media post-processor even when the member did not explicitly request that representation. It receives no path-based authority: the bytes must first become a Requested Artifact Snapshot, retain the Primary Reply's provenance plus producer labels, pass the current-policy check, and use a separate durable Egress Intent and one-use permit. Automatic extraction never authorizes a host/external path, mutable bytes, unknown provenance, a destination or route change, or delivery after the Durable Task terminates.
_Avoid_: User-request fiction, path-implies-authority, host-file auto-upload, unbound TTS, implicit destination fallback

**Restricted Egress Candidate**:
The immutable exact text or bytes proposed for a Restricted Logical Delivery, carrying the union of all source and producer Data Provenance Labels. `secret`, `policy_control`, or `unknown` blocks originating-group delivery; owner-private, PII, or NDA content requires the existing exact-payload/exact-destination owner decision; ordinary policy-authorized public, origin-group, brokered-policy, and task-generated content may proceed. Model editing, summarization, or omission never declassifies a blocked candidate; only a separately constructed content-free Minimal Status Notice may report the block.
_Avoid_: Surface-text scan, model redaction, partial-send fallback, unlabeled edit

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
