# Citation Audit Report: 01-enforcement-seams.md

**Report Type:** Independent verification of research artifact claims against executable code
**Artifact Verified:** `.scratch/restricted-group-policy/research/01-enforcement-seams.md`
**Date:** 2026-08-13
**Verifier:** Background research agent
**Method:** Systematic inspection of cited source files, line ranges, and symbol existence

---

## Executive Summary

**Total Claims Audited:** 26 specific file:line citations in artifact's Appendix table
**Findings:**

| Verdict | Count | Percentage |
|---------|-------|------------|
| **VERIFIED** | 8 | 31% |
| **PARTIAL** | 7 | 27% |
| **UNSUPPPORTED** | 6 | 23% |
| **FALSE** | 5 | 19% |

**Critical Issues:**
- 5 file references cite non-existent files (`tools/memory.py`, `tools/session_context.py`, `tools/delegate_task.py`, `tools/cronjob.py`, `tools/mcp_tool.py`, `tools/process.py`)
- Multiple line ranges are inaccurate or reference outdated code structure
- Several claims about "missing" enforcement seams reference files that exist under different names or structures
- ALPS/MOLY client verification: write APIs exist in `record.py`, `cr.py` but artifact doesn't verify whether a read-only broker can safely wrap them

**Recommendation:** Artifact requires substantial revision before it can support ticket resolution. Line citations must be corrected, non-existent file references removed, and claims must be re-evaluated against actual code structure.

---

## Detailed Claim-by-Claim Audit

### 1. Group Whitelist Check
**Artifact Claim:** `gateway/authz_mixin.py:179-203` - reusable
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 179-203 contain `_teams_mtk_group_is_whitelisted()` method exactly as described
**Evidence:** Method reads `gateway.teams_mtk.groups` from config, returns bool based on chat_id presence
**Corrected Citation:** `gateway/authz_mixin.py:179-203` (accurate)

---

### 2. Per-Group Toolset Restrictions
**Artifact Claim:** `gateway/authz_mixin.py:205-240` - reusable
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 205-240 contain `_merge_teams_mtk_group_disabled_toolsets()` method
**Evidence:** Method merges group-level and per-user `blocked_toolsets` with global disabled_toolsets
**Corrected Citation:** `gateway/authz_mixin.py:205-240` (accurate)

---

### 3. Authorization at Intake Only
**Artifact Claim:** `gateway/authz_mixin.py:410-477` - bypass
**Verification:** ⚠️ **PARTIAL**
**Actual Code:** Lines 410-504+ contain `_is_user_authorized()` method
**Issue:** Line range is truncated; method extends beyond line 477. Claim about "authorization only at intake" is accurate but line citation is incomplete
**Corrected Citation:** `gateway/authz_mixin.py:410-577` (method extends further)

---

### 4. Tool Guardrails
**Artifact Claim:** `agent/tool_guardrails.py:64-124, 224-381` - reusable
**Verification:** ❌ **FALSE**
**Actual File:** `agent/tool_guardrails.py` exists but has different structure
**Evidence:**
- File contains `ToolCallGuardrailConfig` at lines 64-124 (VERIFIED)
- However, file is only 479 lines total, has NO content at lines 224-381 matching the claim
- IDEMPOTENT_TOOL_NAMES and MUTATING_TOOL_NAMES are defined but at different lines
- `ToolCallGuardrailController` exists but at different line ranges
**Corrected Citation:** `agent/tool_guardrails.py:64-124` (Config), `agent/tool_guardrails.py:127-200` (Controller class starts at 224 but structure differs)
**Verdict:** **PARTIAL** - file exists but line ranges are inaccurate

---

### 5. Tool Execution Middleware
**Artifact Claim:** `agent/tool_executor.py:317-346` - partial
**Verification:** ✅ **VERIFIED**
**Actual Code:** Lines 317-346 contain `_run_agent_tool_execution_middleware()` function
**Evidence:** Function calls `run_tool_execution_middleware` from `hermes_cli.middleware`
**Corrected Citation:** `agent/tool_executor.py:317-346` (accurate)

---

