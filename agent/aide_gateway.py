"""Shared MTK AIDE Gateway connection helper (Azure OpenAI convention).

AIDE serves non-chat capabilities (image / TTS / STT / embeddings) via the
**Azure OpenAI** path convention::

    {endpoint}/openai/deployments/{deployment}/{operation}?api-version=...

The OpenAI SDK's :class:`openai.AzureOpenAI` client builds exactly that path,
so each capability provider only needs a configured client. Auth reuses the
already-present ``providers.aide`` entry in ``config.yaml`` (the same one the
chat provider uses): a CCH ``api_key_helper`` supplies a fresh JWT and
``default_headers.x-user-id`` supplies the mandatory ``X-User-Id`` header.

This module is imported by the AIDE image_gen / tts / transcription plugins so
the credential/endpoint logic lives in one place.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://mlop-azure-gateway.mediatek.inc"


def aide_provider_config() -> Dict[str, Any]:
    """Return the ``providers.aide`` entry from config.yaml ({} on failure)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        provs = cfg.get("providers") if isinstance(cfg, dict) else None
        aide = provs.get("aide") if isinstance(provs, dict) else None
        return aide if isinstance(aide, dict) else {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not load providers.aide config: %s", exc)
        return {}


def resolve_connection() -> Tuple[str, str, str]:
    """Return ``(azure_endpoint, api_key, user_id)`` for the AIDE gateway.

    ``azure_endpoint`` is the gateway root — any trailing ``/v1`` is stripped
    because the Azure SDK appends ``/openai/deployments/...`` itself. The token
    is sourced (in order) from the ``providers.aide`` ``api_key_helper`` (CCH),
    the ``AIDE_API_KEY`` env var, or an inline ``api_key``. ``user_id`` comes
    from ``default_headers.x-user-id`` or ``AIDE_USER_ID``.
    """
    prov = aide_provider_config()

    base = str(
        prov.get("api") or prov.get("base_url") or prov.get("url") or DEFAULT_ENDPOINT
    ).strip()
    base = re.sub(r"/v1/?$", "", base).rstrip("/") or DEFAULT_ENDPOINT

    headers = prov.get("default_headers") if isinstance(prov.get("default_headers"), dict) else {}
    user_id = str(
        headers.get("x-user-id") or headers.get("X-User-Id") or os.environ.get("AIDE_USER_ID", "")
    ).strip()

    token = ""
    helper = str(prov.get("api_key_helper") or "").strip()
    if helper:
        try:
            from hermes_cli.runtime_provider import run_api_key_helper

            token = run_api_key_helper(helper) or ""
        except Exception as exc:
            logger.debug("AIDE api_key_helper failed: %s", exc)
    if not token:
        token = os.environ.get("AIDE_API_KEY", "").strip() or str(prov.get("api_key") or "").strip()

    return base, token, user_id


def has_auth() -> bool:
    """True when a token can be sourced (helper cmd, env, or inline api_key)."""
    prov = aide_provider_config()
    return bool(
        str(prov.get("api_key_helper") or "").strip()
        or os.environ.get("AIDE_API_KEY", "").strip()
        or str(prov.get("api_key") or "").strip()
    )


def azure_client(api_version: str, *, http_client: Any = None):
    """Build an ``openai.AzureOpenAI`` client pointed at the AIDE gateway.

    Raises ``RuntimeError`` if the ``openai`` package is missing or no token
    can be sourced. TLS trusts the system CA bundle (the MTK setup script
    injects the MTK CA into certifi); ``http_client`` is an override hook used
    only by tests.
    """
    try:
        import openai
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("the 'openai' package is required for AIDE gateway access") from exc

    endpoint, token, user_id = resolve_connection()
    if not token:
        raise RuntimeError(
            "no AIDE token available — set providers.aide.api_key_helper (CCH) "
            "or AIDE_API_KEY (run: hermes setup)"
        )

    kwargs: Dict[str, Any] = {
        "azure_endpoint": endpoint,
        "api_key": token,
        "api_version": api_version,
    }
    if user_id:
        kwargs["default_headers"] = {"X-User-Id": user_id}
    if http_client is not None:
        kwargs["http_client"] = http_client
    return openai.AzureOpenAI(**kwargs)
