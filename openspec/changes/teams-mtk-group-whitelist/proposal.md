## Why

TeamsMTK adapter 目前只有一個全域個人白名單（`GATEWAY_ALLOWED_USERS`），沒有「群組白名單」機制。要讓一個 Teams 群組的所有成員直接使用 Hermes 問答（不必 @mention），現在只能靠逐人加 OID 到全域白名單，這會讓那些人在**所有**接到 TeamsMTK 的對話都能用，範圍失控且無法管控功能/關鍵字。需要一個「群組級」授權 + 設定層，讓群組管理跟個人白名單解耦，並支援 per-群組/per-人的功能限制與關鍵字屏蔽。

## What Changes

- 新增 `gateway.teams_mtk.groups` config.yaml 巢狀設定區塊：每個 conv_id 一筆記錄，含 `name`、`require_mention`、`blocked_toolsets`、`blocked_keywords`、`per_user`（per-人再疊加限制）。
- 新增 CLI 指令 `hermes teams-mtk group add/list/set/remove`，用來把群組加入設定並產生預設值（`require_mention: false`），取代手動編輯 `.env`/`config.yaml`。
- `gateway/authz_mixin.py` 新增「群組白名單」路徑：conv_id 存在於 `gateway.teams_mtk.groups` 即視為已授權，群內任何 sender 通過 authz——不再需要把每個成員的 OID 塞進全域 `GATEWAY_ALLOWED_USERS`。
- `gateway/platforms/teams_mtk.py` 的 mention gating 改為查 config（`groups.<id>.require_mention`），取代目前寫死讀 `MTK_TEAMS_NO_MENTION_CONVS` env var CSV 的邏輯。
- `_process_new_messages` 派送前插入雙向過濾：
  - 入站：訊息命中 `blocked_keywords` → 不處理 / 固定話術拒答。
  - 出站：agent 回覆送出前跑同一份 regex，命中則整段拒發或遮罩。
- Agent 建構時依 `blocked_toolsets`（群組 + per_user 疊加）組出 `disabled_toolsets` 參數，餵給既有的 `AIAgent.__init__`（零核心改動，只是設定來源從程式碼改為查表）。

## Capabilities

### New Capabilities
- `teams-mtk-group-policy`：TeamsMTK adapter 的 per-群組授權、mention 豁免、功能/關鍵字限制設定與執行邏輯。

### Modified Capabilities
（無現有 spec 名稱受影響 — 這是 TeamsMTK adapter 的全新能力面，不修改既有 spec 的 requirements。）

## Impact

- **Affected code**:
  - `gateway/authz_mixin.py`（新增群組白名單判斷路徑）
  - `gateway/platforms/teams_mtk.py`（mention gating 改查 config、插入關鍵字/工具過濾 hook）
  - `hermes_cli/config.py`（`DEFAULT_CONFIG` 加 `gateway.teams_mtk.groups: {}`）
  - 新增 `hermes_cli/subcommands/teams_mtk_groups.py`（CLI：group add/list/set/remove）
- **Config**: `~/.hermes/config.yaml` 新增 `gateway.teams_mtk.groups` 區塊；不引入新 `.env` 變數（符合「非機密設定進 config.yaml」政策）。
- **依賴**: 現有的 `AIAgent(disabled_toolsets=...)` 參數、既有 `teams` skill 用於查 conv_id（無需新工具）。
- **相容性**: 沒被列入 `groups` 的 conv_id 維持現行行為（不在白名單，被 authz 擋掉）——預設拒絕、明確加入才開放，不改變既有安全姿態。
- **重啟需求**: 改 gateway 程式碼需重啟 gateway 生效（既有慣例，非本次新增限制）。
