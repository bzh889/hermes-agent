# teams-mtk-hermes-native-parity

比對 Hermes 原生 Teams 實作（`plugins/platforms/teams/adapter.py`，官方 SDK 版）
與跨模組整合點，逐項核對 `gateway/platforms/teams_mtk.py`（MTK skypetoken 版）
是否有遺漏或可優化之處。**不涉及 WSP daemon**——那是另一份比對
（尚未執行，見 Backlog）。

## Methodology

對照來源：
1. `plugins/platforms/teams/adapter.py`（官方 SDK 版，webhook-based）
2. `gateway/platforms/base.py` + `gateway/platforms/ADDING_A_PLATFORM.md`（介面契約，定義每個
   platform adapter「應該」實作哪些方法）
3. 跨模組整合點：`cron/scheduler.py`、`tools/send_message_tool.py`、
   `hermes_cli/status.py`、`agent/prompt_builder.py`、`gateway/channel_directory.py`、
   `gateway/config.py`

每一項 gap 都跑過驗證（`grep`/實際 import 執行），不是憑印象判斷。

## Confirmed Gaps（有具體證據）

### G1. `send_typing()` 未 override（已在 streaming-reliability spec 記錄為 GAP-1）
- **證據**：`grep "send_typing" gateway/platforms/teams_mtk.py` 零命中
- **影響**：`base.py:3770` 的 `_keep_typing()` 背景 loop 對 teams_mtk 空轉，使用者處理期間無視覺回饋
- **對照**：`plugins/platforms/teams/adapter.py:1185` 已實作（呼叫 SDK 的 `TypingActivityInput()`）
- **狀態**：已在 `teams-mtk-streaming-reliability` spec 追蹤，此處不重複，僅存交叉引用

### G2. `send_exec_approval()` 未 override
- **證據**：`grep "approve|approval|dangerous" gateway/platforms/teams_mtk.py` 零命中
- **對照**：`plugins/platforms/teams/adapter.py:1087` 用 Adaptive Card 渲染 Allow Once/Allow
  Session/Always Allow/Deny 四個按鈕
- **影響**：`gateway/run.py:17575` 的 fallback 邏輯證實——沒有 override 時危險指令核准會
  退化成純文字訊息，使用者要打 `/approve`/`/approve session`/`/approve always`/`/deny`
- **技術限制已確認**：讀了 `plugins/platforms/teams/adapter.py:992` 的 `_on_card_action`，
  按鈕點擊是透過 Bot Framework 的 `AdaptiveCardInvokeActivity`（`Action.Execute`）送回
  webhook endpoint 觸發的 invoke activity——這需要 Teams SDK 的 `App` webhook server
  接收回呼。teams_mtk 走 skypetoken 輪詢架構，**沒有 webhook endpoint 接收這類 invoke
  activity**，Adaptive Card 的按鈕回呼機制在此架構下無法運作。
- **判定：架構限制，不追求對等。** G2/G3 都適用此結論，關閉，不排入實作。

### G3. `send_clarify()` / `send_slash_confirm()` 未 override
- **證據**：`grep` 零命中，同 G2 的技術限制分析適用
- **對照**：`base.py:3038/3073` 定義的通用契約，webhook-based 平台（Telegram/Discord/Slack/
  Matrix/Feishu）都有 override 渲染按鈕
- **判定：架構限制，不追求對等**（見 G2 分析——按鈕回呼機制需要 webhook，teams_mtk 沒有）

### G4. `PLATFORM_HINTS` 缺少 `teams_mtk` 條目
- **證據**：實際執行驗證 `'teams_mtk' in PLATFORM_HINTS` → `False`
  （`agent/prompt_builder.py:620` 字典裡完全沒有 `teams`/`teams_mtk` key）
- **影響**：agent 不知道自己在 Teams 平台上，可能用錯格式化語法（比照 Telegram/WhatsApp
  各自有客製化的 markdown 轉換提示）
- **判定**：**確定漏做**，無技術限制，應該補

### G5. Cron 不認識 `teams_mtk` 為合法投遞平台 ✅ 已修
- **證據**：`_is_known_delivery_platform('teams_mtk')` → `True`
- **修復**：`cron/scheduler.py:208` `_KNOWN_DELIVERY_PLATFORMS` frozenset 已含 `teams_mtk`
- **判定**：✅ 已修

### G6. `send_message` tool 沒有 teams_mtk 專用路由 ✅ 已修
- **證據**：`tools/send_message_tool.py:311/607` 已有 `teams_mtk` 專用路由 + `contact:` target
- **修復**：G13-A.3/B.2 contact target 已整合，platform routing 已有
- **判定**：✅ 已修

### G7. `hermes_cli/status.py` 狀態顯示缺少 teams_mtk ✅ 已修
- **證據**：`grep "teams_mtk" hermes_cli/status.py` 零命中；`platforms` 字典
  （`status.py:425`）只列了 Telegram/Discord/WhatsApp/Signal/Slack/Email/SMS/DingTalk/
  Feishu/WeCom/WeCom Callback/Weixin/BlueBubbles/QQBot/Yuanbao，沒有 Teams 或 TeamsMTK
- **影響**：`hermes status` 指令看不到 teams_mtk 是否連線、home channel 是什麼
- **修復**：`status.py:445` platforms dict 加入 `"TeamsMTK": ("MTK_TEAMS_CONVERSATION_ID", ...)`
- **判定**：✅ 已修

### G8. `_PLATFORM_CONNECTED_CHECKERS` 缺少 teams_mtk ✅ 已修
- **證據**：`gateway/config.py:541` 已有 `Platform.TEAMS_MTK: lambda cfg: bool(cfg.extra.get("conversation_id"))`
- **修復**：checker 已加入
- **判定**：✅ 已修

### G9. 媒體原生發送（send_image/send_document/send_video/send_voice）未 override
- **證據**：`grep "async def send_image\|send_document\|send_video\|send_voice"
  gateway/platforms/teams_mtk.py` 零命中
- **現況**：inbound 已有 `_download_attachment`（收訊息時抓附件），但 outbound 完全沒有
  對應方法，繼承 `base.py` 的預設 fallback（把圖片網址當純文字貼出）
- **對照**：`plugins/platforms/teams/adapter.py:1193-1326` 完整實作了四個媒體發送方法，
  用 SDK 的 card/attachment 機制
- **判定**：**確定漏做**，但需先確認 skypetoken 協議的媒體上傳 API 存不存在（MTK 內網
  環境可能有額外限制），非直接照抄官方 SDK 版

