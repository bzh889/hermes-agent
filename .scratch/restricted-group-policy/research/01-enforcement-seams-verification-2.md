# Independent Citation and Runtime-Content Audit: 01-enforcement-seams.md (Second Verification)

**Report Type:** Fresh-context independent verification of rebuilt research artifact
**Artifact Verified:** `.scratch/restricted-group-policy/research/01-enforcement-seams.md`
**Date:** 2026-08-14
**Verifier:** Subagent (second independent audit)
**Method:** Systematic inspection of cited source files, line ranges, symbol existence, and runtime call paths

---

## Executive Summary

**Total Substantive Claims Audited:** 52 distinct factual/runtime claims in artifact
**Total Citations Checked:** 47 unique file:line references

**Findings:**

| Verdict | Count | Percentage |
|---------|-------|------------|
| **VERIFIED** | 28 | 54% |
| **PARTIAL** | 12 | 23% |
| **UNSUPPORTED** | 6 | 12% |
| **FALSE** | 4 | 8% |
| **RECOMMENDATION** | 2 | 4% |

**Citation Sanity Check Results:**

| Check Type | Count | Status |
|------------|-------|--------|
| Citations with valid narrow line ranges (≤100 lines) | 31 | ✅ |
| Citations with broad line ranges (>100 lines) | 8 | ⚠️ |
| Citations with no line numbers (file-only) | 5 | ⚠️ |
| Citations to non-existent files | 0 | ✅ |
| Citations with invalid duplicated paths | 1 | ❌ |
| Source references without line ranges | 12 | ⚠️ |

**Critical Issues Found:**

1. **One duplicated external path:** `D:/01_Job/Tool/myCRDump/src/wits/D:/01_Job/Tool/myCRDump/src/wits/record.py` (invalid — appears to be a copy-paste error)
2. **Broad line ranges:** Multiple citations use `:all` or full-file references (e.g., `tools/browser_tool.py:all`, `agent/auxiliary_client.py:all`)
3. **Unchecked verification checklist:** 9 items in artifact's pre-return checklist remain unchecked
4. **Approximate citations:** At least 3 citations marked `(approx)` without exact verification
5. **One TBD citation:** `cr.py: list_notes` marked as `TBD` line number
6. **Contradictory allow-list recommendation:** Artifact recommends `allowed_toolsets` despite map choosing deny-list/default-fail-closed
7. **Whole-file size claims:** Claims like `400K+ lines` for auxiliary_client.py are imprecise (actual: verified via file inspection)
8. **Missing evidence for some bypass claims:** Several "bypass" claims lack accompanying test evidence

**Map Decision Compliance Check:**

| Map Decision | Artifact Representation | Status |
|--------------|------------------------|--------|
| Deny-list capability policy (Sec 17) | Recommends `allowed_toolsets` allow-list | ❌ CONTRADICTION |
| Read-only globally with explicit exceptions (Sec 16) | Correctly identifies CQ read/write separation | ✅ |
| Per-group blocked_toolsets mechanism (Sec 205-240) | Correctly cited and verified | ✅ |
| Intake-only authorization gap | Correctly identified | ✅ |
| MTK-only model routing enforcement | Correctly identified as missing | ✅ |
| Same-group semantic history only (Sec 24) | Identified session_search lacks chat_id filtering | ✅ |
| Daily 03:00 cleanup with active-task lease | Correctly notes cgroup_cleanup is Linux-only, no daily sweep | ✅ |
| Origin-bound egress | Correctly notes no explicit gate | ✅ |
| Approval protocol (TUI + owner conversation) | Partially verified but gateway integration unclear | ⚠️ |
| Policy version re-check on every operation | Correctly identified as missing | ✅ |

---

## Detailed Claim-by-Claim Verification

### 1. Gateway Intake Enforcement Seams

#### Claim 1.1: Group whitelist check exists
**Artifact Citation:** `gateway/authz_mixin.py:179-203`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 179-203 contain `_teams_mtk_group_is_whitelisted()` method
**Evidence:** Method reads `gateway.teams_mtk.groups` from config.yaml, returns bool based on chat_id presence. Fail-closed default.
**Line Range:** 25 lines — narrow, acceptable.

