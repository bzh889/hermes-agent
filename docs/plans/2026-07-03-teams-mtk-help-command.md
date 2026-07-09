# Teams MTK `/help` 指令實作計劃

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 在 Teams MTK adapter 的 `_process_new_messages` 中攔截 `/help` 指令，直接回傳可用指令清單，不經過 agent loop。

**Architecture:** Teams MTK 是 polling-only adapter（無 webhook），訊息由 `_process_new_messages` 解析後交給 `handle_message`。目前所有 `/` 開頭的指令都走完整 agent pipeline（base → gateway run → slash_commands），但 `/help` 是純查詢、不需要模型推理，應在 adapter 層直接攔截並回覆，減少延遲與 token 消耗。

**Tech Stack:** Python 3.12, asyncio, pytest

---

### Task 1: 在 TeamsMTKAdapter 新增 `_handle_help_command` 方法

**Objective:** 新增一個方法，產生 Teams MTK 專屬的 `/help` 回覆文字。

**Files:**
- Modify: `gateway/platforms/teams_mtk.py` (class `TeamsMTKAdapter`, approximately line 930)

**Step 1: Write the method**

在 `_process_new_messages` 方法之前（約 line 810），加入：

```python
async def _handle_help_command(self, chat_id: str) -> None:
    """Reply with available slash commands (no agent round-trip)."""
    from hermes_cli.commands import gateway_help_lines
    from agent.skill_commands import get_skill_commands

    lines = ["📋 **Hermes 可用指令：**", ""]
    for line in gateway_help_lines():
        lines.append(line)

    try:
        skill_cmds = get_skill_commands()
        if skill_cmds:
            lines.append("")
            lines.append(f"🧩 **技能指令（{len(skill_cmds)} 個）：**")
            for cmd in sorted(skill_cmds):
                desc = skill_cmds[cmd].get("description", "").strip() or "（無說明）"
                lines.append(f"`{cmd}` — {desc}")
    except Exception:
        pass

    lines.append("")
    lines.append("💡 輸入 `/commands` 查看完整分頁列表")

    await self.send(chat_id, "\n".join(lines))
```

**Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('gateway/platforms/teams_mtk.py').read()); print('OK')"`  
Expected: `OK`

**Step 3: Commit**

```bash
git add gateway/platforms/teams_mtk.py
git commit -m "feat(teams_mtk): add _handle_help_command method"
```

---

### Task 2: 在 `_process_new_messages` 中攔截 `/help`

**Objective:** 在訊息解析階段偵測 `/help` 並直接呼叫 `_handle_help_command`，跳過 `handle_message` pipeline。

**Files:**
- Modify: `gateway/platforms/teams_mtk.py` (`_process_new_messages`, approximately line 930)

**Step 1: Add interception logic**

在 `_process_new_messages` 中，於 mention-gating 之後（約 line 930 `text = re.sub(...).strip()` 之後）、model picker 攔截之前（約 line 933 之前），插入：

```python
            # ---- /help fast-path: reply without agent round-trip ----
            if text.lower().strip() in ("/help", "/h"):
                await self._handle_help_command(self._conv_id)
                self._last_message_id = msg_id
                continue
```

**Rationale:**
- 攔截位置在 mention 剝離之後 → 群組中 `@hermes /help` 也能正確觸發
- 攔截位置在 model picker 之前 → `/help` 不會被 picker 誤攔
- 使用 `text.lower().strip()` → `/Help`、`/HELP` 也能觸發
- `/h` 是 `help` 的 alias（定義在 `CommandDef(aliases=("h",))`），一併支援

**Step 2: Verify parsing still works**

Run: `python -c "import ast; ast.parse(open('gateway/platforms/teams_mtk.py').read()); print('OK')"`  
Expected: `OK`

**Step 3: Commit**

```bash
git add gateway/platforms/teams_mtk.py
git commit -m "feat(teams_mtk): intercept /help in _process_new_messages"
```

---

### Task 3: 撰寫單元測試 — `_handle_help_command` 產生正確內容

**Objective:** 驗證 `_handle_help_command` 產生的回覆包含 gateway 指令與技能指令。

**Files:**
- Create: `tests/gateway/platforms/test_teams_mtk_help.py`

**Step 1: Write the test**

