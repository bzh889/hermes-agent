# MTK Upstream Merge Context for Claude Code / Codex

> **Purpose**: This document provides everything an external coding agent (Claude Code / Codex) needs to safely merge upstream `fork/main` into `mtk-integration` without losing MTK customizations.

## 1. Repository State

| Item | Value |
|------|-------|
| Repo path | `D:\01_Job\Tool\Hermes Agent` |
| Current branch | `mtk-integration` @ `22c055738` (2026-09-04) |
| Upstream target | `fork/main` @ `63279301b` (2026-09-03) |
| Merge base | `339d968689` (2026-07-26, ~40 days ago) |
| MTK custom commits | 106 |
| Upstream new commits | 9,621 |
| Files modified on both sides | 237 (conflict risk) |
| Working tree | CLEAN (all committed) |

## 2. Remotes

```
fork    https://github.com/bzh889/hermes-agent.git  (your fork, has upstream synced)
origin  https://github.com/NousResearch/hermes-agent.git  (official, was 503)
```

`fork/main` tracks official upstream and is current as of 2026-09-03.

## 3. Safety Steps (BEFORE starting merge)

```bash
# 1. Create backup branch
git branch backup-mtk-pre-upgrade-$(date +%Y%m%d) mtk-integration

# 2. Create upgrade working branch
git checkout -b upgrade/upstream-$(date +%Y%m%d) mtk-integration

# 3. Verify clean state
git status --short  # must be empty

# 4. Record MTK file inventory
git diff --name-status fork/main...mtk-integration > /tmp/mtk-inventory.txt
```

## 4. MTK Customization Categories

### 4A. NEW FILES — Must NOT be deleted by merge (202 files)

These exist ONLY on mtk-integration. If `git merge` tries to delete them, it's a bug — restore them.

**Critical MTK modules (core functionality):**

| File | Purpose |
|------|---------|
| `gateway/platforms/teams_mtk.py` | Teams MTK platform adapter — THE central MTK integration |
| `teams_skype_sdk/` (entire dir) | Skype SDK for Teams direct integration |
| `agent/aide_gateway.py` | AIDE Gateway interface |
| `agent/execution_authority.py` | Executable skill strategies — owner control |
| `agent/strategy_runtime.py` | Strategy runtime for contracted transitions |
| `agent/garbage_detector.py` | Garbage output detection + retry |
| `gateway/egress_broker.py` | Origin-bound egress permit/deny |
| `gateway/egress_wiring.py` | Wire emitters through egress broker |
| `gateway/audit_chain.py` | HMAC-linked audit chain |
| `gateway/cq_broker.py` | CQ read broker (7 read-only ops) |
| `gateway/durable_approval.py` | Durable approval state + restart-safe resume |
| `gateway/model_routing_gate.py` | AIDE-only model routing gate |
| `gateway/restricted_origin.py` | Origin binding module + ContextVar |
| `gateway/restricted_group_gate.py` | Restricted group policy gate |
| `gateway/restricted_history.py` | Exact-group semantic history retrieval |
| `gateway/restricted_sandbox.py` | Disposable per-group execution sandbox |
| `gateway/phase5_capabilities.py` | Confidence-gated triage learning |
| `gateway/platform_config_bridges.py` | Platform config bridges for MTK |
| `hermes_cli/aide_models.py` | AIDE model discovery + metadata |
| `hermes_cli/subcommands/teams_mtk.py` | Teams MTK CLI subcommands |
| `hermes_cli/teams_mtk_groups.py` | Teams MTK group whitelist management |
| `hermes_cli/desktop_entry.py` | Desktop entry point for Windows |
| `hermes_cli/gateway_control_entry.py` | Gateway control entry point |
| `hermes_cli/gateway_runtime_entry.py` | Gateway runtime entry point |
| `hermes_cli/venv_entry.py` | Venv entry point |
| `hermes.bat` / `hermes.sh` / `hermes-desktop.bat` / `hermes-web.bat` | Windows launchers |
| `plugins/image_gen/aide/` | AIDE image generation backend |
| `plugins/tts/aide/` | AIDE TTS backend |
| `plugins/transcription/aide/` | AIDE transcription backend |

