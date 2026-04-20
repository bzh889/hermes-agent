"""Tests for AIDE provider registration."""

from hermes_cli.auth import PROVIDER_REGISTRY


def test_aide_provider_registered():
    assert "aide" in PROVIDER_REGISTRY
    p = PROVIDER_REGISTRY["aide"]
    assert p.id == "aide"
    assert p.name == "MTK AIDE Gateway"
    assert p.auth_type == "api_key"
    assert p.inference_base_url == "https://mlop-azure-gateway.mediatek.inc/v1"
    assert "AIDE_API_KEY" in p.api_key_env_vars
    assert p.base_url_env_var == "AIDE_BASE_URL"


def test_aide_io_provider_registered():
    assert "aide-io" in PROVIDER_REGISTRY
    p = PROVIDER_REGISTRY["aide-io"]
    assert p.id == "aide-io"
    assert p.name == "MTK AIDE Gateway (IO)"
    assert p.auth_type == "api_key"
    assert p.inference_base_url == "https://mlop-azure-gateway-io.mediatek.inc/v1"
    assert "AIDE_IO_API_KEY" in p.api_key_env_vars
