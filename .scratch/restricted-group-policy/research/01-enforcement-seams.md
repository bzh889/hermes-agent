# Restricted Group Policy: executable enforcement seams

## Resolution

Hermes has reusable primitives for trusted turn identity, Teams MTK group admission, tool-schema scoping, dispatch middleware, approval transport, and exact-conversation Teams history. It does **not** yet have a Restricted Group Policy authority that survives every execution domain and re-checks every operation, a capability registry, a CQ read broker, an isolated per-group workspace, an origin-bound egress gate, or an AIDE-only model gate.

The minimal route is to extend those primitives. Keep the map's capability deny-list: private reads and non-exempt writes fail closed; classified non-private reads remain allowed; an unknown capability pauses for authenticated owner approval. Toolsets remain defense-in-depth exposure control, not the authorization model.

## Scope and evidence method

This investigation traced current executable source and behavioral tests. A citation proves only the adjacent factual claim. Design recommendations are labeled **Recommendation**; behavior requiring a live gateway, real CQ, or side-effect readback is labeled **Requires E2E**.

Excluded as executable evidence: documentation, skills, schemas without dispatch inspection, filenames alone, comments about intended behavior, and the two earlier self-verification reports. No credential/config secret was read from `myCRDump`.

## Existing executable call path

1. `SessionSource` carries platform, chat, user, thread, message, and relay trust metadata, but no Restricted Policy id/version: `gateway/session.py:148-179`.
2. A Teams MTK group key under `gateway.teams_mtk.groups` authorizes every sender in that exact group; missing/invalid config fails closed: `gateway/authz_mixin.py:179-203`, `gateway/authz_mixin.py:465-477`.
3. The adapter enforces `@hermes` for normal group messages while recognized control commands bypass the mention gate: `gateway/platforms/teams_mtk.py:5452-5479`. `/stop`, `/new`, `/reset`, `/approve`, and `/deny` are tested as active-session bypass commands: `tests/gateway/e2e/test_teams_mtk_e2e.py:991-1000`.
4. Gateway binds origin identity into task-local ContextVars before tool execution. The current binding includes platform/source/chat/user/session/cwd, but no policy id/version: `gateway/session_context.py:123-161`, `gateway/session_context.py:179-238`.
5. `current_execution_authority()` recomputes authority from the bound turn, fails closed when a hosted turn has no bound origin, and recognizes only local owner surfaces plus the exact configured Teams control conversation/owner pair: `agent/execution_authority.py:84-149`. The current enum has only `skill_write` and `contract_execute`: `agent/execution_authority.py:14-37`.
6. Tool schemas are assembled from enabled/disabled toolsets: `model_tools.py:288-310`. Core defaults include terminal, process, file, browser, memory, session search, code execution, delegation, and cron: `toolsets.py:29-81`.
7. Deferred `tool_call` is scoped to the same session toolsets and recursively dispatches the real tool name: `model_tools.py:1141-1203`. Behavioral tests reject an out-of-scope registered plugin tool: `tests/tools/test_tool_search.py:511-586`.
8. Concurrent and sequential tool paths unwrap deferred calls and invoke tool request middleware before hooks/guardrails/dispatch: `agent/tool_executor.py:411-473`, `agent/tool_executor.py:1106-1139`. Agent-level context-engine and memory-provider tools also run through tool execution middleware: `agent/tool_executor.py:1449-1508`.
9. Registry calls receive the session toolsets at dispatch: `agent/tool_executor.py:1527-1580`. The dispatcher rechecks deferred scope and supports request middleware and blocking plugin hooks: `model_tools.py:1170-1203`, `model_tools.py:1205-1273`.

## Enforcement seam verdicts

### Reusable

