## Context

TeamsMTK adapter（`gateway/platforms/teams_mtk.py`）目前的授權/mention 邏輯完全靠 env var：
- `MTK_TEAMS_CONVERSATION_ID`：逗號分隔的 conv_id 清單，adapter 輪詢這些對話。
- `MTK_TEAMS_NO_MENTION_CONVS`：逗號分隔的 conv_id 清單，命中則該對話視為 DM（免 @mention）。
- `GATEWAY_ALLOWED_USERS`（`gateway/authz_mixin.py`）：**全域個人**白名單，跨所有平台通用，不區分對話。

問題：TeamsMTK 沒有走其他 adapter（`weixin.py`）已有的 `enforces_own_access_policy` / `dm_policy` / `group_policy` 機制，導致「群組授權」只能退化成「把群組成員的 OID 一個個塞進全域白名單」——這會讓那些人在**所有** TeamsMTK 對話（包括其他群組、1-1）都被授權，範圍失控，且完全沒有 per-群組/per-人的功能限制或關鍵字屏蔽能力。

## Goals / Non-Goals

**Goals:**
- 群組級白名單：把整個 conv_id 加入名單，群內任何 sender 均授權（不需逐人加 OID）。
- 群組級 mention 豁免：預設一鍵加入的群組即為免 @mention。
- Per-群組 / per-人的工具限制（`disabled_toolsets`）與關鍵字屏蔽（雙向）。
- CLI 一鍵管理（add/list/set/remove），取代手動編輯 `.env`/`config.yaml`。

**Non-Goals:**
- 不做「自動偵測新群組並生成 pending 申請」的 approve flow（那是 `gateway/pairing.py` 現有模式，但本次范围不含 — 使用者明確要的是「直接加入白名单」，非審批）。
- 不修改 Weixin/QQBot 等其他平台的 authz 路徑。
- 不支援關鍵字屏蔽的語意層分析（僅 regex/字串比對，非 LLM 判斷是否洩密）。

## Decisions

1. **設定存放於 `config.yaml`，非 `.env`。**
   理由：這是行為設定（feature flag / 政策），非機密（AGENTS.md 政策：`.env` 僅存密鑰）。用巢狀 dict `gateway.teams_mtk.groups.<conv_id>` 存每個群組的 name/require_mention/blocked_toolsets/blocked_keywords/per_user。
   替代方案考慮過：延用 env var CSV（如 `MTK_TEAMS_NO_MENTION_CONVS`）——否決，因为无法表达 per-群組結構化欄位（工具清單、關鍵字清單、per-人巢狀）。

2. **Authz 走新的「群組白名單」路徑，與既有 `GATEWAY_ALLOWED_USERS` 並存但獨立判斷。**
   在 `authz_mixin.py._is_user_authorized`（或對應方法）中，對 `source.platform == Platform.TEAMS_MTK` 且 `source.chat_type == "group"` 時，先查 `config.yaml` 的 `gateway.teams_mtk.groups`：conv_id 存在即直接 `return True`（群內任何 sender 通過），完全跳過個人白名單檢查。1-1 對話（DM）不受影響，繼續走現有的 `GATEWAY_ALLOWED_USERS` 個人白名單。
   替代方案考慮過：讓 TeamsMTK 實作 `enforces_own_access_policy`（仿 weixin 那套 dm_policy/group_policy）——否決，因為 weixin 那套是「per-sender allow_from 清單」語意，跟本次要的「整群直接放行」語意不同，硬套會導致行為混淆；新增一個明確的「群組白名單」判斷比复用一个语义不合的 property 更清楚。

3. **`require_mention` 讀取順序：`groups.<id>.require_mention` → 全域 `self.require_mention`（`TEAMS_MTK_REQUIRE_MENTION` env var）→ 硬編碼 default `True`。**
   取代目前 `MTK_TEAMS_NO_MENTION_CONVS` CSV 檢查的邏輯位置（`teams_mtk.py:1025-1026`）。CLI `group add` 預設寫入 `require_mention: false`，符合「一鍵加入=免提及」的需求。

4. **工具限制透過既有 `disabled_toolsets` 參數傳遞，不新增 core 機制。**
   在派送訊息給 agent 前（`_process_new_messages` 或上層呼叫處），依 `groups.<id>.blocked_toolsets` ∪ `groups.<id>.per_user.<user_id>.blocked_toolsets` 組出最終 `disabled_toolsets` 清單，傳給 `AIAgent.__init__`。此參數已存在（見 AGENTS.md AIAgent 簽名），零核心改動。

