"""MTK AIDE Gateway image generation backend.

AIDE speaks the **Azure OpenAI** convention for non-chat capabilities:
``{endpoint}/openai/deployments/{deployment}/images/generations?api-version=``.
The OpenAI SDK's :class:`openai.AzureOpenAI` client builds exactly that path,
so this provider is a thin wrapper — image save + response shaping are reused
from :mod:`agent.image_gen_provider`, and the endpoint/auth from the shared
:mod:`agent.aide_gateway` helper (reuses ``providers.aide``: CCH
``api_key_helper`` + the mandatory ``X-User-Id`` header — same credential path
as chat).

Deployments (gateway catalog, ``type: image``):

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
from typing import Any, Dict, List, Optional

from agent.aide_gateway import azure_client, has_auth
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

# Azure api-version for the image endpoint. Overridable via config
# (image_gen.aide.api_version) or AIDE_IMAGE_API_VERSION env.
DEFAULT_API_VERSION = "2024-05-01-preview"

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2": {
        "display": "GPT Image 2 (AIDE)",
        "speed": "~40s",
        "strengths": "High fidelity, strong prompt adherence",
        "sizes": {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"},
    },
    "Dalle3": {
        "display": "DALL·E 3 (AIDE)",
        "speed": "~15s",
        "strengths": "Fast, creative compositions",
        "sizes": {"landscape": "1792x1024", "square": "1024x1024", "portrait": "1024x1792"},
    },
}
DEFAULT_MODEL = "gpt-image-2"


def _image_gen_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


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


def _api_version() -> str:
    cfg = _image_gen_config()
    aide_cfg = cfg.get("aide") if isinstance(cfg.get("aide"), dict) else {}
    return str(
        (aide_cfg or {}).get("api_version")
        or os.environ.get("AIDE_IMAGE_API_VERSION")
        or DEFAULT_API_VERSION
    ).strip()


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
        return has_auth()

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

        model_id = _resolve_model()
        meta = _MODELS[model_id]
        size = meta["sizes"].get(aspect, meta["sizes"]["square"])

        try:
            client = azure_client(_api_version())
        except RuntimeError as exc:
            return error_response(
                error=str(exc),
                error_type="auth_error",
                provider="aide",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        # AIDE / gpt-image-2 return b64 and reject `response_format` as unknown;
        # don't send it. `model` is the Azure deployment name.
        try:
            response = client.images.generate(model=model_id, prompt=prompt, size=size, n=1)
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


def register(ctx) -> None:
    """Plugin entry point — wire ``AideImageGenProvider`` into the registry."""
    ctx.register_image_gen_provider(AideImageGenProvider())
