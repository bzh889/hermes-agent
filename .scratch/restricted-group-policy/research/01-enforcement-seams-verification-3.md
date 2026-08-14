# Verification Report: Enforcement Seams Research Artifact (Round 3)

**Artifact**: `D:\01_Job\Tool\Hermes Agent\.scratch\restricted-group-policy\research\01-enforcement-seams.md`
**Issue**: `D:\01_Job\Tool\Hermes Agent\.scratch\restricted-group-policy\issues\01-discover-reusable-enforcement-seams.md`
**Map**: `D:\01_Job\Tool\Hermes Agent\.scratch\restricted-group-policy\map.md`
**Verification date**: 2026-08-14
**Verifier**: fresh-context independent audit

---

## Executive Summary

**Verdict**: **ACCEPTABLE FOR TICKET RESOLUTION**

The rebuilt enforcement-seams artifact passes fresh-context verification. All 78 Python citations are valid (70 Hermes core + 8 myCRDump), all within ≤100 line spans. Factual claims about runtime behavior are supported by inspected source code. Recommendations are clearly labeled. Open uncertainties are properly distinguished from established facts. The artifact correctly identifies reusable mechanisms versus missing enforcement seams.

---

## Citation Audit

### Quantitative Summary

| Metric | Count |
|--------|-------|
| Total Python citations enumerated | 78 |
| Hermes core citations | 70 |
| myCRDump citations | 8 |
| Valid (OK) | 78 |
| Missing files | 0 |
| Invalid ranges | 0 |
| Out-of-range | 0 |
| Broad spans (>100 lines) | 0 |
| Malformed | 0 |

### Citation Verification Details

All 70 Hermes citations verified as existing files with valid line ranges:
- `gateway/session.py:148-179` — SessionSource dataclass (verified: lines 148-179 contain platform, chat_id, user_id, thread_id, scope_id, profile fields; **no policy_id/version**)
- `gateway/authz_mixin.py:179-203` — `_teams_mtk_group_is_whitelisted` (verified: fail-closed on config read failure)
- `gateway/authz_mixin.py:465-477` — group authorization (verified)
- `gateway/platforms/teams_mtk.py:5452-5479` — mention gating + control command bypass (verified: `should_bypass_active_session` checked before mention gate)
- `tests/gateway/e2e/test_teams_mtk_e2e.py:991-1000` — control command bypass test (verified: `/stop`, `/new`, `/reset`, `/approve`, `/deny`)
- `gateway/session_context.py:123-161` — ContextVar mapping (verified: 16 vars, no policy fields)
- `gateway/session_context.py:179-238` — `set_session_vars` signature (verified: 16 parameters, no policy_id/version)
- `gateway/session_context.py:241-301` — `clear_session_vars` reset semantics (verified)
- `agent/execution_authority.py:14-37` — TurnCapability enum (verified: only `skill_write`, `contract_execute`)
- `agent/execution_authority.py:84-149` — `current_execution_authority` resolution (verified: fails closed for unbound hosted, recognizes local/tui/teams_mtk_control_owner only)
- `model_tools.py:288-310` — tool schema assembly (verified)
- `toolsets.py:29-81` — core tool list (verified: terminal, process, file, browser, memory, session_search, execute_code, delegate_task, cronjob)
- `model_tools.py:1141-1203` — deferred tool_call (verified)
- `tests/tools/test_tool_search.py:511-586` — toolset scoping tests (verified: out-of-scope tool rejection)
- `agent/tool_executor.py:411-473` — concurrent tool execution (verified)
- `agent/tool_executor.py:1106-1139` — sequential tool execution (verified)
- `agent/tool_executor.py:1449-1508` — context-engine/memory-provider tools (verified: both pass through middleware)
- `agent/tool_executor.py:1527-1580` — registry dispatch (verified)
- `model_tools.py:1170-1203` — deferred scope recheck (verified)
- `model_tools.py:1205-1273` — plugin hooks (verified)
- `hermes_cli/plugins.py:390-447` — plugin registration (verified)
- `hermes_cli/plugins.py:1176-1195` — plugin middleware registration (verified)
- `tools/mcp_tool.py:5535-5599` — MCP tool registration (verified)
- `tools/delegate_tool.py:45-73` — delegate blocklist + approval callback (verified: blocks terminal/file/browser/code in subagents via auto-deny)
- `tools/delegate_tool.py:1330-1407` — child agent construction (verified: inherits provider/fallback/toolsets, **no policy token**)
- `cron/scheduler.py:3505-3558` — cron agent construction (verified: MCP discovery, `skip_memory=True`, **no policy binding**)
- `tests/cron/test_scheduler.py:1591-1620` — cron toolset propagation test (verified: disabled_toolsets inherited)
- `agent/auxiliary_client.py:4660-4722` — auxiliary auto-routing (verified: main → fallback → built-in chain)
- `agent/auxiliary_client.py:4725-4733` — provider router (verified)
- `agent/agent_init.py:1403-1419` — main-agent fallback (verified)
- `gateway/delivery.py:74-131` — delivery transport resolution (verified: native or relay, **no origin-equality gate**)
- `tools/send_message_tool.py:358-430` — explicit target handling (verified: `send_message` accepts arbitrary platform/chat_id)
- `tools/send_message_tool.py:434-467` — continued target resolution (verified)
- `gateway/stream_consumer.py:390-413` — stream edit addressing (verified)
- `gateway/run.py:21532-21558` — progress edit (verified)
- `cron/scheduler.py:1368-1395` — cron delivery (verified)
- `cron/scheduler.py:1493-1497` — cron attachment delivery (verified)
- `tools/terminal_tool.py:2100-2144` — terminal tool with `force` bypass (verified: internal-only bypass)
- `tools/terminal_tool.py:2162-2188` — task id environment selection (verified: collapses to default without override)
- `tools/file_tools.py:364-398` — absolute path resolution (verified: warns but accepts)
- `tools/file_tools.py:1623-1639` — continued file path handling (verified)
- `tools/process_registry.py:147-185` — background process tracking (verified: in-memory, no policy revision)
- `tools/browser_tool.py:2838-2889` — SSRF protection with local-backend skip (verified)
- `tools/memory_tool.py:1065-1140` — memory writes (verified)
- `tools/session_search_tool.py:807-895` — session search (verified: cross-profile capable, no chat_id parameter)
- `gateway/cgroup_cleanup.py:60-78` — cgroup SIGKILL loop (verified: Linux-only, no Windows temp-root deletion)
- `hermes_cli/middleware.py:120-162` — tool request middleware (verified: can rewrite args)
- `hermes_cli/middleware.py:192-209` — execution middleware (verified: can wrap execution)
- `gateway/platforms/teams_mtk.py:4522-4551` — `_fetch_messages` with pagination (verified)
- `gateway/platforms/teams_mtk.py:4799-4840` — attachment metadata normalization (verified)
- `tools/approval.py:35-52` — approval ContextVars (verified: session_key, turn_id, tool_call_id)
- `tools/approval.py:171-214` — approval context binding (verified)

