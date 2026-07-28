## Why

The `mtk-integration` branch contains a long-lived set of MTK, native-Windows, and Teams MTK changes. It needs the newest official Hermes Agent changes from `origin/main` without losing existing commits, the two current uncommitted edits, Hermes memories, installed packages, or improved skills.

## What Changes

- Record independent recovery points for the current committed history and working-tree edits.
- Create a full Hermes home backup using its SQLite-safe backup path, plus an independent inventory of linked skill sources.
- Record the installed Python and Node package sets and keep an untouched Python environment as a fallback.
- Fetch the current official `origin/main`.
- Merge `origin/main` into `mtk-integration` with a merge commit rather than rewriting existing commits.
- Resolve conflicts by preserving the intent of both the upstream changes and the MTK-specific behavior.
- Restore the original uncommitted edits after the upstream merge.
- Verify history reachability, working-tree preservation, version state, and focused tests.

## Capabilities

### New Capabilities

- `safe-upstream-integration`: repeatable preservation and verification requirements for this upstream integration.

### Modified Capabilities

None.

## Impact

- **Git history**: adds one merge commit; existing commit IDs remain unchanged.
- **Working tree**: preserves edits in gateway/platforms/teams_mtk.py and 	ests/gateway/platforms/test_teams_mtk_reliability.py as uncommitted changes.
- **Runtime data**: preserves ~/.hermes memories, sessions, databases, configuration, and physical skill content in a validated full backup.
- **Linked skills**: records and verifies junction targets under ~/.hermes/skills.
- **Packages**: preserves .venv, env, and existing Node dependency directories; no cleanup or destructive reinstall is used.
- **Network**: fetches from `https://github.com/NousResearch/hermes-agent.git`.
- **Remote fork**: no push is performed during implementation or verification.
