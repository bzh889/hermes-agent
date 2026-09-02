# Restricted Group Policy

## Problem Statement

As an authenticated Hermes owner, I want to let members of a designated Teams group query and export internal systems (ALPS/MOLY) through my account, but I cannot safely do so today. The existing Teams MTK adapter has a group-whitelist baseline that controls *who gets in* and a coarse `blocked_toolsets` list that controls *which tool categories are visible* — but once a group member's message is admitted, the model can call any enabled tool, send its output to any destination the adapter supports, fall back to a relay when a native route fails, retry without idempotency, resume blindly after restart, route to a non-approved model provider, or access my credentials directly. There is no per-operation capability authority, no origin-bound egress enforcement, no read-only broker for CQ systems, no model-routing gate, no tamper-evident audit, and no durable approval state. An owner who wants to share access with a group must either trust every member with full owner-equivalent power or not share at all.

## Solution

A **Restricted Group Policy** framework that wraps everyRestricted Task in a fail-closed, per-operation capability authority. At gateway ingress, an immutable `OriginEgressBinding` binds the task to its exact profile, policy identity/version, platform, adapter, account/tenant, chat/conversation, thread/topic, and Durable Task identity. A Core-owned **Egress Broker** sits between every outbound emitter and the adapter edge — replies, streams, edits, files, reactions, TTS, cron, delegation results, Kanban notifications, and webhook/API emissions all pass through it. The Broker validates delivery purpose, origin equality, route equality, task liveness, provenance, content fingerprint, and current policy revision; issues a one-use permit; invokes the adapter; and records the outcome. A **CQ Read Broker** exposes exactly seven read-only operations against ALPS/MOLY and denies everything else. An **AIDE-only model-routing gate** reloads the policy revision and matches the complete route identity before every model invocation. A **content-minimized, HMAC-chained audit trail** records fingerprints only — never raw prompts, CQ content, or credentials. A **disposable per-group sandbox** isolates each task. **Durable approval state** survives restarts. **Confidence-gated triage** holds or blocks on production failures. **Semantic history retrieval** stays bound to the exact conversation. The owner explicitly activates production after adversarial E2E passes, and post-deploy probes verify each enforcement seam.

The framework preserves the existing group-whitelist admission baseline — the whitelist controls who gets in; the Restricted Group Policy controls what they can do once admitted. Multiple restricted groups can coexist with independent policies, capability grants, sandboxes, history scopes, and audit streams. If identity is ambiguous, stale, or mismatched, the system fails closed.

## User Stories

