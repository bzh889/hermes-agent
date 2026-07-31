# Teams MTK Hermes Native Parity — E2E 測試註冊表

本文件彙整所有 Teams MTK Adapter 的端到端測試案例，分為「已驗證通過」與「待實作驗收」兩大區塊。所有測試設計遵循以下原則：
- **真實環境**：使用 `gateway.log` 實際輸出作為驗收依據
- **可重現**：提供明確的操作步驟與驗證條件
- **自動化**：測試腳本位於 `openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py`（正式位置）
  `scripts/e2e_teams_mtk.py` 為轉發 shim，請勿直接編輯

## 執行方式

```bash
# 確保 gateway 正在執行
hermes gateway run

# 執行全部測項
python openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py

# 或透過 shim（等效）
python scripts/e2e_teams_mtk.py

# 執行特定測項
python openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py --only send-image-file list-conversations

# 跳過特定測項
python openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py --skip model-picker
```

---

## ✅ 已驗證通過項目

### 1. 核心通訊可靠性（teams-mtk-answer-reliability）

#### E1: G4 send_typing 實作驗收
**觸發方式**: 用 Graph API user token 發送 Typing 指示
**操作步驟**:
  1. 啟動 gateway 並等待 ready
  2. 發送 `/model` 指令觸發 long streaming
  3. 觀察 `_keep_typing` loop 行為