```python
"""Tests for TeamsMTK /help fast-path interception."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestHelpCommandContent:
    """Test _handle_help_command produces expected output."""

    @pytest.fixture
    def adapter(self):
        with patch("gateway.platforms.teams_mtk.check_teams_mtk_requirements", return_value=True), \
             patch.dict("os.environ", {"MTK_TEAMS_CONVERSATION_ID": "19:abc@thread.v2"}):
            from gateway.platforms.teams_mtk import TeamsMTKAdapter
            from gateway.config import PlatformConfig
            a = TeamsMTKAdapter(PlatformConfig())
        a._connected = True
        a.send = AsyncMock()
        return a

    def test_help_includes_gateway_commands(self, adapter):
        """_handle_help_command output contains at least one known gateway command."""
        asyncio.get_event_loop().run_until_complete(
            adapter._handle_help_command("19:abc@thread.v2")
        )
        adapter.send.assert_called_once()
        reply = adapter.send.call_args[0][1]
        # /new and /help should always appear in gateway help lines
        assert "/new" in reply or "/help" in reply

    def test_help_includes_skill_header_when_skills_exist(self, adapter):
        """When skill commands exist, _handle_help_command includes a skill section."""
        with patch("agent.skill_commands.get_skill_commands", return_value={
            "/ascii-art": {"description": "ASCII art generator"},
        }):
            asyncio.get_event_loop().run_until_complete(
                adapter._handle_help_command("19:abc@thread.v2")
            )
        reply = adapter.send.call_args[0][1]
        assert "/ascii-art" in reply
        assert "ASCII" in reply

    def test_help_sends_to_correct_chat(self, adapter):
        """_handle_help_command sends to the requested chat_id."""
        asyncio.get_event_loop().run_until_complete(
            adapter._handle_help_command("19:xyz@thread.v2")
        )
        adapter.send.assert_called_once_with("19:xyz@thread.v2", adapter.send.call_args[0][1])
```

**Step 2: Run tests to verify they pass (or skip if dependencies missing)**

Run: `python -m pytest tests/gateway/platforms/test_teams_mtk_help.py -v --co`  
Expected: 3 tests collected

**Step 3: Commit**

```bash
git add tests/gateway/platforms/test_teams_mtk_help.py
git commit -m "test(teams_mtk): add _handle_help_command unit tests"
```

---

### Task 4: 撰寫單元測試 — `/help` 攔截邏輯

**Objective:** 驗證 `_process_new_messages` 正確攔截 `/help` 並跳過 agent pipeline。

**Files:**
- Modify: `tests/gateway/platforms/test_teams_mtk_help.py`

**Step 1: Add interception test class**

在 `test_teams_mtk_help.py` 末尾加入：

```python
class TestHelpInterception:
    """Test that /help is intercepted in _process_new_messages."""

    @pytest.fixture
    def adapter(self):
        with patch("gateway.platforms.teams_mtk.check_teams_mtk_requirements", return_value=True), \
             patch.dict("os.environ", {"MTK_TEAMS_CONVERSATION_ID": "19:abc@thread.v2"}):
            from gateway.platforms.teams_mtk import TeamsMTKAdapter
            from gateway.config import PlatformConfig
            a = TeamsMTKAdapter(PlatformConfig())
        a._connected = True
        a._message_handler = None  # no handler → no agent pipeline
        a._handle_help_command = AsyncMock()
        a._auth = MagicMock()
        a._auth.skype_token.return_value = "fake-token"
        a._auth.msg_base = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
        return a

    @pytest.mark.parametrize("text", ["/help", "/Help", "/HELP", "/h", "  /help  "])
    def test_help_intercepted(self, adapter, text):
        """/help (any casing/spacing) triggers _handle_help_command."""
        msg = {
            "id": "123",
            "messagetype": "RichText/Html",
            "content": f"<p>{text}</p>",
            "imdisplayname": "TestUser",
            "from": "8:orgid:test-oid",
            "properties": {},
        }
        asyncio.get_event_loop().run_until_complete(
            adapter._process_new_messages([msg])
        )
        adapter._handle_help_command.assert_called_once_with("19:abc@thread.v2")

    @pytest.mark.parametrize("text", ["/helicopter", "/helping", "help me", "something /help"])
    def test_non_help_not_intercepted(self, adapter, text):
        """Strings that are not exact /help pass through normally."""
        msg = {
            "id": "124",
            "messagetype": "RichText/Html",
            "content": f"<p>{text}</p>",
            "imdisplayname": "TestUser",
            "from": "8:orgid:test-oid",
            "properties": {},
        }
        asyncio.get_event_loop().run_until_complete(
            adapter._process_new_messages([msg])
        )
        adapter._handle_help_command.assert_not_called()
```

**Step 2: Run tests**

Run: `python -m pytest tests/gateway/platforms/test_teams_mtk_help.py -v`  
Expected: All tests pass (7 total: 3 content + 4 interception)