1. As a Teams group member, I want to ask Hermes to query ALPS/MOLY data from within my group conversation, so that I get answers without needing my own credentials.
2. As a Teams group member, I want my query results to appear as a reply in the same group conversation, so that I see the answer where I asked the question.
3. As a Teams group member, I want streaming progress updates to appear in the same group conversation, so that I know the agent is working on my request.
4. As a Teams group member, I want to ask follow-up questions in the same conversation and have the agent recall the prior context, so that I don't have to repeat myself.
5. As a Teams group member, I want attachments from prior messages to be visible as previews, so that I can reference shared files in my queries.
6. As a Teams group member, I want to request full attachment content through a broker, so that I can read shared documents without the model directly accessing credentials.
7. As a Hermes owner, I want to designate a Teams group as a Restricted Group, so that its members get bounded capability instead of full owner power.
8. As a Hermes owner, I want to bind a policy version to each restricted group, so that I can update the policy for one group without affecting another.
9. As a Hermes owner, I want to activate production for a restricted group only after adversarial E2E passes, so that I have proof the enforcement works before real users touch it.
10. As a Hermes owner, I want to receive an approval request when a member action requires my authorization, so that I can review and decide before the action executes.
11. As a Hermes owner, I want to approve a request from my Control Channel or TUI, so that I don't have to switch to the group conversation to approve.
12. As a Hermes owner, I want my first approval decision to be immutable, so that a second or conflicting decision cannot override my intent.
13. As a Hermes owner, I want approval state to survive restarts, so that an interrupted approval flow resumes correctly without replaying sensitive content.
14. As a Hermes owner, I want all CQ operations to go through a read-only broker, so that no member can write, mutate, or drop data in ALPS/MOLY.
15. As a Hermes owner, I want the broker to deny raw SQL queries, so that members cannot bypass the seven approved read operations.
16. As a Hermes owner, I want the broker to deny credential access, so that my authentication tokens never appear in the model's context.
17. As a Hermes owner, I want all model invocations to route through AIDE only, so that no third-party provider sees restricted group content.
18. As a Hermes owner, I want the model-routing gate to reload the policy revision before every invocation, so that a stale or tampered revision cannot bypass the gate.
19. As a Hermes owner, I want an audit trail of every enforcement decision, so that I can review what was allowed, denied, and why.
20. As a Hermes owner, I want the audit trail to store fingerprints only, so that raw prompts, CQ content, attachments, and credentials are never persisted.
21. As a Hermes owner, I want the audit trail to be tamper-evident, so that a modified record is immediately detectable.
22. As a Hermes owner, I want each restricted task to run in a disposable sandbox, so that one task's state cannot leak into another.
23. As a Hermes owner, I want the sandbox destroyed at task end, so that temporary storage does not accumulate.
24. As a Hermes owner, I want all outbound emissions to stay in the originating group conversation, so that restricted content never reaches my DM, another group, another platform, or a relay.
25. As a Hermes owner, I want streamed commentary and progress edits to be origin-bound, so that they appear only in the group where the task started.
26. As a Hermes owner, I want reactions and loop mutations to be denied in restricted context, so that the model cannot perform side-effect operations that are not logical delivery.
27. As a Hermes owner, I want cron deliveries to be denied from restricted context, so that a scheduled job cannot fan out restricted content to other destinations.
28. As a Hermes owner, I want delegation results to return through the Egress Broker, so that a subagent cannot bypass the broker by delivering directly.
29. As a Hermes owner, I want Kanban notifications denied from restricted context, so that a restricted task cannot emit to a non-origin channel.
30. As a Hermes owner, I want the Egress Broker to issue one-use permits, so that a permit cannot be replayed for a second operation.
31. As a Hermes owner, I want the Egress Broker to bind permits to the exact destination, route, payload, and revision, so that a permit for one operation cannot be used for another.
32. As a Hermes owner, I want the audit to record intent before the side effect, so that a crash between intent and outcome leaves a traceable `indeterminate` record.
33. As a Hermes owner, I want restart to mark unmatched intents as `indeterminate`, so that reconciliation does not silently assume success.
34. As a Hermes owner, I want the system to fail closed when identity is ambiguous, stale, or mismatched, so that enforcement never degrades to permissive.
35. As a Hermes owner, I want semantic history retrieval bound to the exact conversation ID, so that Group A's history never leaks into Group B's prompt.
36. As a Hermes owner, I want history injected as a standalone user message with an assistant ack separator, so that role alternation and prompt caching are preserved.
37. As a Hermes owner, I want the LLM to judge history relevance itself, so that retrieval is based on meaning rather than mechanical keyword matching.
38. As a Hermes owner, I want attachments to use a two-phase fetch (preview inline, full content via broker), so that the model does not directly handle credential-bearing fetches.
39. As a Hermes owner, I want to de-identify optimization records, so that learning from restricted tasks does not expose member identities or content.
40. As a Hermes owner, I want shared knowledge candidates to expire after 30 days, so that stale learnings do not persist indefinitely.
41. As a Hermes owner, I want to approve promotion of shared knowledge into my PKB, so that I control what enters my personal knowledge base.
42. As a Hermes owner, I want confidence-gated triage to block inferred functions above 90% confidence while letting unrelated operations continue, so that one failure does not halt the entire group.
43. As a Hermes owner, I want operations at or below 90% confidence to hold for 24 hours, so that uncertain failures get human review before any rollback.
44. As a Hermes owner, I want adversarial error text to be unable to escalate authority, so that a crafted error message cannot trick the system into granting higher privileges.
45. As a Hermes owner, I want CQ export to detect duplicates and gaps across changing pages, so that a paginated export does not silently drop or double-count records.
46. As a Hermes owner, I want CQ export to return `INCOMPLETE_RESULT` on any of the eight fail-closed conditions, so that I never receive a silently truncated export.
47. As a Hermes owner, I want a capability descriptor's fingerprint to invalidate on change, so that a modified descriptor cannot claim an old verified capability.
48. As a Hermes owner, I want ambiguous capability classification to fail closed, so that an uncertain capability is denied rather than allowed.
49. As a Hermes owner, I want the production go-live to require my explicit activation, so that the system never enters production mode automatically.
50. As a Hermes owner, I want progressive per-capability version visibility, so that I can activate one capability at a time rather than all-or-nothing.
51. As a Hermes owner, I want a live egress escape matrix with 17 rows as a production-acceptance contract, so that every emitter path is independently verified before go-live.
52. As a Hermes owner, I want a non-egress adversarial matrix with 11 rows, so that CQ broker, capability leakage, model routing, and descriptor spoofing are all independently verified.
53. As a Hermes owner, I want post-deploy probes to verify each enforcement seam in production, so that I know enforcement works under real traffic.
54. As a Hermes owner, I want violations to auto-hold the triggering operation and notify me, so that I can decide whether to resume, stop, or rollback.
55. As a Hermes owner, I want the observation window to end after 30 consecutive violation-free operations, so that I have quantitative evidence of stability.
56. As a Hermes owner, I want contract-test adapters for unsupported dimensions, so that I can test paths that my live environment does not support.
57. As a Hermes owner, I want the audit chain to use SQLite WAL with HMAC-SHA256 linking, so that the audit trail is durable, append-only, and tamper-evident.
58. As a Hermes owner, I want the audit trail to retain records permanently, so that I can always investigate past enforcement decisions.
59. As a Hermes owner, I want multiple restricted groups to coexist with independent policies, so that I can run different groups with different capability grants.
60. As a Hermes owner, I want approval or modification for one group to never change another group, so that group isolation is absolute even when both use the same template.
61. As a Hermes group member, I want my operations to be scoped to my group only, so that I cannot accidentally affect another group's restricted task.
62. As a Hermes group member, I want the agent to understand my follow-up questions in context, so that I can have a natural multi-turn conversation.
63. As a Hermes group member, I want clear error messages when an operation is denied, so that I understand what I can and cannot do in the restricted group.

