# Hermes Agent V17→V19 升級分析報告

## 執行摘要

**分析範圍**:
- 升級前安全分支：`safety/mtk-integration-pre-upstream-20260726-2f8b5671`
- 官方 V19 基準：`339d96868`
- 升級 merge commit: `4863d875e`
- 升級後補修 commits: `2f8b56712..HEAD` (76 commits)
- 官方 delta：4018 commits (安全分支→V19)
- 總變更：3934 files, +594185/-58561 lines

**關鍵發現**:
1. **重大架構變更**: Tools 分層披露、壓縮串流化、Gateway 重構
2. **MTK 客製重疊**: Teams MTK gateway、Windows 啟動、computer_use 後端
3. **可直接採用**: Schema 消毒、MCP glob 過濾、進度感知超時
4. **需保留客製**: Teams MTK TLS 1.2 適配器、企業網路適配、MTK 專用 E2E

---

## 一、官方 V19 新增核心功能

### 1.1 Tools 系統重大變革

#### 1.1.1 分層工具披露 (Tiered Tool Disclosure)
**Commits**: `0986ac393`, `e9fe060eb`, `e289e561c`

**變更內容**:
- **Tier 0**: 無 MCP/plugin tools → 全部 eager 載入 (pass-through)
- **Tier 1**: 可延遲 tools 的 catalog listing 符合預算 → bridge + skills-style listing
  - 預算計算：`min(threshold_pct% of context, listing_max_tokens)`
  - threshold_pct 預設從 10% → **5%**
  - listing_max_tokens 預設從 4000 → **20000** (cap 60000)
- **Tier 2**: 超出預算甚至 names-only 也放不下 → 僅 bare bridge

**關鍵檔案**:
```
tools/tool_search.py            | +141/-59
hermes_cli/config.py            | +12/-1
tests/tools/test_tool_search.py | +66/-10
```

**實際案例**:
- Linear 24 tools → Tier 1 full listing
- Epic UE 5.8 830 tools → Tier 1 names-only
- **Cloudflare 3,320 tools** → Tier 2 (200K 和 1M context 均無法容納完整 schema)

**適用場景**: MTK 若引入大型 MCP (如 myDataCenter GraphRAG)，可直接採用此機制

---

#### 1.1.2 Schema 消毒與反向映射
**Commit**: `7b793f7d2`

**問題**: Cloudflare MCP 有 61 個 property key 違反 Anthropic 命名規則
(`^[a-zA-Z0-9_.-]{1,64}$`)，例如 `issue_class~neq`、`meta.<field>[<operator>]`

**解決方案**:
```python
# tools/schema_sanitizer.py
def sanitize_tool_schema(schema):
    # 重命名不符合規範的 key
    # bad chars → '_', 64-char 截斷，collision 加 numeric suffix
    # required[] 同步重映射

def unrename_tool_args(args, rename_map):
    # dispatch 時反向映射回原始 wire names
    # 遞迴到 object values 和 array items
```

**關鍵檔案**:
```
tools/schema_sanitizer.py            | +100/-6
tests/tools/test_schema_sanitizer.py | +108
model_tools.py                       | +10
```

**MTK 適用性**: **高** — 若 MTK 內部 MCP 有類似命名問題，可直接採用

---

#### 1.1.3 MCP fnmatch glob 過濾
**Commit**: `e7172ab1b`

**變更**: include/exclude filters 從 exact match → 支援 `*`、`?`、`[` globs

**範例**:
```yaml
# 舊: 只能 exact match
tools.exclude: ["docs_search", "radar_scan"]

# 新: glob 模式
tools.exclude: ["*_radar_*", "docs_*", "purge_*"]
```

**實際效果**: Cloudflare 3,320 tools → 1,905 surviving (排除 1,415 個)

**關鍵檔案**:
```
tools/mcp_tool.py            | +38/-10
hermes_cli/mcp_config.py     | +18/-3
tests/tools/test_mcp_tool.py | +46
```

---

### 1.2 Context Compression 串流化

#### 1.2.1 進度感知超時 (Progress-Aware Timeouts)
**Commits**: `32fd9d65c`, `9de7dfe1c`

**問題**: 舊的 compression 使用固定 30s wall-clock deadline，慢但健康的模型被中途切斷

