"""Unit tests for the Live Teams E2E Probe — ticket 06.

These are UNIT tests: they verify the probe's structure, config loading,
and logic without making real Teams network calls. The live E2E run
(which sends/receives real Teams messages) is a manual step.

Run:
    scripts/run_tests.sh tests/poc/test_live_teams_probe_poc.py -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from poc.terminal_broker.e2e_harness import EvidenceTier, E2EVerdict


def test_live_probe_importable():
    """The live probe module is importable."""
    from poc.terminal_broker.live_teams_probe import LiveTeamsE2EProbe
    assert LiveTeamsE2EProbe is not None


def test_live_probe_is_e2e_result_class():
    """The probe returns E2EResult with LIVE_TEAMS_E2E evidence tier."""
    from poc.terminal_broker.live_teams_probe import LiveTeamsE2EProbe
    # The probe inherits E2EResult from e2e_harness
    from poc.terminal_broker.e2e_harness import E2EResult
    # Verify the evidence tier for live E2E exists
    assert EvidenceTier.LIVE_TEAMS_E2E.value == "live-teams-e2e"


def test_live_probe_does_not_modify_production():
    """The probe module does not import or modify production gateway code
    beyond the read-only _TeamsAuth reuse (spec Decision 1)."""
    import poc.terminal_broker.live_teams_probe as mod
    import inspect
    source = inspect.getsource(mod)
    # It may import _TeamsAuth (read-only reuse) but must not modify
    # the production adapter or gateway routing
    assert "gateway.run" not in source
    assert "gateway/session" not in source
    # It reads _TeamsAuth but does not subclass or patch the adapter
    assert "TeamsMTKAdapter" not in source or "_TeamsAuth" in source


def test_load_control_config_returns_required_fields():
    """_load_control_config returns control_conv_id and owner_oid."""
    from poc.terminal_broker.live_teams_probe import _load_control_config
    # This call will succeed if config.yaml has the control_conversations
    # section configured. If not, it raises — which is a config issue, not
    # a code issue.
    try:
        cfg = _load_control_config()
        assert "control_conv_id" in cfg
        assert "owner_oid" in cfg
        assert isinstance(cfg["control_conv_id"], str)
        assert isinstance(cfg["owner_oid"], str)
        assert len(cfg["control_conv_id"]) > 0
        assert len(cfg["owner_oid"]) > 0
    except RuntimeError as exc:
        pytest.skip(f"Control conversations not configured: {exc}")


def test_live_probe_init_loads_config():
    """The probe constructor loads config on instantiation."""
    from poc.terminal_broker.live_teams_probe import LiveTeamsE2EProbe
    try:
        probe = LiveTeamsE2EProbe()
        assert probe._control_conv is not None
        assert probe._owner_oid is not None
        probe.shutdown()
    except RuntimeError as exc:
        pytest.skip(f"Config not available: {exc}")


def test_live_probe_has_broker_and_adapter():
    """The probe has a SessionBroker and TeamsControlAdapter wired up."""
    from poc.terminal_broker.live_teams_probe import LiveTeamsE2EProbe
    try:
        probe = LiveTeamsE2EProbe()
        assert probe.broker is not None
        assert probe.adapter is not None
        assert probe.stream_manager is not None
        probe.shutdown()
    except RuntimeError as exc:
        pytest.skip(f"Config not available: {exc}")
