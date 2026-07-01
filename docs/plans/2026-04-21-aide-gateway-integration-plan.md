# AIDE Gateway Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MTK AIDE Gateway as a native Hermes provider with setup wizard, model browser, and credential pool support.

**Architecture:** Register `aide` and `aide-io` in `PROVIDER_REGISTRY`, use existing `api_key_helper` for CCH token, `default_headers` for `x-user-id`, and extend `PooledCredential` with per-credential headers. Model discovery merges `/v1/models` + `/llm/v3/models`.

**Tech Stack:** Python 3.11+, OpenAI SDK, httpx for model listing, existing Hermes provider/pool framework.

**Spec:** `docs/specs/2026-04-21-aide-gateway-integration-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `hermes_cli/auth.py` | Modify | Add `aide` + `aide-io` to `PROVIDER_REGISTRY` |
| `hermes_cli/aide_models.py` | Create | AIDE model fetching, merging, alias resolution, display formatting |
| `hermes_cli/main.py` | Modify | Add `hermes models aide` subcommand parser + `--headers` arg on `auth add` |
| `hermes_cli/setup.py` | Modify | AIDE auto-detection + wizard flow |
| `hermes_cli/auth_commands.py` | Modify | Handle `--headers` in `cmd_auth_add` |
| `agent/model_metadata.py` | Modify | AIDE context length resolver step |
| `agent/credential_pool.py` | Modify | Add `headers` field to `PooledCredential` |
| `hermes_cli/runtime_provider.py` | Modify | Merge per-credential headers at request time |
| `tests/hermes_cli/test_aide_provider.py` | Create | Tests for provider registration + auth resolution |
| `tests/hermes_cli/test_aide_models.py` | Create | Tests for model fetching, merging, alias resolution |
| `tests/agent/test_credential_pool_headers.py` | Create | Tests for per-credential headers in pool |

---

## Task 1: Provider Registration

**Files:**
- Modify: `hermes_cli/auth.py` (around line 220, inside `PROVIDER_REGISTRY` dict)
- Test: `tests/hermes_cli/test_aide_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hermes_cli/test_aide_provider.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/hermes_cli/test_aide_provider.py -v`
Expected: FAIL with `KeyError: 'aide'`

- [ ] **Step 3: Add AIDE entries to PROVIDER_REGISTRY**

In `hermes_cli/auth.py`, find the `PROVIDER_REGISTRY` dict (line ~107). Add after the last existing entry (before the closing `}`):

```python
    "aide": ProviderConfig(
        id="aide",
        name="MTK AIDE Gateway",
        auth_type="api_key",
        inference_base_url="https://mlop-azure-gateway.mediatek.inc/v1",
        api_key_env_vars=("AIDE_API_KEY",),
        base_url_env_var="AIDE_BASE_URL",
    ),
    "aide-io": ProviderConfig(
        id="aide-io",
        name="MTK AIDE Gateway (IO)",
        auth_type="api_key",
        inference_base_url="https://mlop-azure-gateway-io.mediatek.inc/v1",
        api_key_env_vars=("AIDE_IO_API_KEY",),
        base_url_env_var="AIDE_IO_BASE_URL",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/hermes_cli/test_aide_provider.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add hermes_cli/auth.py tests/hermes_cli/test_aide_provider.py
git commit -m "feat(aide): register aide and aide-io in PROVIDER_REGISTRY"
```

---

## Task 2: AIDE Model Fetching & Merging

**Files:**
- Create: `hermes_cli/aide_models.py`
- Test: `tests/hermes_cli/test_aide_models.py`

- [ ] **Step 1: Write failing tests for model fetching and merging**

Create `tests/hermes_cli/test_aide_models.py`:

```python
"""Tests for AIDE model discovery, merging, and alias resolution."""

import pytest
from hermes_cli.aide_models import (
    AideModel,
    merge_aide_models,
    resolve_aide_alias,
    format_aide_model_list,
)

# Fixtures: minimal API responses matching real AIDE gateway format

V1_MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {"id": "aws/anthropic.claude-sonnet-4-6", "object": "model", "created": 0, "owned_by": "aws", "type": "chat"},
        {"id": "mtk/deepseek-v32", "object": "model", "created": 0, "owned_by": "mtk", "type": "chat"},
        {"id": "mtk/qwen3-vl-235b-a22b-instruct-fp8", "object": "model", "created": 0, "owned_by": "mtk", "type": "chat"},
        {"id": "aide-text-embedding-3-large", "object": "model", "created": 0, "owned_by": "azure", "type": "embedding"},
        {"id": "mtk/wfm-pro-glm5-744b", "object": "model", "created": 0, "owned_by": "mtk", "type": "chat"},
    ],
}

