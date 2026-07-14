"""Cron-session state must be context-local, never process-global."""

import asyncio

import pytest

from gateway.session_context import clear_session_vars, get_session_env, set_session_vars
from tools import approval


def test_live_gateway_context_overrides_stale_process_cron_flag(monkeypatch):
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    tokens = set_session_vars(platform="teams_mtk", cron_session=False)
    try:
        assert get_session_env("HERMES_CRON_SESSION", "") == ""
    finally:
        clear_session_vars(tokens)


@pytest.mark.asyncio
async def test_cron_flag_is_isolated_between_parallel_tasks(monkeypatch):
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)

    async def read_flag(is_cron):
        tokens = set_session_vars(platform="teams_mtk", cron_session=is_cron)
        try:
            await asyncio.sleep(0)
            return get_session_env("HERMES_CRON_SESSION", "")
        finally:
            clear_session_vars(tokens)

    cron_value, live_value = await asyncio.gather(read_flag(True), read_flag(False))
    assert cron_value == "1"
    assert live_value == ""


@pytest.mark.asyncio
async def test_execute_code_guard_uses_each_tasks_cron_context(monkeypatch):
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    monkeypatch.setattr(approval, "_get_approval_mode", lambda: "ask")
    monkeypatch.setattr(approval, "_get_cron_approval_mode", lambda: "deny")

    async def check(is_cron):
        tokens = set_session_vars(platform="", cron_session=is_cron)
        try:
            await asyncio.sleep(0)
            return approval.check_execute_code_guard("print('ok')", "local")
        finally:
            clear_session_vars(tokens)

    cron_result, live_result = await asyncio.gather(check(True), check(False))
    assert cron_result["approved"] is False
    assert "Cron jobs" in cron_result["message"]
    assert live_result["approved"] is True
