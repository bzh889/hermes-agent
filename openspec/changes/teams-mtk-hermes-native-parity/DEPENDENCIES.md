# teams-mtk-hermes-native-parity — 依賴鏈總覽

> 從 design.md + tasks.md 抽出的所有任務，按依賴關係排序。
> `→` = 必須先完成前者才能做後者；`↘` = 並行可能但建議順序。

---

## 完整依賴圖（ASCII）

```
§1 低風險修補（大部分已完成）
  ╰→ 1.5 G11 Setup Wizard ──────────────────────────────→ REV-3（SDK版更新）

§4 Graph API 擴展（大部分已完成）
  ╰→ 4.0 graph_token() ✅ ──→ 4A/4B/4C/4D/4E/4F/4G
      ├── 4A G-MEDIA-1~4 ✅
      ├── 4B G13-A.1~A.4 ✅
      │   ╰→ G13-B.2 ✅（people.py fallback 已整合）
      │   ╰→ G13-B.3 🔴 blocked（Chat.Create scope 未授權）
      ├── 4C~4G ✅（m365 skill 已現成 + PLATFORM_HINTS 已更新）

§6 Bug 修復（全部已完成）
  BUG-1~6 ✅

─────────────────────────────────────────────────────────────
以下是未完成任務的依賴鏈
─────────────────────────────────────────────────────────────

§11 CLI 反向補強（先修 SDK bug，再整入 gateway）

  C-1 ✅ HTML 剝離修復 ─────────────────→ REV-1 自動關閉
    │
    ├→ C-3 ✅ 全量拉取預設 ─────────────→ REV-2 ✅ cold-start 種子正確
    │
    ├→ C-4 ✅ 附件下載 auth
    │
    ╰→ C-2 🟡 echo guard 加強
         │
         ╰→ C-5 🟡 short-msg gating
         ╰→ C-6 🟡 group whitelist
         ╰→ C-7 🟡 VIP 偵測路由

§7 SDK 整入 gateway（依賴 §11 C-1~C-4 先完成）

  SDK-0 ✅ 抽共用 package
    │
    ├→ SDK-1 ✅ auth adapter ──→ SDK-2 ✅ 驗證 import ──→ SDK-3 🔴 回歸（E2E 待全量跑）
    │
    ╰──→ S1 ✅ 歷史訊息翻頁
    │      S1-1 ✅ PKB 快取 + API 增量
    │      S1-2 ✅ poll loop 全量
    │      S1-3 ✅ 日期範圍查詢
    │      S1-4 ✅ 回歸
    │      S1-5 🟡 PKB 即時落地 hook
    │
    ╰──→ S2 ✅ 訊息搜尋
    │      S2-1 ✅ search_messages
    │      S2-2 ✅ PLATFORM_HINTS 更新
    │      S2-3 ✅ 測試
    │      S2-4 🟡 跨 conv 全域搜尋
    │
    ╰──→ S3 ✅ 使用者查詢
    │      S3-1 ✅ _search_users
    │      S3-2 ✅ _get_schedule
    │      S3-3 ✅ _find_common_availability
    │      S3-4 ✅ PLATFORM_HINTS 更新
    │      S3-5 ✅ 測試
    │
    ╰──→ S4 🟡 Activity feed
    │      S4-1 🟡 _get_activity
    │      S4-2 🟡 poll loop 擴充（依賴 WS-0 或單獨）
    │      S4-3 🟡 PLATFORM_HINTS + 測試
    │
    ╰──→ S5 🟡 通話記錄
    │      S5-1 🟡 _get_call_logs
    │      S5-2 🟡 PLATFORM_HINTS + 測試
    │
    ╰──→ S7 🟡 Reactions
    │      S7-1 🟡 send/remove_reaction
    │      S7-2 🟡 VALID_REACTIONS 驗證
    │      S7-3 🟡 PLATFORM_HINTS + 測試
    │
    ╰──→ S9 🟡 訊息刪除
    │      S9-1 🟡 delete_message
    │      S9-2 🟡 只允許刪自己
    │      S9-3 🟡 PLATFORM_HINTS + 測試
    │
    ╰──→ S10 🟡 訊息轉發
    │      S10-1 🟡 forward_message
    │      S10-2 🟡 只允許轉到白名單
    │      S10-3 🟡 PLATFORM_HINTS + 測試
    │
    ╰──→ REPLACE-1~7 ✅ 漸進替換 gateway 自行實作
           REPLACE-1 ✅ fetch_messages → SDK
           REPLACE-2 ✅ send → SDK
           REPLACE-3 ✅ edit_message → SDK
           REPLACE-4 ✅ send_image_file → SDK（依賴 C-4 附件 auth）
           REPLACE-5 ✅ send_document → SDK
           REPLACE-6 ✅ list_conversations → SDK
           REPLACE-7 ✅ 評估：SDK-fallback 保留 raw HTTP 降級路徑

§9 WS + Poll 雙通道

  WS-0 ✅ MTK 內網 Trouter 驗證
    │
    ╰→ WS-1 ✅ _TrouterListener async class
    ╰→ WS-2 ✅ 自動重連（5次 + exponential backoff）
    ╰→ WS-3 ✅ heartbeat timeout 偵測
    ╰→ WS-4 ✅ WS 事件 → 觸發 fetch + process ──→ REV-4 ✅（VIP flush WS 後也觸發）
    ╰→ WS-5 ✅ poll loop 與 WS 並行
    ╰→ WS-6 ✅ 回歸
    │
    ╰──→ Phase 2（需 Phase 1.5 穩定後）：
         WS-7 🟡 poll 頻率自適應
         WS-8 🟡 WS 穩定指標追蹤
         WS-9 🟡 評估進一步放寬 poll

§10 跨 Section 影響 Review 任務

  REV-1 ✅ BUG-2 regression ──→ C-1 完成後自動關閉
  REV-2 ✅ BUG-3 cold-start ──→ poll bounded fetch + 種子正確
  REV-3 🟡 G11 Setup Wizard ──→ SDK-0 完成後更新
  REV-4 ✅ VIP flush WS 後觸發 ──→ WS-4 完成後實作
  REV-5 ✅ Trouter event type 觀察 ──→ WS-1 上線後記錄
  REV-6 🟡 §15 文件 ──→ §7 完成後一併寫

Backlog

  G15 🟡 白名單頻道可見度 ──→ 不阻塞，獨立做
  G13-B.3 🔴 blocked（Chat.Create scope） ──→ 等 IT 授權
  G14-2.1 🔴 blocked（P7 Persona） ──→ 等 P7 完成
  1.5 G11 Setup Wizard ──→ REV-3 覆蓋
  1.7 §15 文件 ──→ REV-6 覆蓋
  1.8 §16 測試 ──→ §7.9 REPLACE 測試覆蓋
```