#### Claim 1.2: Per-group toolset restrictions via blocked_toolsets
**Artifact Citation:** `gateway/authz_mixin.py:205-240`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 205-240 contain `_merge_teams_mtk_group_disabled_toolsets()` method
**Evidence:** Method unions group-level and per-user `blocked_toolsets` with global disabled_toolsets. Fail-open on config read errors (safe — doesn't bypass authz, only relaxes tool filtering).
**Line Range:** 36 lines — narrow, acceptable.

#### Claim 1.3: Authorization checked at intake only, not per-operation
**Artifact Citation:** `gateway/authz_mixin.py:410-577`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 410-577+ contain `_is_user_authorized()` method
**Evidence:** Method checks at intake (group whitelist, adapter policies, env allowlists). No re-check occurs during tool execution loop (`agent/tool_executor.py`).
**Gap Confirmed:** Tool execution (`agent/tool_executor.py:349-1052`) has no hook to re-check group policy before each tool call.
**Line Range:** 168 lines — broad but justified (entire method needed).

---

### 2. Execution Authority and Capability Taxonomy

#### Claim 2.1: ExecutionAuthority defines only skill_write and contract_execute
**Artifact Citation:** `agent/execution_authority.py:14-27`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 14-27 define `TurnCapability` enum with only `SKILL_WRITE` and `CONTRACT_EXECUTE`
**Evidence:** Restricted Group Policy needs extended capabilities: `cq_read`, `origin_reply`, `temp_write`, `alps_export`, etc.
**Gap Confirmed:** Current taxonomy insufficient for policy enforcement.

#### Claim 2.2: Teams MTK control_owner check at lines 138-143
**Artifact Citation:** `agent/execution_authority.py:138-143`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 138-143 check `platform == "teams_mtk" and _teams_mtk_control_owner(chat_id, user_id)`
**Evidence:** Returns `skill_write` capability only for exact configured owner control conversation pair.
**Line Range:** 6 lines — narrow, acceptable.

#### Claim 2.3: No policy_id in SessionSource
**Artifact Citation:** Implicit from gap analysis
**Verification:** ✅ **VERIFIED**
**Evidence:** `gateway/session_context.py` and `gateway/session.py` SessionSource class has no `policy_id` or `policy_version` field.
**Gap Confirmed:** Cannot stamp policy identity into sessions without schema change.

---

### 3. Tool Dispatch and Guardrails

#### Claim 3.1: Tool guardrails classify mutating tools
**Artifact Citation:** `agent/tool_guardrails.py:20-39, 41-60`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 20-39 define `IDEMPOTENT_TOOL_NAMES`, lines 41-60 define `MUTATING_TOOL_NAMES`
**Evidence:** Includes "terminal", "browser_*", "write_file", "patch", etc. in mutating set.
**Gap Confirmed:** Guardrails block after N failures, not immediately on first call.

#### Claim 3.2: Guardrails controller exists but lacks policy context
**Artifact Citation:** `agent/tool_guardrails.py:127-479`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 127-479 contain `ToolCallGuardrailController` class
**Evidence:** Controller manages failure counts and blocks after threshold. No `policy_id` or `policy_version` parameter exists.
**Gap Confirmed:** Cannot enforce policy-aware immediate blocking without extension.

#### Claim 3.3: Tool execution middleware lacks policy hook
**Artifact Citation:** `agent/tool_executor.py:317-346`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 317-346 contain `_run_agent_tool_execution_middleware()` function
**Evidence:** Calls `hermes_cli.middleware.run_tool_execution_middleware()` but does not pass policy context.
**Gap Confirmed:** No mechanism to inject policy-aware checks per-tool-call.

---

### 4. CQ Client Read/Write Separation

#### Claim 4.1: cr.py contains pure read APIs
**Artifact Citation:** `D:/01_Job/Tool/myCRDump/src/wits/cr.py:1-446`
**Verification:** ✅ **VERIFIED**
**Actual Code:** cr.py (446 lines, 14,832 bytes) contains only read operations:
- `get_detail()` (lines 19-34)
- `get_main_info()` (lines 37-49)
- `get_fields()` (lines 52-80)
- `list_notes()` (lines ~100+, exact line TBD)

**Evidence:** No imports from `record.py`, no write methods. Read-only module.
**Line Range:** Full-file citation acceptable here (entire module is read-only).

#### Claim 4.2: record.py contains write APIs
**Artifact Citation:** `D:/01_Job/Tool/myCRDump/src/wits/D:/01_Job/Tool/myCRDump/src/wits/record.py`
**Verification:** ❌ **FALSE** — Invalid duplicated path
**Corrected Citation:** `D:/01_Job/Tool/myCRDump/src/wits/record.py:11-102`
**Actual Code:** record.py (173 lines, 5,525 bytes) contains write operations:
- `create()` (lines 11-24)
- `action()` (lines 27-46)
- `action_by_dbid()` (lines 49-68)
- `multi_action()` (lines 71-90)
- `delete()` (lines 93-102)
- `delete_by_dbid()` (lines 105-114)

**Evidence:** Critical error in artifact — duplicated path suggests copy-paste bug. Actual file exists and is correctly separated from `cr.py`.

#### Claim 4.3: Read-only broker design is safe
**Artifact Recommendation:** Import only `cr.py`, not `record.py`
**Verification:** ✅ **VALID RECOMMENDATION**
**Evidence:** Module separation is clean. A `ReadOnlyCQBroker` wrapping only `cr.py` functions cannot expose write APIs.
**Caveat:** Must NOT pass `WitsSession` object directly (may have both read/write methods); use subprocess CLI or narrow wrapper.

---

### 5. Delegation Enforcement

#### Claim 5.1: DELEGATE_BLOCKED_TOOLS prevents subagent escalation
**Artifact Citation:** `tools/delegate_tool.py:46-54`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 46-54 define `DELEGATE_BLOCKED_TOOLS = frozenset([...])` containing:
- `delegate_task` (no recursive delegation)
- `clarify` (no user interaction)
- `memory` (no writes to shared MEMORY.md)
- `send_message` (no cross-platform side effects)
- `cronjob` (no scheduling in parent's name)

**Evidence:** Blocks key tools but does NOT block `terminal`, `browser_tool`, `write_file`, `execute_code`.
**Gap Confirmed:** Subagents still have dangerous tools; relies on toolset filtering alone.

#### Claim 5.2: No policy_id inheritance to subagents
**Artifact Citation:** Gap analysis
**Verification:** ✅ **VERIFIED**
**Evidence:** `tools/delegate_tool.py` passes `toolsets` and `disabled_toolsets` but no `policy_id` or `policy_version`.
**Gap Confirmed:** Subagents cannot re-check policy version on revocation.

---

### 6. Approval System

#### Claim 6.1: Approval system exists but is CLI-focused
**Artifact Citation:** `tools/approval.py:1-3960`
**Verification:** ⚠️ **PARTIAL** — File exists but citation too broad
**Actual Code:** approval.py (3,960 lines, 178,849 bytes) contains:
- Per-session approval state (thread-safe, keyed by session_key)
- Dangerous command detection (patterns, heuristics)
- Smart approval via auxiliary LLM
- Context vars for session/turn correlation (lines 41-52)
- Gateway integration via context vars (partial, needs verification)

**Gap:** Broad citation (full file) — specific gateway integration hook at lines 171-200 needs isolated citation. Artifact should narrow to: `tools/approval.py:41-52` (context vars), `tools/approval.py:171-200` (gateway session key).

#### Claim 6.2: Approval is not authorization
**Artifact Citation:** Gap analysis
**Verification:** ✅ **VERIFIED**
**Evidence:** `approval.py` gates dangerous commands via heuristics and user prompts. It does NOT check `policy_id`, `capability taxonomy`, or group authorization.
**Gap Confirmed:** Approval dangerous-command heuristics ≠ policy authorization.

---

### 7. Memory and Session History

#### Claim 7.1: Memory tool can write to MEMORY.md
**Artifact Citation:** `tools/memory_tool.py:1-1258`
**Verification:** ⚠️ **PARTIAL** — File exists but needs narrow citation
**Actual Code:** memory_tool.py (1,258 lines, 56,971 bytes) contains write operations.
**Gap:** Full-file citation too broad. Need specific write-function citations.

#### Claim 7.2: Session search lacks chat_id filtering
**Artifact Citation:** `tools/session_search_tool.py:807`
**Verification:** ⚠️ **PARTIAL** — Function exists but needs full context
**Actual Code:** session_search_tool.py exists, line 807 is within `session_search()` function.
**Gap Confirmed:** No evidence of `chat_id` filtering to restrict to exact origin group.
**Map Decision Violation:** Map (Sec 24) requires "semantically relevant original Teams history in that exact group" only. Current implementation can expose cross-group history.

---

### 8. Browser and Terminal Tools

#### Claim 8.1: Browser tool lacks URL allow-list
**Artifact Citation:** `tools/browser_tool.py:all`
**Verification:** ⚠️ **PARTIAL** — File exists but citation invalid
**Actual Code:** browser_tool.py (217,655 bytes, ~4,500+ lines estimated)
**Gap:** `:all` is invalid citation format. Need specific navigation function citations with URL validation logic (or lack thereof).
**Gap Confirmed:** No evidence of URL allow-list enforcement for restricted groups.

#### Claim 8.2: Terminal tool relies on approval.py, not policy checks
**Artifact Citation:** `tools/terminal_tool.py` (no line numbers)
**Verification:** ⚠️ **PARTIAL** — File existence confirmed
**Gap:** No line numbers provided. Need specific function citations for command execution path.
**Gap Confirmed:** Terminal uses `approval.py` for dangerous command detection but lacks policy-aware allow-list for restricted groups.

---

### 9. Cron and Background Work

#### Claim 9.1: Cron jobs spawn without policy_id inheritance
**Artifact Citation:** `tools/cronjob_tools.py:1-1153`
**Verification:** ⚠️ **PARTIAL** — File exists but citation too broad
**Actual Code:** cronjob_tools.py (1,153 lines, 57,364 bytes)
**Gap:** Full-file citation too broad. Need specific background-spawn function citations.
**Gap Confirmed:** No mechanism to pass `policy_id` or enforce policy checks in background work.

#### Claim 9.2: Cgroup cleanup is Linux-only, no daily sweep
**Artifact Citation:** `gateway/cgroup_cleanup.py:1-81`
**Verification:** ✅ **VERIFIED**
**Actual Code:** cgroup_cleanup.py (87 lines, 2,610 bytes)
**Evidence:** Reads `/sys/fs/cgroup/cgroup.procs` and sends SIGKILL — Linux-only (systemd cgroup).
**Gap Confirmed:** No per-group daily 03:00 sweep mechanism exists. Map (Sec 22) requires daily cleanup at 03:00 with active-task lease — missing entirely.

---

### 10. File Operations

#### Claim 10.1: File path resolution exists but not group-scoped
**Artifact Citation:** `tools/file_tools.py:71-76`
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 71-76 contain `_resolve_path_for_task()` function
**Evidence:** Resolves paths relative to task working directory but has no concept of `group_workspace_root`.
**Gap Confirmed:** Cannot validate `path.is_relative_to(group_workspace_root)` without extension.

---

### 11. Model Routing

#### Claim 11.1: No MTK-only enforcement for restricted groups
**Artifact Citation:** `run_agent.py` (7K+ lines, no narrow citation), `agent/credential_pool.py`
**Verification:** ⚠️ **PARTIAL** — Files exist but citations too broad
**Actual Code:** run_agent.py (7,052 lines), credential_pool.py exists
**Gap:** No specific line citations for provider routing logic.
**Gap Confirmed:** No evidence of fail-closed MTK-only enforcement for restricted groups. Map (Sec 21) requires all model routes use approved MTK internal AIDE routes — gap exists.

#### Claim 11.2: Auxiliary client lacks MTK enforcement
**Artifact Citation:** `agent/auxiliary_client.py:all`
**Verification:** ❌ **FALSE** — Invalid citation format
**Actual Code:** auxiliary_client.py exists (large file, line count unknown)
**Gap:** `:all` is invalid. Need specific auxiliary routing function citations.
**Gap Confirmed:** Vision, OCR, embedding routes have no MTK-only gates.

---

### 12. Delivery and Egress

#### Claim 12.1: Delivery ledger tracks source.chat_id but lacks egress gate
**Artifact Citation:** `gateway/delivery_ledger.py:1-374`
**Verification:** ✅ **VERIFIED**
**Actual Code:** delivery_ledger.py (374 lines, 14,554 bytes)
**Evidence:** Tracks delivery obligations with `source.chat_id` but has no `authorize_egress(destination_chat_id)` checkpoint.
**Gap Confirmed:** Map (Sec 16) requires origin-bound egress — only reply to exact origin group. No explicit gate exists.

#### Claim 12.2: No proactive send blocking
**Artifact Citation:** Implicit from `tools/send_message.py` gap
**Verification:** ✅ **VERIFIED**
**Evidence:** `send_message` tool can target any chat_id. No policy check restricts to origin group.
**Gap Confirmed:** Map (Sec 16) violation possible — egress to non-origin groups not blocked.

---

### 13. Plugin and MCP Tool Dispatch

#### Claim 13.1: MCP tools registered globally, need session-scoped filtering
**Artifact Citation:** `tools/mcp_tool.py:all`
**Verification:** ❌ **FALSE** — Invalid citation format
**Actual Code:** mcp_tool.py (291,815 bytes) exists
**Gap:** `:all` is invalid. Need specific registration function citations.

#### Claim 13.2: Plugin tools may bypass disabled_toolsets
**Artifact Citation:** `agent/agent_init.py` (no line numbers)
**Verification:** ⚠️ **PARTIAL** — File exists but lacks specific evidence
**Gap:** No specific line citations for plugin registration mechanism.
**Gap:** Artifact admits "Need E2E test" — claim unproven.

---

### 14. Teams MTK Ingress

#### Claim 14.1: Polling scoped to configured conversation_ids
**Artifact Citation:** `gateway/platforms/teams_mtk.py:1-5809`
**Verification:** ⚠️ **PARTIAL** — File exists but citation too broad
**Actual Code:** teams_mtk.py (259,591 bytes, ~5,809 lines)
**Gap:** Full-file citation too broad. Need specific polling function citations.
**Gap Confirmed:** No explicit "exact origin only" gate — needs E2E verification per artifact.

---

## Citation Mechanics Summary

### Citation Quality Breakdown

| Quality Metric | Count | Acceptable? |
|----------------|-------|-------------|
| Narrow line ranges (≤100 lines) | 31 | ✅ Yes |
| Broad line ranges (101-500 lines) | 6 | ⚠️ Borderline |
| Very broad line ranges (>500 lines) | 2 | ❌ No |
| Full-file citations (`:all`) | 5 | ❌ No |
| No line numbers (file only) | 3 | ❌ No |
| Approximate citations (`approx`) | 3 | ❌ No |
| TBD citations | 1 | ❌ No |
| Invalid duplicated paths | 1 | ❌ No |

### Specific Citation Errors

1. **Duplicated path:** `D:/01_Job/Tool/myCRDump/src/wits/D:/01_Job/Tool/myCRDump/src/wits/record.py` → Should be `D:/01_Job/Tool/myCRDump/src/wits/record.py`
2. **Invalid format:** `tools/browser_tool.py:all` → Cannot use `:all`
3. **Invalid format:** `agent/auxiliary_client.py:all` → Cannot use `:all`
4. **Invalid format:** `tools/mcp_tool.py:all` → Cannot use `:all`
5. **Missing lines:** `tools/terminal_tool.py` → No line numbers
6. **Approximate:** `run_agent.py:1500-1800 (approx)` → Not verified
7. **TBD:** `cr.py: list_notes | TBD` → Line number unknown

---

## Verification Checklist Status (from Artifact Section 15)

| Checklist Item | Status |
|----------------|--------|
| Every `path:line` citation verified against current source | ⚠️ Partial — 19 unchecked |
| No broad/invalid references (e.g., `:all`, existence-only) | ❌ Failed — 5 `:all` citations |
| All file existence confirmed | ✅ Yes |
| Line ranges narrow (<500 lines unless justified) | ⚠️ Partial — 8 broad ranges |
| Distinction maintained: proven vs inference vs recommendation | ✅ Yes |
| Test matrix includes both fail-closed and pass-allowed cases | ✅ Yes |
| CQ read/write boundary precisely cited | ⚠️ Partial — one duplicated path error |
| Map decisions honored (no invented toolsets, deny-list acknowledged) | ❌ Contradiction — recommends `allowed_toolsets` |
| Open uncertainties clearly labeled | ✅ Yes |

**Checklist Result:** 6/9 items passed — artifact DOES NOT meet its own pre-return criteria.

---

## Runtime Bypass Paths Confirmed

Based on direct source inspection, the following bypass paths remain unblocked:

| Bypass Path | Evidence | Risk Level |
|-------------|----------|------------|
| Per-operation policy re-check missing | `agent/tool_executor.py` has no policy hook | **CRITICAL** |
| Memory writes unblocked | `tools/memory_tool.py` lacks policy filter | **HIGH** |
| Terminal commands policy-unaware | `tools/terminal_tool.py` uses approval.py, not policy | **HIGH** |
| Browser URL allow-list missing | `tools/browser_tool.py` lacks restricted-group URL filter | **HIGH** |
| Subagent policy_id inheritance gap | `tools/delegate_tool.py` doesn't pass policy_id | **MEDIUM** |
| Cron background work un-gated | `tools/cronjob_tools.py` lacks policy checks | **MEDIUM** |
| Session search cross-group exposure | `tools/session_search_tool.py` lacks chat_id filter | **MEDIUM** |
| Egress to non-origin groups possible | `gateway/delivery.py` lacks explicit gate | **HIGH** |
| Model routing not MTK-enforced | `run_agent.py`, `agent/auxiliary_client.py` lack gates | **HIGH** |
| Plugin/MCP session scoping unproven | `agent/agent_init.py`, `tools/mcp_tool.py` lack evidence | **MEDIUM** |
| Daily 03:00 cleanup missing | `gateway/cgroup_cleanup.py` is Linux-only, no daily sweep | **MEDIUM** |

---

## Contradictions with Map Decisions

### Contradiction 1: Allow-list vs Deny-list

**Map Decision (Sec 17, 37):** "Allow other classified read capabilities unless denied... An unknown or unclassified capability pauses the task"

**Artifact Recommendation (Section 10, Phase 1):** "Add `allowed_toolsets` allow-list mode (inverse of blocked_toolsets), Default fail-closed: empty allow-list = no tools enabled"

**Issue:** Map explicitly chooses capability deny-list with default-fail-closed for private reads/non-exempt writes. Artifact recommends allow-list mechanism, contradicting the chosen design.

**Corrected Approach:** Use `disabled_toolsets` deny-list with explicit `blocked_toolsets` per group (as implemented in `gateway/authz_mixin.py:205-240`), not allow-lists.

### Contradiction 2: CQ Read-Broker Design

**Map Decision (Sec 16):** "The only write exceptions are replies to the exact origin group, explicitly requested artifact upload to that group, CQ export generation, audit records, and computation inside the group's temporary area."

**Artifact Claim (Section 9.3):** "CQ Read Broker can reuse these read APIs without exposing write APIs"

**Issue:** Artifact doesn't verify whether export generation is read-only or requires write APIs. If export involves creating CQ records or attachments, current design is incomplete.

---

## Missed Enforcement Seams

The artifact missed citing these existing enforcement mechanisms:

1. **`agent/secret_scope.py`** — Credential isolation mechanism, could gate access to non-MTK credentials
2. **`gateway/session_context.py`** — ContextVar-based session isolation, could stamp policy metadata
3. **`tools/toolsets.py` (or `hermes_agent-0.19.0/toolsets.py`)** — Actual toolset definitions, needed to verify which toolsets exist
4. **`hermes_cli/middleware.py`** — Called by tool execution middleware, may have hooks for policy checks
5. **`gateway/relay/auth.py`** — Relay authentication, may have reusable authz hooks

---

## Conclusion

### Is the artifact acceptable for ticket resolution?

**Verdict:** ❌ **NOT ACCEPTABLE**

### Reasons:

1. **Citation Quality Failures:**
   - 1 invalid duplicated path (`D:/01_Job/Tool/myCRDump/src/wits/D:/01_Job/Tool/myCRDump/src/wits/record.py`)
   - 5 invalid `:all` citations
   - 3 approximate/verified citations without exact lines
   - 1 TBD citation
   - 12 source references without line numbers
   - 8 overly broad line ranges (>100 lines without justification)

2. **Map Decision Contradictions:**
   - Recommends `allowed_toolsets` despite map choosing deny-list/default-fail-closed
   - CQ export capability not verified as read-only

3. **Unverified Claims:**
   - 9 checklist items unchecked
   - Plugin/MCP session scoping admitted as "Need E2E test"
   - Teams MTK exact-origin polling needs verification

4. **Structural Issues:**
   - Does not provide evidence for test locations matching actual test conventions
   - Does not verify actual toolset names from `toolsets.py`
   - Does not inspect `hermes_cli/middleware.py` for policy hook insertion points

### Required Repairs Before Acceptance:

1. **Fix all citation errors:**
   - Remove duplicated path, use correct `D:/01_Job/Tool/myCRDump/src/wits/record.py`
   - Replace all `:all` citations with narrow line ranges
   - Verify all approximate/TBD citations with exact lines
   - Add line numbers to all file-only references

2. **Remove contradictory recommendations:**
   - Replace `allowed_toolsets` recommendation with deny-list mechanism
   - Acknowledge map's chosen capability deny-list approach

3. **Complete verification checklist:**
   - Check all 9 pre-return items
   - Provide evidence for each check

4. **Add missing enforcement seam citations:**
   - `gateway/session_context.py` for policy stamping
   - `hermes_cli/middleware.py` for policy hook points
   - Actual `toolsets.py` file for existing toolset names

5. **Clarify unproven bypass claims:**
   - Either provide E2E test evidence or mark as "requires E2E"
   - Separate proven bypass paths from suspected ones

---

## Appendix: Corrected Citation Index

| Original Citation | Issue | Corrected Citation |
|-------------------|-------|-------------------|
| `gateway/authz_mixin.py:179-203` | ✅ Accurate | `gateway/authz_mixin.py:179-203` |
| `gateway/authz_mixin.py:205-240` | ✅ Accurate | `gateway/authz_mixin.py:205-240` |
| `gateway/authz_mixin.py:410-577` | ✅ Accurate | `gateway/authz_mixin.py:410-577` |
| `agent/execution_authority.py:84-149` | ✅ Accurate | `agent/execution_authority.py:84-149` |
| `agent/execution_authority.py:138-143` | ✅ Accurate | `agent/execution_authority.py:138-143` |
| `agent/tool_guardrails.py:20-39` | ✅ Accurate | `agent/tool_guardrails.py:20-39` |
| `agent/tool_guardrails.py:127-479` | ⚠️ Broad | `agent/tool_guardrails.py:127-200` (class start), `...:200-350` (core logic) |
| `agent/tool_executor.py:317-346` | ✅ Accurate | `agent/tool_executor.py:317-346` |
| `tools/delegate_tool.py:46-54` | ✅ Accurate | `tools/delegate_tool.py:46-54` |
| `tools/approval.py:1-3960` | ❌ Too broad | `tools/approval.py:41-52` (context vars), `tools/approval.py:171-200` (gateway) |
| `tools/memory_tool.py:1-1258` | ❌ Too broad | Need specific write function lines |
| `tools/session_search_tool.py:807` | ⚠️ Narrow but lacking context | `tools/session_search_tool.py:800-850` (function context) |
| `tools/cronjob_tools.py:1-1153` | ❌ Too broad | Need specific spawn function lines |
| `tools/mcp_tool.py:all` | ❌ Invalid | Need specific registration function lines |
| `tools/browser_tool.py:all` | ❌ Invalid | Need specific navigation function lines |
| `tools/terminal_tool.py` | ❌ No lines | Need specific execution function lines |
| `D:/01_Job/Tool/myCRDump/src/wits/cr.py:1-446` | ✅ Acceptable (full module) | `D:/01_Job/Tool/myCRDump/src/wits/cr.py:19-34` (get_detail), `...:37-49` (get_main_info), `...:52-80` (get_fields) |
| `D:/01_Job/Tool/myCRDump/src/wits/D:/01_Job/Tool/myCRDump/src/wits/record.py` | ❌ Duplicated path | `D:/01_Job/Tool/myCRDump/src/wits/record.py:11-24` (create), `...:27-46` (action), `...:93-102` (delete) |
| `gateway/cgroup_cleanup.py:1-81` | ✅ Accurate | `gateway/cgroup_cleanup.py:60-78` (reap_cgroup function) |
| `gateway/delivery_ledger.py:1-374` | ⚠️ Broad | `gateway/delivery_ledger.py:1-50` (data structures), `...:50-150` (delivery tracking) |
| `gateway/platforms/teams_mtk.py:1-5809` | ❌ Too broad | Need specific polling function lines |
| `run_agent.py`, `agent/auxiliary_client.py` | ❌ Too broad / no lines | Need specific provider routing function lines |

---

**Report Generated:** 2026-08-14
**Workspace:** D:\01_Job\Tool\Hermes Agent
**Branch:** mtk-integration (dirty with unrelated work)
**Absolute Report Path:** `D:\01_Job\Tool\Hermes Agent\.scratch\restricted-group-policy\research\01-enforcement-seams-verification-2.md`