**Gateway log 驗證**: 出現 `TeamsMTK: send_typing OK for conv=...`
**回覆內容驗證**: Teams 對話中顯示「正在輸入...」狀態指示器
**DONE 定義**: 連續 3 次以上 send_typing 訊息成功發送（間隔 3-4s）
**驗證證據**: [streaming-reliability/tasks.md L9-18](tasks.md#L9-L18) + [gateway.log 2026-07-10](#L16-18)

#### E2: G6 mention gating 群組白名單驗收
**觸發方式**: Graph API user token 發送不含 @hermes 的訊息
**操作步驟**:
  1. 設定群組 require_mention=true
  2. 發送「E2E_AUTO no mention」訊息
  3. 等待 10 秒觀察處理結果
**Gateway log 驗證**: 出現 `ignoring group message (require_mention=true)`
**回覆內容驗證**: Teams 對話中無 Hermes 回覆
**DONE 定義**: 連續 3 次測試均無回覆且 log 正確記錄
**驗證證據**: [teams-mtk-group-whitelist/tasks.md L42-47](tasks.md#L42-L47) + [`e2e_teams_mtk.py` mention-gating-ignore](e2e_teams_mtk.py#L138-L147)

#### E3: G8 echo guard 重啟行為驗收
**觸發方式**: 重啟 gateway 並恢復歷史訊息處理
**操作步驟**:
  1. 發送「E2E_AUTO echo guard test」訊息
  2. 重啟 gateway
  3. 確認舊訊息不被重新處理
**Gateway log 驗證**: 出現 `seeded last_message_id` 且無 `new message from` 舊訊息
**回覆內容驗證**: 無重複回覆歷史訊息
**DONE 定義**: 重啟後首次 poll 不觸發歷史訊息處理
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L148-153](tasks.md#L148-L153) + [`e2e_teams_mtk.py` restart-no-replay](e2e_teams_mtk.py#L188-L202)

#### E4: G23 model picker slug 驗收
**觸發方式**: Graph API user token 發送 `/model` 指令
**操作步驟**:
  1. 發送 `/model` 觸發第一步驟
  2. 發送 `1` 選擇第一個 provider
  3. 確認第二步驟正確帶入 slug
**Gateway log 驗證**: 出現 `model picker step 2.*slug=`
**回覆內容驗證**: Teams 收到模型選擇回覆
**DONE 定義**: 連續 5 次測試均有正確 slug 傳遞
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L148-153](tasks.md#L148-L153) + [`e2e_teams_mtk.py` model-picker](e2e_teams_mtk.py#L162-L185)

#### E5: G5 cron standalone_sender_fn 驗收
**觸發方式**: 執行 `cronjob action=run` 觸發 daily-e2e-skill-verify job
**操作步驟**:
  1. 確認 `deliver=teams_mtk` job 定義存在
  2. 手動執行 cron job
  3. 檢查投遞結果
**Gateway log 驗證**: 出現 `execution_success: true` + Teams 對話收到 cron 內容
**回覆內容驗證**: Teams 對話中顯示 cron job 預期內容
**DONE 定義**: job 執行成功且訊息正確送達
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L27-39](tasks.md#L27-L39)

### 2. 媒體與通訊功能（teams-mtk-hermes-native-parity）

#### E6: G-MEDIA-1/3 send_image_file 驗收
**觸發方式**: Graph API user token 發送圖片訊息
**操作步驟**:
  1. 使用 `send_image_file` 上傳 100x50 PNG
  2. 透過 Graph API GET readback 確認附件
  3. Teams 客戶端確認顯示
**Gateway log 驗證**: 出現 `AMS upload completed` + `send_image_file ams_id=`
**回覆內容驗證**: Teams 對話中顯示正確圖片
**DONE 定義**: POST/GET readback 與客戶端顯示三者一致
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L299-306](tasks.md#L299-L306)

#### E7: G-MEDIA-2 send_document 驗收
**觸發方式**: Graph API user token 發送文件訊息
**操作步驟**:
  1. 使用 `send_document` 上傳測試文件
  2. 確認 OneDrive share link 生成
  3. Teams 點擊下載驗證
**Gateway log 驗證**: 出現 `OneDrive upload 201` + `share link generated`
**回覆內容驗證**: Teams 對話中顯示可點擊的分享連結
**DONE 定義**: share link 可成功下載原始文件
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L302-304](tasks.md#L302-L304)

#### E8: G13-A.1 list_conversations 驗收
**觸發方式**: 執行 `list_conversations(limit=10)`
**操作步驟**:
  1. 呼叫 API 取得對話清單
  2. 確認回傳 10 筆真實對話
  3. 檢查標題為非空，證據只記錄 hash 與長度
**Gateway log 驗證**: 出現 `list_conversations returning 10 conversations`
**回覆內容驗證**: 回傳清單包含非空真實標題，輸出只保留 hash 與長度
**DONE 定義**: 連續 3 次呼叫均取得有效對話清單
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L356-360](tasks.md#L356-L360)

#### E9: G14-1.1 VIPBuffer 基礎功能驗收
**觸發方式**: 發送 VIP OID 的真實訊息
**操作步驟**:
  1. 設定 VIP OID 與 notify_targets
  2. 發送觸發訊息
  3. 等待 buffer_timeout_seconds 後檢查通知
**Gateway log 驗證**: 出現 `VIP buffer flushed to notify_targets`
**回覆內容驗證**: 目標群組收到含原始內容的通知訊息
**DONE 定義**: 訊息在 timeout 前正確轉發且內容完整
**驗證證據**: [teams-mtk-hermes-native-parity/tasks.md L528-535](tasks.md#L528-L535)

### 3. 輸出品質 Content Tier 測項（2026-07-13 新增）

> 這批測項誕生於一次會話中連續發現 5 個 **log-pattern tier 無法偵測** 的真實 bug。
> 詳見 tasks.md 頂部 Verdict Tier 分級說明。

#### E10: streaming-no-echo-duplication（Tier 2）
**對應 bug**: MSG API POST 只回 `OriginalArrivalTime` 無 `id`，streaming edit 無目標造成重複發送 11 次近相同訊息
**觸發方式**: 用 Graph API user token（`send_chat_message()`）發送觸發多步 streaming edit 的查詢
**操作步驟**:
  1. 記錄 baseline 訊息 IDs
  2. 發送 `/new` + 查詢
  3. 等待 45s 让 agent 完成一個 full turn
  4. `get_messages_raw()` 讀回真實對話
  5. 對新 bot 訊息按正規化 prefix 分組，計數近似重複
**Gateway log 驗證**: N/A（本測項專門驗證 log 看不到的內容品質問題）
**回覆內容驗證**: 同一正規化 prefix 出現 ≤1 次（無重複 progress message）
**DONE 定義**: 同一 turn 內無近似重複的 bot 訊息 body
**驗證證據**: ✅ 2026-07-13 PASS（`e2e_teams_mtk.py` streaming-no-echo-duplication）
**關鍵教訓**: `send_via_sdk()` 用 bot 自己的 token 會被 echo guard 跳過，必須用 `send_chat_message()`（真實 user token）

#### E11: no-residual-markdown-in-reply（Tier 2）
**對應 bug**: `_build_html()` 有 HTML tags 時跳過 markdown 轉換 → `**bold**`/`` `code` ``/`[text](url)`/`- bullet`/`| pipe |` 原樣送到 Teams
**觸發方式**: 用 Graph API user token 發送刻意觸發粗體+表格+連結的查詢
**操作步驟**:
  1. 記錄 baseline
  2. 發送 `/new` + 「用一個 table 列出 3 個測試項目的狀態，並用粗體標註結論」
  3. 等待 45s
  4. `get_messages_raw()` 讀回真實 HTML
  5. 正則檢查 5 種殘留語法：`**...**`、`` `...` ``、`[...](url)`、`- bullet`、`| pipe |`
**Gateway log 驗證**: N/A
**回覆內容驗證**: 全部 5 種 markdown 語法均未殘留在渲染後的 HTML 中
**DONE 定義**: 回覆 HTML 中無任何原始 markdown 語法
**驗證證據**: ✅ 2026-07-13 PASS（`e2e_teams_mtk.py` no-residual-markdown-in-reply）
**修復記錄**: `_inline_md_to_html()` static method 新增（bold→`<b>`, code→`<code>`, link→`<a href>`, bullet→`• `），`_build_html()` 三個分支都先跑 `_inline_md_to_html()`

#### E12: no-disallowed-fallback-models（Tier 1）
**對應 bug**: `wfm-coder-qwen3-coder-480b` 在 AIDE 帳號無權限呼叫（HTTP 403），但仍在 fallback chain 中 → 每次 garbage trigger 白耗一次 retry + 連發 fallback 切換訊息
**觸發方式**: 靜態檢查 `~/.hermes/config.yaml`
**操作步驟**:
  1. 讀取 config.yaml
  2. 遍歷所有 provider 的 models 清單
  3. 比對 KNOWN_DISALLOWED set
**Gateway log 驗證**: N/A（靜態配置檢查）
**回覆內容驗證**: N/A
**DONE 定義**: 無已知無權限模型存在於任何 provider 的 model list
**驗證證據**: ✅ 2026-07-13 PASS（`e2e_teams_mtk.py` no-disallowed-fallback-models）

#### E13: attachment-domain-routing-covers-asyncgw（Tier 1）
**對應 bug**: `as-prod.asyncgw.teams.microsoft.com` 圖片下載 403 — SDK `download_with_auth_url()` domain match 未涵蓋 asyncgw 子域名，錯用 Bearer header 代替 skypetoken
**觸發方式**: 靜態檢查 `_http.py` domain routing 條件
**操作步驟**:
  1. 取得 `download_with_auth_url` source
  2. 驗證 `"teams.microsoft.com" in netloc` 涵蓋所有 `*.asyncgw.teams.microsoft.com` 子域名
**Gateway log 驗證**: N/A（靜態邏輯檢查）
**回覆內容驗證**: N/A
**DONE 定義**: `teams.microsoft.com` substring match 涵蓋 `as-prod.asyncgw.teams.microsoft.com` 等 subdomain
**驗證證據**: ✅ 2026-07-13 PASS（`e2e_teams_mtk.py` attachment-domain-routing-covers-asyncgw）
**備註**: 目前的 substring match `"teams.microsoft.com" in netloc` 天然涵蓋所有子域名；此測項防止有人未來改寫為 exact host match 又破掉

#### E14: garbage-detector-no-false-positive（Tier 2）
**對應 bug**: Output quality check 偶發觸發 garbage discard + fallback，使用者質疑是否誤判
**觸發方式**: 用 Graph API user token 發送簡短查詢，觀察真實 gateway 行為
**操作步驟**:
  1. 記錄 baseline
  2. 發送 `/new` + 簡短查詢（不需 tool call）
  3. 等待 30s
  4. `get_messages_raw()` 確認 bot 回覆送達
  5. `gateway.log` 計數 `Garbage output detected` 次數
**Gateway log 驗證**: `Garbage output detected` 計數（非零仍算 PASS，因 retry loop 成功）
**回覆內容驗證**: Bot 回覆存在（代表 retry 成功）
**DONE 定義**: Bot 回覆存在；若 discard > 0 則附記「retry succeeded after N discard(s)」
**驗證證據**: ✅ 2026-07-13 PASS（`e2e_teams_mtk.py` garbage-detector-no-false-positive）
**結論**: AIDE 高 context 偶發 Cyrillic/Arabic 退化是真警報（score ~8.0 vs threshold 3.0），非誤判；但 fallback chain 包含無權限模型是 bug（已修，見 E12）

#### E15: inbound-edit-revision-reopens-query（Tier 2）
**對應 bug**: 已處理的真人查詢原地編輯後保留相同 remote identity，舊 cursor 僅依 message ID 判斷而不會再開 revised turn
**觸發方式**: Graph API 建立真人訊息；等待原始 turn 完成後，以 canonical MSG API 對讀回的同一 identity 原地編輯
**操作步驟**:
  1. 記錄 baseline，送出 `/new` 並確認新 acknowledgement
  2. 送出唯一原始查詢，等待一個 exact bot reply
  3. canonical read-back 取得真人查詢 identity，以 MSG `PUT` 編輯該 identity
  4. 等待 poll/WebSocket overlap settle window，再做第二次 canonical read-back
  5. 分別計數 revised exact reply、duplicate、original replay 與 cleanup residue
**Gateway log 驗證**: 僅保留 `recorded revision candidate` 的 message/conversation hash、字元長度與 content hash，不記錄 raw identity/body
**回覆內容驗證**: `revised_dispatch=1`、`duplicate_dispatch=0`、完整 edited body match、`original_replay=0`
**DONE 定義**: 同一 remote identity 只產生一個完整 revised turn，finally 清理後 marker residue 為 0；任何 cleanup 錯誤使測項 FAIL
**驗證證據**: ✅ 2026-07-31 targeted real-gateway PASS（`--only inbound-edit-revision-reopens-query`）；最終驗收仍需不帶 `--only` 的完整 NAMED_TESTS

---

## 🟡 待實作驗收項目

### 1. 歷史訊息與搜尋功能

#### S1-1/S1-2 historical message full fetch + PKB cache
**觸發方式**: 用 Graph API user token 對真實 conv 發訊息
**操作步驟**:
  1. 確保 PKB 無該 conv 歷史快取
  2. 執行 `list_conversations` 觸發全量拉取
  3. 確認 PKB 生成 `raw/teams/<conv_id>.md`
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `fetched X messages via API (full fetch)`
**回覆內容驗證**: PKB 檔案包含完整歷史訊息內容
**DONE 定義**: 全量拉取後 PKB 檔案大小 > 100KB 且消息數量符合預期

#### S2-1 search_messages() method
**觸發方式**: 用 Graph API user token 發送 `/search 合規`
**操作步驟**:
  1. 在目標 conv 發送 5 則含「合規」的訊息
  2. 呼叫 `search_messages(conv_id, '合規')`
  3. 確認回傳結果
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `search_messages returning Y results`
**回覆內容驗證**: 回傳結果包含所有相關訊息內容片段
**DONE 定義**: 搜尋結果精準匹配 5 則訊息且無額外結果

#### S3-1 _search_users() method
**觸發方式**: 用 Graph API user token 發送 `/search_user 郭中仁`
**操作步驟**:
  1. 呼叫 `_search_users('郭中仁')`
  2. 確認回傳 OID/email/display_name
  3. 驗證 Graph API 可取得相同結果
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `search_users returning Z users`
**回覆內容驗證**: 回傳結果包含 `display_name='郭中仁'` 的條目
**DONE 定義**: 搜尋結果與 Graph API 直接呼叫結果完全一致

### 2. 媒體與進階功能

#### G-MEDIA-4 send_adaptive_card
**觸發方式**: 用 Graph API user token 對真實 conv 發送 adaptive card
**操作步驟**:
  1. 構建符合 Skype 消費端規格的 card payload
  2. 呼叫 `send_adaptive_card()`
  3. Teams 客戶端確認渲染
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `sent adaptive_card with properties.cards`
**回覆內容驗證**: Teams 對話中正確顯示按鈕/選項卡
**DONE 定義**: POST/GET readback 確認 card 內容持久化且客戶端可互動

#### G13-A (list_conversations, _find_conv_by_display_name) — 真實 E2E 補強
**觸發方式**: CLI 執行 `hermes teams-mtk group list`
**操作步驟**:
  1. 確認 `list_conversations` 回傳 >5 筆對話
  2. 從清單動態選擇真實標題後呼叫 `_find_conv_by_display_name(title)`
  3. 驗證回傳 conv_id 正確
**Gateway log 驗證**: 觀察 `gateway.log` 確認查找成功；證據只記錄 title hash 與結果狀態
**回覆內容驗證**: CLI 輸出正確 conv_id 與標題
**DONE 定義**: 連續 3 次呼叫均取得正確結果且無空值

### 3. 系統與預備測試

#### WS-0 Trouter connectivity check
**觸發方式**: 執行 `listen.py --timeout 10`
**操作步驟**:
  1. 在 MTK 內網環境執行
  2. 確認 WebSocket 連接成功
  3. 發送測試事件驗證通道
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `WS connection established`
**回覆內容驗證**: CLI 輸出包含 `Received event: trouter.message`
**DONE 定義**: 連續 5 次連接均成功建立且事件可接收

#### send_typing (GAP-1) — 完整驗收補強
**觸發方式**: 用 Graph API user token 發送長篇訊息
**操作步驟**:
  1. 觸發需 >10s 生成的回覆
  2. 觀察 Typing 指示器持續更新
  3. 確認斷線後重連行為
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `send_typing OK` 每 3-4s 一次
**回覆內容驗證**: Teams 用戶全程看到「正在輸入...」狀態
**DONE 定義**: Typing 狀態持續至回覆完成，斷線後重連不中斷

#### standalone_sender_fn (cron deliver=teams_mtk) — 二次確認
**觸發方式**: 等待 cronjob 自動觸發 `daily-e2e-skill-verify`
**操作步驟**:
  1. 確認 job 排程在 09:00
  2. 09:00 檢查 Teams 對話
  3. 驗證訊息內容正確
**Gateway log 驗證**: 觀察 `gateway.log` 確認出現 `cronjob executed: daily-e2e-skill-verify`
**回覆內容驗證**: Teams 對話收到 cron job 預期內容
**DONE 定義**: 自動排程訊息成功送達且內容與手動執行一致

### 4. Query revision 與 native reply（P0）

> 這三個 verdict 必須獨立。Transport probe 只證明 raw envelope 可支援契約，不能取代真實 gateway dispatch、MessageEvent context、native outbound relation 或 cleanup 驗收。

#### inbound-edit-revision-reopens-query（Tier 2）
**觸發方式**: 由真實 human inbound 路徑建立一則唯一 query，等待首輪完成後直接編輯同一 remote message identity
**操作步驟**:
  1. 記錄控制對話 baseline 與唯一 marker
  2. 發送原始 query，等待 canonical read-back 與首輪 model reply
  3. 對同一 message identity 寫入修訂後完整 query
  4. 等待 poll/WS 重疊窗口結束並再次 canonical read-back
  5. 在 `finally` 依精確 IDs／marker 清除原始、修訂與所有 bot artifacts
**Gateway log 驗證**: 同一 chat/message identity 只出現一次 revision dispatch；重複 poll 不新增 turn
**回覆內容驗證**: 新回覆只根據修訂後完整 query；舊 body 未重播，revision 只產生一個新回答
**DONE 定義**: revision dispatch=1、duplicate=0、canonical edited body match、cleanup residue=0

#### quoted-reply-full-context-revises-query（Tier 2）
**觸發方式**: 由 human inbound 路徑對一則長於 quote preview 的來源訊息做 native reply，reply body 明確修訂需求
**操作步驟**:
  1. 建立含 terminal sentinel 的長來源訊息並 canonical read-back
  2. 以 native reply 提交修訂 body
  3. 驗證 reply relation identity，並用該 identity 直接取得完整 source
  4. 驗證 gateway event／model reply使用完整 source＋修訂 body，而非 preview
  5. 在 `finally` 清除 source、reply與所有 bot artifacts並 read-back residue
**Gateway log 驗證**: reply source identity 與 full-context fetch 成功；不把 preview 標成 full context
**回覆內容驗證**: 回覆必須反映 terminal sentinel 後的完整 source 資訊與修訂 body
**DONE 定義**: exact relation match、full source hash match、preview-only=false、cleanup residue=0

#### reply-to-native-thread-roundtrip（Tier 2）
**觸發方式**: 讓 Hermes 透過正式 delivery path 帶 `reply_to` 回覆受控來源訊息
**操作步驟**:
  1. 建立受控 target message 並取得 canonical identity
  2. 呼叫 Hermes delivery path 產生回覆
  3. canonical read-back 驗證 reply-chain／quoted-message／blockquote relation 指向 target
  4. 額外用 forced pre-send-unavailable fixture 驗證 flat fallback 只送一次且有 degradation signal
  5. 在 `finally` 清除 target、native reply、fallback fixture與所有相關 artifacts
**Gateway log 驗證**: 正常路徑明確走 native SDK reply；只有 pre-send unavailable 可出現 flat degradation；indeterminate send 不得二次 flat send
**回覆內容驗證**: 正常路徑保留 native relation；fallback 路徑內容只出現一次
**DONE 定義**: native relation read-back PASS、duplicate=0、forced fallback observable、cleanup residue=0