5. **關鍵字屏蔽為雙向 regex 比對，命中即整段拒絕（非部分遮罩）。**
   - 入站：訊息文字（mention 剝除後）比對 `blocked_keywords` 清單（視為 regex，大小寫不敏感）。命中 → 不呼叫 agent，回覆固定話術（如「這個問題不在此群組討論範圍」），並記錄一筆 log（供事後稽核，不落地到 PKB）。
   - 出站：`send()` 前對最終回覆文字跑同一份 regex。命中 → 整段拒發，改發固定話術（如「回覆內容涉及限制詞，已攔截」），同樣記錄 log。
   替代方案考慮過：部分遮罩（把命中詞替換成 `***`）——否決，因為遮罩仍可能透過上下文推斷洩漏，且實作複雜度不成比例；整段拒絕更保守、更符合 MTK 內部資訊管控預期。

6. **CLI 指令掛在新檔案 `hermes_cli/subcommands/teams_mtk_groups.py`，仿 `hermes_cli/pairing.py` 的結構（純函式 + argparse 子命令），不擴充現有 `pairing.py`。**
   理由：pairing.py 的語意是「code-based approval」，跟本次「直接群組白名單」語意不同，混在一起會讓兩套心智模型打架。獨立檔案，但複用 `hermes_cli/config.py` 的 `save_config_value()` 寫回 config.yaml。

## Risks / Trade-offs

- **[Risk] 群組白名單一旦加入，群內任何人都能觸發 terminal/browser 等高權限工具（除非額外設 blocked_toolsets）** → Mitigation: CLI `group add` 的預設值不僅是 `require_mention: false`，也應提示（非強制）使用者考慮 `--block-toolset` 常見的高風險工具（terminal/code_execution/browser），文件/help text 中明確提醒。
- **[Risk] 關鍵字整段拒絕可能誤判（false positive），造成群組內合法問題被擋** → Mitigation: `blocked_keywords` 預設為空清單（不啟用），需使用者主動設定；log 記錄命中內容方便事後檢視誤判並調整規則。
- **[Risk] Config 查表邏輯若寫錯 fallback 順序，可能導致某群組意外變成需要 mention 或意外免 mention** → Mitigation: `hermes teams-mtk group list` 要清楚顯示每個群組「生效中」的 require_mention 值（含 fallback 來源標註），而非只顯示 raw config。
- **[Risk] 改 gateway 程式碼需重啟才生效，若忘記重啟會誤以為設定沒作用** → Mitigation: CLI `group add/set` 執行後印出明確提醒「需重啟 gateway 才會生效」（沿用專案既有慣例，非新增摩擦）。
- **[Trade-off] 不做自動偵測新群組（pending/approve flow）**，換取實作範圍更小、心智模型更簡單——代價是使用者仍需手動用 `teams` skill 查 conv_id 再跑 CLI，非全自動。使用者已明確表示這是可接受的（見 proposal 對應討論）。

## Migration Plan

1. `config.yaml` 加入 `gateway.teams_mtk.groups: {}` 預設空 dict（`DEFAULT_CONFIG` 深合併，既有使用者升級不受影響，行為不變直到主動加群組）。
2. 部署新 CLI 指令，`.env` 中現有的 `MTK_TEAMS_CONVERSATION_ID` / `MTK_TEAMS_NO_MENTION_CONVS` 兩個 conv_id 可選擇性地透過 `group add` 遷移進 `config.yaml`（保留 env var 讀取作為 back-compat fallback，兩者取聯集，不強制遷移）。
3. `authz_mixin.py` 新增群組白名單路徑後，先在測試環境驗證既有 `GATEWAY_ALLOWED_USERS` 白名單行為不受影響（迴歸測試）。
4. 上線後於一個測試群組先行驗證 `require_mention: false` + 群組白名單生效，再逐步把其他群組遷移進 `config.yaml`。
5. Rollback：`groups` 清空或移除該 conv_id 條目即恢復原行為（回退到 authz 的個人白名單判斷）；無需資料庫遷移或不可逆操作。

## Open Questions

- 關鍵字命中後的固定話術文字內容，是否需要使用者自訂（per-群組不同措辭）？目前設計為單一全域預設話術，若需 per-群組自訂，需在 `groups.<id>` 加 `blocked_message` 欄位（本次先不做，留待需求明確後再加）。
- 是否需要 `hermes teams-mtk group list` 額外顯示「該群組上次活動時間 / 成員數」等營運資訊？目前設計僅顯示設定值，不含即時 Teams API 查詢（避免 CLI 依賴網路且變慢）。