**Test files (MTK-specific, must keep):**
- `tests/gateway/platforms/test_teams_mtk_*.py` (24 files)
- `tests/gateway/test_*_broker.py`, `test_audit_chain.py`, `test_restricted_*.py`, etc.
- `tests/agent/test_strategy_runtime.py`, `test_garbage_detector.py`, etc.
- `tests/hermes_cli/test_aide_*.py`, `test_mtk_launchers.py`, etc.
- `tests/tools/test_skill_execution_authority.py`, `test_send_message_loop.py`
- `tests/run_agent/test_named_aide_fallback_policy.py`
- `tests/tui_gateway/test_identity_headers_survive_agent_build.py`
- `tests/teams_skype_sdk/` (entire dir)

**Docs / specs / scratch (safe to keep, no conflict risk):**
- `.scratch/` directory (issue trackers, research, prototypes)
- `docs/adr/` (9 ADR files)
- `docs/mtk-upstream-upgrade-runbook.md`
- `docs/plans/2026-04-21-aide-gateway-integration-plan.md`
- `docs/specs/2026-04-21-aide-gateway-integration-design.md`
- `openspec/` (change proposals, specs)
- `V17_to_V19_upgrade_analysis_zh-TW.md`
- `CONTEXT.md`

**Scratch/spike files (safe to keep or clean up):**
- `spikes/` directory, `mongo_tc50_*.py`, `run_mongo.sh`, etc.

### 4B. MODIFIED CORE FILES — High conflict risk (90 files)

These files exist on both sides and were modified by BOTH MTK and upstream.
Use this priority for conflict resolution:

| Priority | Strategy | Files |
|----------|----------|-------|
| **KEEP MTK** | MTK version wins; cherry-pick upstream fixes if needed | `gateway/run.py` (Teams wiring), `gateway/platforms/base.py` (Teams adapter hooks), `gateway/session.py` (session authority), `agent/ssl_guard.py` (truststore), `agent/credential_pool.py` (per-credential headers), `hermes_cli/main.py` (entry points, Windows) |
| **KEEP UPSTREAM** | Upstream wins; re-apply MTK hooks if needed | `hermes_state.py` (schema v30), `agent/model_metadata.py` (new models), `pyproject.toml` (deps) |
| **MANUAL MERGE** | Both sides have substantive changes; combine carefully | See below |

**Manual merge files (most critical):**

| File | MTK changes | Upstream changes | Merge strategy |
|------|-------------|-----------------|----------------|
| `run_agent.py` | AIDE provider, credential pool headers, GC detector | delegation perf, usage-less handling, stream cut fix | Keep upstream base + re-apply MTK AIDE/credential hooks |
| `cli.py` | AIDE models, Windows launchers, Teams commands | model picker, setup wizard changes | Keep upstream base + re-apply MTK commands |
| `agent/conversation_loop.py` | FailoverReason fix, garbage detection, strategy runtime | compression heartbeat, rearm reset, delegate-child cleanup | Keep upstream perf fixes + MTK garbage detector |
| `agent/chat_completion_helpers.py` | GLM-5 reasoning handling | reasoning 400 retry, mandatory-reasoning | Take upstream (subsumes MTK fixes) |
| `agent/reasoning_timeouts.py` | GLM-5 stale timeout floor | reasoning retry logic | Take upstream + re-apply GLM-5 specifics if needed |
| `agent/prompt_builder.py` | Skill authority, strategy activation | Task-learned knowledge routing | Keep upstream + re-apply MTK skill authority |
| `tools/registry.py` | MTK tool registration changes | Tool discovery changes | Merge both registration sets |
| `tools/skill_manager_tool.py` | Skill execution authority | Skill maintenance targets | Merge both |
| `tools/send_message_tool.py` | Teams MTK message sending | (may have upstream changes) | Keep MTK version |
| `gateway/config.py` | Teams MTK config bridges | Config changes | Merge both |
| `tui_gateway/server.py` | Identity headers, truststore injection | Server changes | Merge both |
| `tui_gateway/entry.py` | Truststore injection | Entry changes | Merge both |
| `hermes_constants.py` | Profile-aware paths (may be same) | Profile changes | Check if identical |

### 4C. TEST FILES — Low risk (107 files)

Most test files can be auto-merged. For MTK-specific tests:
- If upstream changed the same test file, prefer the MTK version (our tests cover MTK behavior)
- If upstream added new tests, keep both sets
- Run `scripts/run_tests.sh` after merge to verify

## 5. MTK 106 Commits (keep all)