## Implementation Decisions

### Architecture and Partitioning

1. **Origin binding module** — A new `gateway/restricted_origin.py` module owns the `OriginEgressBinding` class and its ContextVar. The binding is created at gateway ingress (when a message from a restricted group is received) and is immutable for the lifetime of the task. It captures: profile, policy identity, policy version, platform, adapter identity, account/tenant, chat/conversation ID, thread/topic ID, and Durable Task identity. The ContextVar is set in `gateway/session_context.py` alongside the existing platform/chat_id/thread_id ContextVars. The binding class lives in `gateway/` because the binding action occurs at ingress; the data structure is consumed by both the Egress Broker (gateway layer) and the agent's capability resolution (agent layer).

2. **Egress Broker** — A Core-owned module that sits between every outbound emitter and the adapter edge. It is the single choke point for all restricted-context side effects. The Broker: (a) validates delivery purpose — the operation must be a Restricted Logical Delivery purpose (reply, stream, edit, send_message text/media, derived media delivery); (b) validates origin equality — the destination must match the origin binding's conversation/thread; (c) validates route equality — native route only for restricted context; relay route denied; (d) validates task liveness — the Durable Task must be active; (e) validates content provenance — sealed provenance-aware media; (f) checks current policy revision — stale revision fails closed; (g) persists an `EgressIntent` record (intent phase) to the audit DB before invoking the adapter; (h) issues a one-use permit bound to exact operation, destination, route, payload fingerprint, and policy revision; (i) invokes the adapter; (j) records the structured outcome and actual remote handle (outcome phase). Adapters deny restricted-context calls that lack a valid permit.

3. **CQ Read Broker** — A host-side, credential-owning broker that exposes exactly seven read-only operations (ALPS/MOLY query, page, export, search, filter, sort, aggregate). denies: raw-query, mutation (INSERT/UPDATE/DELETE), credential access, and any operation not in the seven. All member-credentialed access goes through the broker; the model never sees the owner's credentials. The broker authenticates to the CQ system using the owner's credentials but does not expose them to the restricted task's model context.

