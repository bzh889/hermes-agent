# Hermes Agent V17→V19 升級分析紀錄

> 本文件取代 `0c097c26c` 初版。初版引用了未經驗證的子代理結果，將升級前 MTK commits 誤算成升級後補修，並把 MTK 本地整合層誤列為官方 V19 功能。本版只保留經 Git、程式碼與測試直接核對的結論。

## 1. 分析基準

<table>
<thead><tr><th>項目</th><th>Commit／分支</th><th>用途</th></tr></thead>
<tbody>
<tr><td>V17 基準</td><td><code>53b017f03e</code></td><td>升級前官方共同祖先</td></tr>
<tr><td>V18 tag</td><td><code>7c1a02955</code></td><td>版本分段參考</td></tr>
<tr><td>V19 tag</td><td><code>3ef6bbd20</code></td><td>正式 V19 tag</td></tr>
<tr><td>實際官方升級基準</td><td><code>339d96868</code></td><td>此次 merge 採用的官方基準，比 V19 tag 更新</td></tr>
<tr><td>升級前 MTK 安全分支</td><td><code>safety/mtk-integration-pre-upstream-20260726-2f8b5671</code></td><td>保留升級前 MTK 客製</td></tr>
<tr><td>V19 merge</td><td><code>4863d875e</code></td><td>官方基準合入 <code>mtk-integration</code></td></tr>
<tr><td>本次分析截點</td><td><code>0c097c26c</code></td><td>修正本文前的 HEAD</td></tr>
</tbody>
</table>

### 1.1 可重現的 Git 計數

以下皆以 `git rev-list --count` 實測：

- V17 → V19 tag：**2,566 commits**
- V19 tag → 實際官方升級基準：**1,452 commits**
- V17 → 實際官方升級基準：**4,018 commits**
- 升級前 MTK 安全分支相對 V17：**68 commits**
- `4863d875e..0c097c26c`：**9 個升級後本地 commits**

最後一個數字是「截至特定 commit」的歷史值；後續修正本文或新增補丁後應自然增加，不應把它寫成永久不變的測試常數。

## 2. 官方 V19 可直接使用的能力

### 2.1 分層工具披露

- 主要位置：`tools/tool_search.py`、`model_tools.py`
- 大型 MCP／plugin tool catalog 不再必須把全部 schema 固定塞進每次模型呼叫。
- 小 catalog 可直接披露；較大 catalog 可退化為名稱清單或只保留 `tool_search`／`tool_describe`／`tool_call` 橋接。
- 對 MTK 的價值：未來接入較大的內部 MCP 時，可控制 prompt 體積，不必新增另一套 MTK 工具註冊器。

**目前狀態：已在現行 V19 路徑中，不需另行移植。**

### 2.2 MCP schema 消毒與參數反向映射

- 主要位置：`tools/schema_sanitizer.py`
- 修正不符合 provider 命名限制的 property keys，並在執行前還原原始參數名稱。
- 這是 provider 相容性與防禦性改善，不與 Teams MTK 客製衝突。

**目前狀態：已可直接使用，不需另寫 MTK sanitizer。**

### 2.3 MCP glob 過濾

- 主要位置：`tools/mcp_tool.py`
- `include_tools`／`exclude_tools` 支援 glob，而不只精確名稱。
- 適合大型 MCP；目前實測只有一個小型 MCP、九個工具，沒有 prompt 膨脹或名稱衝突，因此不應為了「有功能」而加無需求的過濾規則。

**目前狀態：能力已存在；暫不新增設定。**

### 2.4 進度感知的 context compression 逾時

- 主要位置：`agent/context_compressor.py`
- `compression.hygiene_timeout_seconds` 是無進展逾時。
- `compression.hygiene_total_ceiling_seconds` 是總上限。
- `compression.min_tail_user_messages` 保留最近使用者訊息，降低長任務壓縮後遺失新修正的風險。
- 現行 `agent/context_compressor.py` 相對官方 `339d96868` 沒有 MTK delta；不存在另一套仍待替換的 MTK fixed-deadline compressor。

**本次採用的明確設定：**

```yaml
compression:
  min_tail_user_messages: 3
  hygiene_timeout_seconds: 30
  hygiene_total_ceiling_seconds: 600
```

以上透過 `hermes config set` 寫入使用者設定，非新增環境變數。

### 2.5 Computer Use 漸進升級

