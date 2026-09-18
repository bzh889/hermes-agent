# Windows Terminal Remote Control POC

**Status:** ready-for-agent
**Type:** standalone POC specification
**Research:** `docs/research/teams-terminal-remote-control.md`

## Problem Statement

The owner can already use Hermes through the Teams MTK gateway, but cannot yet use Teams from a phone to observe and control a Windows Terminal session running on this PC.

The desired capability is a persistent terminal session that can continue running locally while also being controllable remotely through the owner's exact Teams control channel. The owner must be able to switch between local keyboard control and Teams remote control without restarting the shell, losing session state, duplicating input, duplicating output, or bringing a new window to the foreground.

The first POC is intended to establish whether this control plane is worth integrating into Hermes production. It must use text stdin/stdout as the primary I/O path. Screenshots, OCR, and UI automation are fallback investigation paths, not the primary POC interface.

## Solution

Build a throwaway, Windows-only Terminal Session Broker POC outside the production Teams gateway.

The broker owns a newly created Windows PTY/ConPTY session and exposes a narrow public interface for:

- creating a session;
- reading text output;
- writing text input;
- reporting session state;
- switching the active input authority between local and remote control;
- resizing the terminal;
- closing the session.

A local POC harness will act as the local terminal side and a remote-simulation client will act as the future Teams side. The harness must prove that both sides operate on the same child process and that handoff is state-preserving.

After the broker and handoff harness pass, a separate integration slice may connect the broker to the Teams MTK gateway. That integration must enforce both the exact configured Teams control conversation and the owner's immutable sender OID on every turn. It must use existing Teams streaming/edit delivery rather than creating a second messaging transport.

An independent existing-tab attach probe will investigate whether an arbitrary Windows Terminal tab that was not started through the broker can be observed or controlled. A negative result is an acceptable and useful outcome; it must not block the broker-owned POC.

## User Stories

1. As the PC owner, I want to start a persistent Windows terminal session through the broker, so that the session has a stable identity for local and remote control.
2. As the PC owner, I want to see terminal output locally, so that the broker does not replace normal Windows Terminal use.
3. As the PC owner, I want to see the same terminal output through the remote control client, so that I can monitor work from my phone.
4. As the PC owner, I want to send input locally, so that ordinary keyboard use continues to work.
5. As the PC owner, I want to send input remotely, so that I can operate the same shell while away from the PC.
6. As the PC owner, I want to switch input authority from local to remote without restarting the child process, so that long-running commands and interactive sessions retain their state.
7. As the PC owner, I want to switch input authority from remote back to local without restarting the child process, so that I can resume work at the keyboard.
8. As the PC owner, I want the broker to reject remote input while local control is active, so that remote commands cannot unexpectedly interfere with local typing.
9. As the PC owner, I want the broker to reject local input while remote control is active when exclusive control is selected, so that two writers cannot race.
10. As the PC owner, I want output to remain observable during either control mode, so that changing input ownership does not hide process state.
11. As the PC owner, I want each output chunk to have one routing path, so that Teams or the remote client does not show duplicate output.
12. As the PC owner, I want the broker to preserve output ordering, so that command results remain understandable.
13. As the PC owner, I want the broker to expose running/exited state, PID, uptime, working directory, and last-output information, so that I can determine whether a remote session is healthy.
14. As the PC owner, I want to resize the PTY, so that interactive programs receive a valid terminal size.
15. As the PC owner, I want to close a named session explicitly, so that stopping one session does not affect another.
16. As the PC owner, I want multiple sessions to have independent identities and lifecycle, so that Codex, Claude Code, Hermes TUI, and ordinary shells can later be managed separately.
17. As the PC owner, I want a remote command to identify its target session explicitly, so that commands cannot accidentally reach another terminal.
18. As the PC owner, I want a failed or unavailable Windows PTY dependency to produce an explicit diagnostic, so that the POC does not silently claim interactive support when it has fallen back to pipe mode.
19. As the PC owner, I want the broker to avoid creating or raising an unrelated foreground window, so that remote monitoring does not interrupt my current work.
20. As the PC owner, I want the local/remote handoff harness to prove that the same child process survives the transition, so that a passing command response is not mistaken for session continuity.
21. As the PC owner, I want an existing Windows Terminal tab to be investigated separately, so that the POC distinguishes broker-owned sessions from post-hoc attachment.
22. As the PC owner, I want the existing-tab probe to fail clearly when no supported attach seam exists, so that unsupported process injection is not mistaken for a production design.
23. As the PC owner, I want Teams control restricted to my exact control conversation and immutable sender identity, so that another Teams user or conversation cannot operate the PC.
24. As the PC owner, I want Teams status and output delivered through the existing gateway transport, so that the POC does not introduce a second Teams authentication or message pipeline.
25. As the PC owner, I want the first Teams integration to expose status, output, input, mode switching, and stop operations only, so that the remote control surface remains narrow and auditable.
26. As the PC owner, I want the POC result to state separately whether broker-owned control and existing-tab attach passed, so that investment decisions are based on the correct evidence.

## Implementation Decisions

