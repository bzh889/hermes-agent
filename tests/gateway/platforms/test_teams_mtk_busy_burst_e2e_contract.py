"""Behavior contract for the live Teams MTK busy-burst E2E."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _branded_bot_html(body: str) -> str:
    return (
        '<div style="border-left:3px solid #6264A7;padding-left:10px">'
        '<b>🤖 Hermes</b><br><br>'
        f"<p>{body}</p><br>"
        '<span style="color:#888;font-size:0.85em">'
        "— Hermes · 2026-07-25 12:00</span></div>"
    )


def _load_e2e_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "openspec"
        / "changes"
        / "teams-mtk-hermes-native-parity"
        / "e2e_teams_mtk.py"
    )
    spec = importlib.util.spec_from_file_location("teams_mtk_busy_burst_e2e", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_busy_burst_preconditions_accept_supported_scheduled_runtime(
    monkeypatch,
    tmp_path,
):
    e2e = _load_e2e_module()
    e2e.GROUP_CHAT_ID = "test-group"

    module_path = e2e.__file__
    assert module_path is not None
    repo_root = Path(module_path).resolve().parents[3]
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "gateway.pid").write_text(
        json.dumps(
            {
                "pid": 123,
                "argv": [str(repo_root / "hermes_cli" / "gateway_runtime_entry.py")],
            }
        ),
        encoding="utf-8",
    )

    gateway_env = {
        "PYTHONPATH": str(repo_root),
        "VIRTUAL_ENV": str(Path(e2e.sys.prefix)),
    }
    process = SimpleNamespace(
        cwd=lambda: str(hermes_home),
        exe=lambda: str(tmp_path / "Python312" / "python.exe"),
        environ=lambda: gateway_env,
    )

    import hermes_cli.config
    import hermes_constants
    import psutil

    monkeypatch.setattr(
        hermes_cli.config,
        "load_config",
        lambda: {
            "display": {"busy_input_mode": "interrupt"},
            "gateway": {
                "teams_mtk": {
                    "groups": {"test-group": {"require_mention": False}}
                }
            },
        },
    )
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(psutil, "Process", lambda _pid: process)

    ok, evidence = e2e._busy_burst_preconditions()

    assert ok is True, evidence
    assert "source=gateway_runtime_entry.py" in evidence
    assert "venv=current" in evidence


def test_busy_group_burst_redirect_is_named_and_verifies_one_ack_and_final(
    monkeypatch,
):
    e2e = _load_e2e_module()

    assert (
        e2e.NAMED_TESTS["busy-group-burst-redirect"]
        is e2e.test_busy_group_burst_redirect
    )

    e2e.GROUP_CHAT_ID = "test-group"
    old = {"id": "old", "content": "old conversation message"}
    initial = {
        "id": "graph-initial",
        "content": "initial E2EBURSTABCDEF123456OLD prompt",
    }
    correction_a = {
        "id": "graph-a",
        "content": "correction E2EBURSTABCDEF123456A",
    }
    correction_b = {
        "id": "graph-b",
        "content": "correction E2EBURSTABCDEF123456B",
    }
    ack = {
        "id": "ack",
        "content": "Redirected current run",
        "_raw_content": _branded_bot_html(
            "↪ Redirected current run. I'll adjust using your correction."
        ),
    }
    progress = {
        "id": "progress",
        "content": "Running the requested command",
        "_raw_content": _branded_bot_html("Running the requested command"),
    }
    final = {
        "id": "final",
        "content": "E2EBURSTABCDEF123456A E2EBURSTABCDEF123456B",
        "_raw_content": _branded_bot_html(
            "E2EBURSTABCDEF123456A E2EBURSTABCDEF123456B"
        ),
    }
    current_messages = [
        final,
        ack,
        progress,
        correction_b,
        correction_a,
        initial,
        old,
    ]
    read_count = 0
    sent_contents = []
    sent_ids = iter(["graph-initial", "graph-a", "graph-b"])
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(
        e2e,
        "_busy_burst_preconditions",
        lambda: (True, "gateway pid=123 checkout=current interpreter=venv"),
    )
    monkeypatch.setattr(
        e2e,
        "_busy_burst_group_idle_preflight",
        lambda **_kwargs: (True, "control group idle"),
    )
    monkeypatch.setattr(
        e2e,
        "_wait_for_process_marker",
        lambda *_args, **_kwargs: True,
    )
    def get_messages(*_args, **_kwargs):
        nonlocal read_count
        read_count += 1
        return [old] if read_count == 1 else list(current_messages)

    monkeypatch.setattr(e2e, "get_messages_raw", get_messages)

    def send_message(_chat, content):
        sent_contents.append(content)
        return next(sent_ids)

    monkeypatch.setattr(e2e, "send_chat_message", send_message)
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda _chat, message_id: deleted_graph.append(message_id),
    )
    def delete_msg(_chat, message_id):
        deleted_msg.append(message_id)
        current_messages[:] = [
            message
            for message in current_messages
            if str(message.get("id") or "") != message_id
        ]

    monkeypatch.setattr(e2e, "delete_msg_message", delete_msg)
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_busy_group_burst_redirect(
        "unused.log",
        0,
        tool_start_timeout=0,
        reply_timeout=0,
        poll_interval=0,
        settle_seconds=0,
    )

    assert ok is True, evidence
    assert "one redirect" in evidence.lower()
    assert len(sent_contents) == 3
    assert "E2EBURSTABCDEF123456OLD" in sent_contents[0]
    assert {"E2EBURSTABCDEF123456A", "E2EBURSTABCDEF123456B"} == {
        marker
        for content in sent_contents[1:]
        for marker in (
            "E2EBURSTABCDEF123456A",
            "E2EBURSTABCDEF123456B",
        )
        if marker in content
    }
    assert set(deleted_graph) == {"graph-initial", "graph-a", "graph-b"}
    assert set(deleted_msg) == {
        "ack",
        "final",
        "progress",
        "graph-initial",
        "graph-a",
        "graph-b",
    }
