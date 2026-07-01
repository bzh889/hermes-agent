# AIDE Gateway Integration for Hermes Agent

**Date**: 2026-04-21
**Status**: Approved
**Scope**: Native AIDE provider, setup wizard, model browser, credential pool support

## Problem

Hermes Agent runs in MTK's internal network where external LLM APIs are unreachable. MTK provides the AIDE (GAISF) gateway at `mlop-azure-gateway.mediatek.inc`, an OpenAI-compatible proxy to 87+ commercial and in-house models. A companion tool CCH (`coding-cli-helper.exe`) provides daily-refreshed JWT tokens. Currently, Hermes has no AIDE integration — users must manually configure custom providers.

## Goals

1. First-class AIDE provider in Hermes's provider registry
2. Setup wizard with CCH auto-detection for zero-friction onboarding
3. Model browser showing all available AIDE models with metadata
4. Credential pool support for multi-identity quota distribution
5. Dual gateway support (primary + IO) for advanced users

## Non-Goals

- Automatic quota monitoring or usage dashboards
- Round-robin load balancing between gateways
- Token expiry detection or mid-session refresh (JWT ~30 day TTL is sufficient)
- Modifying CCH itself

---

## Architecture

### AIDE API Surface (Verified)

| Endpoint | Purpose | Auth Headers |
|---|---|---|
| `GET /v1/models` | Full model list (87+), type/owned_by fields | `Authorization: Bearer <token>`, `x-user-id: <uid>` |
| `GET /llm/v3/models` | In-house models only, with `max_model_len`, `available`, `aliases`, `backend_type` | Same |
| `POST /v1/chat/completions` | Inference (all models) | Same |

Key findings from API testing:
- `/v1/chat/completions` is the only inference endpoint. `/llm/v3/chat/completions` returns 404.
- Both `Authorization: Bearer` and `api-key` headers are accepted for auth.
- In-house models require `mtk/` prefix on `/v1/` (e.g., `mtk/qwen3-30b-a3b-instruct-2507`). Short names without prefix return `"Invalid Azure OpenAI model format"`.
- Commercial models use `{provider}/{model_id}` format (e.g., `aws/anthropic.claude-sonnet-4-6`).
- IO gateway (`mlop-azure-gateway-io.mediatek.inc`) has the same API surface with separate quota.

### Two Gateway Instances

| Gateway | URL | Auth Method | Audience |
|---|---|---|---|
| **Primary** | `https://mlop-azure-gateway.mediatek.inc/v1` | CCH dynamic token or static API key | All users |
| **IO (Stage)** | `https://mlop-azure-gateway-io.mediatek.inc/v1` | Static API key only (web-applied) | Advanced users |

Both share the same API format. The same CCH token works on primary only. IO gateway requires a separately-applied static key.

---

## Design

### 1. Provider Registration

Add `aide` and `aide-io` to `PROVIDER_REGISTRY` in `hermes_cli/auth.py`:

```python
ProviderConfig(
    id="aide",
    name="MTK AIDE Gateway",
    auth_type="api_key",
    inference_base_url="https://mlop-azure-gateway.mediatek.inc/v1",
    api_key_env_vars=("AIDE_API_KEY",),
    base_url_env_var="AIDE_BASE_URL",
)

ProviderConfig(
    id="aide-io",
    name="MTK AIDE Gateway (IO)",
    auth_type="api_key",
    inference_base_url="https://mlop-azure-gateway-io.mediatek.inc/v1",
    api_key_env_vars=("AIDE_IO_API_KEY",),
    base_url_env_var="AIDE_IO_BASE_URL",
)
```

### 2. Authentication

Two auth paths, both using existing Hermes mechanisms:

**Path A — CCH Dynamic Token (recommended for primary gateway)**
- Config: `api_key_helper: "coding-cli-helper.exe key"`
- Uses existing `run_api_key_helper()` in `runtime_provider.py`
- Token fetched once per session startup

**Path B — Static API Key**
- Config: `key_env: "AIDE_API_KEY"` or inline `api_key`
- Standard API key resolution