---

## 建議執行順序（關鍵路徑）

### Phase 0 — 先修 SDK bug（§11 高價值）

| 順序 | 任務 | 依賴 | 產出 |
|---|---|---|---|
| 1 | **C-1** ✅ HTML 剝離修復 | 無 | SDK `<at>`/`<blockquote>`/4層附件正確 ✅ → **REV-1 ✅** |
| 2 | **C-3** ✅ 全量拉取預設 | 無 | SDK `get()` limit=None ✅ → **REV-2 ✅** |
| 3 | **C-4** ✅ 附件下載 auth | 無 | SDK `_download_with_auth()` ✅ |
| 4 | **C-2** 🟡 echo guard | C-1（fingerprint 邏輯） | `poll.py` 4道防線 |

### Phase 1 — SDK 整入 gateway（§7 核心）

| 順序 | 任務 | 依賴 | 產出 |
|---|---|---|---|
| 5 | **SDK-0** ✅ 抽共用 package | Phase 0 完成 | `teams_skype_sdk` package ✅ |
| 6 | **SDK-1** ✅ auth adapter | SDK-0 | `_SDKAuthAdapter` ✅ |
| 7 | **SDK-2** ✅ 驗證 import | SDK-1 | gateway 能用 SDK ✅ |
| 8 | **SDK-3** 🔴 回歸測試（E2E） | SDK-2 | 全量 E2E 8/8 |
| 9 | **S1-1~4** ✅ 歷史翻頁 | SDK-0 | 全量拉取 + PKB 快取 ✅ |
| 10 | **S2-1~3** ✅ 訊息搜尋 | SDK-0 | search_messages ✅ |
| 11 | **S3-1,4,5** ✅ 使用者查詢 | SDK-0 | _search_users ✅ |
| 12 | **REPLACE-1~7** ✅ 漸進替換 | SDK-0 + S1~S3 | gateway 用 SDK ✅ |

