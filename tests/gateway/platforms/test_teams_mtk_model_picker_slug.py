"""Unit tests for model picker slug handling in teams_mtk.

Validates that provider dicts with missing/empty 'slug' keys are handled
gracefully (slug defaults to ""), and that deduplication by slug works
correctly.  Prevents regression of G23 (slug=None display bug caused by
test script reading wrong key; gateway code itself was always correct).
"""

import pytest


# ── Minimal stub that mirrors the relevant dedup/build logic from
#    teams_mtk.py send_model_picker (L1627-1644) ─────────────────────

def _dedupe_and_build_entries(providers: list) -> list:
    """Reproduce the provider dedup + entry-building logic from send_model_picker."""
    seen_slugs: set = set()
    deduped_providers: list = []
    for prov in providers:
        slug = prov.get("slug", "")
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        deduped_providers.append(prov)

    prov_entries = []
    for prov in deduped_providers:
        prov_name = prov.get("name") or prov.get("slug", "?")
        prov_slug = prov.get("slug", "")
        models = prov.get("models", [])
        is_current = prov.get("is_current", False)
        prov_entries.append((prov_slug, prov_name, len(models), is_current))

    return prov_entries


# ── Tests ──────────────────────────────────────────────────────────


class TestModelPickerSlug:
    """Slug handling in the model picker provider list."""

    def test_slug_present(self):
        """Providers with a 'slug' key use that slug."""
        providers = [{"slug": "aide", "name": "MTK AIDE", "models": ["m1"]}]
        entries = _dedupe_and_build_entries(providers)
        assert entries == [("aide", "MTK AIDE", 1, False)]

    def test_slug_missing_defaults_empty(self):
        """Provider dict without 'slug' key defaults slug to '' (empty string), not None."""
        providers = [{"name": "No Slug Provider", "models": ["m1"]}]
        entries = _dedupe_and_build_entries(providers)
        assert entries[0][0] == ""  # slug is "", not None
        assert entries[0][1] == "No Slug Provider"  # name fallback works

    def test_slug_empty_string(self):
        """Provider with slug='' is handled same as missing slug."""
        providers = [{"slug": "", "name": "Empty Slug", "models": ["m1"]}]
        entries = _dedupe_and_build_entries(providers)
        assert entries[0][0] == ""

    def test_slug_none_in_dict(self):
        """If slug is explicitly None, prov.get('slug', '') returns None
        (key exists with value None — default is NOT used). Dedup adds
        None to seen_slugs, and the entry's slug tuple element is None.
        Name is still read from 'name' key as normal."""
        providers = [{"slug": None, "name": "Null Slug", "models": ["m1"]}]
        entries = _dedupe_and_build_entries(providers)
        # prov.get("slug", "") returns None (key exists, value is None)
        assert entries[0][0] is None
        # name: prov.get("name") → "Null Slug" (truthy, so short-circuits)
        assert entries[0][1] == "Null Slug"

    def test_dedup_by_slug(self):
        """Duplicate slugs are deduplicated — only first occurrence kept."""
        providers = [
            {"slug": "openrouter", "name": "OpenRouter", "models": ["a"]},
            {"slug": "openrouter", "name": "OpenRouter (dup)", "models": ["b"]},
            {"slug": "aide", "name": "AIDE", "models": ["c"]},
        ]
        entries = _dedupe_and_build_entries(providers)
        assert len(entries) == 2
        assert entries[0][1] == "OpenRouter"
        assert entries[1][1] == "AIDE"

    def test_missing_slug_name_fallback(self):
        """When both slug and name are missing, name falls back to '?'."""
        providers = [{"models": ["m1"]}]
        entries = _dedupe_and_build_entries(providers)
        assert entries[0][1] == "?"  # prov.get("name") or prov.get("slug", "?")

    def test_real_world_providers(self):
        """Typical provider list from list_picker_providers works correctly."""
        providers = [
            {"slug": "moa", "name": "Mixture of Agents", "models": [], "is_current": False},
            {"slug": "aide", "name": "MTK AIDE Gateway", "models": ["wfm-pro-glm5", "qwen3"], "is_current": True},
        ]
        entries = _dedupe_and_build_entries(providers)
        assert len(entries) == 2
        assert entries[0] == ("moa", "Mixture of Agents", 0, False)
        assert entries[1] == ("aide", "MTK AIDE Gateway", 2, True)

    def test_no_providers(self):
        """Empty provider list → empty entries."""
        assert _dedupe_and_build_entries([]) == []