V3_MODELS_RESPONSE = {
    "data": [
        {
            "id": "deepseek-v32", "object": "model", "owned_by": "mamba-inference-cluster",
            "root": "deepseek-ai/deepseek-v3.2", "max_model_len": 163840,
            "aliases": ["deepseek-v3.2", "deepseek"], "available": True,
        },
        {
            "id": "qwen3-vl-235b-a22b-instruct-fp8", "object": "model", "owned_by": "mamba-inference-cluster",
            "root": "qwen/qwen3-vl-235b-a22b-instruct-fp8", "max_model_len": 262144,
            "aliases": ["qwen3-vl"], "available": True,
        },
        {
            "id": "wfm-pro-glm5-744b", "object": "model", "owned_by": "mamba-inference-cluster",
            "root": "fts/wfm-pro", "max_model_len": 202752,
            "aliases": ["wfm-pro"], "available": True, "private": True,
        },
    ],
}


def test_merge_filters_chat_only():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    ids = [m.id for m in models]
    assert "aide-text-embedding-3-large" not in ids
    assert "aws/anthropic.claude-sonnet-4-6" in ids
    assert "mtk/deepseek-v32" in ids


def test_merge_enriches_mtk_models():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    ds = next(m for m in models if m.id == "mtk/deepseek-v32")
    assert ds.max_model_len == 163840
    assert ds.available is True
    assert "deepseek" in ds.aliases


def test_merge_commercial_no_context_length():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    claude = next(m for m in models if m.id == "aws/anthropic.claude-sonnet-4-6")
    assert claude.max_model_len is None
    assert claude.aliases == []


def test_merge_marks_private():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    wfm = next(m for m in models if m.id == "mtk/wfm-pro-glm5-744b")
    assert wfm.private is True


def test_resolve_alias_exact():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    assert resolve_aide_alias("mtk/deepseek-v32", models) == "mtk/deepseek-v32"


def test_resolve_alias_short_name():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    assert resolve_aide_alias("deepseek", models) == "mtk/deepseek-v32"


def test_resolve_alias_with_mtk_prefix():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    assert resolve_aide_alias("qwen3-vl", models) == "mtk/qwen3-vl-235b-a22b-instruct-fp8"


def test_resolve_alias_unknown():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    assert resolve_aide_alias("nonexistent-model", models) is None


def test_format_groups_by_owner():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    output = format_aide_model_list(models)
    assert "Commercial" in output
    assert "In-House" in output
    assert "aws/anthropic.claude-sonnet-4-6" in output
    assert "mtk/deepseek-v32" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/hermes_cli/test_aide_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_cli.aide_models'`

- [ ] **Step 3: Implement aide_models.py**

Create `hermes_cli/aide_models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/hermes_cli/test_aide_models.py -v`
Expected: all 9 tests passed

- [ ] **Step 5: Commit**

```bash
git add hermes_cli/aide_models.py tests/hermes_cli/test_aide_models.py
git commit -m "feat(aide): model discovery with merge, alias resolution, and display formatting"
```

---

## Task 3: Credential Pool Per-Credential Headers

**Files:**
- Modify: `agent/credential_pool.py` (PooledCredential dataclass, ~line 89)
- Modify: `hermes_cli/runtime_provider.py` (header merging)
- Test: `tests/agent/test_credential_pool_headers.py`

- [ ] **Step 1: Write failing test for per-credential headers**

Create `tests/agent/test_credential_pool_headers.py`:

