"""A named AIDE provider can opt into the Responses API via ``transport``.

MTK AIDE's OpenAI-compatible ``/v1/chat/completions`` route cannot serve
reasoning and function tools at the same time for the gpt-5.6 family: with
``tools`` present every effort level except ``none`` returns a non-retryable
400 (see tests/agent/test_gpt56_chat_completions_reasoning_effort.py). The same
gateway's Responses route accepts ``tools`` together with ``effort: max``, so a
user who wants the strongest reasoning has to be routed there.

That routing is config-only — a ``providers:`` entry with
``transport: codex_responses`` — and these tests pin the two properties that
make it work, because both are easy to break from a distance:

  - the named-provider resolver honours ``transport`` (a stale ``api_mode``
    guard exists for *plain* ``provider: custom`` endpoints and must not
    swallow named providers on a non-OpenAI host)
  - the Responses transport clamps ``ultra`` to ``max``, the highest level the
    endpoint accepts (it rejects ``ultra`` with a 400)

The base URL is the ``/openai`` prefix, not ``/v1``: the Responses route lives
at ``<host>/openai/responses`` and expects the deployment name *without* the
``azure/`` prefix that the chat-completions route requires.
"""

import hermes_cli.runtime_provider as rp
from agent.transports import get_transport

_HOST = "https://mlop-azure-gateway.mediatek.inc"
_RESPONSES_BASE_URL = f"{_HOST}/openai"

_PROVIDER_NAME = "aide-crlogai001-responses"
_CONFIG = {
    "providers": {
        _PROVIDER_NAME: {
            "name": _PROVIDER_NAME,
            "api": _RESPONSES_BASE_URL,
            "key_env": "AIDE_CRLOGAI001_KEY",
            "transport": "codex_responses",
            "default_headers": {"x-user-id": "srv_cr_log_ai001"},
            "models": ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra"],
        }
    }
}


def test_named_provider_transport_selects_responses_api(monkeypatch):
    """``transport: codex_responses`` survives resolution on the AIDE host.

    ``_resolve_plain_custom_api_mode`` drops a configured ``codex_responses``
    when the URL is not a recognised OpenAI/xAI host. That guard is scoped to
    bare ``provider: custom``; a named provider must keep its declared
    transport or the request silently falls back to chat completions, where
    tools + reasoning is impossible.
    """
    monkeypatch.setattr(rp, "load_config", lambda *a, **k: _CONFIG)

    resolved = rp._get_named_custom_provider(_PROVIDER_NAME)

    assert resolved is not None, "named provider must resolve"
    assert resolved["api_mode"] == "codex_responses"
    assert resolved["base_url"] == _RESPONSES_BASE_URL
    assert resolved["default_headers"]["x-user-id"] == "srv_cr_log_ai001"


def test_responses_transport_sends_max_with_tools():
    """The wire payload keeps ``effort: max`` when tools are present.

    This is the whole point of the routing: the chat-completions transport has
    to strip the field here, and the Responses route does not.
    """
    transport = get_transport("codex_responses")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    kwargs = transport.build_kwargs(
        "gpt-5.6-luna",
        [{"role": "user", "content": "hi"}],
        tools,
        reasoning_config={"enabled": True, "effort": "max"},
        base_url=_RESPONSES_BASE_URL,
        base_url_hostname="mlop-azure-gateway.mediatek.inc",
        provider="custom",
    )

    assert kwargs["reasoning"]["effort"] == "max"
    assert kwargs["tools"], "tools must survive alongside max reasoning"
    assert kwargs["model"] == "gpt-5.6-luna", (
        "the Responses route rejects the azure/ prefix that chat completions "
        "requires — 400 'Model not supported'"
    )


def test_responses_transport_clamps_ultra_to_max():
    """``ultra`` is not a level the endpoint knows; ``max`` is its ceiling."""
    transport = get_transport("codex_responses")

    kwargs = transport.build_kwargs(
        "gpt-5.6-luna",
        [{"role": "user", "content": "hi"}],
        None,
        reasoning_config={"enabled": True, "effort": "ultra"},
        base_url=_RESPONSES_BASE_URL,
        base_url_hostname="mlop-azure-gateway.mediatek.inc",
        provider="custom",
    )

    assert kwargs["reasoning"]["effort"] == "max"