**解決方案**:
- **閒置超時**: `hygiene_timeout_seconds` (預設 30s) — 從上次進度更新開始計算
- **總天花板**: `hygiene_total_ceiling_seconds` (預設 600s) — 防止退化 trickle stream

**實作**:
```python
# agent/conversation_compression.py
class CompressionCommitFence:
    def touch_progress(self):  # 每次收到 chunk 時呼叫
        self._last_progress = time.time()

    def seconds_since_progress(self):
        return time.time() - self._last_progress

# agent/auxiliary_client.py
aux_progress_hook = threading.local()  # thread-local progress hook
# 安裝到 stream 呼叫，每 chunk tick 一次
```

**關鍵檔案**:
```
agent/conversation_compression.py | +31/-7
agent/auxiliary_client.py         | +91/-12
gateway/run.py                    | +48/-15
agent/context_compressor.py       | +167/-44
```

**MTK 適用性**: **高** — 特別適合 reasoning models 或慢但穩定的摘要模型

---

#### 1.2.2 總結呼叫全面串流化
**Commit**: `9de7dfe1c`

**變更**: Fenceless compression callers (CLI /compress, in-loop auto-compression) 現在使用相同的 streamed path

```python
# agent/conversation_compression.py
def compress_context(...):
    # 安裝 no-op progress hook → 自動路由到 stream call
    # timeout 變成 inactivity-based 而非 total wall-clock
```

---

### 1.3 Gateway 架構重構

#### 1.3.1 Relay Phase 1-4 完整實作
**Commits**: `ebab890ae`, `689b51bef`, `fffa66122`, `40eebc7d7`

**Phase 1 Parity**:
- supported_ops discovery
- identity fields wiring
- `/handoff` aliasing
- displayName provisioning

**Phase 2 Media**:
- send_media egress
- inbound media localization

**Phase 3 Interactive**:
- native prompt UX (approvals/confirms/clarify)
- react ack lifecycle

**Phase 4 Thread Lifecycle**:
- handoff threads
- semantic renames
- reply_to context
- hello command manifest

**關鍵檔案**:
```
gateway/relay/adapter.py         | +1169/-0
gateway/relay/command_manifest.py | +145
gateway/relay/media.py           | +205
gateway/relay/ws_transport.py    | +155/-?
```

**MTK 適用性**: **中** — Teams MTK 若需完整 relay 支援可採用

---

#### 1.3.2 Platform Config Bridges
**Commit**: (多個 gateway 重構 commits)

**新增**:
```
gateway/platform_config_bridges.py  | +133
gateway/platform_registry.py        | +27/-?
gateway/readiness.py                | +122
```

**目的**: 將 platform 配置與 runtime 解耦，啟動時不載入未啟用的 heavy platform 模組

**MTK 適用性**: **高** — 符合 runbook 中「不要掃描未啟用的 platform」原則

---

### 1.4 Computer Use / cua-driver 改進

#### 1.4.1 --no-overlay 自動檢測
**Commits**: `f957fe376`, `3d8468971`, `849c17752`, `37a27664c`