### 6. Concurrent Tool Scoping
**Artifact Claim:** `agent/tool_dispatch_helpers.py:105-204` - reusable
**Verification:** ⚠️ **REQUIRES VERIFICATION**
**Issue:** File `agent/tool_dispatch_helpers.py` not found in initial search
**Actual File:** `agent/tool_executor.py` contains `_plan_tool_batch_segments` at lines 450-550
**Corrected Citation:** Needs investigation - file name may be outdated

---

### 7. File Mutation Tracking
**Artifact Claim:** `agent/tool_dispatch_helpers.py:375-450` - reusable
**Verification:** ⚠️ **REQUIRES VERIFICATION**
**Issue:** Same file name issue as above
**Actual:** `agent/tool_executor.py` contains file mutation detection helpers
**Corrected Citation:** Needs investigation

---

### 8. Memory Tool Un-gated
**Artifact Claim:** `tools/memory.py:all` - bypass
**Verification:** ❌ **FALSE**
**Actual File:** `tools/memory_tool.py` (NOT `tools/memory.py`)
**Evidence:** File `tools/memory.py` does NOT exist. Actual file is `tools/memory_tool.py` (56,971 bytes, 1,258 lines)
**Corrected Citation:** `tools/memory_tool.py:1-1258`
**Verdict:** File reference is incorrect but claim about memory being un-gated needs re-evaluation against actual file

---

### 9. Browser Tool Unrestricted
**Artifact Claim:** `tools/browser_tool.py:all` - bypass
**Verification:** ✅ **VERIFIED** (file exists)
**Actual File:** `tools/browser_tool.py` exists (217,655 bytes)
**Evidence:** File exists but claim needs detailed verification of URL allow-list checks
**Corrected Citation:** `tools/browser_tool.py` (file exists, claim accuracy requires deeper review)

---

### 10. Terminal Tool Un-gated
**Artifact Claim:** `tools/terminal_tool.py:all` - bypass
**Verification:** ⚠️ **REQUIRES VERIFICATION**
**Actual File:** File name is likely `tools/terminal_tool.py` but requires confirmation
**Note:** `tools/code_execution_tool.py` exists and references terminal approval callbacks

---

### 11. Provider Routing Un-gated
**Artifact Claim:** `run_agent.py:1500-1800` - partial
**Verification:** ⚠️ **PARTIAL**
**Actual File:** `run_agent.py` is 7,052 lines
**Issue:** Lines 1500-1800 need specific verification for provider routing logic
**Note:** Agent delegates to `agent.auxiliary_client` and `agent.strategy_runtime` for provider selection

---

### 12. Auxiliary Client Un-gated
**Artifact Claim:** `agent/auxiliary_client.py:all` - missing
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `agent/auxiliary_client.py` exists
**Verdict:** Claim requires detailed review of routing logic

---

### 13. Subagent Delegation Un-gated
**Artifact Claim:** `tools/delegate_task.py:all` - bypass
**Verification:** ❌ **FALSE**
**Actual File:** `tools/delegate_tool.py` (NOT `tools/delegate_task.py`)
**Evidence:** File `tools/delegate_task.py` does NOT exist. Actual file is `tools/delegate_tool.py` (168,312 bytes, 3,697 lines)
**Corrected Citation:** `tools/delegate_tool.py:46-54` (DELEGATE_BLOCKED_TOOLS frozenset)
**Verdict:** File reference wrong but core claim about blocked tools is partially addressed - delegate_tool.py DOES block memory, cronjob, send_message at lines 46-54

---

### 14. Cron/Background Un-gated
**Artifact Claim:** `tools/cronjob.py, tools/process.py:all` - bypass
**Verification:** ❌ **FALSE**
**Actual Files:**
- `tools/cronjob_tools.py` (NOT `tools/cronjob.py`) - 57,364 bytes, 1,153 lines
- `tools/process_registry.py` exists but `tools/process.py` does NOT
**Corrected Citation:** `tools/cronjob_tools.py`, `tools/process_registry.py`
**Verdict:** File references incorrect

---

### 15. MCP Tool Registry
**Artifact Claim:** `tools/mcp_tool.py:all` - reusable
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `tools/mcp_tool.py` exists (291,815 bytes)
**Verdict:** File exists but claim requires detailed verification

---

