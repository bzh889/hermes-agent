# POC Verdict: Windows Terminal Remote Control via Teams

**Date:** 2026-09-18
**Status:** Complete — POC verdict recorded
**Spec:** `.scratch/teams-terminal-remote-control/spec.md`
**Commits:** `3ee833b86` → `ac1acdee1` (tickets 01-06 + live bridge)

## Verdict Summary

| Verdict | Result | Evidence Tier |
|---------|--------|--------------|
| Broker-owned session | **PASS** | harness-verified + live-teams-e2e |
| Existing-tab attach | **unsupported** (valid negative result) | probe-confirmed |
| Investment justified | **YES** | broker-owned verdict is sufficient per spec |

## What Was Proven

### Broker-Owned Session — PASS

A Windows ConPTY session created and owned by the broker can be controlled
from both local (PC keyboard) and remote (Teams mobile) without restarting
the child process, with incremental streaming output delivered back to
Teams.

Evidence hierarchy (spec Decision 15):

1. **local-unit** (164 tests, automated):
   - PTY Bridge: spawn, read, write, resize, close, PtyUnavailableError
   - Session Broker: multi-session, explicit handoff, mode enforcement, close isolation
   - Teams Adapter: per-turn auth (conversation + sender OID), 5 command verbs, deny paths
   - Streaming Manager: one logical edited reply, cursor-based dedup, no missing/duplicate content
   - E2E Harness: 9 checks (incremental output, auth, stop isolation, failure states, evidence tier)

2. **harness-verified** (Live ConPTY, automated):
   - Handoff harness: PID 47912→47912 across local→remote→local transitions
   - E2E harness: 9/9 PASS with real ConPTY sessions on Windows 11
   - Full chain demo: Teams command → auth → broker → ConPTY → streaming → read-back

3. **live-teams-e2e** (Real Teams transport, eye-witness):
   - Step 1: POC → Teams (POST 201, message appears on phone)
   - Step 2: Teams → POC (user typed "hello-e2e", bridge received and replied)
   - Step 3: Teams → auth → ConPTY → status response → back to Teams
   - Step 4: Visible bridge — user typed 2+3 → PC terminal showed 5, phone Teams showed 5
   - Step 5: Continuity — user typed os.getpid() → both sides showed PID 21156
   - Step 6: TEST_ONLY group — user typed [POC] 99+88 → both sides showed 187

### Existing-Tab Attach — unsupported

Ticket 04 probe confirmed that an arbitrary Windows Terminal tab not started
through the broker cannot be controlled bidirectionally. ConPTY handles are
process-scoped; there is no API to attach to an existing session. This is a
valid and useful negative result. It does not block the broker-owned path.

## Investment Decision

**The next Codex, Claude Code, and Hermes TUI integration investment IS
justified** based on the broker-owned session verdict.

The broker-owned architecture creates and owns the ConPTY session from the
start, so it retains full I/O control for the lifetime of the session. This
works for any child process (Codex, Claude Code, Hermes TUI, ordinary shell)
because the broker creates the PTY before starting the child.

## Known Limitations

1. **SSL intermittent failures on MTK proxy**: The Teams Skype API
   connection through the MTK corporate proxy has intermittent SSL EOF
   errors. The bridge handles these with try/except and retries on the next
   poll cycle, but a single poll may fail. Production integration should
   use the gateway's existing `edit_message` path which has 429 backoff
   and retry logic.

2. **Self-chat echo guard**: The control conversation is a self-chat
   (`@unq.gbl.spaces`), so bot-sent and human-sent messages share the same
   sender OID. The bridge distinguishes them by `hermes_sender` property.
   Messages sent from the Teams client do not have this property; messages
   sent via the Skype API do. This works but requires the `hermes_sender`
   tag on all bot-sent messages.

3. **Group conversation requires [POC] prefix**: When using a shared group
   (TEST_ONLY), the bridge only processes messages prefixed with `[POC]`
   to avoid collision with the Hermes gateway's normal Q&A handling.

4. **No persistence**: The bridge runs as a standalone process. If it
   crashes or times out, the session is lost. Production integration
   should manage session lifecycle within the gateway process.

5. **Single session**: The POC tested one session at a time. Multi-session
   management (spec User Story 16) is implemented in the broker but not
   exercised in the live E2E.

## Architecture Decisions Confirmed

| Decision | POC Result |
|----------|------------|
| Broker creates PTY before child (Decision 2) | ✅ Works — full I/O control |
| ConPTY, not pipes (Decision 2) | ✅ PTY required for interactive sessions |
| Explicit session ID (Decision 5) | ✅ All commands target explicit session |
| Per-turn auth: conversation + sender OID (Decision 13) | ✅ Wrong conversation/sender denied |
| POC command vocabulary: status, output, input, mode, stop (Decision 14) | ✅ All 5 verbs work |
| Existing Teams transport reused (Decision 12) | ✅ Skype API POST/GET/PUT used |
| Evidence tiers separated (Decision 15) | ✅ local-unit ≠ harness-verified ≠ live-teams-e2e |

## Files

| File | Purpose |
|------|---------|
| `poc/terminal_broker/pty_bridge_poc.py` | ConPTY bridge — spawn, read, write, resize, close |
| `poc/terminal_broker/session_broker.py` | Multi-session management with explicit handoff |
| `poc/terminal_broker/handoff_harness.py` | Local/remote handoff acceptance harness |
| `poc/terminal_broker/attach_probe.py` | Existing-tab attach feasibility probe |
| `poc/terminal_broker/teams_control_adapter.py` | Teams command adapter with per-turn auth |
| `poc/terminal_broker/streaming_manager.py` | Incremental output streaming (one logical reply) |
| `poc/terminal_broker/e2e_harness.py` | End-to-end harness (9 checks, evidence classification) |
| `poc/terminal_broker/live_teams_probe.py` | Live Teams transport bridge (Skype API) |
| `poc/terminal_broker/visible_bridge.py` | Visible PC terminal + Teams two-way bridge (eye-witness proof) |
| `poc/terminal_broker/live_terminal_bridge.py` | Background ConPTY → Teams streaming bridge |
| `.scratch/teams-terminal-remote-control/spec.md` | POC specification |
| `.scratch/teams-terminal-remote-control/issues/01-06*.md` | 6 tickets, all done |

## Next Steps

1. **Production integration design** — bridge the broker into the Teams MTK
   gateway as a terminal control command handler, using the gateway's existing
   `send`/`edit_message` transport.
2. **Real target testing** — Codex, Claude Code, Hermes TUI as ConPTY child
   processes, controlled from Teams.
3. **SSL stability hardening** — retry logic for MTK proxy intermittent failures.
4. **Multi-session testing** — exercise 2+ concurrent broker sessions.
