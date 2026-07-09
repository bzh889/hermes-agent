## 1. Config schema

- [x] 1.1 在 `hermes_cli/config.py` 的 `DEFAULT_CONFIG` 加入 `gateway.teams_mtk.groups: {}`（深合併，不影響現有使用者）
- [x] 1.2 確認 `load_cli_config()` / `load_config()` / gateway 直讀 YAML 三條路徑都能看到這個新 key（依 AGENTS.md 的三路徑規則檢查）

## 2. Authz：群組白名單路徑

- [x] 2.1 在 `gateway/authz_mixin.py` 新增輔助方法（如 `_teams_mtk_group_is_whitelisted(chat_id) -> bool`），讀 `gateway.teams_mtk.groups` 判斷 conv_id 是否存在
- [x] 2.2 在授權主邏輯中，對 `source.platform == Platform.TEAMS_MTK` 且 `chat_type == "group"` 時，優先呼叫 2.1，命中即 `return True`，其餘（DM、未列入白名單的群組）維持現有 `GATEWAY_ALLOWED_USERS` 判斷路徑不變
- [x] 2.3 補迴歸測試：確認現有 `GATEWAY_ALLOWED_USERS` 個人白名單行為（DM + 未列入群組）完全不受影響 — `tests/gateway/test_teams_mtk_group_whitelist_authz.py`

## 3. Mention gating 改查 config

- [x] 3.1 在 `gateway/platforms/teams_mtk.py` 新增 `_group_config(conv_id) -> dict`，讀 `gateway.teams_mtk.groups.<id>`，不存在則回傳 `{}`
- [x] 3.2 修改 `_process_new_messages` 的 mention gating 判斷（現在的 `MTK_TEAMS_NO_MENTION_CONVS` CSV 檢查），改為讀取順序：`_group_config(conv_id).get("require_mention")` → `self.require_mention`（既有 env var）→ `True`
- [x] 3.3 保留 `MTK_TEAMS_NO_MENTION_CONVS` env var 作為 back-compat fallback（讀取邏輯 OR 進新的 config 判斷，兩者取聯集），避免既有使用者設定失效

**副產品修復**：實作過程中發現並修正一個既有 bug — `chat_type` 判斷原本混雜了「是否 @thread」和「是否免 mention」兩個獨立概念，導致免mention的群組被誤判為 `chat_type="dm"`，讓新的群組白名單 authz 分支完全打不到。已拆開為純函式判斷（詳見 `teams-mtk-adapter` skill 的 pitfall「chat_type Must Reflect Actual Conversation Type」）。

## 4. 工具限制（disabled_toolsets）

- [x] 4.1 在派送訊息給 agent 前的呼叫路徑上，組出 `disabled_toolsets = group_cfg.get("blocked_toolsets", []) + group_cfg.get("per_user", {}).get(user_id, {}).get("blocked_toolsets", [])`（去重）— `gateway/authz_mixin.py::_merge_teams_mtk_group_disabled_toolsets`
- [x] 4.2 確認該清單正確傳入 `AIAgent.__init__(disabled_toolsets=...)`（或對應的 agent 建構呼叫點）— `gateway/run.py` 兩處呼叫點皆已接上；unit test 驗證 union 邏輯正確（`test_merge_disabled_toolsets_*`），**尚未在真實 gateway 上用實際群組手動驗證工具確實被擋（見 7.2 的阻塞說明）**

## 5. 關鍵字雙向過濾

- [x] 5.1 在 `_process_new_messages` 的入站文字處理階段（mention 剝除之後），比對 `group_cfg.get("blocked_keywords", [])`（regex，大小寫不敏感）；命中則不轉發給 agent，改發固定拒答話術，並寫一筆 log
- [x] 5.2 在 `send()`（出站）前對最終回覆文字跑同一份 regex；命中則不送出原文，改發固定拒答話術，並寫一筆 log
- [x] 5.3 定義並集中管理固定拒答話術文字（單一常數，全域共用，不做 per-群組自訂——對齊 design.md 的 Open Questions 決議）— `_BLOCKED_KEYWORD_NOTICE`