4. **Model-routing gate** — An `authorizeAndInvoke` function called before every model invocation in restricted context. It: (a) atomically reloads the current policy revision; (b) matches the complete route identity (provider, model, base_url, route class) against the policy's allowed AIDE routes; (c) denies on any mismatch; (d) denies if the revision changed since the permit was issued. Non-AIDE providers never pass. The gate is stateless between invocations — it holds no cached revision.

5. **Audit chain** — SQLite WAL mode, append-only, HMAC-SHA256-chained records. Each record stores: sequence number, previous record HMAC, intent/outcome phase, decision (allow/deny), reason, operation type, destination fingerprint, content fingerprint, policy revision, timestamp. No raw prompts, CQ content, attachments, generated code, or credentials. Write-before-execute: the intent phase record is committed before any restricted side effect. On restart, unmatched intent records (no corresponding outcome) are marked `indeterminate`. Records are retained permanently. The audit DB lives under `get_hermes_home() / "audit" / "restricted_group.db"`.

6. **Disposable per-group sandbox** — Each restricted task gets a fresh, policy-stamped sandbox. All credentialed access is brokered. The sandbox is destroyed at task end. No state persists between tasks. The sandbox boundary is the Durable Task identity — one task, one sandbox.

7. **Durable approval state** — Owner approval is a metadata-only Durable Task. First-wins: the first owner decision is immutable; subsequent decisions for the same task are rejected. Zero raw sensitive persistence — only fingerprints and metadata are stored. Restart reconciles completion by matching intent/outcome records, not by replaying the approval flow.

8. **Confidence-gated production failure triage** — On a production failure: (a) >90% confidence that the failure is in the inferred function → block the inferred function, allow unrelated operations to continue; (b) ≤90% confidence → hold the triggering operation for 24 hours; (c) adversarial text in error messages cannot escalate authority — error text is treated as untrusted input, never as an instruction.

9. **Privacy-preserving learning** — De-identified Optimization Records capture what worked (strategy, outcome) without member identities or raw content. Shared Knowledge Candidates have a 30-day expiry. Promotion into the owner's PKB requires explicit owner approval. No auto-ingestion of Monitor Group content.

10. **CQ export consistency** — Stable sort key + duplicate detection + gap detection across paginated exports. Eight fail-closed conditions (page boundary mismatch, sort key change, duplicate key, gap in sequence, count mismatch, schema drift, timeout, partial page) → `INCOMPLETE_RESULT` with diagnostic metadata.

11. **Exact-group semantic history retrieval** — Reply-chain traversal (backwardLink pagination) first, then sliding-window recent messages. No mechanical pre-filter — the LLM judges relevance of each retrieved message. Attachments appear as inline previews; full content requires a two-phase broker fetch (preview → broker). No redaction. History is injected as a standalone user message followed by an assistant ack separator, preserving role alternation and prompt caching. Identity is bound to the exact `conv_id` — no cross-conversation fan-out. Three-layer forced marker tests verify zero leakage: (1) API-level marker presence in correct conversation only, (2) red marker visible in origin group but absent in cross-group, (3) dual-group cross-injection attempt denied.

12. **Capability descriptor fingerprinting** — Capability descriptors carry a fingerprint computed from their schema evidence (not prose description). Ambiguous classification fails closed. A fingerprint change invalidates the descriptor's verified status.

13. **Owner approval protocol** — Profile-local canonical request with Control Channel and TUI projections. Immutable first-wins. Metadata-only restart. PII/NDA content authorizes one exact-payload, exact-destination logical delivery — the authorization is bound to the specific content and destination, not to a category.

14. **Production go-live gate** — Exact owner activation (no auto-activation). Scoped defect acceptance (owner accepts a specific, evidenced implementation-defect risk). Progressive per-capability version visibility (activate one capability at a time). Selective failure triage (confidence-gated, not all-or-nothing).

