"""Provider identity headers must reach the TUI/desktop agent and survive /model.

MTK AIDE service accounts authenticate with two parts: the bearer key *and* an
``x-user-id`` header naming the service account. Drop the header and the gateway
answers ``403 missing UID in logging context`` — the key alone is not enough.

``resolve_runtime_provider()`` returns that header in ``default_headers`` (from
``providers.<name>.default_headers``), and the classic CLI hands it to
``AIAgent(default_headers=...)``. The TUI/desktop gateway builds its agent
through its own constructor call, which is where the header was lost: a session
started from the TUI 403'd on its very first turn while the same provider worked
from the CLI.

The second test covers the other half of the same header's lifetime. An
in-place ``/model`` switch rebuilds ``_client_kwargs`` from scratch, and
``_apply_client_headers_for_base_url()`` clears ``default_headers`` for any host
it has no special case for — AIDE is such a host. The restore that follows looks
the provider up by name, but the *runtime* provider of a named custom provider is
the literal string ``"custom"`` (the entry slug survives only in
``requested_provider``), so a name-keyed lookup finds nothing and the header
stays gone.
"""

import pytest

_HOST = "https://mlop-azure-gateway.mediatek.inc"
_RESPONSES_BASE_URL = f"{_HOST}/openai"
_PROVIDER_SLUG = "aide-crlogai001-responses"
_IDENTITY = {"x-user-id": "srv_cr_log_ai001"}

_RUNTIME = {
    "provider": "custom",
    "requested_provider": _PROVIDER_SLUG,
    "base_url": _RESPONSES_BASE_URL,
    "api_key": "test-key",
    "api_mode": "codex_responses",
    "default_headers": dict(_IDENTITY),
}

_CONFIG = {
    "providers": {
        _PROVIDER_SLUG: {
            "api": _RESPONSES_BASE_URL,
            "key_env": "AIDE_CRLOGAI001_KEY",
            "transport": "codex_responses",
            "default_headers": dict(_IDENTITY),
        }
    }
}


def test_tui_agent_build_passes_default_headers(monkeypatch):
    """``_make_agent`` must forward ``default_headers`` to ``AIAgent``.

    Without this the TUI/desktop agent is built with no identity header at all,
    so the first request of a fresh session fails 403 while the CLI succeeds
    against the very same provider entry.
    """
    import tui_gateway.server as srv

    captured = {}

    class _FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("run_agent.AIAgent", _FakeAgent)
    monkeypatch.setattr(srv, "_load_cfg", lambda *a, **k: {})
    monkeypatch.setattr(srv, "_resolve_startup_runtime", lambda: ("gpt-5.6-luna", _PROVIDER_SLUG))
    monkeypatch.setattr(
        srv,
        "_resolve_runtime_with_fallback",
        lambda kwargs: srv._RuntimeFallbackResolution(dict(_RUNTIME), None, False),
    )
    monkeypatch.setattr(srv, "_get_db", lambda: None)

    srv._make_agent("sid-1", "key-1")

    assert captured.get("default_headers") == _IDENTITY, (
        "AIDE identity header dropped at TUI agent build — the gateway "
        "rejects the request with 403 'missing UID in logging context'"
    )
    assert captured.get("requested_provider") == _PROVIDER_SLUG, (
        "the entry slug must ride along; 'custom' alone cannot be mapped back "
        "to its providers: entry by any later header/credential lookup"
    )


def test_switch_keeps_entry_identity_for_custom_provider(monkeypatch):
    """``switch_model`` must not overwrite the entry slug with ``"custom"``.

    ``new_provider`` is the resolved billing class shared by every named entry.
    Storing it in ``requested_provider`` discards the only handle back to the
    ``providers:`` entry, so the header lookup below has nothing to match even
    when it does check ``requested_provider``.
    """
    import agent.agent_runtime_helpers as arh
    import hermes_cli.runtime_provider as rp

    monkeypatch.setattr(
        rp, "canonical_custom_identity", lambda **kw: f"custom:{_PROVIDER_SLUG}"
    )

    # Assert on the identity as the header lookup sees it, mid-switch. Checking
    # the agent afterwards would prove nothing: switch_model rolls every mutated
    # field back to its pre-swap snapshot on failure, restoring the slug and
    # making the assertion pass with or without the fix.
    seen = {}

    def _spy(agent, new_provider):
        seen["requested_provider"] = getattr(agent, "requested_provider", None)
        return {}

    monkeypatch.setattr(arh, "_resolve_switch_default_headers", _spy)

    class _Agent:
        model = "gpt-5.6-luna"
        provider = "custom"
        requested_provider = _PROVIDER_SLUG
        base_url = _RESPONSES_BASE_URL
        api_key = "test-key"
        api_mode = "codex_responses"

        def _create_openai_client(self, *a, **k):
            return object()

        def _apply_client_headers_for_base_url(self, *a, **k):
            self._client_kwargs.pop("default_headers", None)

    agent = _Agent()
    agent._client_kwargs = {"default_headers": dict(_IDENTITY)}
    try:
        arh.switch_model(
            agent,
            "gpt-5.6-sol",
            "custom",
            api_key="test-key",
            base_url=_RESPONSES_BASE_URL,
            api_mode="codex_responses",
        )
    except Exception:
        # Later stages of the switch need runtime state this stub has no
        # business faking; the identity swap already happened.
        pass

    assert seen.get("requested_provider") != "custom", (
        "the entry slug was overwritten by the resolved billing class — "
        "per-entry config (default_headers, extra_headers) is unreachable after"
    )
    assert _PROVIDER_SLUG in (seen.get("requested_provider") or "")


@pytest.mark.parametrize("provider_arg", ["custom", f"custom:{_PROVIDER_SLUG}"])
def test_switch_resolves_headers_for_custom_runtime(monkeypatch, provider_arg):
    """The switch-time restore must resolve headers for a ``custom`` runtime.

    ``switch_model`` is handed the *resolved* provider name. For every named
    custom provider that name is ``custom`` (optionally ``custom:<slug>``), so a
    lookup that only matches the bare slug returns ``{}`` and the header wiped
    by ``_apply_client_headers_for_base_url`` is never restored — ``/model``
    turns a working session into a 403 one.
    """
    import agent.agent_runtime_helpers as arh
    import hermes_cli.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda *a, **k: _CONFIG)

    class _Agent:
        provider = "custom"
        requested_provider = _PROVIDER_SLUG
        base_url = _RESPONSES_BASE_URL

    headers = arh._resolve_switch_default_headers(_Agent(), provider_arg)

    assert headers == _IDENTITY, (
        f"provider={provider_arg!r} lost the identity header on switch"
    )