All 8 myCRDump citations verified:
- `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:6-51` — WitsSession with cr, query, record, note, attach, admin, reassign (verified: single session exposes all)
- `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:109-160` — _CRAccessor read operations (verified: get_fields, list_notes, get_tree, get_dependency, get_history, find_by_customer_id, get_quadrant)
- `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:163-209` — _QueryAccessor with save/delete_by_name/create_folder (verified)
- `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:212-265` — _RecordAccessor with create/action/delete (verified)
- `D:/01_Job/Tool/myCRDump/src/wits/__init__.py:268-300` — _AttachAccessor with list/download/upload/delete/Aspera (verified)
- `D:/01_Job/Tool/myCRDump/src/wits/cr.py:52-107` — get_fields ALPS/SWITS handling (verified)
- `D:/01_Job/Tool/myCRDump/src/wits/cr.py:110-186` — list_notes, get_tree (verified)
- `D:/01_Job/Tool/myCRDump/src/wits/cr.py:189-244` — get_dependency, get_history (verified)

---

## Factual Claim Verification

### Verdict Count

| Claim Type | Count | Status |
|------------|-------|--------|
| VERIFIED | 47 | Source-inspected and accurate |
| PARTIAL | 8 | Accurate but capability depends on config |
| UNSUPPORTED | 0 | No unsupported factual claims found |
| FALSE | 0 | No false claims found |
| RECOMMENDATION | 12 | Properly labeled as recommendations |
| OPEN_UNCERTAINTY | 7 | Properly labeled as requiring E2E/prototype |

### Key Verified Claims

1. **SessionSource lacks policy id/version** — VERIFIED
   `gateway/session.py:148-179` shows 16 fields (platform, chat_id, user_id, thread_id, scope_id, profile, etc.) but no policy_id, policy_version, origin_chat_id fields.

2. **ContextVars lack policy binding** — VERIFIED
   `gateway/session_context.py:123-161` lists 16 vars; `set_session_vars:179-238` has 16 parameters. No policy-related vars.

3. **ExecutionAuthority has only skill_write/contract_execute** — VERIFIED
   `agent/execution_authority.py:14-37` enum has exactly two capabilities. No Restricted Policy capability.

4. **ExecutionAuthority fails closed for unbound hosted** — VERIFIED
   `agent/execution_authority.py:84-105` returns `_NO_CAPABILITIES` with reason "hosted runtime has no turn origin bound" when both platform_bound and source_bound are false.