15. **Egress Escape Matrix (17 rows)** — Each row tests one emitter path: (1) final reply — exact origin ALLOW; (2) streamed commentary — ALLOW; (3) send_message text — ALLOW; (4) send_message media — ALLOW; (5) reaction — DENY; (6) loop mutation — DENY; (7) native route — ALLOW; (8) relay route — ALLOW; (9) automatic MEDIA delivery — ALLOW; (10) TTS — ALLOW; (11) document delivery — ALLOW; (12) cron fan-out — DENY; (13) cron mirroring — DENY; (14) delegated/background completion — DENY (must return through broker); (15) Kanban notification — DENY; (16) plugin/webhook/API emitter — per policy; (17) future registered adapter — per policy. Each row verifies: safe pre-gate reachability, policy-defined outcome, forced cross-group denial, independent source-and-target readback with unique markers, restart reconciliation, same-identity retry only after confirmed absence, and cleanup.

16. **Non-egress adversarial E2E matrix (11 rows)** — (1) CQ broker INSERT → DENY; (2) CQ broker UPDATE → DENY; (3) CQ broker DELETE → DENY; (4) Group A operation affects Group B → DENY; (5) Group A history injected into Group B → DENY; (6) Group A descriptor read by Group B → DENY; (7) Forged route identity → DENY; (8) Stale policy revision → DENY; (9) Gate-check-and-switch race → DENY; (10) Forged descriptor capability → DENY; (11) Tampered descriptor fingerprint → DENY.

17. **Production rollout** — Production Monitor Group is the existing test group `19:cbdcf6224c48469ea048147752ed92d9@thread.v2`. Per-seam independent probes verify each enforcement seam. Compensation: auto-hold the violating operation + owner notification; policy continues running. Observation window: 30 consecutive violation-free operations.

18. **Implementation sequence** — Five phases: (1) origin binding + ContextVar; (2) Egress Broker core; (3) adapter wiring; (4) CQ Read Broker + execution sandbox; (5) approval, audit, resume, learning, triage, history. Four test layers: unit → integration → adversarial → E2E. Strict layer-gated progression (phase N must pass all layers before phase N+1 starts). E2E runs only at Phase 3 (adapter wiring) and Phase 5 (full integration).

### Security model

19. **Fail-closed by default** — If identity is ambiguous, stale, or mismatched; if the policy revision is stale; if the descriptor fingerprint does not match; if the permit is invalid or already used; if the audit DB is unavailable; if the route identity does not match — deny. No silent degradation to permissive.

20. **Owner credentials isolation** — The owner's CQ credentials are used by the CQ Read Broker to authenticate to the CQ system but are never present in the model's context, the sandbox, the audit trail, or the group conversation. The model interacts with the broker's API, not with credentials.

21. **Cross-group isolation** — Each restricted group has its own policy, capability grants, temporary elevations, sandbox, history scope, and audit stream. ContextVar isolation prevents cross-session descriptor access. Semantic history retrieval is bound to exact `conv_id`. Origin binding prevents cross-group task influence.

## Testing Decisions

### Testing philosophy

Only test external behavior, not implementation details. A good test asserts how two pieces of data must relate (invariants), not what a current value happens to be. Tests must not read source files. Tests must not be change-detectors (asserting on model lists, config version numbers, or enumeration counts). Tests must exercise the real path with real imports against a temp `HERMES_HOME` — mocks hide integration bugs.

### Test layers

1. **Unit tests** — Pure logic: OriginEgressBinding immutability, permit one-use enforcement, audit HMAC chain validation, CQ broker operation classification (read vs. write), capability descriptor fingerprint computation, CQ export duplicate/gap detection, confidence-gated triage threshold (>90% block, ≤90% hold), 30-day expiry calculation, first-wins approval logic.

2. **Integration tests** — Multi-module assembly: gateway ingress → origin binding → ContextVar → Egress Broker → adapter mock; CQ broker → mock CQ system → result; model-routing gate → mock AIDE provider → invoke/deny; audit chain → intent → outcome → restart → indeterminate reconciliation; semantic history → mock conversation → retrieval → prompt injection → role alternation.

3. **Adversarial tests** — The 17-row egress escape matrix and 11-row non-egress adversarial matrix, executed against real adapters and contract-test adapters for unsupported dimensions. Each row asserts: the policy-defined outcome (ALLOW or DENY), no side effect on deny targets (verified by independent readback), unique UUID markers in test messages, and audit records matching the decision.

4. **E2E tests** — Real Teams group send/receive with API readback, run only at Phase 3 (adapter wiring) and Phase 5 (full integration). Uses the existing test group as origin and the owner DM as deny target. Contract-test adapters simulate unsupported dimensions (alternate platform, alternate account, webhook).