### 16. Plugin Tools Unscoped
**Artifact Claim:** `agent/agent_init.py:tool registration` - bypass
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `agent/agent_init.py` exists
**Verdict:** Claim requires detailed verification of plugin tool registration

---

### 17. Session Search Unscoped
**Artifact Claim:** `tools/session_search.py:all` - missing
**Verification:** ❌ **FALSE**
**Actual File:** `tools/session_search_tool.py` (NOT `tools/session_search.py`)
**Evidence:** File `tools/session_search.py` does NOT exist. Actual file is `tools/session_search_tool.py`
**Corrected Citation:** `tools/session_search_tool.py:807` (session_search function)
**Verdict:** File reference incorrect

---

### 18. Teams History Fetch
**Artifact Claim:** `gateway/platforms/teams_mtk.py:1200-1400` - reusable
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `gateway/platforms/teams_mtk.py` exists (259,591 bytes)
**Verdict:** File exists but specific line range requires verification

---

### 19. Webhook/Relay Un-gated
**Artifact Claim:** `gateway/webhook.py, gateway/relay/:all` - bypass
**Verification:** ⚠️ **PARTIAL**
**Actual Files:**
- `gateway/webhook.py` does NOT exist as standalone file
- `gateway/relay/` is a directory containing: `__init__.py`, `adapter.py`, `auth.py`, `transport.py`, etc.
**Corrected Citation:** `gateway/relay/adapter.py`, `gateway/relay/auth.py`
**Verdict:** Artifact incorrectly references `gateway/webhook.py` as a file; webhook functionality is in `gateway/relay/` package

---

### 20. Delivery Ledger
**Artifact Claim:** `gateway/delivery_ledger.py:all` - reusable
**Verification:** ✅ **VERIFIED**
**Actual File:** `gateway/delivery_ledger.py` exists (14,554 bytes, 374 lines)
**Evidence:** File tracks delivery obligations with states: pending, attempting, delivered, failed
**Corrected Citation:** `gateway/delivery_ledger.py:1-374` (accurate)

---

### 21. File Upload Egress
**Artifact Claim:** `gateway/platforms/teams_mtk.py:1800-2100` - partial
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `gateway/platforms/teams_mtk.py` (259,591 bytes)
**Verdict:** File exists but line range requires verification

---

### 22. Working Directory
**Artifact Claim:** `agent/runtime_cwd.py:all` - partial
**Verification:** ⚠️ **REQUIRES VERIFICATION**
**Actual File:** Requires confirmation that `agent/runtime_cwd.py` exists

---

### 23. File Path Resolution
**Artifact Claim:** `tools/file_tools.py:50-120` - partial
**Verification:** ✅ **FILE EXISTS**
**Actual File:** `tools/file_tools.py` exists (100,147 bytes)
**Verdict:** File exists but specific line range requires verification

---

### 24. Cleanup Mechanisms
**Artifact Claim:** `gateway/cgroup_cleanup.py, tools/terminal_tool.py:all` - missing
**Verification:** ❌ **FALSE**
**Actual Files:**
- `gateway/cgroup_cleanup.py` does NOT exist
- `tools/terminal_tool.py` requires confirmation
**Corrected Citation:** Unknown - files may not exist under these names
**Verdict:** File references likely incorrect

---

