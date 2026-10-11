"""Regression tests for the two databricks/AIDE-Responses picker fixes:

1. Section-3 display-name collapsing: single-member provider groups must keep
   the configured name verbatim — the digit-token trim (Palantir version
   suffixes) only applies when a group actually FOLDS multiple entries.
   (Six ``providers.aide-responses*`` entries carrying account names with
   digits — "AIDE Responses ds901472 (IO)" etc. — were collapsing to five
   indistinguishable "AIDE Responses" rows.)

2. ``probe_api_models`` catalog selection must follow the transport: a
   ``codex_responses`` endpoint serves TWO catalogs from /v1/models
   (``data[]`` chat ids + ``models[]`` Responses slugs). Membership-checking
   only ``data[]`` reported every Responses-only model as "not found".
"""

import json
from unittest.mock import patch

import hermes_cli.models as models_mod
from hermes_cli.model_switch import list_authenticated_providers


# ---------------------------------------------------------------------------
# 1. picker display names stay distinct for single-member groups
# ---------------------------------------------------------------------------

def _six_aide_responses_providers():
    return {
        "aide-responses": {
            "name": "MTK AIDE Responses (Codex-style)",
            "base_url": "https://gw.example.com/v1",
            "key_env": "AIDE_KEY",
            "default_headers": {"x-user-id": "MTK12265"},
            "transport": "codex_responses",
            "models": ["databricks/glm-5-3"],
        },
        "aide-responses-ds901472": {
            "name": "AIDE Responses ds901472 (primary)",
            "base_url": "https://gw.example.com/v1",
            "key_env": "AIDE_DS901472_KEY",
            "default_headers": {"x-user-id": "ds901472"},
            "transport": "codex_responses",
            "models": ["databricks/glm-5-3"],
        },
        "aide-responses-io": {
            "name": "AIDE Responses MTK12265 (IO)",
            "base_url": "https://gw-io.example.com/v1",
            "key_env": "AIDE_IO_API_KEY",
            "default_headers": {"x-user-id": "MTK12265"},
            "transport": "codex_responses",
            "models": ["databricks/glm-5-3"],
        },
        "aide-responses-io-ds901472": {
            "name": "AIDE Responses ds901472 (IO)",
            "base_url": "https://gw-io.example.com/v1",
            "key_env": "AIDE_DS901472_IO_KEY",
            "default_headers": {"x-user-id": "ds901472"},
            "transport": "codex_responses",
            "models": ["databricks/glm-5-3"],
        },
    }


def _providers_rows(monkeypatch, user_providers):
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr(models_mod, "HERMES_OVERLAYS", {}, raising=False)
    monkeypatch.setattr(models_mod, "fetch_api_models", lambda *a, **k: [])
    rows = list_authenticated_providers(
        user_providers=user_providers,
        custom_providers=[],
        max_models=50,
    )
    return [p for p in rows if p.get("source") == "user-config"]


def test_single_member_provider_rows_keep_configured_name(monkeypatch):
    """The AIDE-Responses regression: none of these four rows share a
    (url, credential, api_mode, headers) key, so none fold — and none may
    have their digit-bearing account name trimmed away."""
    import hermes_cli.providers as providers_mod

    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    rows = _providers_rows(monkeypatch, _six_aide_responses_providers())
    names = {p["slug"]: p["name"] for p in rows}
    assert names["aide-responses"] == "MTK AIDE Responses (Codex-style)"
    assert names["aide-responses-ds901472"] == "AIDE Responses ds901472 (primary)"
    assert names["aide-responses-io"] == "AIDE Responses MTK12265 (IO)"
    assert names["aide-responses-io-ds901472"] == "AIDE Responses ds901472 (IO)"


def test_distinct_names_no_duplicates_in_picker(monkeypatch):
    """Invariant form of the user-facing symptom: the picker must show N
    distinct labels for N distinct configured providers."""
    import hermes_cli.providers as providers_mod

    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    rows = _providers_rows(monkeypatch, _six_aide_responses_providers())
    labels = [p["name"] for p in rows]
    assert len(labels) == len(set(labels)), f"duplicate picker labels: {labels}"


def test_folding_still_trims_version_suffix(monkeypatch):
    """The Palantir case must keep working: two same-endpoint+credential
    entries whose names differ only by version really fold AND trim to the
    shared prefix."""
    import hermes_cli.providers as providers_mod

    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    rows = _providers_rows(monkeypatch, {
        "palantir-claude46": {
            "name": "Palantir Claude 4.6 Opus",
            "base_url": "https://foundry.example.com/anthropic",
            "key_env": "PALANTIR_TOKEN",
            "model": "claude-4.6",
        },
        "palantir-claude47": {
            "name": "Palantir Claude 4.7 Opus",
            "base_url": "https://foundry.example.com/anthropic",
            "key_env": "PALANTIR_TOKEN",
            "model": "claude-4.7",
        },
    })
    assert len(rows) == 1
    assert rows[0]["name"] == "Palantir Claude"
    assert set(rows[0]["models"]) == {"claude-4.6", "claude-4.7"}


# ---------------------------------------------------------------------------
# 2. codex_responses catalog merge in probe_api_models
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        import io

        self._buf = io.BytesIO(json.dumps(payload).encode())

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _catalog_payload():
    """One /v1/models payload carrying both catalogs, like AIDE."""
    return {
        "data": [
            {"id": "mtk/glm-5-3", "type": "chat"},
            {"id": "mtk/deepseek-v4-flash", "type": "chat"},
        ],
        "models": [
            {"slug": "databricks/glm-5-3", "display_name": "GLM-5.3 (1M context)"},
            {"slug": "databricks/kimi-k3", "display_name": "Kimi K3"},
        ],
    }


def test_codex_responses_probe_merges_both_catalogs():
    with patch.object(
        models_mod, "_urlopen_model_catalog_request"
    ) as mock_open:
        mock_open.return_value = _FakeResponse(_catalog_payload())
        probe = models_mod.probe_api_models(
            "key", "https://gw.example.com/v1", api_mode="codex_responses"
        )
    ids = probe["models"]
    assert "mtk/glm-5-3" in ids  # chat catalog retained
    assert "databricks/glm-5-3" in ids  # responses slug merged
    # display_name synonyms ride along too
    assert "GLM-5.3 (1M context)" in ids
    assert len([i for i in ids if i == "databricks/glm-5-3"]) == 1  # no dupes


def test_chat_transport_probe_keeps_data_only():
    with patch.object(
        models_mod, "_urlopen_model_catalog_request"
    ) as mock_open:
        mock_open.return_value = _FakeResponse(_catalog_payload())
        probe = models_mod.probe_api_models(
            "key", "https://gw.example.com/v1", api_mode="chat_completions"
        )
    ids = probe["models"]
    assert "mtk/glm-5-3" in ids
    assert "databricks/glm-5-3" not in ids  # chat transport never sees slugs


def test_custom_provider_validation_accepts_responses_model(monkeypatch):
    """End-to-end form: validate_requested_model on a codex_responses custom
    endpoint must RECOGNIZE a databricks slug (no 'not found' warning)."""
    with patch.object(
        models_mod, "_urlopen_model_catalog_request"
    ) as mock_open:
        mock_open.return_value = _FakeResponse(_catalog_payload())
        result = models_mod.validate_requested_model(
            "databricks/glm-5-3",
            "custom",
            api_key="key",
            base_url="https://gw.example.com/v1",
            api_mode="codex_responses",
        )
    assert result["accepted"] is True
    assert result["recognized"] is True
    assert result["message"] is None