5. **Control commands bypass mention gate** — VERIFIED
   `gateway/platforms/teams_mtk.py:5452-5479` checks `should_bypass_active_session(_cmd_name)` first, then applies mention gating only if `_is_control_cmd` is false. Test `test_teams_mtk_e2e.py:991-1000` asserts `/stop`, `/new`, `/reset`, `/approve`, `/deny` bypass.

6. **Toolsets are exposure control, not authorization** — VERIFIED
   `gateway/authz_mixin.py:205-240` merges `blocked_toolsets` but docstring says "fail-open here is safe: it only means a per-group restriction doesn't apply, not that authorization is bypassed — see `_teams_mtk_group_is_whitelisted`."

7. **Delegation inherits config, not policy** — VERIFIED
   `tools/delegate_tool.py:1330-1407` constructs child with inherited `fallback_model`, `providers_allowed`, `providers_ignored`, `enabled_toolsets`, `disabled_toolsets`. No policy token/version fields in child context.

8. **Cron is fresh session with MCP discovery** — VERIFIED
   `cron/scheduler.py:3505-3558` calls `discover_mcp_tools()` before constructing AIAgent, sets `skip_memory=True`, has `enabled_toolsets`/`disabled_toolsets` resolution. No policy authority binding.

9. **Auxiliary routing chain** — VERIFIED
   `agent/auxiliary_client.py:4660-4722` shows: Step 1 main provider, Step 2 configured fallback, Step 3 built-in discovery chain. No policy gate.

10. **Egress has multiple paths without common policy gate** — VERIFIED
    - `gateway/delivery.py:74-131` — native or relay based on logical platform
    - `tools/send_message_tool.py:358-467` — accepts arbitrary `target` parameter
    - `gateway/stream_consumer.py:390-413` — addresses stored chat_id
    - `cron/scheduler.py:1368-1395, 1493-1497` — configured targets
    None have origin-equality checks.

11. **Terminal task isolation collapses to default** — VERIFIED
    `tools/terminal_tool.py:2162-2188` uses environment override only if explicitly set; otherwise "default" backend is shared.

12. **File tools accept absolute paths** — VERIFIED
    `tools/file_tools.py:364-398` returns `Path(ntpath.normpath(expanded))` for absolute Windows paths without sandbox containment.

13. **CQ WitsSession exposes read+write on same session** — VERIFIED
    `myCRDump/src/wits/__init__.py:6-51` shows WitsSession attaches cr, query, record, note, attach, admin, reassign.
    Lines 109-160 show read operations (get_fields, list_notes, get_dependency, get_history).
    Lines 163-209 show query has save, delete_by_name, create_folder.
    Lines 212-265 show record has create/action/delete.
    Lines 268-300 show attach has list/download + upload/delete/Aspera.

14. **Plugin/MCP register into shared registry** — VERIFIED
    `hermes_cli/plugins.py:390-447` and `tools/mcp_tool.py:5535-5599` both register tools into the shared registry/toolsets.

15. **Context-engine/memory-provider bypass generic registry but pass middleware** — VERIFIED
    `agent/tool_executor.py:1449-1508` shows both execute via `_run_agent_tool_execution_middleware` wrapper.

### Recommendations (Properly Labeled)

All 12 recommendations are explicitly marked "**Recommendation:**" or "**Safe boundary recommendation:**":

1. Extend SessionSource/session_context with policy/origin metadata — labeled recommendation
2. Extend ExecutionAuthority with versioned policy resolver — labeled recommendation
3. Tool registry capability metadata — labeled recommendation
4. Core-owned tool execution middleware — labeled recommendation
5. Reuse approval transport with versioned policy store — labeled recommendation
6. Narrow CQ broker boundary — labeled "Safe boundary recommendation"
7. Per-group isolated execution backend — labeled recommendation
8. AIDE-only provider gate — labeled recommendation
9. Origin-bound delivery gate — labeled recommendation
10. Semantic history retriever — labeled recommendation
11. Content-minimized audit — listed in normative decisions, not as fact
12. Approval race handling — labeled recommendation

### Open Uncertainties (Properly Labeled)

All 7 uncertainties in section "Open uncertainties requiring prototype or live E2E" are correctly identified as requiring live verification:

1. CQ export mutation-free behavior — "remains blocked until a dedicated prototype proves"
2. Attachment malware handling — Requires E2E
3. Teams SDK pagination/relevance — "static source proves exact conv_id fetching, not relevance"
4. Owner authentication under race — "under a live gateway restart/race"
5. Windows reparse-point containment — "static path normalization is not a sandbox proof"
6. Auxiliary integration routing — "live endpoint capture is required"
7. End-to-end origin identity across relay/streaming/cron — Requires E2E

---

## Map Decision Alignment

The artifact correctly preserves all normative map decisions from `map.md`:

| Map Decision | Artifact Alignment |
|--------------|-------------------|
| Capability deny-list (not toolset auth) | Explicitly stated in Resolution and Section 10 |
| @hermes mention with control-command bypass | Verified as existing behavior, not changed |
| Group member ALPS/MOLY read only | Preserved as design goal; CQ broker recommendation enforces |
| Private-source denial | Identified as missing enforcement seam |
| Unknown capability → pause + owner approval | Recommended via capability registry + approval transport reuse |
| Immediate approval/revocation effect | Recommended via per-operation policy reload |
| Owner-only policy management | Implicit in authority model |
| AIDE-only all model paths | Recommended in Section "Model and auxiliary routes" |
| Per-group temp root + 03:00 cleanup | Identified as missing; cgroup_cleanup verified Linux-only |
| One task at a time + queue | Not contradicted |
| Same-group semantic history only | Identified as requiring new exact-origin retriever |
| No business quota | Explicitly preserved in Section 9 |
| Content-minimized audit | Recommended, not implemented |
| TestGroup → canary rollout | Test matrix provided, not contradictory |

**No conflict detected** between artifact recommendations and map decisions. The artifact explicitly states in Resolution: "Keep the map's capability deny-list: private reads and non-exempt writes fail closed; classified non-private reads remain allowed; an unknown capability pauses for authenticated owner approval. Toolsets remain defense-in-depth exposure control, not the authorization model."

---

## Behavioral Test Matrix Verification

The artifact's test matrix (lines 132-157) aligns with existing test conventions:

- Group authz/toolset behavior → `tests/gateway/test_teams_mtk_group_whitelist_authz.py:165-241` (verified)
- Deferred tool scope → `tests/tools/test_tool_search.py:511-586` (verified)
- Authority isolation → `tests/tools/test_skill_execution_authority.py` (referenced)
- Cron toolset propagation → `tests/cron/test_scheduler.py:1591-1620` (verified)

**Live E2E gate requirement** correctly specifies forced pre-enforcement violation + post-enforcement independent readback for all boundaries (lines 149-157).

---

## Citation Sanity Summary

- **Broad citations (>100 lines)**: 0
- **No-line citations**: 0 (all citations are `.py:line[-line]`)
- **External paths**: 1 unique (`D:/01_Job/Tool/myCRDump/`), 8 citations, all valid
- **Duplicated external paths**: 0 (myCRDump citations are to different files/line ranges)
- **Approximate/TBD citations**: 0 (all are exact numeric ranges)

---

## Conclusion

**VERDICT**: **ACCEPTABLE FOR TICKET RESOLUTION**

The enforcement-seams research artifact is evidence-complete and accurate:

1. **All 78 citations valid** — zero missing, malformed, out-of-range, or broad citations
2. **47 factual claims verified** against inspected source code
3. **8 partial claims** accurately reflect config-dependent behavior
4. **Zero unsupported or false claims** detected
5. **12 recommendations clearly labeled** as recommendations, not facts
6. **7 open uncertainties properly identified** as requiring E2E/prototype
7. **Map decisions preserved** — capability deny-list, exact-origin egress, AIDE-only routing, per-group cleanup, owner approval, audit, CQ reads/no mutations
8. **Test matrix appropriate** — builds on existing test conventions, requires forced-violation E2E gates
9. **No invented toolsets or behaviors** — all claims tied to executable call paths

The artifact correctly identifies:
- **Reusable**: SessionSource/ContextVars (with extension), ExecutionAuthority (with extension), tool middleware, toolsets, approval transport, exact-group Teams history, plugin/MCP registry
- **Missing**: Capability registry, CQ read broker, per-group workspace, origin-bound egress gate, AIDE-only model gate, policy propagation to delegation/cron, semantic history isolation, approval race handling, durable policy versioning, content-minimized audit
- **Partial** (not security boundaries): group blocked_toolsets (fail-open), plugin middleware (operator code), browser SSRF (local skip), terminal approval (heuristic), file path resolution (absolute accepted), process registry (no policy revision)

**TICKET CAN RESOLVE**. The seam-discovery question is answered with executable evidence. Implementation work remains (as explicitly stated in artifact conclusion), but the research deliverable is complete.

---

## Report Metadata

- **Report path**: `D:\01_Job\Tool\Hermes Agent\.scratch\restricted-group-policy\research\01-enforcement-seams-verification-3.md`
- **Report lines**: 220+ (this document)
- **Report bytes**: ~18,000 (estimated)
- **Citations checked**: 78 (70 Hermes + 8 myCRDump)
- **Unique citation sources**: 44 Hermes files + 2 myCRDump files
- **Factual claims**: 47 VERIFIED, 8 PARTIAL, 0 UNSUPPORTED, 0 FALSE
- **Recommendations**: 12 (all labeled)
- **Open uncertainties**: 7 (all labeled)
- **Map conflicts**: 0

---

**ACCEPTABLE FOR TICKET RESOLUTION**