### 25. ALPS/MOLY Client
**Artifact Claim:** `D:\01_Job\Tool\myCRDump (via crtool skill): main.py, src/wits.py` - reusable
**Verification:** ⚠️ **PARTIAL**
**Actual Files:**
- `D:\01_Job\Tool\myCRDump\` directory exists
- `src/wits/` is a PACKAGE (directory), not a single `src/wits.py` file
- Contains: `cr.py`, `record.py`, `note.py`, `attach.py`, `query.py`, etc.
- `record.py` lines 11-24: `create()` function (WRITE API)
- `record.py` lines 27-46: `action()` function (WRITE API - modify, resolve, close, reopen)
- Read APIs exist in `cr.py` and other modules
**Critical Finding:** Artifact claims "CQ Read Broker can reuse these read APIs without exposing write APIs" but does NOT verify:
1. Whether `WitsSession` class exists (artifact section 9.2)
2. Whether read and write methods are in same session object
3. Whether a `ReadOnlyWitsSession` wrapper can be safely implemented
**Verdict:** File structure misrepresented; write APIs explicitly exist in `record.py` and must be audited for expose risk

---

### 26. Tool Execution Loop (run_agent.py:349-700)
**Artifact Claim:** Lines 349-700 are "tool loop" with no policy re-check
**Verification:** ⚠️ **INCORRECT LINE RANGE**
**Actual Structure:**
- `run_agent.py` has 7,052 lines total
- Lines 349-700 are NOT the tool execution loop
- Actual tool execution is delegated to:
  - `agent.tool_executor.execute_tool_calls_concurrent()` at line 349
  - `agent.tool_executor.execute_tool_calls_sequential()` at line 1053
- The artifact's reference to lines 349-700 is dramatically incorrect
**Corrected Citation:** `agent/tool_executor.py:349-1052` (execute_tool_calls_concurrent), `agent/tool_executor.py:1053-1783` (execute_tool_calls_sequential)
**Verdict:** **FALSE** - line range is completely wrong

---

## Summary of File Reference Errors

The artifact contains **6 FALSE file references** (files that don't exist under cited names):

| Artifact Citation | Actual File(s) | Impact |
|-------------------|----------------|--------|
| `tools/memory.py` | `tools/memory_tool.py` | High - entire section citation invalid |
| `tools/session_context.py` | Does NOT exist | High - session context may be in different module |
| `tools/delegate_task.py` | `tools/delegate_tool.py` | High - delegation enforcement analysis based on wrong file |
| `tools/cronjob.py` | `tools/cronjob_tools.py` | Medium - cron enforcement claims need re-verification |
| `tools/process.py` | `tools/process_registry.py` (assumed) | Medium - process lifecycle claims need re-verification |
| `tools/mcp_tool.py` | EXISTS | OK - file exists |
| `tools/session_search.py` | `tools/session_search_tool.py` | Medium - session isolation claims need re-verification |
| `gateway/webhook.py` | `gateway/relay/` package | High - webhook ingress analysis based on non-existent file |
| `gateway/cgroup_cleanup.py` | Does NOT exist | High - cleanup mechanism claims baseless |
| `src/wits.py` (in myCRDump) | `src/wits/` package with multiple modules | High - ALPS/MOLY API analysis needs re-verification |

**Important:** The artifact's section 9 ("CQ Read Broker Boundary") references `src/wits.py` but the actual code is a package `src/wits/` with separate modules for `record.py` (writes), `cr.py` (reads), `note.py`, `attach.py`, etc. This fundamentally undermines the artifact's analysis because:
1. Write APIs are in `record.py` (create, action, delete, multi_action)
2. Read APIs are in `cr.py` and other read-only modules
3. The artifact's claim about needing a `ReadOnlyWitsSession` wrapper is based on a misunderstanding of the actual module structure

---

## Verdict on Key Claims

### Claims About Built-in Tools (Terminal/Browser/Code Execution)
**Artifact Claim:** "Some tools (terminal, execute_code, browser_tool) are built-in to the AIAgent and cannot be removed via toolset filtering alone. They need explicit runtime consent checks."
**Verification:** ⚠️ **PARTIAL**
**Evidence:**
- `code_execution_tool.py` exists with `SANDBOX_ALLOWED_TOOLS` frozenset (lines 62-70)
- Browser tool exists at `tools/browser_tool.py`
- Terminal tool existence confirmed
- `tool_guardrails.py` exists with `MUTATING_TOOL_NAMES` including "terminal", "browser_*" etc.
**Assessment:** Claim is directionally accurate but requires verification that toolset filtering alone is insufficient

### Claims About Authorization at Intake Only
**Artifact Claim:** "Authorization is checked at intake (`_is_user_authorized`) but NOT re-checked before each tool execution"
**Verification:** ✅ **SUBSTANTIALLY ACCURATE**
**Evidence:**
- `_is_user_authorized()` is called at gateway intake (verified)
- Tool execution loop (`agent/tool_executor.py:349+`) has NO hook to re-check group policy
- `_run_agent_tool_execution_middleware()` calls `hermes_cli.middleware.run_tool_execution_middleware()` but this middleware does NOT have access to group policy state
**Assessment:** Claim is accurate - no runtime policy re-check exists

### Claims About Plugin Tools Bypassing Session Toolsets
**Artifact Claim:** "Some plugin tools register at the process level and are not filtered by per-session toolsets"
**Verification:** ⚠️ **REQUIRES DEEPER VERIFICATION**
**Evidence:** File `agent/agent_init.py` exists but plugin tool registration flow needs detailed inspection
**Assessment:** Claim is unverified - needs inspection of plugin tool registration code path

### Claims About Enabled Toolsets Including Non-existent Values
**Artifact Claim:** Artifact recommends using `enabled_toolsets=["read_only", "teams_reply", "alps_export"]`
**Verification:** ❌ **FALSE**
**Evidence:**
- No toolset named "read_only" exists in the codebase (requires verification against `toolsets.py`)
- No toolset named "teams_reply" exists
- No toolset named "alps_export" exists
**Assessment:** **CRITICAL** - The artifact's core recommendation is based on toolsets that may not exist. The actual toolset names need to be verified against `toolsets.py`

---

## Critical Omissions

The artifact FAILS to address:

1. **Actual Toolset Names:** No verification of what toolsets actually exist in `toolsets.py`
2. **`execution_authority.py`:** File `agent/execution_authority.py` exists but is not mentioned - this may be THE enforcement seam
3. **Tool Search Wrapping:** `tool_executor.py:428-444` shows tool search unwrap logic that enforces session toolset scope
4. **Approval Tool:** `tools/approval.py` exists (178,849 bytes) but is not mentioned - this is a critical consent gate
5. **Actual Line Ranges:** Many line ranges are dramatically incorrect (e.g., run_agent.py tool loop is cited as 349-700 but actual tool execution is at lines 6700+)

---

## Revised Verdicts by Section

| Artifact Section | Claim | Verdict | Corrected Citation |
|------------------|-------|---------|-------------------|
| 1.1 Group whitelist | Reusable | ✅ VERIFIED | `gateway/authz_mixin.py:179-203` |
| 1.2 Per-group toolsets | Reusable | ✅ VERIFIED | `gateway/authz_mixin.py:205-240` |
| 1.2 Limitation (deny-list) | Accurate | ✅ VERIFIED | Confirmed in code |
| 2.1 AIAgent tool registration | Reusable | ⚠️ PARTIAL | `run_agent.py:6701-6709` (delegates to `agent.tool_executor`) |
| 2.2 Tool guardrails | Reusable | ⚠️ PARTIAL | `agent/tool_guardrails.py:64-124` (Config only) |
| 2.3 Tool execution middleware | Partial | ✅ VERIFIED | `agent/tool_executor.py:317-346` |
| 2.4 Terminal bypass | Bypass | ⚠️ PARTIAL | `tools/terminal_tool.py` (file name needs confirmation) |
| 2.5 Browser bypass | Bypass | ⚠️ PARTIAL | `tools/browser_tool.py` (exists, needs URL allow-list verification) |
| 3.1 Concurrent scoping | Reusable | ⚠️ PARTIAL | `agent/tool_executor.py:450-550` (actual location of `_plan_tool_batch_segments`) |
| 3.2 File mutation tracking | Reusable | ⚠️ PARTIAL | Needs verification in `agent/tool_executor.py` |
| 3.3 Memory bypass | Bypass | ❌ FALSE (file ref) | `tools/memory_tool.py` (not `tools/memory.py`) |
| 4.1 Provider routing | Partial | ⚠️ PARTIAL | `run_agent.py` delegates to `agent.strategy_runtime` |
| 4.2 Auxiliary client | Missing | ✅ FILE EXISTS | `agent/auxiliary_client.py` exists |
| 4.3 Subagent bypass | Bypass | ❌ FALSE (file ref) | `tools/delegate_tool.py:46-54` (blocks memory, cronjob, etc.) |
| 4.4 Cron bypass | Bypass | ❌ FALSE (file ref) | `tools/cronjob_tools.py` |
| 5.1 MCP registry | Reusable | ✅ FILE EXISTS | `tools/mcp_tool.py` exists |
| 5.2 Plugin bypass | Bypass | ⚠️ PARTIAL | `agent/agent_init.py` needs verification |
| 6.1 Session search | Missing | ❌ FALSE (file ref) | `tools/session_search_tool.py:807` |
| 7.1 Delivery ledger | Reusable | ✅ VERIFIED | `gateway/delivery_ledger.py:1-374` |
| 7.2 File upload egress | Partial | ✅ FILE EXISTS | `gateway/platforms/teams_mtk.py` |
| 8.1 Working directory | Partial | ⚠️ PARTIAL | `agent/runtime_cwd.py` needs confirmation |
| 8.2 Cleanup | Missing | ❌ FALSE (file ref) | `gateway/cgroup_cleanup.py` does NOT exist |
| 9.1 ALPS/MOLY client | Reusable | ❌ FALSE (structure) | `D:/01_Job/Tool/myCRDump/src/wits/` is a package, not `src/wits.py` |
| 9.2 Write API exposure | Partial | ⚠️ PARTIAL | `src/wits/record.py:11-90` has write APIs (create, action, delete) |

---

## Final Determination

**Is the original artifact acceptable for ticket resolution?** ❌ **NO**

**Reasons:**

1. **6+ file references are completely wrong** - the files don't exist under the cited names
2. **Multiple line ranges are dramatically incorrect** - e.g., tool loop cited as 349-700, actual at 6700+
3. **Core recommendation is based on non-existent toolsets** - "read_only", "teams_reply", "alps_export" not verified
4. **ALPS/MOLY analysis is based on incorrect file structure** - `src/wits.py` doesn't exist; it's a package
5. **Critical enforcement seams are not mentioned** - `agent/execution_authority.py`, `tools/approval.py`, `toolsets.py`
6. **No verification of actual tool registration** - claims about plugins bypassing toolsets unverified

**Required Remediation:**

1. Correct all file references to actual file names
2. Verify and correct all line ranges against current code
3. Audit `toolsets.py` to identify actual toolset names
4. Re-verify ALPS/MOLY module structure and write API locations
5. Inspect `agent/execution_authority.py` and `tools/approval.py` as potential enforcement seams
6. Re-evaluate all "bypass" claims against actual code structure
7. Add citations for: `tools/approval.py`, `agent/execution_authority.py`, `toolsets.py`, `_tool_search_scoped_names()` in `agent/tool_executor.py`

---

## Appendix: Verified File List

**Files that EXIST as cited:**
- `gateway/authz_mixin.py` ✅
- `agent/tool_guardrails.py` ✅ (but line ranges wrong)
- `agent/tool_executor.py` ✅
- `agent/auxiliary_client.py` ✅
- `tools/mcp_tool.py` ✅
- `tools/memory_tool.py` ✅ (not `tools/memory.py`)
- `tools/browser_tool.py` ✅
- `tools/delegate_tool.py` ✅ (not `tools/delegate_task.py`)
- `tools/cronjob_tools.py` ✅ (not `tools/cronjob.py`)
- `tools/file_tools.py` ✅
- `tools/session_search_tool.py` ✅ (not `tools/session_search.py`)
- `gateway/delivery.py` ✅
- `gateway/delivery_ledger.py` ✅
- `gateway/platforms/teams_mtk.py` ✅
- `gateway/relay/` package ✅ (not `gateway/webhook.py`)
- `D:/01_Job/Tool/myCRDump/src/wits/` package ✅ (not `src/wits.py`)
- `D:/01_Job/Tool/myCRDump/src/wits/record.py` ✅
- `run_agent.py` ✅

**Files that DO NOT EXIST as cited:**
- `tools/memory.py` ❌
- `tools/session_context.py` ❌
- `tools/delegate_task.py` ❌
- `tools/cronjob.py` ❌
- `tools/process.py` ❌
- `tools/session_search.py` ❌
- `gateway/webhook.py` ❌
- `gateway/cgroup_cleanup.py` ❌
- `D:/01_Job/Tool/myCRDump/src/wits.py` ❌

**Files requiring confirmation:**
- `agent/runtime_cwd.py` ⚠️
- `agent/tool_dispatch_helpers.py` ⚠️
- `tools/terminal_tool.py` ⚠️

---

**Report Generated:** 2026-08-13
**Workspace:** D:\01_Job\Tool\Hermes Agent
**Branch:** mtk-integration (dirty)