### Phase 1.5 — WS + Poll 雙通道（§9）

| 順序 | 任務 | 依賴 | 產出 |
|---|---|---|---|
| 13 | **WS-0** ✅ Trouter 驗證 | 無（但建議 Phase 1 後） | 確認 MTK 內網可達 ✅ |
| 14 | **WS-1~6** ✅ Phase 1.5 | WS-0 通過 | WS 加速 + poll 兜底 ✅ |
| 15 | **REV-4** ✅ VIP flush WS 後觸發 | WS-4 | VIP 更精確 ✅ |
| 16 | **REV-5** ✅ Trouter event 觀察 | WS-1 | 記錄 event type ✅ |

### Phase 2 — 功能擴充（中價值）

| 順序 | 任務 | 依賴 | 產出 |
|---|---|---|---|
| 17 | **S4-1~3** 🟡 Activity | SDK-0 | _get_activity |
| 18 | **S5-1~2** 🟡 通話 | SDK-0 | _get_call_logs |
| 19 | **S7-1~3** 🟡 Reactions | SDK-0 | send/remove_reaction |
| 20 | **S9-1~3** 🟡 訊息刪除 | SDK-0 | delete_message |
| 21 | **S10-1~3** 🟡 訊息轉發 | SDK-0 | forward_message |
| 22 | **C-5~7** 🟡 poll.py 加強 | C-2 | short-msg / whitelist / VIP |
| 23 | **S1-5** 🟡 PKB 即時落地 | S1-1 | 全量寫 PKB |
| 24 | **S2-4** 🟡 跨 conv 搜尋 | S2-1 | 全域搜尋 |
| 25 | **S3-2~3** 🟡 行事曆 | S3-1 | schedule + availability |
| 26 | **WS-7~9** 🟡 poll 自適應 | WS-6 穩定 | poll 15s~30s |

### Phase 3 — 收尾（低優先）

| 順序 | 任務 | 依賴 | 產出 |
|---|---|---|---|
| 27 | **REV-2** ✅ cold-start 重測 | C-3 + S1-1 | poll bounded fetch limit=30 ✅ |
| 28 | **REV-3** 🟡 Setup Wizard | SDK-0 | 引導 SDK 安裝 |
| 29 | **REV-6** 🟡 §15 文件 | Phase 1+2 | 完整文件 |
| 30 | **G15** 🟡 白名單可見度 | 獨立 | chat-native 查詢 |

### Blocked（等外部）

| 任務 | 阻塞原因 |
|---|---|
| **G13-B.3** 🔴 | Chat.Create scope 未授權（需 IT 申請） |
| **G14-2.1** 🔴 | P7 Persona 完成 |

---

## 任務統計

| 狀態 | 數量 |
|---|---|
| ✅ 已完成 | 59 |
| 🔴 待做（高優先） | 3 |
| 🟡 待做（中優先） | 21 |
| 🔴 blocked | 2 |

## 關鍵路徑

```
C-1 ✅ → C-3 ✅ → SDK-0 ✅ → SDK-1~2 ✅ → S1~S3 ✅ → REPLACE-1~7 ✅
                         → WS-0 ✅ → WS-1~6 ✅
```

Phase 0 + 1 + 1.5 關鍵路徑已完成。下一步 = Phase 2（功能擴充）或 Phase 3 收尾。
