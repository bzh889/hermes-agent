# teams-mtk-streaming-reliability — Tasks

## 1. `send_typing` override (GAP-1)
- [x] 1.1 ✅ `TeamsMTKAdapter.send_typing()` 已實作（teams_mtk.py L670），
      複用 `_TeamsAuth.skype_token()` + `_auth.msg_base`，
      POST `{"messagetype": "Control/Typing", "content": ""}` 到
      `/conversations/{chat_id}/messages` endpoint。
      修正：移除不存在的 `_get_proxies()` 呼叫（與 `send()` 一樣不傳 proxies）。
- [x] 1.2 ✅ E2E 手動驗證通過（2026-07-10）：
      用 teams skill 的 skypetoken 直接 POST Control/Typing 到
      `apac.ng.msg.teams.microsoft.com`：
      - 1-1 對話：**201** `{"OriginalArrivalTime":...}` ✅
      - 群組對話：**201** `{"OriginalArrivalTime":...}` ✅
      不會產生出現在訊息列表的實體紀錄（Control message 不顯示為內容）。
- [x] 1.3 ✅ `_keep_typing` loop 驅動驗證通過（2026-07-10）：
      Gateway log 確認 `19:02:47..19:02:56` 三次
      `TeamsMTK: send_typing OK for conv=19:6e8a676c...`，
      間隔 ~3-4s，符合 `base.py:3767` `_keep_typing()` 每 `KEEP_TYPING_INTERVAL` 
      呼叫 `self.send_typing()` 的機制。無需改 gateway/run.py。
      成功 log 等級已改回 `logger.debug`（生產環境不 noise）。
- [x] 1.4 ✅ 單元測試 3/3 通過（test_teams_mtk_reliability.py::TestSendTyping）：
      - `test_send_typing_posts_control_typing`：驗證 POST payload 格式
        `{"messagetype":"Control/Typing","content":""}` + skypetoken auth header
      - `test_send_typing_non_201_logs_warning`：403 不 raise，只 log warning
      - `test_send_typing_exception_does_not_raise`：ConnectionError 不 raise，
        確保 `_keep_typing` loop 不會因單次失敗中斷

## Backlog（需真實資料才決定，暫不實作）
- [ ] B.1 GAP-2 `prefers_fresh_final_streaming` — 先觀察真實 gateway log 中
      finalize edit 429/失敗頻率，數據顯示需要才動工

## Retracted / Not Doing（原 tasks.md 內容，已確認查無實作依據或與既有機制重複）
- ~~placeholder 文字改善~~（查無此功能）
- ~~finalize edit fail→fallback send~~（憑空編造，且 §4 finalize 序列化已存在）
- ~~progress sender 限速~~（`gateway/run.py:16534` `_PROGRESS_EDIT_INTERVAL` 已存在）
- ~~finalize 競態防護 lock~~（`gateway/run.py:18785` `progress_task.cancel()` 已先於
  `stream_task` 完成，序列化已成立，無競態證據）
