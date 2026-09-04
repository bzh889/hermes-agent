# MTK Upstream Merge — Verification & Switch Checklist

> **When to use**: After Claude Code / Codex completes the merge on `upgrade/upstream-YYYYMMDD`.
> Run every gate in order. If any gate fails, stop and report — do NOT switch to the upgrade branch.

## Gate 1: Git Layer

```bash
cd "D:\01_Job\Tool\Hermes Agent"

# 1.1 Confirm branch
git branch --show-current
# EXPECT: upgrade/upstream-YYYYMMDD

# 1.2 No residual conflict markers
git diff --check
# EXPECT: no output

# 1.3 MTK critical files exist
for f in \
  gateway/platforms/teams_mtk.py \
  teams_skype_sdk/__init__.py \
  agent/aide_gateway.py \
  agent/execution_authority.py \
  agent/strategy_runtime.py \
  agent/garbage_detector.py \
  gateway/egress_broker.py \
  gateway/egress_wiring.py \
  gateway/audit_chain.py \
  gateway/cq_broker.py \
  gateway/durable_approval.py \
  gateway/model_routing_gate.py \
  gateway/restricted_group_gate.py \
  gateway/restricted_history.py \
  gateway/restricted_origin.py \
  gateway/restricted_sandbox.py \
  gateway/phase5_capabilities.py \
  gateway/platform_config_bridges.py \
  hermes_cli/aide_models.py \
  hermes_cli/subcommands/teams_mtk.py \
  hermes_cli/teams_mtk_groups.py \
  hermes_cli/desktop_entry.py \
  hermes_cli/gateway_control_entry.py \
  hermes_cli/gateway_runtime_entry.py \
  hermes_cli/venv_entry.py \
  plugins/image_gen/aide/__init__.py \
  plugins/tts/aide/__init__.py \
  plugins/transcription/aide/__init__.py \
  hermes.bat \
  hermes.sh \
  hermes-desktop.bat \
  hermes-web.bat \
  docs/mtk-upstream-upgrade-runbook.md \
; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done
# EXPECT: all OK, 0 MISSING
```

## Gate 2: Python Imports

```bash
cd "D:\01_Job\Tool\Hermes Agent"
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null

python -c "
from gateway.platforms.teams_mtk import TeamsMTKAdapter; print('1/8 teams_mtk OK')
from agent.aide_gateway import *; print('2/8 aide_gateway OK')
from gateway.egress_broker import *; print('3/8 egress_broker OK')
from gateway.cq_broker import *; print('4/8 cq_broker OK')
from agent.strategy_runtime import *; print('5/8 strategy_runtime OK')
from agent.garbage_detector import *; print('6/8 garbage_detector OK')
from hermes_cli.aide_models import *; print('7/8 aide_models OK')
from gateway.restricted_group_gate import *; print('8/8 restricted_group_gate OK')
"
# EXPECT: 8/8 OK, 0 ImportError

# Also verify upstream new modules import cleanly
python -c "
import hermes_state; print('hermes_state OK')
import run_agent; print('run_agent OK')
import cli; print('cli OK')
import model_tools; print('model_tools OK')
"
# EXPECT: all OK
```

## Gate 3: Test Suite

```bash
cd "D:\01_Job\Tool\Hermes Agent"

# Run in this order — agent/gateway first (most likely to catch merge issues)
scripts/run_tests.sh tests/agent/ -q
# EXPECT: all PASS (FLAKY markers acceptable)

scripts/run_tests.sh tests/gateway/ -q
# EXPECT: all PASS

scripts/run_tests.sh tests/tools/ -q
# EXPECT: all PASS

scripts/run_tests.sh tests/hermes_cli/ -q
# EXPECT: all PASS

scripts/run_tests.sh tests/teams_skype_sdk/ -q
# EXPECT: all PASS
```

## Gate 4: TUI Build

```bash
cd "D:\01_Job\Tool\Hermes Agent\ui-tui"
npm install
npm run build
# EXPECT: build succeeds, no TS errors

npm test
# EXPECT: all vitest tests PASS

cd ..
```

## Gate 5: Behavior Verification (runbook Section 4)

> These require actual startup. Run on the upgrade branch.

### 5a. Gateway + Teams MTK

```bash
# Start gateway (in a terminal that stays open)
hermes gateway
```

Check:
- [ ] Process stays alive (PID does not exit)
- [ ] `gateway_state` reports `running`
- [ ] `teams_mtk` platform reports `connected`
- [ ] Send a real Teams 1-to-1 message → bot receives it
- [ ] Bot replies → message arrives in Teams chat
- [ ] Stop gateway cleanly (Ctrl+C or /stop)

### 5b. TUI

```bash
# In a separate terminal
hermes --tui
```

Check:
- [ ] TUI launches without error
- [ ] Provider picker shows AIDE models
- [ ] Submit a prompt → get a response
- [ ] No "gateway ready timeout"
- [ ] Exit cleanly (Ctrl+C or /quit)

### 5c. (Optional) Desktop

```bash
hermes dashboard
```

Check:
- [ ] Dashboard opens in browser
- [ ] Chat page loads
- [ ] Can submit a prompt

## Switch Procedure (ALL gates passed)

```bash
cd "D:\01_Job\Tool\Hermes Agent"

# 1. Push upgrade branch to fork (remote backup)
git push fork upgrade/upstream-YYYYMMDD

# 2. Switch to mtk-integration
git checkout mtk-integration

# 3. Fast-forward to upgrade branch
git merge --ff-only upgrade/upstream-YYYYMMDD

# 4. Push updated mtk-integration to fork
git push fork mtk-integration

# 5. Delete upgrade branch (keep backup branch!)
git branch -d upgrade/upstream-YYYYMMDD

# 6. Verify final state
git log --oneline -1
# EXPECT: the merge commit at HEAD

git branch --show-current
# EXPECT: mtk-integration

git status --short
# EXPECT: clean
```

## Rollback (if any gate fails)

```bash
cd "D:\01_Job\Tool\Hermes Agent"

# Abort merge if still in progress
git merge --abort 2>/dev/null

# Switch back to original
git checkout mtk-integration

# Delete the failed upgrade branch
git branch -D upgrade/upstream-YYYYMMDD

# Verify nothing was touched
git log --oneline -1
# EXPECT: 22c055738 (or whatever the pre-upgrade HEAD was)

# Backup branch backup-mtk-pre-upgrade-YYYYMMDD is still intact
git branch | grep backup
```

## Final Notes

- **Backup branch** `backup-mtk-pre-upgrade-YYYYMMDD` must survive until all behavior is verified in production for at least 1 day.
- **Do NOT force-push** mtk-integration during switch — use `--ff-only` merge only.
- **Do NOT delete** the backup branch until you are 100% confident the upgrade is stable.
- **Run `scripts/run_tests.sh`** (NOT raw `pytest`) — the wrapper enforces CI-parity isolation.