```
22c055738 docs: update map.md with completion status + add production go-live guide
432c32ee6 fix(egress): add task liveness, content provenance, delegation brokering
b2d506754 docs(openspec): mark all restricted-group-policy tasks complete (24-35)
880f6751c feat(gateway): restricted group policy egress broker, CQ read broker, audit chain, and sandbox
0a0190a78 fix: refresh AIDE model context metadata in picker
444a534c2 fix: harden owner control configuration
5ba3d5f19 fix(gateway): close plugin and Windows test regressions
1db819bf3 docs: add restricted group policy research
678b8e012 feat(agent): add executable skill strategies and harden Windows integration
33bb3ac5f chore: refresh workspace metadata
99845ecde fix(teams-mtk): process file-only messages
02a55fa4a fix(gateway): restore nested session authority
ae5b1e319 test(teams-mtk): settle delayed cleanup mirrors
5ac488005 test(teams-mtk): cover delayed cleanup readback
d232ca96e test(teams-mtk): report cleanup errors on functional failure
4b16abfa2 test(teams-mtk): verify marker mirror cleanup
db078577a test(teams-mtk): cover user mirror cleanup
7f0accf45 test(teams-mtk): clean user E2E message mirrors
a90b2f051 fix(teams-mtk): default-deny message forwarding
994130aa6 fix(teams-mtk): preserve native replies and exact final output
8b66b4152 feat(teams-mtk): add duplicate-safe native reply delivery
e7567bf3a fix(skills): resolve plugin-provided maintenance targets
32598fd86 feat: enforce skill authority and exact Teams reply context
f3d849f5b fix(gateway): process Teams message edits exactly once
714eb512c docs: add agent workflows and Teams MTK research
b102a4239 test(gateway): finalize V19 integration verification
80c009661 fix(gateway): trust Windows certificates before startup
569986d6c fix(gateway): preserve busy group burst updates
0c097c26c docs: add V17 to V19 upgrade analysis
f7898a9cb fix(gateway): redirect busy group messages safely
0f6a66b0f fix: harden Teams model picker and context compression
3c510a80c docs: record MTK upstream upgrade runbook
05be01c23 fix(desktop): allow slow Windows backend probes
7124749bb fix(gateway): make Windows restart reliable and bounded
5b0364747 fix(windows): keep execute_code subprocesses windowless
95d99e7ee docs(openspec): archive v19 MTK upgrade
ead5a6d1c fix(windows): complete MTK integration on v19
4863d875e Merge official main 339d968 into mtk-integration
2f8b56712 test(teams-mtk): harden UI fallback verdict
d2a0d3281 fix(gateway): harden Teams MTK and Windows lifecycle
a5d05cb55 fix: harden Windows decoding and Teams E2E evidence
30c77ce4c fix(windows): harden enterprise gateway and tooling
552338b43 fix(windows): improve enterprise tooling reliability
32677b495 fix(computer_use): clean up failed cua-driver starts
93c99409a fix(windows): stop leaking ghost Terminal windows via CREATE_NEW_CONSOLE
8bc0bb9ae fix(computer_use): tolerate slow cua-driver cold starts
e55987e71 fix(tui_gateway): inject truststore so proxy-intercepted providers work
8c411d6e8 docs(teams_mtk): record S1-6 weave digest pipeline
6d43cd10d docs(teams_mtk): record S1-6 incremental scan optimizations
d6d5a6a8e docs(teams_mtk): record S1-6 PKB full-scan + incremental
ea301cba5 docs(teams_mtk): record G13-B.5 leave_chat in tasks.md
f5b418592 feat(teams_mtk): add leave_chat (outbound pair to create_chat)
595a10781 feat(teams_mtk): implement create_chat via Skype API
05213b7a5 fix(cron): use hidden-console strategy for script spawns
8e38cee93 fix(teams_mtk): adapt E2E to log redaction + add download-success log
c6011ed00 feat(teams_mtk): add model-picker authorization + platform system prompt
d3d75c6b6 feat(api-server): request-scoped disabled_toolsets + Windows test infra
e786b5e5f feat(teams_mtk): integrate verified daemon-parity payload
b5e402a2a fix(windows): spawn LSP/cron subprocesses under substring path filters
ecbb889a5 fix(teams_mtk): harden fallback and e2e evidence
b8eecfc48 test(teams_mtk): verify contact directory fallback
7fe063dd7 test(teams_mtk): eliminate live E2E false-pass gaps
416230552 fix(teams_mtk+agent+process): harden live reliability
056b2b729 fix(teams_mtk+process_registry+skills): four-category fix batch
62b39c15d feat(teams_mtk): add find-conversation E2E, fix send_typing
593a51dbf fix(teams_mtk): remove dead-code duplicate list_conversations
141fce6c1 fix(teams_mtk-e2e): eliminate 7 fake E2E test items
da3ca1ed7 feat(gateway): garbage detector tuning, streaming first-fragment gate
9e5854cc9 fix(teams_mtk): residual markdown in HTML replies
b43cbd43a feat(teams_mtk): design.md gap cleanup
110d7463d feat(teams_mtk): §16 test coverage + blocked stubs
93a56289f feat(teams_mtk): Phase 2 full
11dc8c4ae feat(teams_mtk): C-2/C-5/C-7 echo fingerprint + short-msg gating + VIP buffer
765f168ea fix(teams_mtk): control commands bypass mention gating
849027267 feat(teams_mtk): Phase 1 + 1.5 — SDK delegation + Trouter WS listener
bf816a82a fix: remove redundant function-level imports
9cdc58dec fix: UnboundLocalError on FailoverReason in conversation_loop.py
42f9ad369 fix: garbage-output detection + retry to prevent session corruption
35731d5be docs(teams-mtk): record G-MEDIA/G13-A re-loss+rebuild + cron standalone_sender_fn
09839972b fix(teams-mtk): TTL echo-guard dedup + send_typing() implementation
5335ac250 feat(teams_mtk): G-MEDIA image/doc/card send + G13-A contact lookup
bbe38367c feat(teams_mtk): Phase1 SDK integration — fetch, HTML strip, download bridge
504088abe fix(teams-mtk): token cache atomic write + auto-purge + edit throttle
016a3b84c fix(teams-mtk): echo guard + @mention preserve + parallel poll
cb8dd5239 feat(teams_mtk): reply throttle + reliability tests + E2E verified
2cfba16fe feat(teams_mtk): group whitelist config chain + token cache resilience
3f411bc7c fix(teams-mtk): MessageType.FILE→DOCUMENT + 13 attachment tests
539b3cfdb feat(teams_mtk): 429 rate-limit backoff + answer reliability
bd2920730 chore(mtk): gitignore .claude/ local settings
1170ca859 refactor(mtk,teams): conform TeamsMTKAdapter to BasePlatformAdapter
0891802a7 fix(mtk,ssl): tolerate truststore SSL contexts lacking get_ca_certs()
ddaa42410 chore(mtk): web + desktop launchers
c3b49f7a0 fix(mtk): hermes.bat double-click launches in Windows Terminal
598e32194 chore(mtk): one-click launchers for native Windows
1b2cc74ea feat(tts,transcription): MTK AIDE Gateway backends
97e295da9 feat(image_gen): MTK AIDE Gateway backend
9ef919a04 chore(mtk): Windows/AIDE setup script, integration docs, cp950 uninstall fix
ea4ae2216 feat(gateway): MTK Teams (teams_mtk) platform adapter
e8721be12 feat(aide): preserve default_headers + api_key_helper in custom-provider config
4ab911f85 docs(aide): MTK AIDE gateway setup guide in README
e592a5a72 feat(aide): user-friendly AIDE gateway error messages
8b36d4a6a feat(aide): runtime + auxiliary header resolution, model metadata & browser data
78ae57f30 feat(pool): add per-credential headers field to PooledCredential
e80c0ab9e feat(aide): model discovery with merge, alias resolution, and display formatting
0cd5e4642 feat(aide): register aide and aide-io in PROVIDER_REGISTRY
6dab8f650 chore(gitignore): ignore MTK-local junk
```

