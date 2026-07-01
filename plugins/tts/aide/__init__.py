"""MTK AIDE Gateway text-to-speech backend.

Thin :class:`TTSProvider` over :class:`openai.AzureOpenAI` pointed at the AIDE
gateway, which natively builds the Azure path AIDE uses::

    {endpoint}/openai/deployments/aide-tts/audio/speech?api-version=...

Auth + endpoint come from the shared :mod:`agent.aide_gateway` helper (reuses
``providers.aide``: CCH ``api_key_helper`` + ``X-User-Id``). Deployments from
the gateway catalog (``type: audio``): ``aide-tts`` (default), ``aide-tts-hd``,
``gpt-4o-mini-tts``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent.aide_gateway import azure_client, has_auth
from agent.tts_provider import (
    DEFAULT_OUTPUT_FORMAT,
    TTSProvider,
    resolve_output_format,
)

logger = logging.getLogger(__name__)

# Azure api-version for the audio endpoints (per AIDE wiki examples).
DEFAULT_API_VERSION = "2024-05-01-preview"

_MODELS: Dict[str, Dict[str, Any]] = {
    "aide-tts": {"display": "AIDE TTS", "languages": ["en", "zh", "ja"]},
    "aide-tts-hd": {"display": "AIDE TTS HD (higher quality)", "languages": ["en", "zh", "ja"]},
    "gpt-4o-mini-tts": {"display": "GPT-4o mini TTS", "languages": ["en", "zh", "ja"]},
}
DEFAULT_MODEL = "aide-tts"

# Standard OpenAI/Azure TTS voices.
_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
DEFAULT_VOICE = "alloy"


def _api_version() -> str:
    return (os.environ.get("AIDE_AUDIO_API_VERSION") or DEFAULT_API_VERSION).strip()


class AideTTSProvider(TTSProvider):
    """MTK AIDE Gateway ``audio.speech`` backend (Azure OpenAI convention)."""

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
        return [{"id": mid, "display": meta["display"], "languages": meta["languages"]} for mid, meta in _MODELS.items()]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def list_voices(self) -> List[Dict[str, Any]]:
        return [{"id": v, "display": v.title()} for v in _VOICES]

    def default_voice(self) -> Optional[str]:
        return DEFAULT_VOICE

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MTK AIDE Gateway",
            "badge": "MTK internal",
            "tag": "aide-tts / aide-tts-hd via the internal AIDE gateway (reuses providers.aide auth)",
            "env_vars": [],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = DEFAULT_OUTPUT_FORMAT,
        **extra: Any,
    ) -> str:
        model_id = model if model in _MODELS else DEFAULT_MODEL
        voice_id = voice if voice in _VOICES else DEFAULT_VOICE
        fmt = resolve_output_format(format)

        client = azure_client(_api_version())
        params: Dict[str, Any] = {
            "model": model_id,          # Azure deployment name
            "voice": voice_id,
            "input": text,
            "response_format": fmt,
        }
        if isinstance(speed, (int, float)) and speed > 0:
            params["speed"] = float(speed)

        response = client.audio.speech.create(**params)
        # openai>=1.0 binary response: write bytes to the target path.
        response.write_to_file(output_path)
        return output_path


def register(ctx) -> None:
    """Plugin entry point — wire ``AideTTSProvider`` into the registry."""
    ctx.register_tts_provider(AideTTSProvider())
