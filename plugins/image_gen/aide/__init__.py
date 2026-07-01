"""MTK AIDE Gateway image generation backend.

AIDE speaks the **Azure OpenAI** convention for non-chat capabilities:
``{endpoint}/openai/deployments/{deployment}/images/generations?api-version=``.
The OpenAI SDK's :class:`openai.AzureOpenAI` client builds exactly that path,
so this provider is a thin wrapper — all the heavy lifting (image save,
response shaping) is reused from :mod:`agent.image_gen_provider`.

Auth reuses the already-configured ``providers.aide`` entry from
``config.yaml`` (the same one the chat provider uses): the CCH
``api_key_helper`` supplies a fresh JWT, and ``default_headers.x-user-id``
supplies the mandatory ``X-User-Id`` cost-allocation header. Nothing new to
configure — if ``hermes`` chat already talks to AIDE, image gen does too.

Deployments (from the gateway model catalog, ``type: image``):

    gpt-image-2   b64 output, high fidelity  (default)
    Dalle3        URL output, fast

Selection precedence (first hit wins):

1. ``AIDE_IMAGE_MODEL`` env var (escape hatch for scripts / tests)
2. ``image_gen.aide.model`` in ``config.yaml``
3. ``image_gen.model`` in ``config.yaml`` (when it names one of our deployments)
4. :data:`DEFAULT_MODEL` — ``gpt-image-2``
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://mlop-azure-gateway.mediatek.inc"
# Azure api-version for the image endpoint. Overridable via config
# (image_gen.aide.api_version) or AIDE_IMAGE_API_VERSION env.
DEFAULT_API_VERSION = "2024-05-01-preview"

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2": {
        "display": "GPT Image 2 (AIDE)",
        "speed": "~40s",
        "strengths": "High fidelity, strong prompt adherence",
        "response": "b64",
        # gpt-image-2 supported sizes
        "sizes": {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"},
    },
    "Dalle3": {
        "display": "DALL·E 3 (AIDE)",
        "speed": "~15s",
        "strengths": "Fast, creative compositions",
        "response": "url",
        # Dalle3 supported sizes
        "sizes": {"landscape": "1792x1024", "square": "1024x1024", "portrait": "1024x1792"},
    },
}

DEFAULT_MODEL = "gpt-image-2"


# ---------------------------------------------------------------------------
# Config / connection
# ---------------------------------------------------------------------------


def _aide_provider_config() -> Dict[str, Any]:
    """Read the ``providers.aide`` entry from config.yaml (shared with chat)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        provs = cfg.get("providers") if isinstance(cfg, dict) else None
        aide = provs.get("aide") if isinstance(provs, dict) else None
        return aide if isinstance(aide, dict) else {}
    except Exception as exc:
        logger.debug("Could not load providers.aide config: %s", exc)
        return {}


def _image_gen_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def _resolve_connection() -> Tuple[str, str, str, str]:
    """Return ``(azure_endpoint, api_key, user_id, api_version)`` for AIDE.

    Endpoint is the gateway root (any trailing ``/v1`` is stripped — the
    Azure SDK appends ``/openai/deployments/...`` itself). Token comes from
    the ``providers.aide`` ``api_key_helper`` (CCH), falling back to the
    ``AIDE_API_KEY`` env or an inline ``api_key``.
    """
    prov = _aide_provider_config()

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

    img_cfg = _image_gen_config().get("aide") if isinstance(_image_gen_config().get("aide"), dict) else {}
    api_version = str(
        (img_cfg or {}).get("api_version")
        or os.environ.get("AIDE_IMAGE_API_VERSION")
        or DEFAULT_API_VERSION
    ).strip()

    return base, token, user_id, api_version


