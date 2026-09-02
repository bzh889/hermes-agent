"""gpt-5.6 reasoning_effort limits on OpenAI-compatible /v1/chat/completions.

Azure-backed OpenAI-compatible gateways (MTK AIDE) reject the top-level
``reasoning_effort`` field for the gpt-5.6 family on chat completions in two
distinct ways, both verified live against
``mlop-azure-gateway.mediatek.inc/v1``:

  1. with ``tools`` in the request, ANY effort level other than ``none``:
     "Function tools with reasoning_effort are not supported for
     gpt-5.6-luna in /v1/chat/completions. To use function tools, use
     /v1/responses or set reasoning_effort to 'none'."
  2. with or without tools, the level ``max``:
     "Unsupported value: 'reasoning_effort' does not support 'max' with this
     model. Supported values are: 'none', 'low', 'medium', 'high', and
     'xhigh'."

Both are non-retryable 400s, so an agent whose configured
``agent.reasoning_effort`` is ``max``/``ultra`` cannot make a single tool-using
call. Older families on the same endpoint (gpt-5.5, gpt-5.4, gpt-5.2) and
non-OpenAI models (glm, qwen) accept tools + ``max`` fine, so the clamp must
stay scoped to gpt-5.6.

Dropping the field keeps chat completions *working*, but it cannot deliver
reasoning together with tools — the endpoint has no level that allows both.
The strongest effort a tool-using gpt-5.6 request can actually get is on the
Responses API, which accepts ``tools`` + ``effort: max`` (verified live on the
same gateway at ``/openai/responses``, where ``max`` measurably spends more
reasoning tokens than ``xhigh``). Routing a gpt-5.6 provider there is a config
choice — ``transport: codex_responses`` — and the clamp below is what keeps the
chat-completions route usable for everything that stays on it.
"""

from agent.transports.chat_completions import ChatCompletionsTransport

_AIDE_BASE_URL = "https://mlop-azure-gateway.mediatek.inc/v1"
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ping",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def _build(model, *, tools, effort):
    from providers import get_provider_profile

    return ChatCompletionsTransport().build_kwargs(
        model,
        [{"role": "user", "content": "hi"}],
        _TOOLS if tools else None,
        provider_profile=get_provider_profile("custom"),
        reasoning_config={"enabled": True, "effort": effort},
        supports_reasoning=True,
        base_url=_AIDE_BASE_URL,
    )


def test_tools_drop_reasoning_effort_for_gpt56():
    """Tool-using gpt-5.6 requests must not carry reasoning_effort at all."""
    for effort in ("max", "ultra", "xhigh", "high", "medium", "low"):
        kwargs = _build("azure/gpt-5.6-luna", tools=True, effort=effort)
        assert "reasoning_effort" not in kwargs, (
            f"effort={effort!r} leaked reasoning_effort with tools present — "
            "AIDE rejects this with a non-retryable 400"
        )


def test_tools_keep_explicit_none_for_gpt56():
    """``none`` is explicitly allowed alongside tools — keep it."""
    kwargs = _build("azure/gpt-5.6-luna", tools=True, effort="none")
    assert kwargs.get("reasoning_effort") == "none"


def test_toolless_gpt56_clamps_max_to_xhigh():
    """Without tools gpt-5.6 reasons, but ``max`` is not a valid level."""
    for effort in ("max", "ultra"):
        kwargs = _build("azure/gpt-5.6-luna", tools=False, effort=effort)
        assert kwargs.get("reasoning_effort") == "xhigh", (
            f"effort={effort!r} must clamp to xhigh, the highest level the "
            "endpoint accepts for gpt-5.6"
        )


def test_toolless_gpt56_keeps_supported_levels():
    for effort in ("xhigh", "high", "medium", "low", "none"):
        kwargs = _build("azure/gpt-5.6-luna", tools=False, effort=effort)
        assert kwargs.get("reasoning_effort") == effort


def test_whole_azure_gpt56_family_is_covered():
    """All three gpt-5.6 deployments reject tools + effort (verified live)."""
    for model in (
        "azure/gpt-5.6-luna",
        "azure/gpt-5.6-sol",
        "azure/gpt-5.6-terra",
    ):
        assert "reasoning_effort" not in _build(model, tools=True, effort="max")


def test_unprefixed_gpt56_keeps_max():
    """The clamp is scoped to the ``azure/`` deployment prefix.

    OpenAI's own gpt-5.6 route accepts ``max`` (that is why ``ultra`` maps to
    ``max`` rather than being dropped), so an unprefixed model name must not
    inherit the Azure gateway's narrower contract.
    """
    assert _build("gpt-5.6-luna", tools=True, effort="max")["reasoning_effort"] == "max"
    assert _build("gpt-5.6-luna", tools=True, effort="ultra")["reasoning_effort"] == "max"


def test_other_models_keep_tools_plus_max():
    """Non-gpt-5.6 models on the same endpoint accept tools + max (verified live)."""
    for model in (
        "azure/gpt-5.5",
        "azure/gpt-5.4",
        "azure/gpt-5.2",
        "mtk/wfm-pro-glm5-2-744b",
        "mtk/qwen3-5-397b-a17b",
    ):
        kwargs = _build(model, tools=True, effort="max")
        assert kwargs.get("reasoning_effort") == "max", (
            f"{model} must keep its configured effort — the gpt-5.6 clamp "
            "must not widen to models that accept max"
        )