```python
"""Tests for per-credential headers in credential pool."""

from agent.credential_pool import PooledCredential


def test_pooled_credential_has_headers_field():
    cred = PooledCredential(
        provider="aide",
        id="test-1",
        label="test",
        auth_type="api_key",
        priority=0,
        source="manual",
        access_token="fake-token",
        headers={"x-user-id": "MTK12265"},
    )
    assert cred.headers == {"x-user-id": "MTK12265"}


def test_pooled_credential_headers_default_none():
    cred = PooledCredential(
        provider="aide",
        id="test-2",
        label="test",
        auth_type="api_key",
        priority=0,
        source="manual",
        access_token="fake-token",
    )
    assert cred.headers is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_credential_pool_headers.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'headers'`

- [ ] **Step 3: Add `headers` field to PooledCredential**

In `agent/credential_pool.py`, find the `PooledCredential` dataclass (line ~89). Add after the `extra` field (line ~113):

```python
    headers: Optional[Dict[str, str]] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_credential_pool_headers.py -v`
Expected: 2 passed

- [ ] **Step 5: Update runtime_provider to merge per-credential headers**

In `hermes_cli/runtime_provider.py`, find `_resolve_runtime_from_pool_entry()` (line ~172). At the end of the function where `result` dict is assembled, add:

```python
    if hasattr(entry, "headers") and entry.headers:
        existing = result.get("default_headers", {})
        existing.update(entry.headers)
        result["default_headers"] = existing
```

- [ ] **Step 6: Run full credential pool test suite to check no regressions**

Run: `pytest tests/agent/test_credential_pool.py tests/agent/test_credential_pool_headers.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add agent/credential_pool.py hermes_cli/runtime_provider.py tests/agent/test_credential_pool_headers.py
git commit -m "feat(pool): add per-credential headers field to PooledCredential"
```

---

## Task 4: `hermes auth add --headers` CLI Support

**Files:**
- Modify: `hermes_cli/main.py` (auth_add argument parser, ~line 6896)
- Modify: `hermes_cli/auth_commands.py` (handle --headers in add flow)

- [ ] **Step 1: Add `--headers` argument to auth add parser**

In `hermes_cli/main.py`, find `auth_add` parser (line ~6896). After the `--ca-bundle` argument (line ~6928), add:

```python
    auth_add.add_argument(
        "--headers",
        help='Per-credential custom headers as JSON (e.g. \'{"x-user-id": "MTK12265"}\')',
    )
    auth_add.add_argument(
        "--api-key-helper",
        help="Command to run for dynamic API key (e.g. coding-cli-helper.exe key)",
    )
```

- [ ] **Step 2: Handle --headers in auth_commands.py**

In `hermes_cli/auth_commands.py`, find the `cmd_auth_add` function. Where the new pool entry dict is assembled, add headers support:

```python
    import json

    headers_raw = getattr(args, "headers", None)
    if headers_raw:
        try:
            entry["headers"] = json.loads(headers_raw)
        except json.JSONDecodeError:
            print(f"Error: --headers must be valid JSON, got: {headers_raw}")
            return

    api_key_helper = getattr(args, "api_key_helper", None)
    if api_key_helper:
        entry["api_key_helper"] = api_key_helper
```

- [ ] **Step 3: Test manually**

Run: `python -m hermes_cli.main auth add aide --api-key "test-key" --headers '{"x-user-id": "MTK12265"}' --label test-cred`

Verify: `hermes auth list aide` shows the credential with headers.

- [ ] **Step 4: Commit**

```bash
git add hermes_cli/main.py hermes_cli/auth_commands.py
git commit -m "feat(auth): add --headers and --api-key-helper flags to hermes auth add"
```

---

## Task 5: AIDE Context Length Resolver

**Files:**
- Modify: `agent/model_metadata.py` (insert new resolver step, ~line 1012)

- [ ] **Step 1: Write test for AIDE context length resolution**

Add to `tests/hermes_cli/test_aide_models.py`:

```python
from hermes_cli.aide_models import get_aide_context_length, merge_aide_models


def test_aide_context_length_inhouse():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    length = get_aide_context_length("mtk/deepseek-v32", models)
    assert length == 163840


def test_aide_context_length_commercial_returns_none():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    length = get_aide_context_length("aws/anthropic.claude-sonnet-4-6", models)
    assert length is None


def test_aide_context_length_alias():
    models = merge_aide_models(V1_MODELS_RESPONSE, V3_MODELS_RESPONSE)
    length = get_aide_context_length("deepseek", models)
    assert length == 163840
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/hermes_cli/test_aide_models.py::test_aide_context_length_inhouse -v`
Expected: FAIL with `ImportError: cannot import name 'get_aide_context_length'`

