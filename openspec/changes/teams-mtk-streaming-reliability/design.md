# teams-mtk-streaming-reliability

TeamsMTK streaming/typing 可靠性：leverage Hermes 既有 `base.py` streaming hooks
+ Skype/Teams 原生 `Control/Typing` protocol，取代對話式 placeholder 訊息。

## When to Use

- Teams 上 agent 處理中缺乏視覺回饋（沒有 typing indicator）
- edit 429 導致 streaming 中斷，使用者看不到進度
- teams_mtk 需要 override Hermes base.py 已有的 streaming hooks，而非自建機制

## Evidence（每項都附來源，禁止臆測）

1. **`gateway/platforms/base.py:3150`** — `send_typing(chat_id, metadata=None)`：預設 no-op，
   子類別 override 即可提供 platform typing indicator。
2. **`gateway/platforms/base.py:3770` `_keep_typing()`** — 已有背景 loop 每 2s 呼叫
   `send_typing`，含 timeout 保護、`_typing_paused` 暫停機制（配合審批流程）。
   **teams_mtk 完全沒有 override `send_typing`，所以這個既有 loop 對 Teams 目前是空轉。**
3. **`plugins/platforms/teams/adapter.py:1185`**（同 repo 內、官方 SDK 版 Teams adapter）
   已實作 `send_typing`：
   ```python
   async def send_typing(self, chat_id, metadata=None):
       await self._app.send(chat_id, TypingActivityInput())
   ```
   這是用 Teams Bot Framework SDK 的方式；teams_mtk 走的是 skypetoken 協議，做法不同但概念可抄。
4. **Skype/Teams 底層協議**（`skpy` library 原始碼，`skpy/event.py`：
   `msgType in ("Control/Typing", "Control/ClearTyping")`）——證實 skypetoken 協議本身
   原生支援 typing indicator，透過 POST 同一個 `/conversations/{id}/messages` endpoint，
   `messagetype: "Control/Typing"`，不需要建立/編輯真實訊息。
   **teams_mtk.py 的 `send()`/`edit_message()` 已經在用同一個 endpoint + skypetoken auth**
   （見 `teams_mtk.py:495` `url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"`），
   加 `send_typing` 只需複用現有 `_TeamsAuth` + session，換 payload 即可。
5. **`gateway/platforms/base.py:2456` `supports_draft_streaming()`** — 預設 False，
   teams_mtk 未 override。Skype/Teams 協議本身沒有 Telegram 式 `sendMessageDraft` 動畫
   API，所以維持預設是正確的，**不是 gap**。
6. **`gateway/platforms/base.py:2475` `prefers_fresh_final_streaming()`** — 預設 False
   （finalize 用 edit-in-place）。teams_mtk 未 override，也未驗證是否需要 override。
   **是否要 override，要先觀察 finalize edit 失敗率，不能未驗證就假設要改。**
7. **`gateway/run.py:16522` progress-message 機制** — 已對所有支援 `edit_message` 的
   adapter（包含 teams_mtk）通用套用，含 throttle（`_PROGRESS_EDIT_INTERVAL = 1.5s`，
   `gateway/run.py:16534`）、flood-control 偵測（`gateway/run.py:16744`）、overflow 分段
   （`_roll_progress_overflow_if_needed`）。**這條路徑 teams_mtk 已經在用，不需要另建
   progress sender 限速機制**——`_maybe_throttle`（§5.6/§7 已完成）是 teams_mtk 自己
   send/edit 的節流，跟 gateway 通用 progress 機制是兩層互補，不衝突。
8. **`gateway/run.py:18785` finally block** — `progress_task.cancel()` 先執行，
   接著才 `await stream_task`（timeout=5.0）。**這已經是序列化保護**：progress sender
   被取消在先，stream consumer 的 final edit 在後，兩者不會同時對同一 message_id 呼叫
   edit。**沒有觀察到競態證據，§4 的「finalize 競態防護」原始假設不成立。**

## Corrected Problem Statement

teams_mtk.py 沒有 leverage 上述已有的 Hermes 機制：

### GAP-1: 沒有 `send_typing` override
- **影響**：`_keep_typing()` 背景 loop 對 Teams 空轉，使用者在 agent 處理期間沒有
  任何「正在輸入」視覺回饋
- **證據**：`teams_mtk.py` grep `send_typing`/`_keep_typing` 零命中
- **修法**：teams_mtk override `send_typing`，複用 `_TeamsAuth` + `requests.Session`，
  POST `{"messagetype": "Control/Typing", "content": ""}` 到現有 messages endpoint

### GAP-2: `prefers_fresh_final_streaming` 未驗證
- **影響**：未知——目前 finalize 走 edit-in-place（預設行為），沒有觀察到失敗證據
- **修法**：先蒐集真實 finalize edit 失敗率（log 觀察），有數據才決定是否 override

## Retracted (原 tasks.md 的錯誤假設)

- ~~BUG-A placeholder 殘留~~ — 查無此功能，是我編造的
- ~~Option C 事件驅動 streaming~~ — gateway 已有 progress-message 機制在跑，這是
  重新發明現有輪子，不需要
- ~~§3 progress sender 限速~~ — `gateway/run.py:16534` 已有 `_PROGRESS_EDIT_INTERVAL`，
  重複建置
- ~~§4 finalize 競態防護~~ — `gateway/run.py:18785` 已序列化 cancel，沒有競態證據

## Scope Decision

Phase1（本次範圍）: GAP-1 only — `send_typing` override
Backlog（待真實資料才決定）: GAP-2 — 若觀察到 finalize edit 失敗率高，再評估
  `prefers_fresh_final_streaming` override
