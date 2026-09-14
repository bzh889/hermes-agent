"""Regression coverage for primary 429 recovery before fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from run_agent import AIAgent


class RateLimitError(Exception):
    status_code = 429

    def __init__(self, retry_after: str | None = None):
        super().__init__("Your requests to gpt-5.6-luna have exceeded rate limit.")
        headers = {"Retry-After": retry_after} if retry_after else {}
        self.response = SimpleNamespace(headers=headers)
        self.body = {"error": {"message": str(self)}}


def _response(content: str):
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model="gpt-5.6-luna", usage=None)


def _agent() -> AIAgent:
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI", return_value=MagicMock()),
        patch("agent.strategy_runtime.attach_strategy_execute_tool"),
    ):
        agent = AIAgent(
            api_key="primary-key",
            base_url="https://mlop-azure-gateway.mediatek.inc/openai",
            provider="custom",
            model="gpt-5.6-luna",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            fallback_model={
                "provider": "aide",
                "model": "mtk/deepseek-v4-flash",
                "base_url": "https://mlop-azure-gateway.mediatek.inc/v1",
            },
        )
    agent.client = MagicMock()
    agent._api_max_retries = 2
    return agent


def test_primary_429_retries_before_activating_fallback():
    """A transient primary 429 must get its bounded retry opportunity first."""
    agent = _agent()
    requests = []

    def api_call(_kwargs):
        requests.append((agent.provider, agent.model))
        if len(requests) == 1:
            raise RateLimitError(retry_after="0")
        return _response("Primary recovered.")

    with (
        patch.object(agent, "_interruptible_api_call", side_effect=api_call),
        patch.object(agent, "_recover_with_credential_pool", return_value=(False, False)),
        # Returning True makes the former eager-429 branch observable without
        # coupling this regression to fallback-client construction.
        patch.object(agent, "_try_activate_fallback", return_value=True) as fallback,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
        patch("agent.conversation_loop.time.sleep"),
    ):
        result = agent.run_conversation("hello")

    assert result["completed"] is True
    assert result["final_response"] == "Primary recovered."
    assert requests == [
        ("custom", "gpt-5.6-luna"),
        ("custom", "gpt-5.6-luna"),
    ]
    fallback.assert_not_called()
