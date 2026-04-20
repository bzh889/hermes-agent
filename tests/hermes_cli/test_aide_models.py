"""Tests for AIDE model discovery, merging, and alias resolution."""

import pytest
from hermes_cli.aide_models import (
    AideModel,
    merge_aide_models,
    resolve_aide_alias,
    format_aide_model_list,
)

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