- [ ] **Step 3: Add `get_aide_context_length` to aide_models.py**

Add to `hermes_cli/aide_models.py`:

```python
def get_aide_context_length(
    model_name: str, models: List[AideModel]
) -> Optional[int]:
    resolved = resolve_aide_alias(model_name, models)
    if resolved is None:
        return None
    for m in models:
        if m.id == resolved:
            return m.max_model_len
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/hermes_cli/test_aide_models.py -v`
Expected: all 12 tests passed

- [ ] **Step 5: Integrate into model_metadata.py resolution chain**

In `agent/model_metadata.py`, find `get_model_context_length()` (line ~941). After the custom endpoint `/models` query step (line ~1012) and before the Anthropic API check (line ~1014), add:

```python
    # Step 3b: AIDE gateway — use /llm/v3/models metadata
    if provider in ("aide", "aide-io") or "mlop-azure-gateway" in (base_url or ""):
        try:
            from hermes_cli.aide_models import get_aide_context_length, fetch_aide_models, merge_aide_models
            if api_key and base_url:
                user_id = ""
                cfg = _load_config_safe()
                if cfg:
                    providers = cfg.get("providers", {})
                    for pname in ("aide", "aide-io"):
                        p = providers.get(pname, {})
                        hdrs = p.get("default_headers", {})
                        if hdrs.get("x-user-id"):
                            user_id = hdrs["x-user-id"]
                            break
                if user_id:
                    v1_data, v3_data = fetch_aide_models(base_url, api_key, user_id)
                    models = merge_aide_models(v1_data, v3_data)
                    ctx = get_aide_context_length(model, models)
                    if ctx:
                        _save_to_cache(model, ctx)
                        return ctx
        except Exception:
            logger.debug("AIDE context length lookup failed", exc_info=True)
```

- [ ] **Step 6: Run existing model_metadata tests for regressions**

Run: `pytest tests/ -k "model_metadata or context_length" -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add hermes_cli/aide_models.py agent/model_metadata.py tests/hermes_cli/test_aide_models.py
git commit -m "feat(aide): context length resolution via /llm/v3/models metadata"
```

---

## Task 6: `hermes models aide` Subcommand

**Files:**
- Modify: `hermes_cli/main.py` (add subcommand parser)
- Modify: `hermes_cli/models.py` or create handler function

- [ ] **Step 1: Add `models` subcommand parser to main.py**

In `hermes_cli/main.py`, after the `model` parser section (line ~6653), add:

```python
    # =========================================================================
    # models command (model listing / browsing)
    # =========================================================================
    models_parser = subparsers.add_parser(
        "models",
        help="Browse available models by provider",
    )
    models_subparsers = models_parser.add_subparsers(dest="models_command")

    models_aide = models_subparsers.add_parser(
        "aide", help="List models available on MTK AIDE Gateway"
    )
    models_aide.add_argument(
        "--all", action="store_true", dest="show_all",
        help="Include non-chat models (embedding, audio, image)",
    )
    models_aide.add_argument(
        "--available", action="store_true",
        help="Only show models with available=true",
    )
    models_aide.add_argument(
        "--refresh", action="store_true",
        help="Force re-fetch from gateway (clear cache)",
    )
    models_parser.set_defaults(func=cmd_models)
```

- [ ] **Step 2: Implement cmd_models handler**

In `hermes_cli/main.py`, find the command handler section. Add:

```python
def cmd_models(args):
    """Browse models by provider."""
    if getattr(args, "models_command", None) == "aide":
        _cmd_models_aide(args)
    else:
        print("Usage: hermes models aide [--all] [--available] [--refresh]")


def _cmd_models_aide(args):
    """List AIDE gateway models."""
    from hermes_cli.config import load_config
    from hermes_cli.aide_models import fetch_aide_models, merge_aide_models, format_aide_model_list
    from hermes_cli.runtime_provider import run_api_key_helper

    config = load_config()
    providers = config.get("providers", {})
    aide_cfg = providers.get("aide", {})

    if not aide_cfg:
        print("AIDE provider not configured. Run: hermes setup")
        return

    api_key = ""
    helper = aide_cfg.get("api_key_helper")
    if helper:
        api_key = run_api_key_helper(helper)
    if not api_key:
        import os
        api_key = os.environ.get("AIDE_API_KEY", aide_cfg.get("api_key", ""))
    if not api_key:
        print("No AIDE API key available. Run: hermes setup aide")
        return

    user_id = aide_cfg.get("default_headers", {}).get("x-user-id", "")
    base_url = aide_cfg.get("api", aide_cfg.get("base_url", aide_cfg.get("url", "")))
    if not base_url:
        base_url = "https://mlop-azure-gateway.mediatek.inc"

    try:
        v1_data, v3_data = fetch_aide_models(base_url, api_key, user_id)
    except Exception as e:
        print(f"Failed to fetch models: {e}")
        return

    models = merge_aide_models(v1_data, v3_data)
    chat_count = len([m for m in models if m.model_type == "chat"])
    total = len(v1_data.get("data", []))

    print(f"\nAIDE Gateway: {total} models total, {chat_count} chat models\n")
    print(format_aide_model_list(
        models,
        show_all_types=getattr(args, "show_all", False),
        available_only=getattr(args, "available", False),
    ))
```

- [ ] **Step 3: Test manually (requires AIDE config)**

Run: `python -m hermes_cli.main models aide`
Expected: grouped model list output

- [ ] **Step 4: Commit**

```bash
git add hermes_cli/main.py
git commit -m "feat(aide): add 'hermes models aide' subcommand for model browsing"
```

---

## Task 7: Setup Wizard — AIDE Auto-Detection

**Files:**
- Modify: `hermes_cli/setup.py` (auto-detection + wizard flow)

- [ ] **Step 1: Add AIDE detection function to aide_models.py**

Add to `hermes_cli/aide_models.py`:

```python
import json
import os
import shutil
import socket
from pathlib import Path


def detect_aide_environment() -> dict:
    result = {"cch_path": None, "user_id": None, "gateway_reachable": False}

    cch = shutil.which("coding-cli-helper.exe") or shutil.which("coding-cli-helper")
    if not cch:
        cchelper_dir = Path.home() / ".cchelper"
        for candidate in (cchelper_dir / "coding-cli-helper.exe", cchelper_dir / "coding-cli-helper"):
            if candidate.exists():
                cch = str(candidate)
                break
    result["cch_path"] = cch

    state_file = Path.home() / ".cchelper" / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            uid = state.get("quota_cache", {}).get("user_id")
            if uid:
                result["user_id"] = uid
        except Exception:
            pass

    try:
        socket.getaddrinfo("mlop-azure-gateway.mediatek.inc", 443, socket.AF_INET, socket.SOCK_STREAM)
        result["gateway_reachable"] = True
    except socket.gaierror:
        pass

    return result
```

- [ ] **Step 2: Write test for detection**

Add to `tests/hermes_cli/test_aide_models.py`:

```python
from unittest.mock import patch
from hermes_cli.aide_models import detect_aide_environment


@patch("hermes_cli.aide_models.shutil.which", return_value=None)
@patch("hermes_cli.aide_models.Path.home")
@patch("hermes_cli.aide_models.socket.getaddrinfo", side_effect=socket.gaierror)
def test_detect_aide_no_cch_no_network(mock_dns, mock_home, mock_which, tmp_path):
    mock_home.return_value = tmp_path
    result = detect_aide_environment()
    assert result["cch_path"] is None
    assert result["gateway_reachable"] is False


import socket

@patch("hermes_cli.aide_models.shutil.which", return_value="/usr/bin/coding-cli-helper.exe")
@patch("hermes_cli.aide_models.socket.getaddrinfo", return_value=[(2, 1, 6, '', ('10.0.0.1', 443))])
def test_detect_aide_with_cch(mock_dns, mock_which):
    result = detect_aide_environment()
    assert result["cch_path"] == "/usr/bin/coding-cli-helper.exe"
    assert result["gateway_reachable"] is True
```

- [ ] **Step 3: Run detection tests**

Run: `pytest tests/hermes_cli/test_aide_models.py -k "detect" -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add hermes_cli/aide_models.py tests/hermes_cli/test_aide_models.py
git commit -m "feat(aide): environment auto-detection for CCH and gateway reachability"
```