### G10. `_sent_message_ids` 自製 echo-guard 沒有用 Hermes 現成的 `MessageDeduplicator`
- **證據**：`teams_mtk.py:317` 用裸 `set()`，無 TTL、無上限；`gateway/platforms/helpers.py:27`
  的 `MessageDeduplicator` 類別已被 6+ 個 adapter（discord/slack/dingtalk/wecom/weixin/
  mattermost/feishu/**teams**）採用，帶 TTL + max_size 防止記憶體無限增長
- **影響**：teams_mtk 長時間運行後 `_sent_message_ids` 只會增長不會清理，理論上有記憶體
  緩慢增長風險（雖然一個 conv 的訊息量有限，實際影響可能很小）
- **判定**：**可優化項**，非緊急，但應該統一到 Hermes 既有 helper 而非維護一份平行邏輯

### G11. Gateway Setup Wizard `_PLATFORMS` 列表沒有 teams_mtk
- **證據**：`grep "teams_mtk|teams-mtk|Microsoft Teams (MTK)" hermes_cli/gateway.py`
  零命中；`_PLATFORMS`（`hermes_cli/gateway.py:4596`）列了 mattermost 等平台的設定精靈
  metadata，但 teams_mtk 完全不在裡面
- **影響**：`hermes setup gateway` 互動精靈選不到 Teams (MTK)，使用者只能手動編輯
  `.env`/`config.yaml`（teams_mtk.py 的 module docstring 也證實現行 setup 流程是手動的：
  `python ~/.claude/skills/teams/auth_run.py` + 手動填 `MTK_TEAMS_CONVERSATION_ID`）
- **判定**：**確定漏做**，跟 G7（status 顯示）同一類「精靈/工具鏈整合缺口」，中風險
  （影響新使用者上手，非功能性 bug）

## Not Yet Reviewed（因對話輪次限制中斷，下一輪繼續）

（本節保留作為歷史記錄；下方新增小節記錄本輪已查完的項目）

## B.1 查證結果（ADDING_A_PLATFORM.md checklist 剩餘項）

### §5 Session Source 擴充欄位 — 已核對，不需要
- **查證**：讀了 `gateway/session.py:93` 的 `SessionSource` dataclass 全部欄位
  （`user_id_alt`/`chat_id_alt` 是給 Signal UUID / Feishu union_id 這類「平台原生 ID
  與顯示 ID 不同」的情境用的）
- teams_mtk 的 `SessionSource` 建構（`teams_mtk.py:1451`）只用了 `platform`/`chat_id`/
  `user_id`/`user_name`/`chat_type` 五個基本欄位，其中 `user_id` 已經是從 `8:orgid:<oid>`
  URL 解析出的穩定 AAD Object ID——**沒有「原生 ID vs 顯示 ID 不同」的情境**，不需要
  `user_id_alt`
- **判定**：不需要擴充，現有欄位已足夠表達 teams_mtk 的身份語意

### §11 Channel Directory — 已核對，屬於「有 fallback 但缺少特化」
- **查證**：讀了 `gateway/channel_directory.py:130-148`，通用邏輯是「非 Discord/Slack 的
  平台，只要不在 `_SKIP_SESSION_DISCOVERY`（local/api_server/webhook），就自動套用
  `_build_from_sessions(plat_name)`」
- teams_mtk **沒有**被排除在 `_SKIP_SESSION_DISCOVERY` 外，所以會自動走 session-based
  discovery fallback——**技術上已覆蓋**，不是完全空白
- **判定**：可運作但體驗較弱（session-based discovery 只能列出「曾經對話過的 chat」，
  不能像 Discord 一樣枚舉所有頻道）。**低優先度優化項**，非緊急漏做

### §13 Gateway Setup Wizard — 已確認（即本 spec 的 G11，見上）

### §14 Phone/ID Redaction — 已核對，發現新問題
- **查證**：`teams_mtk.py:425` `logger.info("TeamsMTK: user OID: %s", self._user_oid)`
  ——**AAD Object ID（UUID 格式）直接明文寫入 log，沒有任何遮罩**
- **對照**：`agent/redact.py` 已有 E.164 手機號碼遮罩機制（`_redact_phone`，Signal/WhatsApp
  用），但沒有 AAD OID 的遮罩規則
- **新發現 G12**：**AAD Object ID 洩漏到日誌**——OID 是使用者的穩定身份識別碼，等同於
  Signal 手機號碼的敏感度，應該遮罩（如 `8:orgid:abc12345-...` → `8:orgid:abc1****...`）
- **判定**：**確定漏做，中等風險**（隱私/合規問題，非功能性 bug）

### §15 Documentation — 已核對，確認缺口
- **查證**：`find website/docs -iname "*teams*"` 只找到 4 個檔案，全部是 Teams **會議
  pipeline**（`teams-meetings.md`/`operate-teams-meeting-pipeline.md`）或官方 SDK 版
  Teams（`teams.md`），**沒有任何 teams_mtk 專屬設定文件**
- 對照 `ADDING_A_PLATFORM.md` §15 要求：`website/docs/user-guide/messaging/<platform>.md`
  應該有專屬頁面
- **判定**：**確定漏做**——新使用者要設定 teams_mtk 只能讀 `teams_mtk.py` 檔頭 docstring
  （`python ~/.claude/skills/teams/auth_run.py` 等步驟），沒有正式文件

### §16 Tests Coverage — 已核對，覆蓋率評估
- **查證**：`tests/gateway/platforms/test_teams_mtk_*.py` 共 6 個檔案（reliability/
  attachment/group_policy/group_whitelist_chain/edit_message_signature/footer_picker）
  + `tests/gateway/test_teams_mtk_group_whitelist_authz.py`
- 對照 `ADDING_A_PLATFORM.md` §16 checklist：
  - ✅ Platform enum 存在 — `Platform.TEAMS_MTK` 已有
  - ⚠️ **Config loading from env vars via `_apply_env_overrides`** — 查無專屬測試
    （teams_mtk 走 `MTK_TEAMS_CONVERSATION_ID` 等專屬 env var，沒看到對應的
    `test_config.py` 或類似測試驗證 env→PlatformConfig 的載入邏輯）
  - ✅ Adapter init（config parsing, allowlist handling） — 已在 reliability/
    group_policy 測試涵蓋
  - ✅ Helper functions（redaction, parsing） — 部分涵蓋（footer_picker/attachment）
  - ❌ **Session source round-trip（to_dict → from_dict）** — 查無專屬測試
  - ✅ Authorization integration — group_whitelist_authz 涵蓋
  - ❌ **Send message tool routing（platform in platform_map）** — 對應 G6，
    本來就沒有路由，自然也沒測試
- **判定**：**確定有覆蓋缺口**——config env loading 和 session round-trip 兩項該補測試

## B.2 查證結果（send_model_picker 完整比對）

- **查證**：讀了 `plugins/platforms/telegram/adapter.py:4239` 的官方版 `send_model_picker`
- **對比結論**：
  - Telegram 版用 inline-keyboard 按鈕（`_build_provider_keyboard`），單則訊息原地編輯
    導航，使用者體驗更流暢（點擊按鈕 vs 回覆數字）
  - teams_mtk 版（`teams_mtk.py:768`）因為 polling 架構限制（同 G2/G3 的技術限制），
    用「發送編號列表 + 使用者回覆數字」模擬選單，poll loop 需要額外攔截器
    （interceptor）辨識「這是在回應選單」還是「這是新指令」
  - **這不是漏做，是架構限制下的合理設計**——teams_mtk 已經在限制範圍內做出最好的近似
    方案（兩步驟 provider→model 流程與官方版邏輯一致，只是互動方式不同）
- **判定**：**無需修改，設計合理**，與 G2/G3 同屬「polling 架構的天花板」，關閉此項

## Updated Confirmed Gaps List（本輪新增）

### G12. AAD Object ID 明文寫入日誌 ✅ 已修
- **修復**：`_redact_oid(oid, visible=8)` 只保留前 8 字元 + `****`；3 處 log 全遮罩（user OID / VIP oids / VIP sender）
- **判定**：✅ 已修

## B.4 WSP AI Agent 完整功能盤點（進行中，本輪盤點結果）

讀了 `teams_bot/core/bot_polling.py`（3116行，run_polling 主迴圈 + 8 個 `_handle_*` 子函式）
+ `teams_bot/core/teams_api.py`（1792行，`TeamsAPI` 類別 29 個方法），逐項對照 teams_mtk.py
現有的 29 個方法（`grep "def \|async def "` 清點結果）。

### WSP 有、teams_mtk 完全沒有的功能

| WSP 方法/功能 | 位置 | teams_mtk 現況 | 判定 |
|---|---|---|---|
| `search_users()` | `teams_api.py:957` | 無 | 使用者搜尋（依名字找 MRI），teams_mtk 沒有任何使用者查找機制，因為它是固定 conv_id 白名單架構，設計上不需要動態找人 |
| `get_or_create_chat()` | `teams_api.py:1180` | 無 | 動態建立 1-1 聊天，teams_mtk 只服務既有 conv_id，同上，設計差異非漏做 |
| `send_message_by_search()` | `teams_api.py:1436` | 無 | 依名字搜尋後直接發訊息（免先知道 conv_id），同上 |
| `get_conversation_members()` | `teams_api.py:846` | 無 | 列出群組成員，teams_mtk 沒有需要列成員的場景（白名單是 conv_id 層級不是 member 層級） |
| `upload_file()` / `send_file_message()` | `teams_api.py:628/692` | 無（inbound 有 `_download_attachment`，outbound 無） | **對應本 spec 已記錄的 G9**，不重複開新項 |
| `_handle_channel_list_request()` + 互動式頻道選擇 | `bot_polling.py:1195/1410` | 無 | WSP 支援「列出所有頻道→使用者選數字→對該頻道做總結」的互動流程；teams_mtk 沒有類似的多頻道互動導航（但 teams_mtk 本來就是明確白名單架構，不太需要「探索頻道」這個功能） |
| Cron 自然語言排程（`_handle_cron_request` 等 5 個函式，`bot_polling.py:1568-2073`） | 一整組 cron 子系統 | **Hermes 已有更完整的 `cronjob` tool**（agent-level，非 platform-level），教學 agent 這裡不需要重造 | **不是 gap，Hermes 原生方案更好**：WSP 是把 cron 功能硬編在 Teams bot 層，Hermes 把它做成通用 agent tool，教學任何平台都能用。teams_mtk 只要接上通用 `cronjob` tool（已在 toolset 裡）即可，不需要仿造 WSP 的 Teams 專屬 cron 解析器 |
| Boss Monitor（老闆訊息偵測+自動建議回覆，`_push_boss_suggestions` 等） | `bot_polling.py:436` + `_boss_monitors` state | 無 | 這是 WSP 特有的「監控特定老闆的訊息並生成建議回覆」功能，屬於**產品定位差異**（WSP 是秘書型助理，主動幫忙回老闆），Hermes teams_mtk 是被動應答型 agent，此功能超出 teams_mtk 的定位範疇，**不建議照搬**——若使用者真的要這個功能，該用 Hermes 的 `@我人設` 機制（見 memory 中「User要Hermes扮演我」）在 agent 層做，而非平台層 |
| 多語言 ACK 訊息字典（`_ACK_MESSAGES`，4 語言：zh_TW/zh_CN/ja/en） | `bot_polling.py:192` | 無（teams_mtk 沒有 ACK/placeholder 訊息機制，見 streaming-reliability spec 的 BUG-A 撤回結論） | 不適用——這正是上次已撤回的編造項，WSP 確實有這功能，但 teams_mtk 現在走 edit-based streaming（累積更新同一則訊息），不需要 ACK 文字。**兩者是不同的技術路線，非漏做** |
| `_detect_language()` 語言偵測 | `bot_polling.py:111` | 無 | teams_mtk 目前是純被動轉發文字給 agent，沒有語言偵測邏輯——**但這本來就該是 agent 層的能力**（Hermes system prompt 已設定「Traditional Chinese for chat」），不該重造在 platform adapter 層 |
| `_matches_trigger()` 關鍵字/@ 觸發雙模式（`bot_polling.py:402`） | 支援「純關鍵字」和「真實@mention」兩種模式切換 | teams_mtk 的 `require_mention` 機制（`teams_mtk.py:330`）**功能對等但更簡潔**——是布林開關而非雙模式 regex，且已有 config.yaml/env var 雙層解析（見 `_group_config`），**比 WSP 的實作更完整**（WSP 只有全域 trigger word，teams_mtk 有 per-group override） | **teams_mtk 已經更好，非漏做** |

### 結論（初版，已被用戶推回訂正——見下方「Revised Judgment」）

~~盤點後發現：WSP AI Agent 是一個「動態發現+互動導航+主動監控」的秘書型 Teams bot...~~
~~**其餘功能差異都是設計定位不同，不建議照搬**~~

**此結論已被用戶推回。** 用戶指出：teams_mtk 的目標是「在 MTK 環境下透過 Teams 發揮最高
效益」，不受 Phase1/Phase2 現有範圍自我限縮。「WSP 是秘書型、teams_mtk 是被動應答型」
是我自己編造的產品定位判斷，不是任何既定 spec 邊界，用這個理由關閉功能是錯誤的。

## Revised Judgment（用戶推回後重新審視）

### G13. 動態聯絡人解析 + 主動建立對話 ✅ Phase A 已修；Phase B 仍 blocked
- **Phase A（唯讀查找）**：✅ 已實作 `find_conversation(name)` + `list_conversations(limit)` + `_find_conv_by_display_name(name)` — SDK ConversationsService 優先 + raw HTTP fallback
- **Phase B（Graph API 動態搜尋+建對話）**：🔴 已阻止 — Chat.Create 未授權
- **重新評估**：這對 MTK 使用場景是真實高價值功能——例如使用者跟 agent 說「幫我訊息
  小明說專案delay了」，不需要先知道 conv_id；或 agent 主動通知同事（cron job 完成後
  通知相關人員）。這不是「產品定位不同」，是**真實的能力缺口**。
- **技術路徑**：WSP `teams_api.py:957` 的 `search_users()` 走 `/contacts` 端點用
  skypetoken 認證；teams_mtk 的 `_TeamsAuth` 已有同一套 skypetoken session
  （`teams_mtk.py:86`），**理論上可以直接複用同一 auth 物件呼叫相同端點**，不需要新的
  認證機制
- **安全設計要點**（這是真正需要設計的部分，不是理由關閉）：
  - 動態聯絡人解析若無限制，會讓白名單機制形同虛設（任何人都能被找到並發訊息）
  - 建議：分離「查找」與「發送」權限——查找不受限（唯讀），但主動發送給**新對象**
    （不在既有白名單 conv_id 清單）需要額外 gate，例如：只允許對 `TEAMS_ALLOWED_USERS`
    清單內的 OID 主動發訊息，或要求原始請求來自已授權對話（不能讓白名單外的人透過
    agent 間接聯絡任意人）
  - 這呼應現有 `gateway/authz_mixin.py` 的 group whitelist 模式，應該延伸而非繞過
- **判定**：**重新開啟為真實功能需求**，排入 tasks.md，需要設計安全 gate 才能實作。
  **詳細架構設計見下方「G13 Detailed Design」**。

## G13 Detailed Design — 動態聯絡人解析 + 主動建立對話

### 現況盤點（實際查證，非猜測）

**WSP 的三層策略**（`teams_api.py:1180` `get_or_create_chat`）：
1. `_find_existing_chat()` — 先掃既有對話（免權限，最快）
2. `_create_chat_via_chatsvc()`（`teams_api.py:1373`）— 用 skypetoken 呼叫
   `{CHATSVC_BASE}/threads`，payload 帶雙方 MRI，**跟 teams_mtk 現有的
   `skype_token()`/`msg_base` 走同一套認證，技術上零障礙**
3. Graph API fallback（`teams_api.py:1227` `self.auth.get_graph_token()`）——
   **這一步需要額外的 Graph API scope**，WSP 的 `TeamsAuth.GRAPH_SCOPE =
   "https://graph.microsoft.com/.default offline_access"`（`teams_auth.py:44`），
   teams_mtk 目前的 `_SKYPE_SCOPE = "https://api.spaces.skype.com/.default
   offline_access"`（`teams_mtk.py:67`）**沒有這個 scope**——若 Strategy 2
   （chatSvc）失敗要 fallback 到 Graph API，teams_mtk 需要重新走一次 OAuth 同意
   流程取得 Graph scope，這是**唯一的技術新增項**，其餘都可複用現有 auth

**`search_users()`**（`teams_api.py:957`）：三層快取（search cache → local contacts
cache → Graph API `/users` 端點），Graph API 呼叫一樣需要 `get_graph_token()`。

### 架構決策：分兩個 Phase 實作，不要一次到位

**Phase A（低風險，先做）：唯讀查找，不新增 Graph scope**
- 只做「掃描既有已知對話」（WSP Strategy 1，`_find_existing_chat`），**不做**
  `search_users()`（那需要 Graph API）
- 新增 `teams_mtk.py` 方法 `_find_conv_by_display_name(name: str) -> Optional[str]`：
  掃描 `list_conversations`（teams_mtk 目前沒有這個方法，需要新增，仿照
  `teams_api.py:246` 的 `list_conversations`）比對顯示名稱
- **這一步不需要新 OAuth scope、不需要新的安全 gate 討論**——因為只能找「Hermes
  已經在對話過的人」，天然被白名單約束（如果 Hermes 沒跟這人講過話，Phase A 找不到）

**Phase B（需要決策，後做）：Graph API 動態搜尋 + 主動建立新對話**
- 需要新增 Graph API scope 到 `_SKYPE_SCOPE`（或另外維護一組 Graph token，比照
  WSP `TeamsAuth` 的雙 scope 設計），**這一步需要重新走 OAuth 同意流程**（`auth_run.py`
  重新授權），是唯一需要使用者介入的技術動作
- 安全 gate（核心設計，見下）：
  ```
  agent 想主動聯絡某人
    │
    ├─ 目標 OID 在 TEAMS_ALLOWED_USERS 清單內？
    │    ├─ 是 → 允許查找 + 允許建立新對話 + 允許發送
    │    └─ 否 → 繼續判斷
    │
    ├─ 目標已有既存對話（Phase A 找得到）？
    │    ├─ 是 → 允許查找 + 允許發送（不需要「建立新對話」，對話已存在）
    │    └─ 否 → 繼續判斷
    │
    └─ 觸發此請求的原始使用者，是否來自已授權對話（source.chat_id 在白名單內
       或 source.user_id 在 GATEWAY_ALLOWED_USERS 內）？
         ├─ 是 → 允許查找（唯讀），但**建立新對話 + 發送需要額外確認**
         │        （比照 send_exec_approval 的核准流程，或至少 log WARNING 供稽核）
         └─ 否 → 拒絕（這個分支理論上不該發生，因為能呼叫 agent 的人本身已經過
                  _is_user_authorized 檢查——但仍要顯式拒絕，防禦深度原則）
  ```
- **關鍵原則**：查找永遠唯讀不受限（低風險，純資訊性），**主動發送/建立新對話**
  才是真正的權限邊界——這條線劃在「白名單內的人可以透過 agent 聯絡白名單內的其他人」
  和「白名單內的人可以透過 agent 聯絡任意組織成員」之間，**後者需要明確的核准或
  更嚴格的 gate**，不能預設開放

### 新工具 Schema 草案（`tools/teams_mtk_contact_tool.py`，走 Footprint Ladder 第 2-3 級）

依照 AGENTS.md 的 Footprint Ladder：這不該是新的 model 核心工具（第6級，成本最高），
應該是**service-gated tool**（第3級，只在 teams_mtk 平台啟用時出現）或
`send_message` tool 的 target 擴充（第1級，延伸既有工具）。

**建議走第1級**——擴充現有 `send_message` tool 的 `target` 語法，不新增工具：
```
target: "teams_mtk:contact:<display_name>"  # 新增的 target 格式
```
`tools/send_message_tool.py` 的 `_parse_target_ref` 加一個 `contact:` 前綴分支，
解析後呼叫 teams_mtk adapter 新增的 `resolve_contact_to_chat_id(display_name, gate_check=True)`
方法，內部做 Phase A/B 判斷 + 安全 gate，回傳 chat_id 或 gate 拒絕的錯誤訊息。
**零新增 model tool schema footprint**，只是 `target` 字串多一種寫法。

### G14. VIP 發送者緩衝觸發 + 草稿建議（Boss Monitor 對等功能）
- **重新評估**：WSP 的 Boss Monitor（`bot_polling.py:436` `_push_boss_suggestions` +
  `_boss_monitors` state）本質是「偵測特定發送者 OID → 緩衝訊息 → 生成回覆建議並推送給
  指定通知對象」。這在 MTK 場景（一級/二級主管訊息處理）是真實有價值的能力，不應該
  因為「這是 agent 層該做的事」而完全排除在 platform adapter 討論之外。
- **重新定位**：這確實橫跨兩層——**偵測+緩衝**是 platform 層合理的能力（teams_mtk 已有
  類似的 per-conv state 管理模式，如 `_model_picker_states`），**生成建議**才是 agent 層
  該做的事（透過 P7 Persona 或既有 agent 呼叫）。正確設計是 teams_mtk 提供「VIP 發送者
  偵測 + 緩衝 + 觸發」的 hook，觸發後呼叫 Hermes agent（不是重造 WSP 的規則式生成器）
- **判定**：**重新開啟，設計為 teams_mtk 的偵測層 + Hermes agent 的生成層**分工，
  排入 tasks.md 作為需要設計文件的項目（依賴 P7 Persona 的介面，但不是「以後才做」，
  是現在就該規劃介面契約）。**詳細架構設計見下方「G14 Detailed Design」**。

## G14 Detailed Design — VIP 發送者緩衝觸發 + 草稿建議

### WSP 現況盤點（實際查證）

`BossMonitor`（`tools/boss_monitor/boss_monitor.py:28`）的核心邏輯，逐一核對：
- `add_message()`（line 78）：收到一則訊息時判斷「是否該立即處理緩衝區」——條件是
  (a) 距上一則訊息超過 `buffer_timeout` 秒（視為新段落，先處理舊緩衝）或
  (b) 這則訊息本身結尾有標點/超過50字元（視為完整句子，立即觸發）
- `flush_if_stale()`（line 121）：**這是關鍵**——設計成「由 bot_polling 每次
  polling iteration 呼叫」，用來處理「使用者發完最後一句話後就不再說話」的情況
  （沒有下一則訊息可以觸發 timeout 判斷，所以需要輪詢主動檢查）
- `_process_buffer()`（line 144）：合併緩衝區訊息，更新 profile，是規則式/LLM
  生成建議回覆的入口（`get_reply_suggestion`，line 190）

WSP 把「偵測」「緩衝」「生成」三件事都寫在 `BossMonitor` 一個類別裡，且生成邏輯
（`_generate_llm_suggestions`，line 286）是獨立呼叫 LLM，**跟 WSP 主 agent 引擎
（`BotEngine`）完全分離**——這是 WSP 的設計缺陷，不是我們要照抄的部分。

### 分層設計（teams_mtk 偵測層 + Hermes agent 生成層）

**Layer 1（teams_mtk platform adapter，新增）**：`_VIPBuffer` 輕量類別
- 只做「偵測 VIP OID + 緩衝 + 判斷何時該觸發」，**不生成任何回覆內容**
- 狀態管理仿照 `_model_picker_states: Dict[str, Optional[Dict[str, Any]]]`
  （`teams_mtk.py:353`）的 per-conv dict 模式：`self._vip_buffers: Dict[str, _VIPBuffer]`
  （key 是 conv_id，因為同一個 VIP 可能在多個 conv 出現）
- 觸發條件複用 WSP 的兩個規則（timeout / 句子結尾），**但改成可設定**
  （`gateway.teams_mtk.vip_monitor.buffer_timeout_seconds`，比照現有
  `teams_mtk.groups.*` 的 config.yaml 慣例）
- `_poll_loop()`（`teams_mtk.py:1110`）每次 tick 呼叫 `_vip_buffers[conv_id].check_flush()`
  ——**複用 WSP `flush_if_stale()` 的輪詢檢查設計**，這部分技術上直接抄，因為
  teams_mtk 本來就是 polling 架構，天然適合這個模式

**Layer 2（Hermes agent，觸發時呼叫）**：**不新增生成器**，而是：
- VIP 緩衝觸發時，teams_mtk 把緩衝內容當成一則正常訊息餵給 `_process_new_messages`
  （`teams_mtk.py:1191`，現有的訊息處理入口），**讓 Hermes agent 用正常對話流程
  處理**，agent 的回應方式由 P7 Persona（`@我人設`）決定要不要生成「建議回覆」還是
  直接代答
- 差異只在於：VIP 訊息**不直接回給 VIP 本人**，而是路由給
  `gateway.teams_mtk.vip_monitor.notify_targets`（比照 WSP 的 `notify_targets` 設定），
  這是**投遞目標的改變**，不是生成邏輯的改變——複用現有 `send_message` tool 或
  `adapter.send()` 對另一個 conv_id 投遞

### 為何不能等 P7 完全做完才動這個

P7 Persona 的介面契約（「觸發時要傳什麼上下文給 agent、agent 回應要投遞到哪裡」）
**現在就該定義**，即使 P7 本身還沒做完——理由：Layer 1（偵測層）跟 P7 是否存在無關，
teams_mtk 現在就可以先把「VIP偵測+緩衝+路由到 notify_targets」的骨架建好，先用
「固定文字通知：VIP老闆訊息已緩衝，請查看原對話」這種最簡單的 Layer 2 佔位，
等 P7 做完再把佔位換成真正的建議生成。**這樣兩層解耦，不互相卡進度**。

### G15. 白名單頻道可見度查詢（原「頻道互動導航」重新定位）
- **重新評估**：WSP 的 `_handle_channel_list_request`（列出所有可用頻道供選擇）在
  teams_mtk 的白名單架構下不是要「無限制探索任意頻道」（那確實違反白名單安全邊界，
  這點維持原判斷不變——**白名單是刻意的安全邊界，非能力不足**），但「讓授權使用者在
  Teams 對話裡直接查詢自己被授權的頻道清單」是合理且低風險的可見度功能，目前只能用
  `hermes teams-mtk group list`（CLI），沒有 chat-native 指令
- **判定**：低優先度但納入 backlog，作為「在 Teams 內建 `/teams-mtk-groups` 或類似查詢
  指令」的候選功能，非拒絕

## 修正後仍維持關閉的項目（附強化理由，非產品定位臆測）

- **Cron 自然語言排程**：維持關閉，但理由改為明確技術事實——Hermes `cronjob` tool 是
  agent-level 通用工具，一旦 G5（cron delivery platform 註冊）修復，agent 在 teams_mtk
  對話裡收到「每天9點提醒我」這種請求時，**本來就會呼叫 `cronjob` tool**，不需要
  teams_mtk 自己解析自然語言時間——重複實作反而會與 agent 層工具衝突。這不是「定位
  不同」，是「有更好的既有機制，重複建置反而是壞事」
- **多語言 ACK 訊息**：維持關閉，純技術路線差異（edit-streaming vs ACK文字），與
  「最大化效益」無關，這裡沒有被埋沒的能力
- **G2/G3 Adaptive Card 按鈕**：維持關閉，純架構限制（polling 無 webhook），與產品
  定位判斷無關，是真實技術天花板
- **`_matches_trigger` 雙模式**：維持關閉，teams_mtk 的 per-group config override
  機制客觀上功能範圍更廣（WSP 只有全域 trigger word），這不是「定位不同」而是
  teams_mtk 已經更好，沒有東西可抄

## Scope Boundary

此 spec 現在同時涵蓋 Hermes 原生 Teams 比對（已完成）與 WSP 功能盤點（B.4，本輪完成）。
兩份盤點都已產出結論；後續動作分別在 tasks.md §1（Hermes 原生 gap）與上方 B.4.1/B.4.2
（WSP 功能，待使用者決定產品方向）追蹤。

## §8. Teams Skill CLI 功能整入評估

### 8.0 背景

teams skill CLI（`~/.claude/skills/teams/`）和 teams_mtk gateway
（`gateway/platforms/teams_mtk.py`）是**兩套獨立的 Skype API client**，
各自實作 HTTP 呼叫邏輯，只是共享同一份 token cache
（`~/.teams-tokens/token_cache.json`）。
這導致：①同一 API 兩份 code，②gateway 缺少 CLI 已有的多項能力。

### 8.1 Skill CLI `src/api/` SDK 層結構

| 模組 | 行數 | 方法數 | 職責 |
|---|---|---|---|
| `_http.py` HTTPLayer | 185 | 15 | HTTP 層、auth headers、retry、HTML↔markdown |
| `_messages.py` MessagesService | 598 | 17 | 收發訊息、編輯/刪除/回覆/轉發、置頂、日期翻頁 |
| `_search.py` SearchService | 157 | 7 | 跨 conv keyword+sender+date 搜尋 |
| `_activity.py` ActivityService | 463 | 11 | 通知/@提及/通話記錄/筆記/追蹤/已儲存 |
| `_files.py` FilesService | 229 | 6 | AMS 圖片上傳、OneDrive 檔案上傳+SharePoint file card |
| `_reactions.py` ReactionsService | 70 | 3 | Graph API 加/移表情反應 |

### 8.2 功能對照表：skill CLI 有 vs gateway 現狀

| # | 功能 | skill CLI | gateway 現狀 | 整入價值 |
|---|---|---|---|---|
| **S1** | 歷史訊息翻頁 | `MessagesService.get_by_date()` — backwardLink 多頁 | `_fetch_messages` 只取 20 條無翻頁 | 🔴 **極高** |
| **S2** | 訊息搜尋 | `SearchService.messages()` — keyword+sender+date 跨 conv | ❌ 完全沒有 | 🔴 **極高** |
| **S3** | 使用者查詢 | `users.py search/schedule/availability` — Graph API | ❌ 完全沒有 | 🔴 **高** |
| **S4** | Activity feed | `ActivityService.list()` — 通知/@提及 | ❌ 完全沒有 | 🟡 **中** |
| **S5** | 通話記錄 | `ActivityService.list_call_logs()` | ❌ 完全沒有 | 🟡 **中** |
| **S6** | 一般檔案上傳 | `FilesService.send_file()` — OneDrive 5 步+SharePoint card | `send_document()` 已有（G-MEDIA-2） | ✅ **已有** |
| **S7** | Reactions | `ReactionsService.send/remove` | ❌ 完全沒有 | 🟡 **中低** |
| **S8** | WebSocket listen | `listen.py` — Trouter WS | `_poll_loop` 3s HTTP poll | 🟢 **低**（見 8.3） |
| **S9** | 訊息刪除 | `MessagesService.delete()` | ❌ | 🟡 **中低** |
| **S10** | 訊息轉發 | `MessagesService.forward()` | ❌ | 🟡 **中低** |
| **S11** | 訊息置頂/取消置頂 | `MessagesService.pin/unpin/list_pinned` | ❌ | 🟢 **低** |
| **S12** | Notes/Threads/Saved | `ActivityService.list_notes/threads/saved` | ❌ | 🟢 **低** |

### 8.3 不整入的項目及理由

| 項目 | 理由 |
|---|---|
| **S8 WebSocket listen** | gateway 已有 3s poll（延遲可接受）；WS 斷線重連邏輯極複雜
（`listen.py` 180 行只處理 happy path）；替換 polling 為 WS 是底層替換
風險大收益小。若未來需要，應獨立 spec 處理 |
| **S11 置頂** | 極低頻使用，需要時 agent 可透過 `terminal` 呼叫
`messages.py pin` 腳本 |

### 8.4 整入架構：共用 SDK 層

**核心原則：不在 gateway 裡重新寫 skill CLI 的 HTTP 呼叫邏輯。**

```
目前：
  gateway → self._session.get/post (硬編 HTTP, ~500行)
  skill CLI → HTTPLayer / MessagesService (結構化 SDK)

目標：
  gateway → import teams_sdk（skill CLI src/api/）→ TeamsClient
  skill CLI → 同一個 TeamsClient
```

**實作路徑**：

1. 把 `~/.claude/skills/teams/src/api/` 抽成**獨立 installable package**
   （`teams-skype-sdk`，或直接加到 `pyproject.toml` 的 local dep），
   放在 `D:/01_Job/Tool/Hermes Agent/lib/teams_skype_sdk/`
2. `HTTPLayer` 需要適配 gateway 的 `_TeamsAuth`：
   - gateway 的 `_TeamsAuth` 已有 `skype_token()` / `access_token()`
   - `HTTPLayer.__init__(auth: TeamsAuth)` 的 `TeamsAuth` interface
     只有 `get_skype_token()` + `get_access_token()` 兩個方法
   - 用 **adapter pattern**：寫一個薄的 `_SDKAuthAdapter`，
     把 `_TeamsAuth` 包成 `HTTPLayer` 接受的 auth interface
3. gateway 的 `_fetch_messages`、`send()`、`edit_message()` 等
   方法漸進替換為 SDK 呼叫，**每次替換一個方法，跑過回歸測試**

### 8.5 S1 詳細設計：歷史訊息翻頁

**現狀問題**：
- `_fetch_messages(conv_id, limit=20)` 只拿最近 20 條，無翻頁
- agent 被問「上週某位同事說了什麼」時只能靠 PKB cron（60m 延遲）
  或 spawn `terminal` 呼叫 `messages.py get --all`

**SDK 方法**：
- `MessagesService.get(conv_id, limit, offset)` — 逐頁掃
- `MessagesService.get_by_date(conv_id, start, end)` — 日期範圍

**gateway 整合**：
- 替換 `_fetch_messages` 為 SDK 的 `get()`
- 新增 `_fetch_messages_full(conv_id, limit=200)` — 用 SDK 的多頁掃描
- PKB 即時落地 hook 可以一次拉全量而不用等 cron

### 8.6 S2 詳細設計：訊息搜尋

**SDK 方法**：
- `SearchService.messages(query, sender, date_from, date_to, limit)` —
  先 Graph API `/me/chats/{id}/messages?$search=`，fallback Skype API 拉全量 client-side filter

**gateway 整合**：
- 新增 `search_messages(conv_id, query, **filters)` 方法
- agent 在 Teams 對話裡被問「某位同事最近說了什麼關於 X 的事」時，
  gateway 能直接搜尋，不需要 spawn subprocess 呼叫 CLI

### 8.7 S3 詳細設計：使用者查詢

**現狀**：`people.py search` 已可用（§4B 已驗證），但需要 agent 手動 spawn
subprocess 呼叫腳本。

**gateway 整合**：
- `users.py` 的 `GraphAPI.search_users()` / `.get_schedule()` /
  `.find_common_availability()` 本身在 skill CLI 的 `src/api/_graph.py` 裡
- gateway 已有 `graph_token()`（§4.0 已完成），可以直接用
- 新增 `_search_users(query)` / `_get_schedule(emails, date)` 方法
- 透過 PLATFORM_HINTS 告知 agent 這些能力可用

### 8.8 S4/S5 詳細設計：Activity + 通話記錄

**SDK**：
- `ActivityService.list()` — 通知+@提及
- `ActivityService.list_call_logs(target_person, days_back)` — 通話記錄含篩選

**gateway 整合**：
- 新增 `_get_activity(limit)` / `_get_call_logs(limit, **filters)` 方法
- 有助於 agent 主動感知 @提及和來電（目前 gateway 完全不感知）

### 8.9 S7 詳細設計：Reactions

**SDK**：`ReactionsService.send(conv_id, msg_id, reaction)` /
`.remove(conv_id, msg_id, reaction)` — Graph API beta

**gateway 整合**：
- 新增 `send_reaction(conv_id, msg_id, reaction)` / `remove_reaction(...)` 方法
- `reaction` 限於 VALID_REACTIONS：like/heart/laugh/surprised/sad/angry
- 低頻但提升互動體驗可用

### 8.10 全量拉取原則（修正 `limit=20` 設計缺陷）

**問題**：`_fetch_messages(conv_id, limit=20)` 和 `_poll_loop` L1841
硬編 `self._fetch_messages(_c, 20)` 是**未經授權的設計缺陷**——
用戶從未指示一次只拉 20 條，實際要求是**除非特別指定，否則就是全量**。

**根因**：寫 gateway 時照 HTTP API 的 `pageSize` 參數隨手寫了 20，
沒有依 spec 也不能追溯到任何用戶指示。

**Skype API 分頁機制**：
- 回傳 `._metadata.backwardLink` URL，有值代表還有更早的訊息
- API 單次上限 `pageSize=50`，但可以連續翻頁直到 `backwardLink` 為空
- SDK 的 `MessagesService.get(conv_id, limit)` 已實作此翻頁邏輯

**修正設計**：
- `_fetch_messages(conv_id, limit=None)`：`limit=None`（預設）→ 全量
- `limit=N`：明確指定時只拉 N 條（保留精確控制能力）
- poll loop 改為 `self._fetch_messages(_c)` 全量拉取
- `_fetch_messages_by_date(conv_id, start, end)`：日期範圍查詢（用 SDK）
- 單頁 `pageSize` 用 API 上限 50，翻頁到 `backwardLink` 為空
- **無封頂**：不設 `max_pages` 限制，全量就是全量

**「全量」= 硬碟歷史 + API 增量（PKB 快取加速）**：

大部分時候不需要從 API 翻頁到底。PKB cron 每 60m 已把全量訊息寫到
`raw/teams/<conv_id>.md`，gateway 的 `_fetch_messages` 可以：

1. **讀硬碟**：從 PKB `raw/teams/` 讀出該 conv 的歷史訊息
2. **拉增量**：只從 API 拉比硬碟最後一條 msgid 更新的訊息
3. **合併**：硬碟舊 + API 新 = 全量

```
PKB raw/teams/<conv_id>.md          Skype API
┌─────────────────────┐     ┌──────────────────┐
│ msg_001 (7/1 10:00) │     │ msg_098 (7/10 9:00)│  ← 新的
│ msg_002 (7/1 10:05) │     │ msg_099 (7/10 9:02)│  ← 新的
│ ...                  │     │ msg_100 (7/10 9:05)│  ← 新的
│ msg_097 (7/10 8:55) │     └──────────────────┘
└─────────────────────┘            ↑
         ↑                     只拉這些
    從硬碟讀              （比 last_msgid 更新）
```

**降 API 開銷**：
- 活躍 conv（2~3 條新訊息/週期）：只需 1 頁 API call
- 冷 conv（0 新訊息）：0 API call（讀硬碟即可）
- 首次 connect 或 PKB 無檔案：才需要全量翻頁

**實作**：
- `_fetch_messages(conv_id)` 先檢查 PKB 檔案是否存在
- 存在 → 讀出最後一條 msgid → API 用 `startTime` 參數只拉更新
- 不存在 → 全量翻頁（首見 conv 或 PKB 損壞）

## §9. WebSocket vs HTTP Poll 架構決策

### 9.1 現狀

gateway 用 HTTP `_poll_loop` 每 2~3 秒（`_POLL_INTERVAL`）拉一次訊息。
teams skill CLI 有 `listen.py`（Trouter WebSocket），可即時收到新訊息事件。

### 9.2 WebSocket listen 的能力與限制

| 特性 | WebSocket listen | HTTP poll |
|---|---|---|
| 到達率 | ❌ **不保證**。WS 斷線時的訊息全部丟失，無重傳 | ✅ 下次 poll 一定拿得到 |
| 連線穩定性 | ❌ `on_close` 只設 `stop_event.set()`，斷線即死 | ✅ 每次獨立 HTTP，天然容錯 |
| 離線補漏 | ❌ 完全沒有。`listen.py` 斷了不回溯 | ✅ poll 自然補齊 |
| 重連邏輯 | ❌ 無自動重連，需要外部 watchdog | ✅ poll loop 永遠循環 |
| 資料完整性 | ⚠️ 只拿到 `resource` 子集（sender, content, conv_id, msg_id） | ✅ 完整 API response |
| 即時性 | ✅ ~0.1s 延遲 | ⚠️ 2~3s 延遲 |
| MTK 內網相容性 | ⚠️ Trouter `*.trouter.skype.com` 可能被 proxy 擋 | ✅ 已證實可通 |
| 資源消耗 | ✅ 長連線，無請求開銷 | ⚠️ 每 2s 一次 HTTP |

### 9.3 結論：WS 不能退役 poll，但要互補

**正確架構是雙通道互補**：

```
WebSocket listen（主通道——即時通知）
     │
     ├─ 收到事件 → 立即觸發一次 _fetch_messages 詳細拉取
     │               （延遲從 2~3s 降到 ~0.1s）
     │
     └─ 斷線/丟包 → poll loop 兜底補漏
                    （頻率可從 2~3s 放寬到 10~15s，
                     因為 WS 正常時不靠它）
```

**poll 不能退役的原因**：
1. WS 斷線期間的訊息無重傳，必須靠 poll 補
2. WS 只推事件摘要，完整資料仍需 HTTP 拉
3. `listen.py` 目前沒有自動重連，放進 gateway 需要補完整
4. MTK 內網 Trouter endpoint 未經驗證

### 9.4 整入計畫

**Phase 1（先做，低風險）**：WS 作為加速通道
- 在 `_poll_loop` 裡並行跑一個 WS listener
- WS 收到事件 → 立即觸發 `_process_new_messages`（不等 poll 週期）
- WS 斷線 → poll loop 照跑，頻率不變
- poll 頻率維持 2~3s（WS 斷線時的兜底仍需快）

**Phase 2（後做，需驗證）**：WS 穩定後放寬 poll
- WS 連續穩定運行 5 分鐘以上 → poll 頻率放寬到 10~15s
- WS 斷線 → poll 立即回到 2~3s
- 需要 WS 自動重連 + exponential backoff（`listen.py` 缺的部分）

**Phase 2 前置**：
- `listen.py` 補自動重連邏輯（`on_close` → 握手→ 重連，上限 5 次，
  exponential backoff 1/2/4/8/16s）
- MTK 內網 Trouter endpoint 可達性驗證
- WS 斷線偵測（heartbeat timeout —— `2::` ping/pong 機制已有）

### 9.5 不做的事

- 不退役 poll loop（見 9.3 分析）
- 不把 WS 當唯一通道（可靠性不足）
- 不在 `listen.py` 現有基礎上直接塞進 gateway——需先重寫為
  async class（`_TrouterListener`），整合到 `_poll_loop` 生命週期

## §10. 反向盤點：gateway 功能 vs skill CLI 幫助

以 gateway 所有功能（已實現 + spec 中尚未實現）為主體，
反向檢查 skill CLI 對每個功能的幫助程度。

### 10.1 已實現的 gateway 功能

| # | gateway 功能 | skill CLI 幫助 | 說明 |
|---|---|---|---|
| G-A1 | 收訊息（3s poll） | ✅ SDK 可替換 | `_poll_loop` 底層改走 SDK `MessagesService.get()` |
| G-A2 | 發訊息（HTML） | ✅ SDK 可替換 | `send()` → SDK `MessagesService.send()` |
| G-A3 | 編輯訊息 | ✅ SDK 可替換 | `edit_message()` → SDK `MessagesService.edit()` |
| G-A4 | 圖片發送（AMS） | ✅ SDK 可替換 | `send_image_file()` → SDK `FilesService.send_image()` |
| G-A5 | 檔案發送（OneDrive） | ✅ SDK 可替換 | `send_document()` → SDK `FilesService.send_file()` |
| G-A6 | Adaptive Card | ❌ CLI 無此能力 | gateway 獨有 |
| G-A7 | Model Picker | ❌ CLI 無此能力 | gateway 獨有 |
| G-A8 | VIP Buffer | ❌ CLI 無此能力 | platform runtime 功能 |
| G-A9 | 附件下載 | ✅ 同 API | `attachments.py download` |
| G-A10 | 列出對話 | ✅ SDK 可替換 | `list_conversations()` → SDK `_conversations.py` |
| G-A11 | 按名字找對話 | ✅ SDK 可替換 | `_find_conv_by_display_name` → SDK `_conversations._find_chat` |
| G-A12 | 按 OID 找對話 | ⚠️ CLI 沒有此方法 | 但 SDK `_conversations.py` 可擴充 |
| G-A13 | PKB 即時落地 | ❌ CLI 無此概念 | gateway pipeline 獨有 |
| G-A14 | Typing indicator | ⚠️ 空實作 | CLI 也不支援 |
| G-A15 | Echo guard/Dedup | ❌ CLI 無此能力 | runtime 狀態管理 |
| G-A16 | Reply throttle | ❌ CLI 無此能力 | runtime 功能 |
| G-A17 | Group whitelist | ❌ CLI 無此能力 | 安全層 |
| G-A18 | Blocked toolsets | ❌ CLI 無此能力 | 安全層 |
| G-A19 | Short-msg gating | ❌ CLI 無此能力 | 訊息篩選 |
| G-A20 | HTML↔markdown | ✅ SDK 已有 | `HTTPLayer` 內建 |

### 10.2 尚未實現的 gateway 功能（spec §7/§9）

| # | gateway 待做 | spec 任務 | skill CLI 幫助 | 說明 |
|---|---|---|---|---|
| G-B1 | 全量翻頁 | S1-1/S1-2 | ✅ 完全現成 | `_messages.py` `get_by_date()` 含 `backwardLink` 翻頁 |
| G-B2 | 日期範圍查詢 | S1-3 | ✅ 完全現成 | `_messages.py` `get_by_date()` |
| G-B3 | PKB 快取+增量 | S1-1 | ❌ CLI 無 PKB | gateway pipeline 獨有 |
| G-B4 | 訊息搜尋 | S2-1 | ✅ 完全現成 | `_search.py` `SearchService.messages()` |
| G-B5 | 使用者搜尋 | S3-1 | ✅ 完全現成 | `users.py search` + SDK `GraphAPI.search_users()` |
| G-B6 | 行事曆查詢 | S3-2 | ✅ 有替代 | `users.py schedule`；outlook `cal.py` 更完整 |
| G-B7 | 找共同空檔 | S3-3 | ✅ 完全現成 | `users.py availability` + SDK `GraphAPI.find_common_availability()` |
| G-B8 | Activity feed | S4-1/S4-2 | ✅ 完全現成 | `_activity.py` `ActivityService.list()` 含翻頁 |
| G-B9 | 通話記錄 | S5-1 | ✅ 完全現成 | `_activity.py` `ActivityService.list_call_logs()` |
| G-B10 | Reactions | S7-1 | ✅ 完全現成 | `_reactions.py` `ReactionsService` |
| G-B11 | 訊息刪除 | S9-1 | ✅ 完全現成 | `_messages.py` `MessagesService.delete()` |
| G-B12 | 訊息轉發 | S10-1 | ✅ 完全現成 | `_messages.py` `MessagesService.forward()` |
| G-B13 | WS listen | WS-1~6 | ✅ 有協議實作 | `listen.py` 有 Trouter；需重寫為 async class |
| G-B14 | WS 自動重連 | WS-2 | ⚠️ CLI 沒有 | gateway 自己補 |
| G-B15 | SDK 共用層 | SDK-0~3 | ✅ **根本就是 CLI 的 SDK** | `src/api/` ≈1700 行已寫好的 code |

### 10.3 幫助三分類

**A. 核心幫助——SDK 就是 CLI 的 code（≈1700 行）**

gateway 待做功能的底層 API 呼叫邏輯幾乎全部已在 skill CLI 的 SDK：

| gateway 功能 | 可直接用的 SDK 模組 | 行數 |
|---|---|---|
| 全量翻頁+日期+刪除+轉發 | `_messages.py` MessagesService | 598 |
| 訊息搜尋 | `_search.py` SearchService | 157 |
| Activity+通話 | `_activity.py` ActivityService | 463 |
| 圖片+檔案上傳 | `_files.py` FilesService | 229 |
| HTML↔markdown+HTTP層 | `_http.py` HTTPLayer | 185 |
| 列出對話 | `_conversations.py` | 248 |
| Reactions | `_reactions.py` ReactionsService | 70 |
| **合計** | | **~1,950** |

**B. 部分幫助——需 gateway 自己補**

| 功能 | CLI 給什麼 | gateway 還需補 |
|---|---|---|
| WS listen | `listen.py` Trouter 協議 | 自動重連、async class、heartbeat |
| 按 OID 找對話 | SDK `_conversations.py` 可擴充 | 成員 OID 比對邏輯 |
| 全量拉取 PKB 快取 | 無 | 讀 `raw/teams/` + 解析 last msgid + 增量 API |
| PKB 即時落地 | 無 | `_pkb_land_message` pipeline |

**C. gateway 獨有——CLI 完全幫不上**

| 功能 | 性質 |
|---|---|
| Adaptive Card / Model Picker | 互動 UI |
| VIP Buffer 偵測/路由 | platform runtime |
| Echo guard / Dedup / Throttle / Gating | 安全和訊息品質 |
| Group whitelist / blocked toolsets | 安全邊界 |
| PKB pipeline | 持久化 + 增量 |

### 10.4 關鍵洞察

1. **SDK 是最大槓桿**：gateway 待做功能的 ~80% 底層已在 CLI SDK 裡。
   SDK-0（抽出共用 package）完成後，S1~S10 的核心 API 呼叫
   幾乎都是一行 `self._sdk.messages.get(conv_id, ...)` 的問題。

2. **gateway 真正獨有的價值在 pipeline 不是 API**：
   PKB 快取/即時落地、VIP buffer、echo guard、throttle、
   group whitelist——這些是 gateway 長駐 runtime 才能做的事，
   CLI subprocess 做不到。

3. **替換不等於刪除——漸進是對的**：
   REPLACE-1~7 的設計正確。gateway 的 `send()` 等方法先
   內部改走 SDK，外部介面不變，回歸測試確認行為不變後
   才刪舊 code。

## §11. CLI 反向補強：gateway 功能回饋到 skill CLI

以「gateway 解了哪些問題是 CLI user 也會遇到的」為標準，
不是搬 daemon 功能進 CLI（那些搬不動），而是 **gateway 修過的
bug / 改過的 UX 同樣影響 CLI user**，應該回饋修進 SDK/CLI。

### 11.1 🔴 高價值 — 所有 CLI user 直接受惠

#### C-1：HTML 內容正確剝離

**問題**：CLI SDK `_http.py` 的 HTML 處理不完整——

1. `<at>` regex 可能吃掉 `@` 前綴（跟 gateway BUG-2 同一個 bug）
2. `<blockquote>` 轉發內容不處理——CLI user 收到的 `content`
   裡混著別人的轉發 HTML，當成自己的訊息
3. `properties.files` / `<file>` / `<img>` 附件不提取——
   收到有附件的訊息時 CLI 只看到 HTML tag，不知道有檔案

**gateway 的解法**（`teams_mtk.py` L2258-2250）：

```
4 層附件提取： ① <img src> → image
              ② <file src name> → file
              ③ properties.files[].contentUrl → file
              ④ attachments[].contentUrl → image/file

<at> regex：    <at ...>([^<]*)</at> → @\1（保留 @ 前綴）

<blockquote>：  用戶文字 + [forwarded message: …]；純轉發 skip

HTML strip：   re.sub(r'<[^>]+>', '', content) + whitespace collapse
```

**補強方案**：Patch SDK `_http.py` 的 `_process_message_content`，
把 gateway 的完整 HTML 處理邏輯修進 SDK。這樣 gateway 整入
SDK 時就不會再出現 BUG-2 regression（§10.5 分析）。

**影響範圍**：所有 `messages.py get/send/reply` 用戶、所有
`poll.py` 用戶、所有 `activity.py feed` 用戶——只要讀訊息就受影響。

#### C-2：Echo guard / 自我訊息篩選

**問題**：CLI `poll.py` 只有簡陋的 `_is_bot_msg()`——
靠 MRI 比對 1 道防線 + 固定字串比對。**不偵測 fingerprint、
不處理 `hermes_sender` property 被剝除的情況**。

實際影響：任何人用 `poll.py` 當 bot loop runner，
都會遇到 bot 回覆自己→再回覆→echo loop。

**gateway 的解法**（4 道防線）：

```
① properties.hermes_sender == "agent"  （send 時注入）
② msgid == last_sent_message_id       （msgid 比對）
③ sent_dedup.is_duplicate(msgid)      （TTL 去重）
④ HTML fingerprint 偵測              （border-left:#6264A7 / <b>🤖 Hermes</b>）
```

**補強方案**：

1. SDK `send()` 時注入 `properties.hermes_sender: "bot"` 
   （gateway 用 `"agent"`，CLI 用 `"bot"` 區分來源）
2. `poll.py` 的 `_is_bot_msg()` 增加第 2 道防線——
   HTML fingerprint 偵測（`border-left` style / bot signature tag）
3. 考慮 `poll-state.json` 記錄 `last_sent_msgid` 做第 3 道防線

#### C-3：全量拉取預設行為

**問題**：CLI `messages.py get` 預設 `--limit 20`，
用戶忘了加 `--all` 就只拿 20 條——跟 gateway `limit=20` 的
**同一個 UX 缺陷**（§8.10 分析的根因完全適用）：
「用戶從未指示一次只拉 20 條」。

**gateway 的解法**：§8.10 改 `limit=None` 預設全量 + PKB 快取。

**補強方案**：

- `messages.py get`：`--limit` 預設改為 `None`（全量）
- 保留 `--limit=N` 明確控制
- 全量 = SDK `backwardLink` 翻頁
- 不加 `max_pages` 封頂（同 §8.10 原則）
- `--all` flag 保留但標為 `--all` is now default,
  use `--limit=N` for bounded fetch"

#### C-4：附件下載 auth

**問題**：CLI `attachments.py download` 不處理 AMS
skypetoken auth——下載 AMS 託管的圖片會 403。
SharePoint / OneDrive 附件也未處理 auth。

**gateway 的解法**（`_download_attachment()` L1338，2026-07-11 實測修正）：

```
1. AMS URL（api.asm.skype.com）→ Authorization: skypetoken ***
2. SharePoint/OneDrive fileUrl → 對任何 token（Skype-audience 或
   單純 Graph-audience Bearer）皆 401 — SharePoint 要求資源專屬
   token，refresh_token 未被授權該資源 scope。
   **真實修法**：改用 properties.files[].fileInfo.shareUrl
   （Skype API 本就回傳的分享連結）+ Graph `/shares` API：
   base64url 編碼 shareUrl 加 `u!` 前綴 →
   GET graph.microsoft.com/v1.0/shares/{encoded}/driveItem/content
   + 一般 Graph-audience Bearer token（`exchange_for_scope`
   換 `https://graph.microsoft.com/.default`）即可下載成功。
   **實測驗證**：3 個真實 SharePoint 檔案（.docx 377KB / .pptx
   225KB / .xlsx 4.9MB）全部下載成功。
3. 普通 URL → no auth
4. 自動偵測 URL 類型並注入對應 auth header/下載路徑
```

**補強方案**：`attachments.py download` 加自動 auth 偵測——
URL 含 `api.asm.skype.com` → `skype_token` header；
含 `sharepoint.com` / `1drv.ms` → **不要**直接對 fileUrl 加 Bearer
graph_token（會 401），改用上述 Graph `/shares` 編碼下載路徑，
輸入需為 `shareUrl` 而非 `fileUrl`。

### 11.2 🟡 中價值 — 特定場景有幫助

#### C-5：Short-message gating

**問題**：CLI `poll.py` 沒有任何訊息品質篩選——
群組裡收到「好」「OK」也觸發 bot 回應，浪費 token。

**gateway 的解法**（BUG-5 fix）：≤2 字元且無 `?？!！` + `@mention`
→ ignore，per-group 可關閉。

**補強方案**：`poll.py` 的 `--config` JSON 加可選欄位：

```json
{
  "chat_id": "...",
  "short_message_threshold": 2,
  "short_message_exceptions": ["?", "？", "!", "！"]
}
```

預設 `null`（不過濾），設了才啟用——向後相容。

#### C-6：Group whitelist 安全邊界

**問題**：CLI `poll.py` 無任何群組限制——
任何 chat_id 都回應。如果有人拿到 config 裡的 chat_id
就可以讓 bot 在任何群組裡回話。

**gateway 的解法**：`hermes teams-mtk group add/list/set`
+ `_is_user_authorized()` + per-group `require_mention`。

**補強方案**：`poll.py --config` JSON 加可選欄位：

```json
{
  "chat_id": "...",
  "allowed_sender_domains": ["@mediatek.com"],
  "allowed_sender_mrIs": ["8:orgid:xxx"]
}
```

預設 `null`（不限），設了才啟用。

#### C-7：VIP 偵測 + 路由

**問題**：CLI `poll.py` 把所有「需要回應」的訊息
走同一個 pipeline。無法針對特定人員（主管）的訊息
做差別處理或路由。

**gateway 的解法**：`_VIPBuffer` + per-conv OID list + `notify_targets`。

**補強方案**：`poll.py --config` JSON 加可選欄位：

```json
{
  "chat_id": "...",
  "vip_oids": ["8:orgid:xxx"],
  "vip_notify_target": "<conversation-id>"
}
```

VIP 訊息路由到 `vip_notify_target`，非 VIP 正常處理。

### 11.3 SDK 改動總覽

把 C-1~C-4 的修補整合到 SDK 時，需考慮跟 §7 SDK 整入的
互動——**先修 SDK bug 再整入 gateway**，否則 gateway 會
繼承 bug。

| 項目 | SDK 改動 | 跟 §7 的關係 |
|---|---|---|
| C-1 | Patch `_http.py`：`<at>` regex + `<blockquote>` + 4層附件提取 | **先做**——SDK 整入前修好，gateway 不會繼承 BUG-2 |
| C-2 | Patch `_messages.py send()`：注入 `hermes_sender`; Patch `poll.py`：加 fingerprint 偵測 | 與 SDK-1 auth adapter 獨立但最好先做 |
| C-3 | Patch `messages.py CLI`：改預設行為 + SDK `get()` 預設 limit=None | **先做**——跟 §8.10 全量拉取同邏輯 |
| C-4 | Patch `attachments.py` + SDK 加 `_download_with_auth()` | 與 REPLACE-4 SDK 替換獨立 |

**建議順序**：C-1 → C-3 → C-4 → C-2 → SDK-0（整入 gateway）

理由：

- C-1 是**資料正確性 bug**——所有下游消費者都受害，最優先修
- C-3 是 UX 預設值——簡單改，修完 CLI 和 gateway 都受益
- C-4 是 auth 問題——修完附件才能用，但不阻塞其他功能
- C-2 是 echo guard—— poll.py 用戶才需要，非 poll 用戶不受影響
- SDK-0 放最後——先讓 SDK 是對的再整入，免得 gateway 繼承 bug
