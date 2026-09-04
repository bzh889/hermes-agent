"""Regression tests for providers emitting empty-choice stream chunks."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from agent import chat_completion_helpers as helpers


def test_empty_choices_terminal_chunk_does_not_index_choices(monkeypatch):
    """A usage/metadata chunk with choices=[] must be ignored, not fail the turn."""
    agent = MagicMock()
    agent._interrupt_requested = False
    agent.provider = "aide"
    agent.model = "mtk/deepseek-v4-flash"
    agent.base_url = "https://mlop-azure-gateway.mediatek.inc/v1/"
    agent.api_mode = "chat_completions"
    agent.verbose_logging = False
    agent._consecutive_stale_streams = 0
    agent._create_request_openai_client.return_value.chat.completions.create.return_value = iter([
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="OK", reasoning_content=None, reasoning=None, tool_calls=[]),
                finish_reason=None,
                tool_calls=[],
                )],
            model="mtk/deepseek-v4-flash",
            usage=None,
        ),
        # Real AIDE-compatible terminal usage chunk shape.
        SimpleNamespace(
            choices=[],
            model="mtk/deepseek-v4-flash",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            tool_calls=[],
            ),
    ])
    agent._stream_diag_init.return_value = {}
    agent._touch_activity = MagicMock()
    agent._fire_stream_delta = MagicMock()
    agent._fire_reasoning_delta = MagicMock()
    agent._fire_tool_gen_started = MagicMock()
    agent._stream_callback = None
    agent.stream_delta_callback = None
    agent._record_streamed_assistant_text = MagicMock()
    agent._current_streamed_assistant_text = "OK"
    agent._fire_first_delta = MagicMock()
    agent._compute_non_stream_stale_timeout.return_value = 30.0
    agent._create_request_openai_client.return_value.chat.completions.create.return_value = iter([
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="OK", reasoning_content=None, reasoning=None, tool_calls=[]),
                finish_reason="stop",
                tool_calls=[],
                )],
            model="mtk/deepseek-v4-flash",
            usage=None,
        ),
        SimpleNamespace(choices=[], model="mtk/deepseek-v4-flash", usage=SimpleNamespace(), tool_calls=[]),
    ])
    result = helpers.interruptible_streaming_api_call(
        agent,
        {"model": agent.model, "messages": []},
    )
    assert result.choices[0].message.content == "OK"
    assert result.choices[0].finish_reason == "stop"