---

## Task 8: Setup Wizard — AIDE Provider Flow

**Files:**
- Modify: `hermes_cli/setup.py` (insert AIDE detection into provider selection, add AIDE wizard steps)

- [ ] **Step 1: Add AIDE detection hook into setup_model_provider**

In `hermes_cli/setup.py`, find `setup_model_provider()` (line ~624). Before the provider selection UI (line ~646 where `select_provider_and_model` is called), insert:

```python
    from hermes_cli.aide_models import detect_aide_environment
    aide_env = detect_aide_environment()
    if aide_env["cch_path"] or aide_env["gateway_reachable"]:
        print("\n🔍 Detected MTK AIDE Gateway", end="")
        if aide_env["cch_path"]:
            print(f" (CCH found)")
        else:
            print(f" (gateway reachable)")
        print()
```

- [ ] **Step 2: Add AIDE-specific setup flow**

Create a new function in `hermes_cli/setup.py`:

```python
def setup_aide_provider(config: dict, aide_env: dict) -> dict:
    """Interactive AIDE provider setup. Returns updated config."""
    from hermes_cli.aide_models import fetch_aide_models, merge_aide_models, format_aide_model_list
    from hermes_cli.runtime_provider import run_api_key_helper

    print("\n━━━ MTK AIDE Gateway Setup ━━━\n")

    # Step 1: Auth method
    api_key = ""
    user_id = aide_env.get("user_id", "")
    cch_path = aide_env.get("cch_path")

    if cch_path:
        print(f"  [1] Use CCH auto-token (recommended)")
        print(f"  [2] Enter API key manually")
        choice = input("\nAuth method [1]: ").strip() or "1"
    else:
        choice = "2"

    if choice == "1" and cch_path:
        api_key = run_api_key_helper(f"{cch_path} key")
        if api_key:
            print(f"  ✓ Token obtained, User: {user_id or 'unknown'}")
            if not user_id:
                user_id = input("  Enter your user ID (e.g. MTK12265): ").strip()
        else:
            print("  ✗ CCH failed. Falling back to manual entry.")
            choice = "2"

    if choice == "2":
        api_key = input("  API Key: ").strip()
        user_id = user_id or input("  User ID (e.g. MTK12265): ").strip()

    if not api_key or not user_id:
        print("  ✗ Missing credentials. Aborting AIDE setup.")
        return config

    # Step 2: Connectivity check
    base_url = "https://mlop-azure-gateway.mediatek.inc"
    try:
        v1_data, v3_data = fetch_aide_models(base_url, api_key, user_id)
        models = merge_aide_models(v1_data, v3_data)
        chat_models = [m for m in models if m.model_type == "chat"]
        print(f"  ✓ Connected — {len(chat_models)} chat models available\n")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return config

    # Step 3: Model selection
    print(format_aide_model_list(models))
    print()
    default_model = "aws/anthropic.claude-sonnet-4-6"
    model_input = input(f"  Select main model [{default_model}]: ").strip() or default_model

    from hermes_cli.aide_models import resolve_aide_alias
    resolved = resolve_aide_alias(model_input, models)
    if resolved:
        model_input = resolved
        print(f"  ✓ Model: {model_input}")
    else:
        print(f"  ⚠ Model '{model_input}' not found in AIDE list, using as-is")

    # Step 4: Build config
    aide_provider = {
        "name": "MTK AIDE Gateway",
        "api": f"{base_url}/v1",
        "default_headers": {"x-user-id": user_id},
        "transport": "openai_chat",
    }

    if choice == "1" and cch_path:
        aide_provider["api_key_helper"] = f"{cch_path} key"
    else:
        aide_provider["api_key"] = api_key

    config.setdefault("providers", {})["aide"] = aide_provider
    config["model"] = {"provider": "aide", "default": model_input}

    # Step 5: Auxiliary (optional)
    aux_choice = input("\n  Configure auxiliary models? (vision/compression) [y/N]: ").strip().lower()
    if aux_choice in ("y", "yes"):
        vision_models = [m for m in models if "vl" in m.id.lower() and m.available is not False]
        small_models = [m for m in models if m.max_model_len and m.max_model_len <= 131072 and m.available is not False and not m.private]

        config.setdefault("auxiliary", {})
        if vision_models:
            vm = vision_models[0]
            print(f"  Vision model: {vm.id}")
            config["auxiliary"]["vision"] = {"provider": "aide", "model": vm.id}
        if small_models:
            sm = sorted(small_models, key=lambda x: x.max_model_len or 0)[0]
            print(f"  Compression model: {sm.id}")
            config["auxiliary"]["compression"] = {"provider": "aide", "model": sm.id}

    print("\n  ✓ AIDE provider configured!\n")
    return config
```