- 主要位置：`tools/computer_use.py`
- 先背景操作；若回傳 `suspected_noop`、`background_unavailable` 或建議升級，再依訊號改用座標或 foreground。
- 與 MTK Windows 修補互補：官方能力處理輸入路徑，MTK 修補處理 Windows 啟動／子程序可靠性。

**目前狀態：已在現行工具中；不要預測性強制 foreground。**

### 2.6 Gateway delivery／busy-session 基礎設施

- `gateway/run.py` 的 `DeliveryLedger`、queue／steer／interrupt、pending message 與控制命令路徑，比 V17 更完整。
- `gateway/platforms/base.py` 提供共用的 busy-session、訊息編輯、長訊息、streaming capability 與 per-channel override 基礎。

**目前狀態：共用基礎可採用，但 Teams MTK 仍需保留自己的企業通訊協定與 E2E。**

## 3. 與 MTK 客製的重疊與衝突

<table>
<thead><tr><th>領域</th><th>官方 V19</th><th>MTK 現況</th><th>判斷</th></tr></thead>
<tbody>
<tr><td>Teams 傳輸與企業驗證</td><td>沒有可直接取代 MTK Skype／MSG／Graph 混合路徑的官方 adapter</td><td><code>gateway/platforms/teams_mtk.py</code>、TLS／proxy／token cache</td><td><strong>保留客製</strong></td></tr>
<tr><td>模型選擇器</td><td>Desktop／一般平台有自己的模型 UI 與命令</td><td>Teams MTK 有完整 provider/model picker 與 callback</td><td><strong>不互相取代</strong></td></tr>
<tr><td>忙碌期間追加訊息</td><td>queue／steer／interrupt 與 active-turn redirect</td><td>群組 burst、subagent、compression 邊界需要 MTK 實際驗證</td><td><strong>採官方語意並補安全邊界</strong></td></tr>
<tr><td>Context compression</td><td>進度感知逾時與保留尾端訊息</td><td>現行核心檔案已是官方實作</td><td><strong>直接使用官方</strong></td></tr>
<tr><td>Per-channel override</td><td><code>channel_overrides</code>／<code>platform_system_prompt</code></td><td>Teams MTK 已有 per-group config 與本地 bridge</td><td><strong>有概念重疊；不可重複設兩個真相來源</strong></td></tr>
<tr><td>Streaming capability flags</td><td><code>supports_draft_streaming</code>、<code>prefers_fresh_final_streaming</code>、overflow／edit-finalize flags</td><td>Teams MTK 有自訂 streaming/edit/send 路徑</td><td><strong>潛在整合點；未經真實 Teams E2E 不切換</strong></td></tr>
<tr><td>Windows gateway 啟動</td><td>一般背景程序與平台基礎</td><td><code>7124749bb</code> 等 MTK Windows readiness／restart 修補</td><td><strong>互補，保留客製</strong></td></tr>
<tr><td>Platform config bridge</td><td>官方沒有同名 MTK bridge</td><td><code>gateway/platform_config_bridges.py</code> 是本地升級後整合</td><td><strong>不可誤列為官方 V19</strong></td></tr>
</tbody>
</table>

## 4. 本次補強

### 4.1 Busy-session 安全路徑

`f7898a9cb` 已補上：

- 支援 active-turn redirect 的核心 agent 優先 redirect。
- subagent 或 context compression 進行中時，interrupt 降級為 steer，避免新回合與舊狀態競爭。
- 群組同一使用者的短時間 burst 先合併，再送出一次 redirect。
- 合併後的 burst 會標示為「全部累積套用」並編號；除非後一則明確宣告取代前一則，模型不可只採最後一則修正。
- DM 維持立即處理，不為群組防抖犧牲直接修正體驗。

因此目前保留：

```yaml
display:
  busy_input_mode: interrupt
```

這不是回到舊式「無條件中斷」；現行程式會依 agent 能力與安全邊界選擇 redirect／steer／interrupt。

### 4.2 真實 Teams busy-burst E2E

新增命名測項 `busy-group-burst-redirect`，要求：

1. 確認 runner 與 live gateway 使用同一 checkout、同一 Python 環境與預期設定。
2. 先讓真實模型進入可觀察的長時間 terminal process。
3. 並發送出同一使用者的兩個修正。
4. 透過 Teams MSG API read-back 驗證實際畫面只有一張 redirect acknowledgment 與一張 final card。
5. final 必須同時包含 A、B 兩個修正 marker，且不能殘留舊 marker。
6. 清理測試建立的 Graph 使用者訊息與 bot 訊息；清理失敗不得靜默 PASS。