- **Turn origin binding.** Extend `set_session_vars()` with immutable `policy_id`, `policy_version`, `origin_chat_id`, and principal fingerprint; preserve nested reset semantics. The existing ContextVar isolation is designed to prevent cross-session identity leaks: `gateway/session_context.py:241-301`.
- **Per-operation authority resolution.** Extend `ExecutionAuthority` and resolve from trusted bound context plus the current durable policy revision on every operation. Existing authority is not model-supplied and exact Teams owner/control matching is already fail closed: `agent/execution_authority.py:1-6`, `agent/execution_authority.py:48-81`.
- **Tool request/execution middleware.** A core-owned policy callback can classify the real tool and normalized arguments immediately before execution. The middleware contract supports request rewriting and wrapping the actual callback: `hermes_cli/middleware.py:120-162`, `hermes_cli/middleware.py:192-209`.
- **Tool exposure.** Toolsets can hide high-risk families from schema and deferred search. Existing group/per-user blocked-toolset merging is tested: `gateway/authz_mixin.py:205-240`, `tests/gateway/test_teams_mtk_group_whitelist_authz.py:165-210`.
- **Owner approval transport.** Approval state already binds session, turn, and tool-call ids in ContextVars: `tools/approval.py:35-52`, `tools/approval.py:171-214`. Reuse the gateway/TUI prompt transport and correlation, not dangerous-command heuristics or smart/YOLO approval policy.
- **Exact-group Teams history primitive.** `_fetch_messages(conv_id, limit=None)` selects the supplied conversation and SDK pagination; attachment metadata is normalized: `gateway/platforms/teams_mtk.py:4522-4551`, `gateway/platforms/teams_mtk.py:4799-4840`.
- **Plugin/MCP registry routing.** Plugin tools register into the shared registry and toolset: `hermes_cli/plugins.py:390-447`. MCP tools likewise register with a per-server toolset: `tools/mcp_tool.py:5535-5557`. They can use the shared dispatcher once capability metadata is mandatory.

### Partial, not security boundaries yet

- Group `blocked_toolsets` is fail-open on config read failure and is session-static; it cannot implement immediate revocation or unknown-capability approval: `gateway/authz_mixin.py:205-240`.
- Tool request middleware can rewrite arguments, while execution middleware can wrap execution, but plugin-registered middleware is operator code and not itself the immutable policy root: `hermes_cli/plugins.py:1176-1195`.
- Browser SSRF and website policy checks are useful defense-in-depth, but private-address blocking is intentionally skipped for local backends: `tools/browser_tool.py:2838-2889`.
- Terminal dangerous-command approval is a command heuristic, and `force` is an internal bypass after confirmation; it is not a capability decision: `tools/terminal_tool.py:2100-2144`.
- File resolution accepts absolute paths. A relative path outside the workspace produces a warning, then writes the resolved absolute path: `tools/file_tools.py:364-398`, `tools/file_tools.py:1623-1639`.
- Process tracking is in-memory and completion notifications create later turns; process records do not carry a policy revision: `tools/process_registry.py:147-185`.

### Missing or proven escape domains

- **Capability registration:** built-in, plugin, MCP, context-engine, and memory-provider operations have no mandatory `(capability, read/write, resource, egress)` descriptor. Unknown tools therefore cannot fail closed by classification.
- **Delegation propagation:** a child gets inherited provider/fallback/toolsets and fresh `AIAgent`, but no Restricted Policy token/version: `tools/delegate_tool.py:1330-1407`. Its fixed blocklist removes messaging, memory, cron, clarify, and recursive delegation, but still permits terminal/file/browser/code according to child toolsets: `tools/delegate_tool.py:45-54`.
- **Cron propagation:** cron constructs a fresh agent with independent provider/fallback/toolsets, discovers MCP, and sets `skip_memory=True`, but carries no originating Restricted Policy authority: `cron/scheduler.py:3505-3558`. Existing tests prove disabled toolsets are inherited, not policy authority: `tests/cron/test_scheduler.py:1591-1620`.
- **Model routing:** auxiliary auto-routing can use main provider, configured fallback, then a built-in provider chain: `agent/auxiliary_client.py:4660-4722`. Tool middleware does not constrain this chain.
- **Origin-bound egress:** normal delivery chooses native or relay transport using an arbitrary logical platform/chat id: `gateway/delivery.py:74-131`; `send_message` accepts and parses an explicit caller-supplied target: `tools/send_message_tool.py:358-430`, `tools/send_message_tool.py:434-467`; stream edits address their own stored chat id: `gateway/stream_consumer.py:390-413`; cron delivers to configured targets and native attachments: `cron/scheduler.py:1368-1395`, `cron/scheduler.py:1493-1497`. No common policy gate proves target equality to the inbound origin.
- **Workspace isolation:** terminal task ids normally collapse to a shared default backend unless an explicit environment override exists: `tools/terminal_tool.py:2162-2188`. `execute_code` can run arbitrary Python and has local/remote paths; its permitted Hermes-tool RPC set does not constrain direct Python filesystem/network access: `tools/code_execution_tool.py:1188-1267`.

## Capability and bypass coverage

### Direct tools and indirect execution