**Step 3: Commit**

```bash
git add tests/gateway/platforms/test_teams_mtk_help.py
git commit -m "test(teams_mtk): add /help interception tests"
```

---

### Task 5: 群組 mention + `/help` 合併測試

**Objective:** 驗證群組中 `@hermes /help` 也能正確觸發，mention 被剝離後 `/help` 被攔截。

**Files:**
- Modify: `tests/gateway/platforms/test_teams_mtk_help.py`

**Step 1: Add mention-aware test**

```python
class TestHelpWithMention:
    """Test /help works with @hermes mention in groups."""

    @pytest.fixture
    def group_adapter(self):
        with patch("gateway.platforms.teams_mtk.check_teams_mtk_requirements", return_value=True), \
             patch.dict("os.environ", {
                 "MTK_TEAMS_CONVERSATION_ID": "19:abc@thread.v2",
                 "TEAMS_MTK_REQUIRE_MENTION": "true",
             }):
            from gateway.platforms.teams_mtk import TeamsMTKAdapter
            from gateway.config import PlatformConfig
            a = TeamsMTKAdapter(PlatformConfig())
        a._connected = True
        a._handle_help_command = AsyncMock()
        a._message_handler = None
        return a

    def test_mention_help_intercepted(self, group_adapter):
        """'@hermes /help' in a group triggers help after mention strip."""
        msg = {
            "id": "200",
            "messagetype": "RichText/Html",
            "content": "<p>@hermes /help</p>",
            "imdisplayname": "GroupUser",
            "from": "8:orgid:user-oid",
            "properties": {},
        }
        asyncio.get_event_loop().run_until_complete(
            group_adapter._process_new_messages([msg])
        )
        group_adapter._handle_help_command.assert_called_once_with("19:abc@thread.v2")

    def test_help_without_mention_ignored_in_group(self, group_adapter):
        """/help without @hermes in a group (require_mention=true) is ignored."""
        msg = {
            "id": "201",
            "messagetype": "RichText/Html",
            "content": "<p>/help</p>",
            "imdisplayname": "GroupUser",
            "from": "8:orgid:user-oid",
            "properties": {},
        }
        asyncio.get_event_loop().run_until_complete(
            group_adapter._process_new_messages([msg])
        )
        group_adapter._handle_help_command.assert_not_called()
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/gateway/platforms/test_teams_mtk_help.py -v`  
Expected: All tests pass (10 total)

**Step 3: Commit**

```bash
git add tests/gateway/platforms/test_teams_mtk_help.py
git commit -m "test(teams_mtk): add /help mention-aware group tests"
```

---

### Task 6: 端到端驗證 — 透過 Teams skill API 發送 `/help`

**Objective:** 在真實 Teams 1-1 對話中發送 `/help`，確認收到指令清單回覆。

**Files:** None (uses live Teams API)

**Step 1: 確認 gateway 正在運行**

Run: `hermes gateway` (background, or verify via `hermes status`)  
Expected: `TeamsMTK: connected`

**Step 2: 透過 Teams 發送 `/help`**

在已連線的 Teams 1-1 對話中輸入 `/help`

**Step 3: 驗證回覆**

Expected behavior:
- 回覆幾乎即時（<2 秒，因為不經過 agent loop）
- 回覆包含 `📋 **Hermes 可用指令：**` 標題
- 回覆列出 `/help`、`/new`、`/stop`、`/status` 等指令
- 如有技能指令，顯示 `🧩 **技能指令**` 區塊

**Step 4: 驗證 `/h` alias 同樣觸發**

在 Teams 對話中輸入 `/h`  
Expected: 與 `/help` 相同的回覆

**Step 5: 驗證群組中的 `@hermes /help`**

在群組對話中輸入 `@hermes /help`  
Expected: 正確觸發 help 回覆（mention 被剝離後觸發 fast-path）

---

## 任務總覽

| Task | 檔案 | 重點 |
|------|------|------|
| 1 | `gateway/platforms/teams_mtk.py` | 新增 `_handle_help_command` 方法 |
| 2 | `gateway/platforms/teams_mtk.py` | `_process_new_messages` 中攔截 `/help` |
| 3 | `tests/.../test_teams_mtk_help.py` | 內容測試（gateway + skill 指令） |
| 4 | `tests/.../test_teams_mtk_help.py` | 攔截測試（大小寫 / alias / 非精確匹配） |
| 5 | `tests/.../test_teams_mtk_help.py` | 群組 mention + `/help` 測試 |
| 6 | N/A (live) | Teams 1-1 真實 E2E 驗證 |
