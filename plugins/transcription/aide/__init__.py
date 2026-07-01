"""MTK AIDE Gateway speech-to-text backend.

Thin :class:`TranscriptionProvider` over :class:`openai.AzureOpenAI` pointed at
the AIDE gateway, which natively builds the Azure path AIDE uses::

    {endpoint}/openai/deployments/aide-whisper/audio/transcriptions?api-version=...

Auth + endpoint come from the shared :mod:`agent.aide_gateway` helper (reuses
``providers.aide``: CCH ``api_key_helper`` + ``X-User-Id``). Deployments from
the gateway catalog (``type: audio``): ``aide-whisper`` (default),
``gpt-4o-transcribe``, ``gpt-4o-mini-transcribe``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent.aide_gateway import azure_client, has_auth
from agent.transcription_provider import TranscriptionProvider

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "2024-05-01-preview"

_MODELS: Dict[str, Dict[str, Any]] = {
    "aide-whisper": {"display": "AIDE Whisper"},
    "gpt-4o-transcribe": {"display": "GPT-4o Transcribe"},
    "gpt-4o-mini-transcribe": {"display": "GPT-4o mini Transcribe"},
}
DEFAULT_MODEL = "aide-whisper"


def _api_version() -> str:
    return (os.environ.get("AIDE_AUDIO_API_VERSION") or DEFAULT_API_VERSION).strip()


class AideTranscriptionProvider(TranscriptionProvider):
    """MTK AIDE Gateway ``audio.transcriptions`` backend (Azure OpenAI convention)."""

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
        return [{"id": mid, "display": meta["display"]} for mid, meta in _MODELS.items()]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MTK AIDE Gateway",
            "badge": "MTK internal",
            "tag": "aide-whisper / gpt-4o-transcribe via the internal AIDE gateway (reuses providers.aide auth)",
            "env_vars": [],
        }

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        model_id = model if model in _MODELS else DEFAULT_MODEL
        try:
            client = azure_client(_api_version())
            params: Dict[str, Any] = {"model": model_id}
            if isinstance(language, str) and language.strip():
                params["language"] = language.strip()
            with open(file_path, "rb") as fh:
                params["file"] = fh
                result = client.audio.transcriptions.create(**params)
            text = getattr(result, "text", None)
            if text is None and isinstance(result, dict):
                text = result.get("text")
            return {
                "success": True,
                "transcript": (text or "").strip(),
                "provider": "aide",
                "model": model_id,
            }
        except Exception as exc:
            logger.debug("AIDE transcription failed", exc_info=True)
            return {
                "success": False,
                "transcript": "",
                "error": f"AIDE transcription failed: {exc}",
                "provider": "aide",
            }


def register(ctx) -> None:
    """Plugin entry point — wire ``AideTranscriptionProvider`` into the registry."""
    ctx.register_transcription_provider(AideTranscriptionProvider())