## 6. Merge Execution Plan

```bash
# Step 1: Create backup + upgrade branch
git branch backup-mtk-pre-upgrade-$(date +%Y%m%d) mtk-integration
git checkout -b upgrade/upstream-$(date +%Y%m%d) mtk-integration

# Step 2: Merge with no auto-commit (see conflicts first)
git merge fork/main --no-commit --no-ff

# Step 3: List conflicts
git diff --name-only --diff-filter=U

# Step 4: Resolve conflicts using the priority table in Section 4B
# For KEEP MTK files:    git checkout --ours <file> && git add <file>
# For KEEP UPSTREAM files: git checkout --theirs <file> && git add <file>
# For MANUAL MERGE files: edit, resolve, git add <file>

# Step 5: Verify all MTK new files still exist
for f in $(cat /tmp/mtk_new_files.txt); do
  test -f "$f" || echo "MISSING: $f"
done

# Step 6: Commit the merge
git commit -m "merge: upstream fork/main (9621 commits) into mtk-integration

Preserves 106 MTK custom commits including:
- Teams MTK platform adapter + Skype SDK
- AIDE Gateway provider integration
- Restricted group policy (egress broker, CQ broker, audit chain, sandbox)
- Executable skill strategies + owner control
- Windows lifecycle hardening
- MTK AIDE plugins (image_gen, tts, transcription)
"
```

