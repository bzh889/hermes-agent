"""Regression tests for named AIDE provider fallback eligibility."""

from types import SimpleNamespace
from time import monotonic
from typing import cast

import pytest

from agent.chat_completion_helpers import try_activate_fallback
from agent.error_classifier import FailoverReason
from run_agent import AIAgent


@pytest.fixture
def named_aide_agent():
    return SimpleNamespace(
        platform="tui",
        provider="custom",
        requested_provider="aide-crlogai001-responses",
        _fallback_chain=[{"provider": "aide", "model": "mtk/deepseek-v4-flash"}],
        _fallback_index=0,
        _primary_runtime={},
        _fallback_activated=False,
        _rate_limited_until=0,
    )


def test_named_aide_custom_provider_is_eligible_for_tui_fallback(named_aide_agent):
    """A named AIDE entry resolves to custom but remains AIDE policy-wise."""
    assert AIAgent._has_pending_fallback(cast(AIAgent, named_aide_agent)) is True


def test_named_aide_custom_rate_limit_reaches_fallback_cooldown(named_aide_agent):
    """The shared fallback gate must not reject a named AIDE rate limit."""
    before = monotonic()
    named_aide_agent._fallback_chain = []

    assert try_activate_fallback(
        named_aide_agent,
        reason=FailoverReason.rate_limit,
    ) is False
    assert named_aide_agent._rate_limited_until >= before + 59


@pytest.mark.parametrize(
    ("provider", "requested_provider"),
    [
        ("aide", "aide"),
        ("custom", "aide-crlogai001"),
        ("custom", "aide-crlogai001-responses"),
    ],
)
def test_all_aide_identity_forms_are_eligible(provider, requested_provider):
    agent = SimpleNamespace(
        platform="cli",
        provider=provider,
        requested_provider=requested_provider,
        _fallback_chain=[{"provider": "aide", "model": "mtk/glm-5-2"}],
        _fallback_index=0,
    )

    assert AIAgent._has_pending_fallback(cast(AIAgent, agent)) is True


def test_non_aide_custom_provider_remains_ineligible():
    agent = SimpleNamespace(
        platform="tui",
        provider="custom",
        requested_provider="my-openai-proxy",
        _fallback_chain=[{"provider": "aide", "model": "mtk/glm-5-2"}],
        _fallback_index=0,
    )

    assert AIAgent._has_pending_fallback(cast(AIAgent, agent)) is False
