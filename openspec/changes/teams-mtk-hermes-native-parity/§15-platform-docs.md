# §15 — TeamsMTK 平台功能文件

> 對應 design.md §7~§11, §9 所有已完成功能的參考文件。

---

## 平台能力總覽

| 分類 | 功能 | 方法 | SDK / Raw |
|------|------|------|-----------|
| 訊息 | 發送 | `send()` | SDK + Raw fallback |
| 訊息 | 編輯 | `edit_message()` | SDK + Raw |
| 訊息 | 刪除（只刪自己）| `delete_message_safe()` | SDK + Raw |
| 訊息 | 轉發（白名單）| `forward_message()` | SDK + Raw |
| 訊息 | 搜尋（單 conv）| `_search_messages()` | SDK |
| 訊息 | 搜尋（跨 conv）| `search_all_conversations()` | SDK per-conv |
| 訊息 | 歷史翻頁 | `_fetch_messages(limit=N)` | SDK + Raw |
| 反應 | 發送/移除 | `send/remove_reaction()` | SDK Graph + Raw |
| 附件 | 圖片/文件/下載 | `send_image_file/send_document/_download_attachment` | SDK + Raw |
| 活動 | Activity feed | `get_activity(kind)` | SDK |
| 活動 | 通話記錄 | `get_call_logs()` | SDK (via Activity) |
| 用戶 | 搜尋/行事曆 | `_search_users/_get_schedule/_find_common_availability` | SDK + Graph |
| 安全 | Echo guard (4道) | dedup → sent_dedup → fingerprint → HTML fingerprint | 內建 |
| 安全 | Short-msg gating | `≤2 chars + no ?/!/mention → ignore` | 內建 |
| 安全 | Group whitelist | authz_mixin `_teams_mtk_group_is_whitelisted` | config.yaml |
| 安全 | VIP buffer | `_VIPBuffer` (立即/stale flush) | config.yaml |
| 安全 | 只刪自己 | `delete_message_safe()` —驗證 sender | 內建 |
| 安全 | 轉發白名單 | `allowed_targets=[]` 參數 | 內建 |
| WS | 雙通道 + 自適應 | WS 即時 + poll 兜底，WS healthy→15s/30s | 內建 |
| PKB | 即時落地 | `on_message_processed()` hook | per-group config |
| 平台提示 | PLATFORM_HINTS | `get_platform_hints()` | 內建 |
| 白名單 | 可見度查詢 | `list_whitelisted_groups()` | config.yaml |

---

## Echo Guard 四道防線

1. **MessageDeduplicator TTL cache** — `msg_id` 在 TTL 內重複 → skip
2. **Sent dedup** — `_sent_dedup.is_duplicate(msg_id)` → skip（我們剛發的）
3. **HTML fingerprint** — `<div style="border-left:#6264A7"` + `<b>🤖 Hermes</b>` → own
4. **Last-sent ID** — `_last_sent_message_id` 直接比對 → skip

---

## Poll 自適應 (WS-7~9)

| 條件 | Poll Interval |
|------|--------------|
| WS 斷線 | 2s |
| WS healthy 5 ticks | 15s |
| WS healthy 20 ticks | 30s |

指標追蹤：`_ws_stats` = `{healthy_ticks, unhealthy_ticks, ws_reconnects, poll_interval_changes}`

---

## 配置參考

```yaml
gateway:
  teams_mtk:
    require_mention: true          # 全域預設
    groups:                        # per-group 覆蓋
      "19:abc@thread.v2":
        require_mention: false
        short_message_ignore: false  # C-5: 關閉短訊 ignore
        pkb_instant_landing: true    # S1-5: 開啟 PKB 落地
        pkb_landing_dir: "/path/to/pkb/dir"
        label: "我的測試群"
    vip_monitor:                   # C-7 VIP
      enabled: true
      oids: ["user-oid-1", "user-oid-2"]
      notify_targets: ["dm-chat-id"]
      stale_timeout: 60
```