**x-user-id header**: Required by AIDE. Configured via `default_headers` in provider config:
```yaml
providers:
  aide:
    api_key_helper: "coding-cli-helper.exe key"
    default_headers:
      x-user-id: "MTK12265"
```

OpenAI SDK sends `Authorization: Bearer <key>` automatically — verified compatible with AIDE.

### 3. Model Discovery

Merge data from two endpoints:

1. `GET /v1/models` → complete list with `id`, `type`, `owned_by`
2. `GET /llm/v3/models` → in-house models with `max_model_len`, `available`, `aliases`, `backend_type`

**Merge logic**:
- Base list from `/v1/models`, filtered to `type: "chat"`
- For models with `owned_by: "mtk"`, enrich with `/llm/v3/models` metadata
- Build alias map from `/llm/v3/models` `aliases` field
- Cache result in `context_length_cache.yaml` (existing mechanism, 5-min TTL)

**Display grouping** (for wizard and `hermes models aide`):

```
━━━ Commercial Models ━━━
  aws/anthropic.claude-opus-4-7          (chat)
  aws/anthropic.claude-sonnet-4-6        (chat)
  azure/aide-gpt-5                       (chat)
  google/gemini-2.5-pro                  (chat)

━━━ MTK In-House Models ━━━
  mtk/qwen3-coder-480b-a35b    ✅ 131K   (chat)
  mtk/deepseek-v32             ✅ 163K   (chat)
  mtk/glm-5                    ✅ 202K   (chat)
  mtk/qwen3-vl-235b-a22b      ✅ 262K   (chat, vision)

━━━ Private/Fine-tuned ━━━
  mtk/wfm-pro-glm5-744b       ✅ 202K   (chat, private)
```

**Context length resolution**: New AIDE-specific resolver inserted into `model_metadata.py` chain:
- In-house models → `max_model_len` from `/llm/v3/models`
- Commercial models → existing hardcoded defaults (Claude 200K, GPT-5 1M, etc.)

**Alias resolution**: When user enters a short name (e.g., `deepseek`):
1. Exact match in `/v1/models` → use it
2. Match in `/llm/v3/models` aliases → resolve to canonical `mtk/` prefixed ID
3. Try prepending `mtk/` → check if valid

### 4. Setup Wizard

#### Auto-Detection (runs at `hermes setup` start)

Detection checks:
- Scan `PATH` for `coding-cli-helper.exe`
- Check `~/.cchelper/` directory exists with `state.json`
- DNS resolve `mlop-azure-gateway.mediatek.inc` (no HTTP request)

If detected, promote AIDE to top of provider list:
```
🔍 Detected MTK AIDE Gateway (CCH found)

  → [1] MTK AIDE Gateway (recommended)
    [2] OpenRouter
    [3] DeepSeek
    [4] Other providers...
```

#### Wizard Flow (after selecting AIDE)

```
Step 1: Auth method
  [1] Use CCH auto-token (recommended, detected)
  [2] Enter API key manually

Step 2a (CCH): Validate
  → Run cch key, confirm token obtained
  → Read user_id from ~/.cchelper/state.json or JWT payload
  → Display: ✓ Token OK, User: MTK12265

Step 2b (Manual): Input
  → Prompt for API key
  → Prompt for x-user-id
  → Validate via GET /v1/models

Step 3: Connectivity check
  → GET /v1/models, confirm 200
  → Display: ✓ Connected, 52 chat models available

Step 4: Select main model
  → Show grouped model list (Section 3 format)
  → User selects or types model name
  → Validate: tiny chat completion test

Step 5: Auxiliary models (optional)
  → "Configure auxiliary models? (vision/compression) [y/N]"
  → Yes: recommend + select from available models
  → No: use auto-recommendations

Step 6: Advanced — IO gateway (hidden by default)
  → Only via hermes setup aide --advanced
  → Input IO gateway API key + user ID
  → Configure as fallback provider
```

#### Generated Config

Standard user:
```yaml
model:
  provider: "aide"
  default: "aws/anthropic.claude-sonnet-4-6"

providers:
  aide:
    name: "MTK AIDE Gateway"
    api: "https://mlop-azure-gateway.mediatek.inc/v1"
    api_key_helper: "coding-cli-helper.exe key"
    default_headers:
      x-user-id: "MTK12265"
    transport: "openai_chat"

auxiliary:
  vision:
    provider: "aide"
    model: "mtk/qwen3-vl-235b-a22b-instruct-fp8"
  compression:
    provider: "aide"
    model: "mtk/qwen3-30b-a3b-instruct-2507"
```