Marker 使用純英數字。`strip_teams_html` 會把底線轉成 Markdown escape；若使用底線，功能正常時測試也會誤判失敗。

### 4.3 Windows MCP 測試可攜性

`os.environ` 在 Windows 對 key 大小寫不敏感，`patch.dict` 可能將 `ProgramFiles` 正規化為 `PROGRAMFILES`。測試改成以 `casefold()` 後的 key 驗證值與 secret 過濾，避免把 Windows 的正確行為當成失敗。

### 4.4 Windows detached gateway 的系統憑證信任

`hermes_cli/gateway_runtime_entry.py` 在匯入 `gateway.run` 及其 HTTP clients 前，先以已釘版的 `truststore` 注入 Windows 系統 CA。這讓 Scheduled Task 啟動的 detached gateway 與互動式 TUI 使用相同的企業 TLS 信任策略；若 `truststore` 不可用，則保留原有 CA 行為而不阻止 gateway 啟動。

對應行為測試驗證注入順序，以及注入不可用時 gateway 仍會啟動。

## 5. 刻意不做的項目

1. **不新增 MCP glob 規則**：目前 catalog 小，沒有量測到需要過濾的問題。
2. **不填假的 channel override**：沒有明確的群組 persona／model 需求時，不建立第二套與 Teams group config 競爭的設定。
3. **不直接啟用 Teams MTK 的官方 streaming flags**：先以真實 Teams E2E 證明 draft、edit、final 與 overflow 語意完全相容。
4. **不以官方 Desktop model picker 取代 Teams picker**：互動介面與 transport 不同。
5. **不把 AIDE provider 重構混入這次補丁**：它是獨立架構工作，需要單獨的 provider routing 與真實 endpoint 驗證。
6. **不把「merge 成功」寫成「無行為衝突」**：真正結論必須由針對性測試與 live gateway E2E 支持。

## 6. 驗證方式

程式測試必須使用專案 wrapper：

```bash
scripts/run_tests.sh tests/gateway/test_busy_session_ack.py \
  tests/gateway/test_active_session_text_merge.py \
  tests/gateway/test_compression_interrupt_demotion_56391.py \
  tests/gateway/test_priority_path_compression_demotion_56391.py -q

scripts/run_tests.sh \
  tests/gateway/platforms/test_teams_mtk_e2e_contract.py \
  tests/gateway/platforms/test_teams_mtk_busy_burst_e2e_contract.py -q

scripts/run_tests.sh tests/tools/test_mcp_tool.py -q

scripts/run_tests.sh tests/hermes_cli/test_gateway_runtime_entry.py -q
```

真實 Teams 測項：

```bash
.venv/Scripts/python.exe \
  openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py \
  --only busy-group-burst-redirect
```

該 live E2E 的 PASS 條件是 Teams read-back 的實際訊息關係，不是「方法存在」、單一 log 字串或吞例外後回傳 True。

## 7. 實際驗證紀錄（2026-07-29）

1. 第一輪 live E2E 的 gateway log 證明 A、B 兩則修正都已送入同一次 tool-boundary steer，但模型把後一則視為覆蓋前一則，最終只輸出 B。這不是訊息遺失，而是 burst 缺少「累積套用」語意；因此修正 production debounce payload，而不是放寬 E2E。
2. 載入 `569986d6c` 後，第二輪 Teams read-back 已看到單一 final 同時含 A、B 且不含 OLD；測試仍因自己的 `/status` preflight 卡片在 MSG API 刪除後短暫重新出現而 FAIL。
3. E2E 改為保留並排除該 preflight card 的確切 ID，不接受任意額外 bot card。第三輪 live E2E 為 **1/1 PASS**：一張 redirect acknowledgment、一張 final、最多一張標準 running progress card，A+B 存在且 OLD 不存在。
4. 最終相關測試集合由 `scripts/run_tests.sh` 執行，結果為 **298 passed、0 failed**；涵蓋 busy ack、active-session merge、compression demotion、Teams E2E contracts、Windows MCP 環境變數與 detached gateway truststore 啟動順序。
5. live 設定確認為 `display.busy_input_mode=interrupt`、`compression.min_tail_user_messages=3`、`compression.hygiene_timeout_seconds=30`、`compression.hygiene_total_ceiling_seconds=600`，控制群組 `require_mention=false`。