- `terminal`, `process`, file tools, browser tools, `execute_code`, `memory`, `session_search`, `delegate_task`, and `cronjob` all sit in the default core list: `toolsets.py:29-81`. Restricted sessions can hide them with toolsets, but any allowed operation still requires per-call capability authorization.
- `tool_call` is not a bypass because both the bridge and executor validate session scope before dispatch: `model_tools.py:1170-1203`, `agent/tool_executor.py:411-473`. The policy classifier must see the unwrapped underlying name and arguments.
- Plugin and MCP tools are not intrinsically dispatch bypasses: both register into the tool registry/toolsets. Their actual gap is missing mandatory capability metadata, and enabled plugins may also register behavior-changing middleware: `hermes_cli/plugins.py:390-447`, `hermes_cli/plugins.py:1176-1195`, `tools/mcp_tool.py:5535-5599`.
- Memory-provider and context-engine tools bypass the generic registry branch but still pass through execution middleware: `agent/tool_executor.py:1449-1508`. Policy must therefore live in the core middleware wrapper, not only in `registry.dispatch()`.
- `memory` writes persistent owner memory: `tools/memory_tool.py:1065-1140`. `session_search` can search/read sessions and even switch profile databases, but has no exact Teams `chat_id` parameter: `tools/session_search_tool.py:807-895`. Both must be denied for Restricted Groups.

### Spawned and delayed work

- Delegated children inherit broad runtime configuration, not a policy capability token. **Recommendation:** include immutable policy/origin fields in child context, recompute the policy before each child operation, and refuse provider/tool overrides outside policy. The current child constructor is `tools/delegate_tool.py:1330-1407`.
- Cron is a fresh session and may initialize MCP before constructing its agent. **Recommendation:** either deny cron creation under Restricted Policy, or persist a signed policy binding and re-resolve the current policy version at every tick. Current construction is `cron/scheduler.py:3505-3558`.
- Background terminal processes outlive the initiating call and later enqueue completion turns: `tools/process_registry.py:147-185`. **Recommendation:** stamp process records and notification events with policy/origin/task-root; recheck policy before process interaction, completion ingestion, and any delivery.
- Async delegation is not durable according to its own execution path, but its completion still enters later-turn rails; it needs the same policy stamp. The delegate blocklist alone is insufficient: `tools/delegate_tool.py:45-73`.

### Model and auxiliary routes

- Main-agent fallback is a separate provider chain: `agent/agent_init.py:1403-1419`.
- Auxiliary auto mode first tries the main provider, then configured fallback, then a built-in discovery chain: `agent/auxiliary_client.py:4660-4722`. The provider router is a distinct choke point from tool execution: `agent/auxiliary_client.py:4725-4733`.
- Delegated children inherit fallback and may accept an explicit provider override: `tools/delegate_tool.py:1330-1407`.
- **Recommendation:** introduce one core `RestrictedProviderAuthority` check at every main/fallback switch, `resolve_provider_client`, auxiliary call, and child/cron agent construction. It must validate provider, base-url host, model, and route class against approved internal AIDE endpoints; an unavailable compliant route fails closed. Tool or prompt instructions are not enforcement.

### History, egress, and cleanup

- Teams MTK can fetch an exact `conv_id` with full SDK pagination and attachment metadata: `gateway/platforms/teams_mtk.py:4522-4551`, `gateway/platforms/teams_mtk.py:4799-4840`. No current semantic-history broker proves that only relevant messages from the bound origin group are injected.
- Generic Hermes history is broader and cross-profile capable: `tools/session_search_tool.py:807-895`. Restricted sessions must set `skip_memory=True`, hide memory/session-history tools, and use only a new exact-origin Teams retriever.
- Egress has multiple concrete paths: normal/relay delivery (`gateway/delivery.py:74-131`), explicit `send_message` targets (`tools/send_message_tool.py:358-430`, `tools/send_message_tool.py:434-467`), streaming edit (`gateway/stream_consumer.py:390-413`), progress edit (`gateway/run.py:21532-21558`), and cron text/media delivery (`cron/scheduler.py:1368-1395`, `cron/scheduler.py:1493-1497`). **Recommendation:** all must call one core origin-equality gate over `(policy_id, policy_version, platform, chat_id, thread_id, operation, artifact_task_id)` immediately before side effect.
- The Linux cgroup cleanup helper kills processes in one cgroup but does not delete a Windows/group temp root: `gateway/cgroup_cleanup.py:60-78`. Existing file tools accept absolute paths and terminal tasks normally share the default environment. **Recommendation:** give every restricted group/task a hard-isolated execution backend with only its task root mounted, no owner credentials/files, and a policy-aware lease manager for task-end, `/stop`, restart recovery, and the daily 03:00 sweep.

