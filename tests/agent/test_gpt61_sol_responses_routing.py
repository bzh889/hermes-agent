
import pytest
from run_agent import AIAgent


def test_gpt61_sol_requires_responses_api():
    """Live-verified 2026-10-11 (AIDE IO gateway): gpt-6.1-sol rejects tools on
    /v1/chat/completions under EVERY reasoning_effort, so the model must be
    routed to the Responses API."""
    assert AIAgent._model_requires_responses_api("azure/gpt-6.1-sol") is True
    assert AIAgent._model_requires_responses_api("gpt-6.1-sol") is True


def test_gpt6_luna_sol_stay_on_chat_completions():
    """gpt-6-luna / gpt-6-sol keep working on chat_completions via the
    reasoning_effort:"none" workaround and must NOT be force-upgraded."""
    assert AIAgent._model_requires_responses_api("azure/gpt-6-luna") is False
    assert AIAgent._model_requires_responses_api("azure/gpt-6-sol") is False


def test_custom_provider_upgrade_gpt61_but_not_generic_custom():
    assert AIAgent._provider_model_requires_responses_api("azure/gpt-6.1-sol", provider="custom") is True
    assert AIAgent._provider_model_requires_responses_api("azure/gpt-6-luna", provider="custom") is False
    # databricks/* requires the Responses API on this gateway (chat/completions
    # 400s with "Invalid model type" — live 2026-10-08), mirroring gpt-6.1-sol:
    # they are now listed under the plain AIDE providers and must auto-upgrade.
    assert AIAgent._provider_model_requires_responses_api("databricks/glm-5-3", provider="custom") is True


def test_codex_transport_strips_azure_prefix_on_aide_for_gpt_only():
    from agent.transports.codex import ResponsesApiTransport

    t = ResponsesApiTransport.__new__(ResponsesApiTransport)
    kw = t.build_kwargs(
        "azure/gpt-6.1-sol",
        [{"role": "user", "content": "hi"}],
        None,
        base_url="https://mlop-azure-gateway-io.mediatek.inc/v1",
    )
    assert kw["model"] == "gpt-6.1-sol"


def test_codex_transport_keeps_other_prefixes_intact():
    from agent.transports.codex import ResponsesApiTransport

    t = ResponsesApiTransport.__new__(ResponsesApiTransport)
    kw = t.build_kwargs(
        "databricks/glm-5-3",
        [{"role": "user", "content": "hi"}],
        None,
        base_url="https://mlop-azure-gateway-io.mediatek.inc/v1",
    )
    assert kw["model"] == "databricks/glm-5-3"


def test_codex_transport_no_strip_on_non_aide_base():
    from agent.transports.codex import ResponsesApiTransport

    t = ResponsesApiTransport.__new__(ResponsesApiTransport)
    kw = t.build_kwargs(
        "azure/gpt-6.1-sol",
        [{"role": "user", "content": "hi"}],
        None,
        base_url="https://api.openai.com/v1",
    )
    assert kw["model"] == "azure/gpt-6.1-sol"
