"""AIDE Gateway model discovery, merging, and display."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

AIDE_PRIMARY_BASE = "https://mlop-azure-gateway.mediatek.inc"
AIDE_IO_BASE = "https://mlop-azure-gateway-io.mediatek.inc"


@dataclass
class AideModel:
    id: str
    owned_by: str
    model_type: str
    max_model_len: Optional[int] = None
    available: Optional[bool] = None
    aliases: List[str] = field(default_factory=list)
    private: bool = False
    backend_type: Optional[str] = None


def fetch_aide_models(
    base_url: str, api_key: str, user_id: str
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_key}", "x-user-id": user_id}
    with httpx.Client(verify=False, timeout=15) as client:
        v1_resp = client.get(f"{base_url.rstrip('/v1')}/v1/models", headers=headers)
        v1_resp.raise_for_status()
        v1_data = v1_resp.json()

        v3_base = base_url.rstrip("/v1").rstrip("/")
        v3_resp = client.get(f"{v3_base}/llm/v3/models", headers=headers)
        v3_data = v3_resp.json() if v3_resp.status_code == 200 else {"data": []}

    return v1_data, v3_data


def merge_aide_models(
    v1_response: Dict[str, Any], v3_response: Dict[str, Any]
) -> List[AideModel]:
    v3_by_short = {}
    for entry in v3_response.get("data", []):
        short_id = entry["id"]
        v3_by_short[short_id] = entry
        for alias in entry.get("aliases", []):
            v3_by_short[alias] = entry

    models = []
    for entry in v1_response.get("data", []):
        if entry.get("type") != "chat":
            continue

        model_id = entry["id"]
        owned_by = entry.get("owned_by", "")

        short_name = model_id.split("/", 1)[1] if "/" in model_id else model_id
        v3_meta = v3_by_short.get(short_name, {})

        models.append(AideModel(
            id=model_id,
            owned_by=owned_by,
            model_type=entry.get("type", "chat"),
            max_model_len=v3_meta.get("max_model_len"),
            available=v3_meta.get("available"),
            aliases=v3_meta.get("aliases", []),
            private=v3_meta.get("private", False),
            backend_type=v3_meta.get("backend_type"),
        ))

    return models


def resolve_aide_alias(name: str, models: List[AideModel]) -> Optional[str]:
    ids = {m.id for m in models}
    if name in ids:
        return name

    for m in models:
        if name in m.aliases:
            return m.id

    prefixed = f"mtk/{name}"
    if prefixed in ids:
        return prefixed

    return None


def _group_key(model: AideModel) -> str:
    if model.private:
        return "Private/Fine-tuned"
    if model.owned_by == "mtk":
        return "MTK In-House"
    return "Commercial"


GROUP_ORDER = ["Commercial", "MTK In-House", "Private/Fine-tuned"]


def format_aide_model_list(
    models: List[AideModel],
    show_all_types: bool = False,
    available_only: bool = False,
) -> str:
    filtered = models
    if available_only:
        filtered = [m for m in filtered if m.available is not False]

    groups: Dict[str, List[AideModel]] = {}
    for m in filtered:
        key = _group_key(m)
        groups.setdefault(key, []).append(m)

    lines = []
    for group_name in GROUP_ORDER:
        group_models = groups.get(group_name, [])
        if not group_models:
            continue
        lines.append(f"\n━━━ {group_name} ━━━")
        for m in sorted(group_models, key=lambda x: x.id):
            parts = [f"  {m.id}"]
            if m.available is not None:
                parts.append("✅" if m.available else "❌")
            if m.max_model_len:
                parts.append(f"{m.max_model_len // 1024}K")
            tags = [f"({m.model_type}"]
            if m.private:
                tags[0] += ", private"
            if m.aliases:
                tags[0] += f", alias: {m.aliases[0]}"
            tags[0] += ")"
            parts.append(tags[0])
            lines.append("  ".join(parts))

    return "\n".join(lines)