## CQ client evidence and safe broker boundary

`myCRDump` has useful ALPS/MOLY read implementations, but its public `WitsSession` is not safe to expose to the model:

- `WitsSession` owns one credentialed `WitsHTTP` and attaches `cr`, arbitrary `query`, `record`, `note`, `attach`, `admin`, `reassign`, and other accessors to the same session: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:6-51`.
- The CR accessor exposes bounded read-shaped operations for detail, fields, notes, dependency, history, customer lookup, and ALPS/MOLY quadrant resolution: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:109-160`.
- `cr.get_fields` explicitly handles both ALPS and SWITS/MOLY transports and filters fields: `D:/01_Job/Tool/myCRDump/src/wits/cr.py:52-107`. Notes, tree, dependency, and history are also read operations: `D:/01_Job/Tool/myCRDump/src/wits/cr.py:110-186`, `D:/01_Job/Tool/myCRDump/src/wits/cr.py:189-244`.
- The same session exposes arbitrary query plus query `save`, `delete_by_name`, and `create_folder`: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:163-209`.
- It exposes record create/action/delete/mutation and note creation: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:212-265`.
- Its attachment accessor mixes list/download with upload/delete/Aspera upload: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:268-300`.

**Safe boundary recommendation:** a narrow credential-owning CQ broker may reuse `WitsHTTP` and specific audited read functions behind a new service-gated tool. The agent receives neither `WitsSession`, `WitsHTTP`, arbitrary WQL/JSON query objects, module objects, credentials, nor filesystem paths outside the task root. The broker exposes explicit operations such as `get_fields`, `list_notes`, `get_dependency`, `get_history`, `list_attachments`, and download-to-task-root, validates ALPS/MOLY identifiers and bounded fields/rows, and maps attachment output only into the group's isolated task directory.

Export is **not yet proven safe**. `query.get_file_by_json` shares a query accessor that also saves/deletes queries, and no evidence here proves that an exported file is mutation-free or bounded. Treat export as a separate capability; prototype and live-readback it before classifying it as allowed. Attachment upload/delete and every record/note/query mutation remain unconditionally denied.

## Minimal architecture that extends existing resources

1. Extend `SessionSource`/`gateway.session_context` with immutable policy/origin metadata; bind it at authorized Teams ingress.
2. Extend `ExecutionAuthority` into a versioned Restricted Policy resolver. Reload current policy state per operation so approval/revocation applies to the next affected operation without rebuilding the prompt.
3. Extend tool registry records with mandatory capability metadata. Unknown classification produces a paused decision, never an implicit allow. Use existing toolset filtering only to reduce exposure.
4. Register a core-owned tool execution middleware that normalizes resources and checks current authority; keep defense in depth at deferred dispatch. Add explicit creation/side-effect gates for delegation, cron/background, model routing, and delivery because they create new authority domains or bypass tool dispatch.
5. Reuse approval correlation/transport, but persist owner decisions in a versioned policy store. Only the exact owner control conversation/owner identity or local TUI may approve/revoke; first valid decision wins idempotently and resumes one paused operation.
6. Add the narrow CQ broker, exact-origin Teams history retriever, per-group isolated execution backend/lease cleanup, AIDE-only provider gate, origin-bound delivery gate, and content-minimized append-only audit.

## Normative map decisions preserved

The architecture above does not replace the chosen capability deny-list with toolset-based authorization. Its acceptance conditions are:

- ordinary group requests require `@hermes`; known control commands bypass the mention gate;
- every group member may perform the bounded ALPS/MOLY read operations, list/download attachments, and request export once export is separately proven safe; every CQ mutation is denied;
- owner-private Teams/email/files/Workflow/Webex/calendar/meetings/OneNote/Hermes memory/PKB/session/config/log/credential/browser-session sources are denied; CQ is the sole owner-account read exception;
- classified non-private reads remain allowed; an unknown capability pauses and notifies both the exact owner control conversation and local TUI; one authenticated owner decision is durable, idempotent, and resumes only the paused operation;
- approval or revocation is read again before every affected operation; the next affected operation observes the new policy version;
- only the authenticated owner can create, bind, modify, approve, revoke, deploy, disable, or roll back policy;
- every main, fallback, auxiliary, vision, OCR, embedding, title, delegated, and cron model route is internal AIDE-only and fails closed when unavailable;
- each group has one isolated root and one active task; 03:00 skips an active root, task completion or `/stop` deletes the active task directory, and queued group messages continue afterward;
- follow-up context has no time limit but uses only semantically relevant original Teams messages from the exact group; it creates no Hermes private memory;
- only exact-origin replies/progress and explicitly requested artifact uploads may leave the task; successful upload ends Hermes-local access restriction while staging remains cleanup-bound;
- there is no business quota on time, rows, attachment/export size, or sandbox storage; implementation resource limits may fail safely but must not silently truncate business results;
- audit is immutable and content-minimized, recording identity/origin fingerprints, policy/version, operation, CQ/query fingerprint, decision/reason, data volume, provider/model, cleanup and egress verdicts—never credentials, prompts, CQ content, attachments, or generated code;
- rollout is adversarial TestGroup E2E, then harmless production canary plus deny probes, rollback readiness, readback, cleanup proof, and verified zero cross-group side effects.

## Behavioral and E2E test matrix

### Unit and integration tests to add

Use the established runtime-test locations rather than source-text tests. Existing relevant conventions are group authz/toolset behavior in `tests/gateway/test_teams_mtk_group_whitelist_authz.py:165-241`, deferred tool scope in `tests/tools/test_tool_search.py:511-586`, exact authority isolation in `tests/tools/test_skill_execution_authority.py:133-184`, and cron toolset propagation in `tests/cron/test_scheduler.py:1591-1620`.

1. **Policy resolution:** concurrent groups/users cannot share policy/origin; missing/malformed policy state fails closed; revocation between two calls denies the second without recreating the agent.
2. **Capability registry completeness:** every exposed built-in/plugin/MCP/context-engine/memory-provider operation has metadata; test registration of an unclassified fake tool and assert schema hiding plus dispatch denial/paused approval.
3. **Indirect execution:** attempt the same denied action through direct file/terminal/browser, `execute_code`, deferred `tool_call`, plugin, MCP, context engine, memory provider, delegation, cron, background process and completion turn. Each must reach the same policy verdict with the real underlying resource.
4. **Approval race:** emit owner-control and TUI decisions concurrently; exactly one durable transition wins, duplicate replies are no-ops, denial/timeout leaves the operation paused or denied, and one approval resumes only one operation.
5. **Provider routing:** inject a non-AIDE main, fallback, auxiliary, vision/OCR/embedding/title, child and cron route; assert no request is sent. Inject an approved AIDE route and assert the expected host/provider/model was used.
6. **History isolation:** exact-group Teams fixtures with cross-group/private marker messages; semantic retrieval may return relevant exact-group content and must never return any marker from another conversation or Hermes session/memory.
7. **Egress:** exercise normal send, stream edit, progress edit, `send_message`, file upload, cron, relay, delegated/background completion. Exact-origin target passes; any different platform/chat/thread fails before adapter invocation.
8. **Filesystem:** absolute path, `..`, alternate separators, junction/symlink/reparse-point escape, remote backend mount, subprocess child, and delayed background write all fail outside task root. Task-end, `/stop`, stale restart and 03:00 paths delete only the intended task/root.
9. **CQ broker:** mocked transports prove only named read operations are callable; arbitrary query, record/note mutation, attachment upload/delete and raw client/session access are impossible. ALPS and MOLY response normalization and attachment download-to-task-root are covered separately.
10. **Audit:** every allow/deny/approval/cleanup/egress/provider decision has required fingerprints and counts; secret/content fixtures never appear in audit output.

### Live E2E gates

For each boundary, first run a controlled **pre-enforcement violation** or test-double proof showing the attempted side effect can reach its destination without the new gate; after implementation, rerun the identical attempt and require denial plus independent readback that the side effect did not occur. A log line or tool-returned `success` is not proof.

- **Teams ingress/queue:** real TestGroup members can invoke only with mention; `/stop` from any member interrupts the one active task, deletes its task directory, and the queued next message proceeds. Verify via gateway state, Teams messages, and disk readback.
- **Private-source denial:** plant unique markers in owner DM, another group, email, local/network file, Workflow, Webex, calendar, OneNote, Hermes memory/session/PKB and browser-session-only page. Force direct and indirect attempts; assert zero marker bytes in model context, reply, artifacts, audit, or temp root.
- **CQ read/write:** with real harmless ALPS and MOLY records, read fields/notes/history/dependencies and list/download attachments. Attempt comment/update/assign/create/delete/upload and arbitrary query. Re-query CQ through an independent client to prove reads caused no mutation. Export remains blocked until a dedicated prototype proves read-only server behavior and bounded staging.
- **Provider:** capture actual endpoint/provider/model for main, fallback, each auxiliary class, child and cron. Force unavailable AIDE and assert fail-closed with zero request to any other host.
- **Egress:** attempt another Teams group, DM, platform, thread and relay target through every egress path. Query target conversations independently and require zero new/edited messages or files.
- **Cleanup/restart:** create active/inactive group roots and background descendants; exercise task end, `/stop`, gateway restart and 03:00. Verify exact deletion/retention and no writes after cleanup.
- **Canary/rollback:** deploy only after TestGroup adversarial pass; production canary is harmless read plus origin reply. Rollback trigger must be exercised and post-rollback deny probes repeated.

## Open uncertainties requiring prototype or live E2E

- Whether CQ query export is mutation-free, bounded, and available for both ALPS and MOLY without exposing arbitrary query state.
- Attachment malware/content handling, large-file streaming, and whether every ALPS/MOLY download path can be forced into the isolated task root.
- Teams SDK pagination consistency and semantic retrieval quality over long histories; static source proves exact `conv_id` fetching, not relevance or redaction.
- Exact owner authentication and simultaneous TUI/control approval delivery under a live gateway restart/race.
- Windows reparse-point and remote-backend containment; static path normalization is not a sandbox proof.
- Whether every configured auxiliary integration in the deployed profile routes through the inspected provider resolver; live endpoint capture is required.
- End-to-end origin identity across relay, streaming, attachment, cron and background completion after gateway restart.

These uncertainties block implementation acceptance, not this seam-discovery conclusion. They are inputs to the CQ broker, sandbox, history, egress, provider, approval, audit, and E2E tickets.

## Citation index

- Trusted ingress and origin: `gateway/session.py:148-179`, `gateway/authz_mixin.py:179-240`, `gateway/authz_mixin.py:465-477`, `gateway/session_context.py:123-161`, `gateway/session_context.py:179-238`, `gateway/session_context.py:241-301`.
- Per-turn authority and approval correlation: `agent/execution_authority.py:14-81`, `agent/execution_authority.py:84-149`, `tools/approval.py:35-52`, `tools/approval.py:171-214`.
- Exposure and dispatch: `toolsets.py:29-81`, `model_tools.py:288-310`, `model_tools.py:1141-1203`, `model_tools.py:1205-1273`, `agent/tool_executor.py:411-473`, `agent/tool_executor.py:1106-1139`, `agent/tool_executor.py:1449-1508`, `agent/tool_executor.py:1527-1580`.
- Extensions: `hermes_cli/plugins.py:390-447`, `hermes_cli/plugins.py:1176-1195`, `tools/mcp_tool.py:5535-5599`.
- Spawned/delayed work and routing: `tools/delegate_tool.py:45-73`, `tools/delegate_tool.py:1330-1407`, `cron/scheduler.py:3505-3558`, `tools/process_registry.py:147-185`, `agent/auxiliary_client.py:4660-4733`.
- History/egress/filesystem: `gateway/platforms/teams_mtk.py:4522-4551`, `gateway/platforms/teams_mtk.py:4799-4840`, `gateway/delivery.py:74-131`, `tools/send_message_tool.py:358-430`, `tools/send_message_tool.py:434-467`, `tools/file_tools.py:364-398`, `tools/file_tools.py:1623-1639`.
- CQ façade and read/write split: `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:6-51`, `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:109-160`, `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:163-209`, `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:212-265`, `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:268-300`, `D:/01_Job/Tool/myCRDump/src/wits/cr.py:52-107`, `D:/01_Job/Tool/myCRDump/src/wits/cr.py:110-186`, `D:/01_Job/Tool/myCRDump/src/wits/cr.py:189-244`.

## Ticket-resolution conclusion

The seam-discovery ticket can graduate once an independent verifier confirms the citations and factual/runtime classifications above. The research conclusion is intentionally narrower than implementation acceptance: existing trusted context, authority resolution, middleware, tool scoping, approval transport, Teams history and registry routing are reusable; every cross-domain policy propagation, CQ broker, origin egress, AIDE routing, isolated execution, semantic history, durable approval and audit component remains implementation work with mandatory forced-violation E2E.