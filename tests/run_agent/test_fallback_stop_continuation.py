"""Regression tests for fallback responses that falsely report a clean stop."""

from types import SimpleNamespace

from run_agent import AIAgent


def _agent(*, fallback_activated: bool) -> AIAgent:
    agent = object.__new__(AIAgent)
    agent._fallback_activated = fallback_activated
    agent.api_mode = "chat_completions"
    agent.model = "mtk/deepseek-v4-flash"
    agent.provider = "aide"
    agent._base_url_lower = "https://mlop-azure-gateway.mediatek.inc/v1"
    return agent


def _tool_history() -> list[dict[str, str]]:
    return [{"role": "tool", "content": "search result"}]


def test_fallback_stop_with_unfinished_table_requests_continuation():
    agent = _agent(fallback_activated=True)
    response = SimpleNamespace(
        content="The completed report starts here:\n|#",
        tool_calls=None,
    )

    assert agent._should_treat_stop_as_truncated("stop", response, _tool_history()) is True


def test_fallback_stop_with_natural_ending_is_final():
    agent = _agent(fallback_activated=True)
    response = SimpleNamespace(
        content="The completed report is ready.",
        tool_calls=None,
    )

    assert agent._should_treat_stop_as_truncated("stop", response, _tool_history()) is False


def test_primary_stop_with_unfinished_text_keeps_normal_stop_semantics():
    agent = _agent(fallback_activated=False)
    response = SimpleNamespace(
        content="The completed report starts here:\n|#",
        tool_calls=None,
    )

    assert agent._should_treat_stop_as_truncated("stop", response, _tool_history()) is False