def _resolve_model() -> str:
    env_override = os.environ.get("AIDE_IMAGE_MODEL")
    if env_override and env_override in _MODELS:
        return env_override
    cfg = _image_gen_config()
    aide_cfg = cfg.get("aide") if isinstance(cfg.get("aide"), dict) else {}
    value = aide_cfg.get("model") if isinstance(aide_cfg, dict) else None
    if isinstance(value, str) and value in _MODELS:
        return value
    top = cfg.get("model")
    if isinstance(top, str) and top in _MODELS:
        return top
    return DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class AideImageGenProvider(ImageGenProvider):
    """MTK AIDE Gateway ``images.generate`` backend (Azure OpenAI convention)."""

    @property
    def name(self) -> str:
        return "aide"

    @property
    def display_name(self) -> str:
        return "MTK AIDE Gateway"

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        # Available when a token can be sourced (helper cmd, env, or inline).
        prov = _aide_provider_config()
        has_auth = bool(
            str(prov.get("api_key_helper") or "").strip()
            or os.environ.get("AIDE_API_KEY", "").strip()
            or str(prov.get("api_key") or "").strip()
        )
        return has_auth

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": "AIDE quota",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MTK AIDE Gateway",
            "badge": "MTK internal",
            "tag": "gpt-image-2 / DALL·E 3 via the internal AIDE gateway (reuses providers.aide auth)",
            "env_vars": [],
        }

    def capabilities(self) -> Dict[str, Any]:
        # Text-to-image only for this slice. AIDE image editing endpoint is
        # unverified; add "image" here once confirmed against the gateway.
        return {"modalities": ["text"], "max_reference_images": 0}

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)

        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider="aide",
                aspect_ratio=aspect,
            )

        try:
            import openai
        except ImportError:
            return error_response(
                error="The 'openai' package is required for the AIDE image backend",
                error_type="dependency_missing",
                provider="aide",
                prompt=prompt,
                aspect_ratio=aspect,
            )

        endpoint, token, user_id, api_version = _resolve_connection()
        if not token:
            return error_response(
                error="No AIDE token available — set providers.aide.api_key_helper (CCH) "
                "or AIDE_API_KEY. Run: hermes setup",
                error_type="auth_error",
                provider="aide",
                prompt=prompt,
                aspect_ratio=aspect,
            )

        model_id = _resolve_model()
        meta = _MODELS[model_id]
        size = meta["sizes"].get(aspect, meta["sizes"]["square"])

        default_headers = {"X-User-Id": user_id} if user_id else None
        try:
            client = openai.AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=token,
                api_version=api_version,
                default_headers=default_headers,
            )
        except Exception as exc:
            return error_response(
                error=f"Could not initialize AIDE (Azure OpenAI) client: {exc}",
                error_type="config_error",
                provider="aide",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        # AIDE / gpt-image-2 return b64 and reject `response_format` as unknown;
        # don't send it. `model` is the Azure deployment name.
        try:
            response = client.images.generate(
                model=model_id,
                prompt=prompt,
                size=size,
                n=1,
            )
        except Exception as exc:
            logger.debug("AIDE image generation failed", exc_info=True)
            return error_response(
                error=f"AIDE image generation failed: {exc}",
                error_type="api_error",
                provider="aide",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        data = getattr(response, "data", None) or []
        if not data:
            return error_response(
                error="AIDE returned no image data",
                error_type="empty_response",
                provider="aide",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        first = data[0]
        b64 = getattr(first, "b64_json", None)
        url = getattr(first, "url", None)
        revised_prompt = getattr(first, "revised_prompt", None)

        if b64:
            try:
                saved_path = save_b64_image(b64, prefix=f"aide_{model_id}")
            except Exception as exc:
                return error_response(
                    error=f"Could not save image to cache: {exc}",
                    error_type="io_error",
                    provider="aide",
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            image_ref = str(saved_path)
        elif url:
            try:
                saved_path = save_url_image(url, prefix=f"aide_{model_id}")
            except Exception as exc:
                logger.warning(
                    "AIDE image URL %s could not be cached (%s); falling back to bare URL.",
                    url,
                    exc,
                )
                image_ref = url
            else:
                image_ref = str(saved_path)
        else:
            return error_response(
                error="AIDE response contained neither b64_json nor URL",
                error_type="empty_response",
                provider="aide",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        extra: Dict[str, Any] = {"size": size}
        if revised_prompt:
            extra["revised_prompt"] = revised_prompt

        return success_response(
            image=image_ref,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="aide",
            modality="text",
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def register(ctx) -> None:
    """Plugin entry point — wire ``AideImageGenProvider`` into the registry."""
    ctx.register_image_gen_provider(AideImageGenProvider())