### Tested modules

- Origin binding (`gateway/restricted_origin.py`) — unit + integration
- Egress Broker — unit + integration + adversarial (egress matrix) + E2E
- CQ Read Broker — unit + integration + adversarial (non-egress matrix rows 1-3)
- Model-routing gate — unit + integration + adversarial (non-egress matrix rows 7-9)
- Audit chain — unit + integration (restart reconciliation)
- Execution sandbox — integration (disposal verification)
- Durable approval — unit + integration (restart-safe resume)
- Confidence-gated triage — unit (threshold logic)
- Semantic history retrieval — integration + adversarial (non-egress matrix rows 4-5) + E2E (three-layer forced marker tests)
- Capability descriptor — unit + adversarial (non-egress matrix rows 10-11)
- CQ export consistency — unit (duplicate/gap detection)

### Prior art

- Existing Teams MTK E2E tests: `openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py` — pattern for real-gateway E2E assertions with API read-back, truthful failure handling, and cleanup.
- Existing `gateway/session_context.py` ContextVar pattern — prior art for origin binding ContextVars.
- Existing `agent/execution_authority.py` — prior art for capability resolution and fail-closed authority.
- Existing `tests/conftest.py` `_isolate_hermes_home` autouse fixture — prior art for temp `HERMES_HOME` in tests.
- Existing `tests/gateway/` test suite — prior art for gateway integration tests.

## Out of Scope

- Monitor Group CQ mutation or external writes to ALPS/MOLY (all CQ access is read-only).
- Exposing owner credentials to the model, sandbox, audit, or group conversation.
- Changing the authenticated owner's local CLI/TUI full permissions (owner always has full power locally).
- Auto-ingesting Monitor Group content into the owner's PKB or Mem0 (promotion requires explicit owner approval).
- Modifying the `teams-mtk-group-whitelist` admission/mention/config baseline (preserved, not replaced).
- Modifying the `teams-mtk-hermes-native-parity` transport/streaming/reply/file/forward behavior contracts.
- Modifying the `Executable Skill Strategies` Execution Authority, Capability Provider, Core guardrail, descendant-authority, and fail-closed vocabulary (RGP extends, not redefines).
- Third-party products or external projects integrated into the core tree.
- Outbound telemetry or usage attribution without opt-in gating.

## Further Notes

- The map's Notes specified: "Once the Wayfinder decision/prototype frontier and remaining fog are clear, run `/to-spec` to synthesize a new cross-cutting `restricted-group-policy` OpenSpec change that cites those baselines, then `/to-tickets` before implementation." This spec fulfills that directive. 21 decision tickets (01-08, 09-16, 18, 20, 21, 22) were resolved through the Wayfinder workflow before this spec was synthesized.
- The existing `teams-mtk-group-whitelist` change is the completed admission/mention/config/toolset/keyword baseline. The existing `teams-mtk-hermes-native-parity` change owns Teams transport, streaming/reply/file/forward behavior and named real E2E. The existing `Executable Skill Strategies` spec owns the generic Execution Authority, Capability Provider, Core guardrail, descendant-authority, and fail-closed vocabulary. This spec cites all three as baselines and does not duplicate their requirements.
- The framework supports multiple Restricted Groups with independent effective permissions. The owner binds each exact tenant/conversation fingerprint to its own policy/version, Capability Grants, Temporary Elevations, sandbox, history scope, and audit stream. Approval or modification for one group never changes another group, even when both began from the same template.
- Implementation follows the five-phase sequence defined in ticket 20. Each phase must pass all applicable test layers before the next phase begins. E2E tests run only at Phase 3 (adapter wiring) and Phase 5 (full integration).
- The live egress escape matrix (ticket 18, 17 rows) and non-egress adversarial E2E matrix (ticket 22, 11 rows) serve as production-acceptance contracts. Both use the existing test group as origin and contract-test adapters for unsupported dimensions.
- Production rollout uses the existing test group as the production Monitor Group. Post-deploy probes verify each enforcement seam independently. Violations auto-hold the triggering operation and notify the owner. The observation window ends after 30 consecutive violation-free operations.