## 7. Post-Merge Verification

```bash
# 7.1 Python tests (use run_tests.sh, NOT pytest directly)
scripts/run_tests.sh tests/agent/ -q
scripts/run_tests.sh tests/gateway/ -q
scripts/run_tests.sh tests/tools/ -q
scripts/run_tests.sh tests/hermes_cli/ -q

# 7.2 TUI build
cd ui-tui && npm install && npm run build && npm test

# 7.3 Gateway startup (critical for Teams MTK)
# Start gateway and verify:
#   - gateway_state == "running"
#   - teams_mtk platform == "connected"
#   - Send/receive a real Teams 1-to-1 message

# 7.4 TUI startup
hermes --tui
# Verify: provider picker present, prompt submits, no gateway timeout

# 7.5 Check MTK-specific imports
python -c "from gateway.platforms.teams_mtk import TeamsMTKAdapter; print('OK')"
python -c "from agent.aide_gateway import *; print('OK')"
python -c "from gateway.egress_broker import *; print('OK')"
python -c "from agent.strategy_runtime import *; print('OK')"
python -c "from hermes_cli.aide_models import *; print('OK')"
```

## 8. Upstream Themes That May Break MTK

Watch for these upstream changes that could conflict with MTK behavior:

1. **`hermes_state.py` schema v30** — trigram FTS excludes delegate transcripts. If MTK modified schema, need manual merge.
2. **`agent/conversation_loop.py` compression** — heartbeat + rearm reset. MTK has FailoverReason fix + garbage detector here.
3. **`agent/reasoning_timeouts.py`** — upstream added reasoning 400 retry. MTK has GLM-5 stale timeout floor. These should compose, not conflict.
4. **`tools/registry.py`** — both sides added registrations. Merge both sets.
5. **`gateway/run.py`** — upstream changed gateway lifecycle. MTK added Teams MTK wiring + Windows restart safety.
6. **`agent/prompt_builder.py`** — upstream added task-learned knowledge routing. MTK added skill authority + strategy activation.
7. **`cron/scheduler.py`** — upstream fixed restart handoff races. MTK added hidden-console spawn strategy.
8. **`uv.lock` / `pyproject.toml`** — take upstream version, verify MTK deps still present (truststore, teams_skype_sdk, etc.)

## 9. Files to NEVER delete or overwrite

```
gateway/platforms/teams_mtk.py
teams_skype_sdk/                    (entire directory)
agent/aide_gateway.py
agent/execution_authority.py
agent/strategy_runtime.py
agent/garbage_detector.py
gateway/egress_broker.py
gateway/egress_wiring.py
gateway/audit_chain.py
gateway/cq_broker.py
gateway/durable_approval.py
gateway/model_routing_gate.py
gateway/restricted_*.py             (all restricted_* files)
gateway/phase5_capabilities.py
gateway/platform_config_bridges.py
hermes_cli/aide_models.py
hermes_cli/subcommands/teams_mtk.py
hermes_cli/teams_mtk_groups.py
plugins/image_gen/aide/
plugins/tts/aide/
plugins/transcription/aide/
hermes.bat / hermes.sh / hermes-desktop.bat / hermes-web.bat
docs/mtk-upstream-upgrade-runbook.md
docs/adr/                           (all 9 ADR files)
.scratch/                           (entire directory)
openspec/changes/teams-mtk-*        (all Teams MTK change proposals)
openspec/changes/restricted-group-policy/
```

## 10. Working Directory Note

This repo is on **Windows 11 with Git Bash (MSYS)**. Shell commands should use POSIX syntax. Path filters for Windows-native tools need `MSYS2_ARG_CONV_EXCL='*'` prefix. Line endings: Git will warn about LF→CRLF conversion — this is normal and safe to ignore.