**問題**: macOS 上 cursor-overlay vImage redraw loop 導致 idle CPU 佔用 (#28152/#47032)

**解決方案**:
```python
# tools/computer_use/cua_backend.py
def _cua_no_overlay() -> bool:
    # 讀取 computer_use.no_overlay config
    # 預設 None → auto-detect
    # macOS: True (防止 vImage loop)
    # headless Linux/WSL2/containers: True
    # Windows/desktop Linux: False
```

**關鍵檔案**:
```
tools/computer_use/cua_backend.py | +1294/-200+
```

**MTK 適用性**: **中** — Windows 環境預設保持 overlay，但可手動覆蓋

---

#### 1.4.2 ActionResult 結構化領地
**Commit**: (cua-driver MCP protocol 更新)

**新增 fields**:
```python
class ActionResult:
    verified: bool      # driver 是否確認動作成功
    effect: str         # 'confirmed' | 'unverifiable' | 'suspected_noop'
    escalation: dict    # {'recommended': 'px' | 'foreground'}
    path: str          # 實際運行的 delivery mode
    degraded: bool     # 功能是否降級
    delivery_mode: str # 請求的 delivery mode
    code: str          # 'background_unavailable' 等
```

**MTK 適用性**: **高** — 見下節 MTK 補修 commmits

---

### 1.5 Desktop/UI 改進

#### 1.5.1 Session Tabs 與 Slash Tab Target
**Commits**: `080ee077a`, `2a6368f04`, `ecf8ef970`

**變更**:
- 從 sidebar 點擊 active session → 返回 chat (不是 full page)
- Skill kickoff 發送到調用它的 tab
- 多 tab 效能優化 (hidden tabs freeze transcripts)

**關鍵檔案**:
```
apps/desktop/electron/main.ts    | +?
web/src/components/*.tsx         | +?
```

---

#### 1.5.2 Model Picker 效能
**Commits**: `d471fc956`, `9aefa4c61`, `f7001f968`

**改進**:
- open-latency probes
- defer model-row submenu bodies until hover
- show exhausted-pool providers in aux/vision pickers
- show custom providers in auxiliary picker

---

### 1.6 Skills 與 Curator

#### 1.6.1 Skill Catalog Listing
**Commit**: `e869accc1`

**變更**: tool_search 採用 skills-style progressive disclosure

```python
# tools/tool_search.py
def tool_search(query, limit=5):
    # 類似 skill_view() 的結構
    # 返回 name + description + category
    # full content via skill_view()
```

---

#### 1.6.2 Curator 改進
**Commits**: `72de75c0a`, `243a01d5d`

- 暴露 unmanaged skills
- 新增 `curator adopt` 命令
- 統一 autonomous write policy

---

## 二、MTK 客製修改分析

### 2.1 升級後補修 Commits (76 commits)

#### 2.1.1 Teams MTK Gateway 強化

**Core Commits**:
```
0f6a66b0f fix: harden Teams model picker and context compression
7124749bb fix(gateway): make Windows restart reliable and bounded
ead5a6d1c fix(windows): complete MTK integration on v19
d2a0d3281 fix(gateway): harden Teams MTK and Windows lifecycle
a5d0d3281 fix: harden Windows decoding and Teams E2E evidence
30c77ce4c fix(windows): harden enterprise gateway and tooling
```

**Teams MTK 新功能**:
```
f5b418592 feat(teams_mtk): add leave_chat (outbound pair to create_chat)
595a10781 feat(teams_mtk): implement create_chat via Skype API (G13-B.3 unblocked)
c6011ed00 feat(teams_mtk): add model-picker authorization + platform system prompt
d3d75c6b6 feat(api-server): request-scoped disabled_toolsets + Windows test infra
e786b5e5f feat(teams_mtk): integrate verified daemon-parity payload from PR branch
593a51dbf feat(teams_mtk): add find-conversation E2E, fix send_typing return value
da3ca1ed7 feat(gateway): garbage detector tuning, streaming first-fragment gate
9e5854cc9 fix(teams_mtk): residual markdown in HTML replies + real-E2E content-tier
b43cbd43a feat(teams_mtk): design.md gap cleanup — G5~G8/G12/G13-A all done
110d7463d feat(teams_mtk): §16 test coverage + blocked stubs
93a56289f feat(teams_mtk): Phase 2 full — S4~S10, C5~C7, WS-8~9, REV-3/6, G15
11dc884ae feat(teams_mtk): C-2/C-5/C-7 echo fingerprint + short-msg gating
765f168ea fix(teams_mtk): control commands bypass mention gating + poll bounded fetch
849027267 feat(teams_mtk): Phase 1 + 1.5 — SDK delegation + Trouter WS listener
bf816a82a fix: remove redundant function-level imports
09839972b fix(teams-mtk): TTL echo-guard dedup + send_typing() implementation
5335ac250 feat(teams-mtk): G-MEDIA image/doc/card send + G13-A contact lookup
```

**關鍵實作**:
```python
# gateway/platforms/teams_mtk.py
class _WindowsTLS12HTTPAdapter(_RequestsHTTPAdapter):
    """Verified TLS 1.2 transport for Windows Teams MSG endpoints."""

    def __init__(self, *args, **kwargs):
        ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE")
        if ca_bundle and Path(ca_bundle).is_file():
            self._ssl_context = ssl.create_default_context(cafile=ca_bundle)
        else:
            self._ssl_context = ssl.create_default_context()
        self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2  # 強制 TLS 1.2

    def cert_verify(self, conn, url, verify, cert):
        if verify is True and cert is None:
            return  # 自定義 context 已執行 CA/hostname checks
        return super().cert_verify(conn, url, verify, cert)

class _SDKHTTPLayer(_SDKBaseHTTPLayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == "win32":
            # MTK 環境 proxy 會中斷此內部 MSG TLS path
            self._session.trust_env = False
            self._session.mount("https://", _WindowsTLS12HTTPAdapter())

async def _send_model_picker_html(self, chat_id, html_content, step_label):
    """通過適配器的可信消息傳輸發送 picker HTML."""
    # 使用 SDK 或 raw HTTP 發送 model picker
```

**E2E 驗證強化**:
```
tests/gateway/platforms/test_teams_mtk_e2e_contract.py | +114/-22
tests/gateway/platforms/test_teams_mtk_core_guards.py  | +91/-?
tests/gateway/platforms/test_teams_mtk_reliability.py  | +63/-?
tests/gateway/platforms/test_teams_mtk_auth.py         | +20
```

---

#### 2.1.2 Windows Gateway 啟動可靠性

**Commit**: `7124749bb`

**變更**:
```
gateway/platform_config_bridges.py  | +133
gateway/run.py                      | +139/-?
hermes_cli/gateway_windows.py       | +192/-120
tests/hermes_cli/test_gateway_windows.py | +174/-?
```

**改進**:
- Task scheduler 查詢 bounded (不重複查詢)
- readiness probe 與 exact PID 綁定
- shutdown 不浪費 full drain window 在 idle gateway

---

#### 2.1.3 Computer Use 後端配合

**Commit**: `5b0364747`

**變更**:
```
tools/code_execution_tool.py | +13/-2
tests/tools/test_code_execution_modes.py | +47
```

**目的**: execute_code subprocesses 保持 windowless (不彈出 terminal windows)

---

#### 2.1.4 Context Compression 硬化

**Commit**: `0f6a66b0f`

**變更**:
```
agent/conversation_loop.py    | +19
gateway/platforms/teams_mtk.py | +176/-92
tests/run_agent/test_413_compression.py | +71
```

**改進**:
- Teams model picker 與壓縮整合
- 413 錯誤時自動壓縮
- progress notices 可選開啟

---

### 2.2 與官方功能重疊分析

#### 2.2.1 直接重疊 (可直接採用官方實作)

| MTK 客製 | 官方對應功能 | 建議 |
|---------|------------|------|
| Teams MTK TLS 1.2 adapter | 無直接對應 (官方無企業 proxy/TLS 強制需求) | **保留客製** |
| Windows restart reliability | `gateway/platform_config_bridges.py` | **合併**: 採用官方 bridge 架構 + MTK Windows 邏輯 |
| E2E test hardening | 官方 E2E 框架 | **保留客製** (MTK 特定場景) |
| execute_code windowless | 官方電腦使用後端 | **合併**: 採用官方 cua-backend 改進 |

#### 2.2.2 部分重疊 (需整合)

| 功能 | 官方實作 | MTK 實作 | 整合策略 |
|-----|---------|---------|---------|
| Progress-aware timeouts | `hygiene_timeout_seconds` + `touch_progress()` | MTK 有自己的超時處理 | **採用官方** + MTK 特定規則 |
| Schema sanitization | `tools/schema_sanitizer.py` | 無 | **直接採用** |
| MCP glob filtering | `tools/mcp_tool.py` fnmatch | 無 | **直接採用** |
| Tiered tool disclosure | `tools/tool_search.py` | 無 | **直接採用** (若引入大型 MCP) |

#### 2.2.3 衝突風險

| 潛在衝突點 | 官方行為 | MTK 行為 | 風險等級 |
|-----------|---------|---------|---------|
| Gateway startup | Readiness probe | Task scheduler + PID | **中** (需驗證 probe 兼容) |
| Computer Use | --no-overlay auto-detect | MTK 的 deliver_mode escalation | **低** (官方 escalation 機制更完善) |
| Context compression | Streamed summary with progress | MTK 可能有自定義壓縮邏輯 | **中** (需檢查 MTK 是否修改 compression.py) |

---

## 三、優先級建議

### 🔴 高優先級 (直接啟用/改用官方實作)

1. **Schema Sanitizer** (`tools/schema_sanitizer.py`)
   - **理由**: 解決 MCP property key 命名問題，MTK 內部 MCP 可能也有同樣問題
   - **行動**: 確保 MTK MCP tools 通過此 sanitizer
   - **風險**: 低 (純防禦性改進)

2. **Progress-Aware Timeouts** (compression)
   - **理由**: 防止慢但健康的 summarizer 被切斷
   - **行動**: 設定 `compression.hygiene_timeout_seconds=30`, `hygiene_total_ceiling_seconds=600`
   - **風險**: 低 (向後兼容)

3. **MCP fnmatch Glob Filtering**
   - **理由**: 若 MTK 使用大型 MCP，需要精細控制工具註冊
   - **行動**: 更新 config.yaml 使用 glob patterns
   - **風險**: 低

4. **Platform Config Bridges**
   - **理由**: 符合 runbook「不載入未啟用 platform」原則
   - **行動**: 採用官方 bridge 架構，保留 MTK platform 實作
   - **風險**: 中 (需驗證 bridge 與 MTK platform 整合)

---

### 🟡 中優先級 (需評估/整合)

1. **Tiered Tool Disclosure**
   - **理由**: 只有引入超大型 MCP (如 Cloudflare 3320 tools) 時才需要
   - **行動**: 監控 MTK MCP 規模，若>500 tools 則啟用
   - **風險**: 低 (自動啟用)

2. **Computer Use Delivery Mode Escalation**
   - **理由**: 官方 escalation ladder 比 MTK 現行實作更完善
   - **行動**: 採用官方 `verified`/`effect`/`escalation` fields
   - **風險**: 中 (需測試 MTK 場景)

3. **Gateway Readiness Probe**
   - **理由**: 官方 `gateway/readiness.py` 提供更標準化的健康檢查
   - **行動**: 整合 MTK Task scheduler 狀態到 readiness probe
   - **風險**: 中 (需確保 backward compatibility)

4. **MoA (Mixture of Agents) Advisor Fanout**
   - **理由**: 官方 MoA 架構更完善 (privacy redaction, per-slot reasoning_effort)
   - **行動**: 評估是否採用官方 MoA 架構
   - **風險**: 高 (重大架構變更)

---

### 🟢 低優先級 (保留客製)

1. **Teams MTK TLS 1.2 HTTP Adapter**
   - **理由**: 官方無企業 proxy/TLS 強制需求，MTK 環境特定
   - **行動**: 保留 `_WindowsTLS12HTTPAdapter` 和 `_SDKHTTPLayer` 修改
   - **風險**: 低 (封裝良好)

2. **Teams MTK E2E Tests**
   - **理由**: MTK 特定場景，官方 E2E 無法覆蓋
   - **行動**: 保留並持續強化
   - **風險**: 低

3. **MTK 特定 Skill Junctures**
   - **理由**: 44 個 `.claude/skills` Junctions 是 MTK 佈署特定需求
   - **行動**: 保留並記錄在 runbook
   - **風險**: 低

---

## 四、具體衝突檢測

### 4.1 已確認衝突

**無直接代碼衝突** — git merge 已成功完成，所有衝突已手動解決

### 4.2 潛在行為衝突

1. **Gateway Startup Sequence**
   ```
   官方：readiness probe → PID tracking → gateway_state
   MTK:   Task scheduler query → PID check → custom state
   ```
   **建議**: 保留 MTK logic，但採用官方 `gateway/readiness.py` interface

2. **Compression Timeout Handling**
   ```
   官方：progress-aware (inactivity-based)
   MTK:   可能有 fixed deadline logic
   ```
   **建議**: 檢查 `agent/context_compressor.py` MTK 修改，確保與官方 stream 路徑兼容

3. **Computer Use Delivery**
   ```
   官方：escalation ladder (background → px → foreground)
   MTK:   可能有自定義 delivery logic
   ```
   **建議**: 採用官方 `ActionResult` structured fields，MTK 邏輯在上面封裝

---

## 五、檔案變更統計

### 5.1 官方 V19 核心變更 (安全分支→339d96868)

```
 gateway/                    | ~150 files, +7360/-? (run.py major rewrite)
 tools/                      | ~80 files, +4000/-?
 agent/                      | ~100 files, +10000/-?
 web/src/                    | ~100 files, +5000/-?
 apps/desktop/electron/      | ~20 files, +2000/-?
```

### 5.2 MTK 補修變更 (339d96868→HEAD)

```
 gateway/platforms/teams_mtk.py    | +231/-?
 tools/computer_use/cua_backend.py | +1294/-200+
 agent/context_compressor.py       | +167/-44
 gateway/run.py                    | +139/-?
 tests/                            | +500+ (E2E hardening)
```

---

## 六、建議行動項目

### 立即行動 (本週)

1. ✅ **採用 Schema Sanitizer**
   ```bash
   # 驗證 MTK MCP tools 通過 sanitizer
   hermes mcp tools <mcp-name> --check-schema
   ```

2. ✅ **設定 Progress-Aware Timeouts**
   ```yaml
   # config.yaml
   compression:
     hygiene_timeout_seconds: 30
     hygiene_total_ceiling_seconds: 600
   ```

3. ✅ **採用 MCP Glob Filtering**
   ```yaml
   mcp:
     servers:
       mtk-internal:
         tools:
           exclude: ["*_debug_*", "internal_*"]
   ```

### 短期行動 (本月)

1. **整合 Platform Config Bridges**
   - 重構 `gateway/platforms/teams_mtk.py` 使用 bridge pattern
   - 保留 `_SDKHTTPLayer` 和 TLS 1.2 adapter

2. **採用 Computer Use Escalation Ladder**
   - 更新 `tools/computer_use/tool.py` 處理 structured fields
   - 測試 `escalation.recommended='foreground'` 場景

3. **統一 Compression Progress Hook**
   - 檢查 MTK 是否有自定義 compression logic
   - 整合到官方 `touch_progress()` 機制

### 中期行動 (下季度)

1. **評估 Tiered Tool Disclosure**
   - 監控 MTK MCP tool counts
   - 若>500 tools，進行負載測試

2. **Gateway Readiness Probe 統一**
   - 將 MTK Task scheduler 狀態映射到 readiness probe
   - 更新 `gateway/status.py`

3. **MoA 架構評估**
   - 若 MTK 使用 multi-agent workflows，考慮遷移到官方 MoA

---

## 七、參考文獻

### 關鍵 Commits

**官方 V19**:
- `0986ac393` feat(tools): tiered tool disclosure
- `e9fe060eb` feat(tools): tier-2 server-summary hint
- `7b793f7d2` fix(tools): schema sanitizer
- `e7172ab1b` feat(mcp): fnmatch glob support
- `32fd9d65c` feat(compression): progress-aware timeouts
- `9de7dfe1c` feat(compression): stream summary call

**MTK 補修**:
- `0f6a66b0f` fix: harden Teams model picker
- `7124749bb` fix(gateway): Windows restart reliable
- `ead5a6d1c` fix(windows): complete MTK integration
- `3c510a80c` docs: MTK upstream upgrade runbook

### 關鍵檔案

```
# 官方新機制
tools/schema_sanitizer.py
tools/tool_search.py
tools/mcp_tool.py
agent/conversation_compression.py
agent/auxiliary_client.py
gateway/platform_config_bridges.py
gateway/readiness.py
tools/computer_use/cua_backend.py

# MTK 客製保留
gateway/platforms/teams_mtk.py (TLS 1.2 adapter)
tests/gateway/platforms/test_teams_mtk_*.py (E2E)
docs/mtk-upstream-upgrade-runbook.md (升級流程)
```

---

## 八、結論

**升級狀態**: ✅ 成功完成 (merge commit `4863d875e` + 76 個補修 commits)

**關鍵發現**:
1. 官方 V19 有許多**高品質架構改進**可直接採用 (schema sanitizer, progress-aware timeouts, MCP glob filtering)
2. MTK 客製**核心價值**在於 Teams MTK gateway 和企業環境適配，這些應保留
3. **無直接代碼衝突**，但有 3 個潛在行為衝突需監控

**建議策略**:
- **直接採用**官方防禦性機制 (sanitizer, timeouts, filtering)
- **整合**官方架構 (platform bridges, escalation ladder)
- **保留**MTK 特定邏輯 (TLS 1.2 adapter, E2E tests, Junctions)

**下一步**: 本週內完成高優先級項目，本月完成中優先級整合評估。

---

*報告生成時間：2026-07-29*
*分析基於 commits: safety/mtk-integration-pre-upstream-20260726-2f8b5671..HEAD*
*總變更：3934 files, +594,185/-58,561 lines*