1. The first implementation is a throwaway POC and must not modify the production Teams adapter or production gateway routing.
2. The broker-owned session is the primary architecture. It creates the PTY before starting the child process and retains ownership of the I/O boundary for the lifetime of the session.
3. The first child process is a deterministic PowerShell or command-shell fixture that emits known markers and accepts known input. Codex, Claude Code, and Hermes TUI are not first-wave acceptance targets.
4. The public broker contract is intentionally narrow: create, list/status, read output, write input, set control mode, resize, and close.
5. Every session has an opaque stable session ID. A session record includes process identity, lifecycle state, control mode, dimensions, working directory, and output cursor/sequence metadata. Raw credentials and secrets are not part of the session record.
6. Control mode is explicit. The initial modes are `local` and `remote`; remote input is accepted only in `remote` mode, and local input is accepted only in `local` mode for exclusive handoff tests. Output remains observable in both modes.
7. Input is serialized through one broker-owned writer. The broker must not accept concurrent writes that can interleave bytes.
8. Output is read once from the PTY and assigned a monotonic sequence or cursor before fan-out. Consumers use the cursor to avoid duplicate delivery.
9. The local harness and remote-simulation client are separate consumers of the broker contract. The remote-simulation client stands in for Teams but does not require Teams credentials or a live gateway.
10. The existing-tab attach probe is an independent experiment. It may inspect process relationships, Windows Terminal CLI behavior, console APIs, UI Automation, and other documented mechanisms, but it must not use unsupported process injection as the basis for the recommended architecture.
11. If the existing-tab probe cannot obtain a reliable bidirectional text stream and preserve local use, it reports `unsupported` rather than silently falling back to screenshot-only control.
12. The future Teams integration uses the existing Teams MTK adapter and its existing streaming/edit delivery path. It does not introduce a second Teams client or Graph webhook for the POC.
13. Teams authorization is evaluated per inbound turn using the exact control conversation and immutable sender OID. Display names, message text, previous turns, and cached agent identity are not authorization inputs. This follows the existing owner control-channel decision in ADR 0003.
14. The initial remote command vocabulary is limited to session status, output retrieval, input write, local/remote mode switch, and stop. Arbitrary shell execution from arbitrary Teams conversations is out of scope.
15. The POC must report the distinction between `source-confirmed`, `harness-verified`, `live Teams E2E`, and `unknown`. A local harness pass is not a Teams E2E pass.

## Testing Decisions

1. Tests assert external behavior through the four approved seams: PTY Bridge, Session Broker, local/remote handoff harness, and later Teams integration.
2. Tests must not inspect private handles, thread implementation, internal queue names, or source text as a substitute for behavior.
3. The PTY Bridge seam tests spawn/read/write/resize/close behavior with deterministic child fixtures. Existing project prior art includes `tests/hermes_cli/test_win_pty_bridge.py`, `tests/hermes_cli/test_pty_bridge.py`, and `tests/tools/test_terminal_tool_pty_fallback.py`.
4. The Session Broker seam tests session identity, lifecycle, explicit target routing, serialized writes, output cursors, mode transitions, and close isolation.
5. The local/remote handoff seam must prove process continuity using a child-generated identity marker before and after mode changes. It must verify no output duplication and no missing marker.
6. The harness must verify that control-mode transitions do not create a new foreground window or restart the child process.
7. Existing-tab attach is tested as a capability probe with explicit `supported`, `unsupported`, or `indeterminate` verdicts. `indeterminate` is not a pass.
8. Teams integration tests must include both allow and deny paths. The allow path requires the exact control conversation plus owner OID; changing either must deny the operation.
9. Teams streaming tests must read back the actual delivered content and distinguish one logical edited reply from multiple duplicate messages. Log-only evidence is insufficient for content claims.
10. The POC must run on the actual Windows environment with the repository's supported test runner where applicable. A unit test or local mock cannot be reported as live Teams E2E.
11. Any failed test is investigated as an implementation or environment issue; tests must not be weakened merely to obtain a pass.

## Out of Scope

- Production integration into `gateway/platforms/teams_mtk.py` before the broker and handoff harness pass.
- Arbitrary post-hoc attach to every existing Windows Terminal tab as a guaranteed feature.
- Undocumented process injection, kernel hooks, credential extraction, or security-boundary bypasses.
- Screenshot/OCR as the primary terminal I/O mechanism.
- Graph change notifications, public webhook deployment, or Bot Framework registration.
- Multi-user terminal collaboration.
- General remote desktop or Windows Terminal UI replacement.
- Formal Codex, Claude Code, or Hermes TUI compatibility certification in the first POC.
- Production persistence, upgrade migration, or cross-machine session replication.
- Commit, push, or deployment of the POC without a separate review and explicit decision.

## Further Notes

The feasibility research is recorded in `docs/research/teams-terminal-remote-control.md`. It identifies broker-owned ConPTY sessions as the high-confidence path and existing-tab post-hoc attachment as a separate uncertain capability.

The POC's investment decision is based on two independent verdicts:

- **Broker-owned session verdict:** can local and remote clients share one persistent Windows PTY session with correct I/O and handoff semantics?
- **Existing-tab attach verdict:** can an unprepared Windows Terminal tab be controlled bidirectionally without restart or loss of local usability?

A successful broker-owned verdict is sufficient to justify investigating Codex, Claude Code, and Hermes TUI integration, but it does not by itself prove arbitrary existing-tab attachment.