Advanced user (with IO gateway):
```yaml
providers:
  aide-io:
    name: "MTK AIDE Gateway (IO)"
    api: "https://mlop-azure-gateway-io.mediatek.inc/v1"
    key_env: "AIDE_IO_API_KEY"
    default_headers:
      x-user-id: "${AIDE_IO_USER_ID}"
    transport: "openai_chat"

fallback_providers: ["aide", "aide-io"]
```

### 5. Credential Pool (Multi-Identity)

For advanced users with multiple (user_id, api_key) pairs on the same gateway. Uses Hermes's existing credential pool system.

**New requirement**: `PoolEntry` needs a `headers: dict` field so each credential in the pool can carry its own `x-user-id`. Currently pool entries only store api_key.

**Usage**:
```bash
# Primary identity (CCH)
hermes auth add aide --api-key-helper "coding-cli-helper.exe key" \
  --headers '{"x-user-id": "MTK12265"}'

# Additional identity (static key)
hermes auth add aide --api-key "sk-aide-xxx" \
  --headers '{"x-user-id": "MTK99999"}'
```

**Rotation strategy**:
```yaml
credential_pool_strategies:
  aide: "fill_first"
```

Behavior: Use credential #1 until 429 → auto-rotate to #2 → all exhausted → fallback to `aide-io` (if configured).

### 6. `hermes models aide` Subcommand

Standalone model browser, usable outside of setup:

```bash
hermes models aide              # List chat models, grouped by owner
hermes models aide --all        # Include embedding/audio/image types
hermes models aide --available  # Only show available=true
hermes models aide --refresh    # Force re-fetch (clear cache)
```

### 7. Runtime Behavior

**API call flow**:
```
User selects model "aws/anthropic.claude-sonnet-4-6" (provider: aide)
  → runtime_provider resolves aide config
  → api_key_helper runs "cch key" → JWT token
  → OpenAI SDK init:
      base_url = "https://mlop-azure-gateway.mediatek.inc/v1"
      api_key = <JWT>
      default_headers = {"x-user-id": "MTK12265"}
  → POST /v1/chat/completions
      model: "aws/anthropic.claude-sonnet-4-6"
      Authorization: Bearer <JWT>
      x-user-id: MTK12265
```

**Error mapping**:

| AIDE Response | Hermes Behavior |
|---|---|
| 200 + choices | Normal response |
| 401/403 | "AIDE token invalid or expired. Run `cch key` or `hermes setup aide`" |
| 429 | Pool rotation → fallback provider → "Quota exhausted" |
| 404 + "Invalid Azure OpenAI model format" | "Model name format error — in-house models need mtk/ prefix" |

**Token lifecycle**: Fetched once at session start via `api_key_helper`. No mid-session refresh. CCH JWT has ~30 day expiry — safe for any session length.

---

## Implementation Changes Summary

| File | Change |
|---|---|
| `hermes_cli/auth.py` | Add `aide` and `aide-io` to `PROVIDER_REGISTRY` |
| `hermes_cli/setup.py` | Add AIDE auto-detection logic + wizard flow |
| `hermes_cli/config.py` | No structural changes (existing `providers` dict + `default_headers` suffice) |
| `agent/model_metadata.py` | Add AIDE-specific context length resolver using `/llm/v3/models` |
| `agent/credential_pool.py` | Extend `PoolEntry` with `headers: dict` field |
| `hermes_cli/models.py` | Add `hermes models aide` subcommand — model listing + filtering |
| `hermes_cli/runtime_provider.py` | Ensure per-credential headers are merged at request time |

## Scope Boundary

This spec covers one complete feature: AIDE as a native Hermes provider. It does not cover:
- Changes to other providers
- UI/TUI changes beyond the existing setup wizard format
- Gateway platform adapters (Telegram/Discord/etc. with AIDE)
- Modifications to CCH itself
