#!/usr/bin/env python3
"""teams_mtk E2E gateway test runner — forwarding shim.

CANONICAL LOCATION: openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py
This file is a thin forwarder — always edit the openspec version.
"""
import runpy, os
_spec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "openspec", "changes",
                     "teams-mtk-hermes-native-parity",
                     "e2e_teams_mtk.py")
runpy.run_path(_spec, run_name="__main__")