## 6. CLI：`hermes teams-mtk group`

- [x] 6.1 新增 CLI 檔案（實際檔名 `hermes_cli/teams_mtk_groups.py`，仿 `hermes_cli/pairing.py` 結構）
- [x] 6.2 實作 `group add <conv_id> [--name] [--require-mention]`：寫入 `gateway.teams_mtk.groups.<id>`，`require_mention` 預設 `false`；完成後印出「需重啟 gateway 生效」提醒
- [x] 6.3 實作 `group list`：列出所有群組的 `name`、有效 `require_mention`（含 fallback 來源標註）、`blocked_toolsets`、`blocked_keywords`
- [x] 6.4 實作 `group set <conv_id> [--require-mention] [--block-toolset ...] [--block-keyword ...] [--user <oid> --block-toolset ...]`：更新對應欄位（去重合併），印出重啟提醒
- [x] 6.5 實作 `group remove <conv_id>`：從 `gateway.teams_mtk.groups` 刪除該條目
- [x] 6.6 在 `hermes_cli/main.py` 掛上這個子命令樹（`build_teams_mtk_parser` + `cmd_teams_mtk_group`），`hermes teams-mtk group ...` 可執行 — 已用臨時 `HERMES_HOME` 手動跑過 add/list/set(toolset+keyword)/set(per-user)/list/remove/list 全流程，行為正確

## 7. 驗證與收尾

- [ ] 7.1 用一個測試群組跑過完整流程：`group add` → 重啟 gateway → 免 @mention 發訊息 → 收到回覆 —
      **BLOCKED**：需要重啟正在運行的正式 gateway（`pythonw.exe`，會中斷使用者現有 Teams session），且需要一個「非擁有者」的真實 Teams 帳號發訊息才能驗證白名單真正繞過個人白名單（目前只有 mtk12265 一個可用身分，無法模擬其他發送者）。已用 unit test 覆蓋邏輯層（authz 分支、mention 解析順序），但未在真實 gateway process 上驗證。需使用者確認：(a) 同意現在重啟 gateway，(b) 提供一個真實測試群組 conv_id，(c) 若要驗證非擁有者授權，需要另一個真實帳號協助發訊息。
- [ ] 7.2 驗證 `blocked_toolsets` 對該群組生效（agent 無法呼叫被封鎖的工具）— 同上，依賴 7.1 的環境才能做真實驗證；unit test 已驗證 union 邏輯（見 task 4.2）
- [ ] 7.3 驗證 `blocked_keywords` 雙向攔截皆生效 — 同上，依賴 7.1；unit test 已驗證 regex 比對邏輯（`_find_blocked_keyword`）
- [x] 7.4 驗證未列入 `groups` 的既有 1-1 對話、既有全域白名單使用者行為完全不受影響（迴歸）— `test_non_whitelisted_group_falls_back_to_individual_allowlist`、`test_dm_conversations_unaffected_by_group_whitelist`、`test_individually_allowlisted_user_still_authorized_in_non_whitelisted_group` 三個測試涵蓋
- [x] 7.5 執行 `scripts/run_tests.sh` 相關測試目錄，確認既有測試綠燈 —
      目標測試（本次新增 + 既有 TeamsMTK/relay authz 相關）：**80/80 全過**。
      全 `tests/gateway/` 目錄（417 檔）：209 個既有失敗，經 `git stash` 比對確認與本次改動無關（有無改動失敗數完全一致，屬於 pre-existing 技術債，主因 Windows symlink 權限與既有 mock/fixture 問題）。
- [x] 7.6 更新對應文件 —
      `website/docs/user-guide/messaging/` 是公開產品文件，但 TeamsMTK 是這個 fork 專屬的 MTK 內部 adapter（不隨 Hermes 上游發布），放公開文件不合適。改為更新 `teams-mtk-adapter` skill：新增 `references/group-permissions-design.md`（完整實作文件：schema、程式碼位置、測試覆蓋）+ SKILL.md 加入 2 個 pitfall（TeamsMTK 無 per-group allowlist 的舊問題已標記 RESOLVED、chat_type 不該混雜 mention policy 的規則）。