- [ ] **Step 3: Wire into setup_model_provider**

In `setup_model_provider()`, after the AIDE detection print, add:

```python
        use_aide = input("  Use AIDE Gateway? [Y/n]: ").strip().lower()
        if use_aide not in ("n", "no"):
            config = setup_aide_provider(config, aide_env)
            from hermes_cli.config import save_config
            save_config(config)
            return
```

- [ ] **Step 4: Test manually**

Run: `python -m hermes_cli.main setup`
Expected: If on MTK network with CCH, AIDE auto-detection triggers and wizard runs.

- [ ] **Step 5: Commit**

```bash
git add hermes_cli/setup.py
git commit -m "feat(aide): interactive setup wizard with auto-detection and model selection"
```

---

## Task 9: Error Mapping for AIDE Responses

**Files:**
- Modify: `run_agent.py` (or wherever API errors are caught and displayed)

- [ ] **Step 1: Find error handling location**

Search for where HTTP 429/401/403 errors from the OpenAI SDK are caught and mapped to user-facing messages. This is typically in `run_agent.py`'s `_run_agent_loop()`.

- [ ] **Step 2: Add AIDE-specific error messages**

In the error handler, add provider-aware messages:

```python
    if provider in ("aide", "aide-io") or "mlop-azure-gateway" in (base_url or ""):
        if status_code == 401 or status_code == 403:
            error_msg = "AIDE token invalid or expired. Run `cch key` or `hermes setup aide`"
        elif status_code == 404 and "Invalid Azure OpenAI model format" in str(error):
            error_msg = "Model name format error — in-house models need mtk/ prefix (e.g. mtk/deepseek-v32)"
```

- [ ] **Step 3: Test with an invalid token**

Set an invalid API key and verify the user-friendly error message appears.

- [ ] **Step 4: Commit**

```bash
git add run_agent.py
git commit -m "feat(aide): user-friendly error messages for AIDE gateway responses"
```

---

## Task 10: Integration Smoke Test

**Files:**
- No new files — manual verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: no regressions

- [ ] **Step 2: End-to-end test — setup + chat**

```bash
# Fresh setup
python -m hermes_cli.main setup

# Select AIDE, go through wizard
# Verify config.yaml looks correct

# Run a chat
python cli.py
# Type a message, verify response comes from AIDE gateway
```

- [ ] **Step 3: Test model switching**

```bash
# In CLI, switch model
/model mtk/deepseek-v32
# Verify it works

/model deepseek
# Verify alias resolution works
```

- [ ] **Step 4: Test model browser**

```bash
python -m hermes_cli.main models aide
python -m hermes_cli.main models aide --available
```

- [ ] **Step 5: Commit any fixups**

```bash
git add -A
git commit -m "fix(aide): integration test fixups"
```

---

## Self-Review Checklist

| Spec Requirement | Task |
|---|---|
| Provider registration (aide + aide-io) | Task 1 |
| Setup wizard with CCH auto-detection | Tasks 7 + 8 |
| Model browser with metadata | Tasks 2 + 6 |
| Credential pool per-credential headers | Tasks 3 + 4 |
| Dual gateway support | Task 1 (registry) + Task 8 (setup --advanced, deferred to future) |
| Context length resolution | Task 5 |
| Error mapping | Task 9 |
| Runtime behavior | Covered by existing Hermes mechanisms (api_key_helper, default_headers) |

**Note:** The IO gateway advanced setup flow (Step 6 in the wizard spec) is covered by the provider registration and `hermes auth add aide-io` commands but does not have a dedicated wizard step in this plan. The user can configure it via `hermes auth add aide-io --api-key <key> --headers '{"x-user-id": "..."}' ` or manual config.yaml editing. A wizard step can be added in a follow-up if needed.
