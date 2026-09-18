# 06: Teams Streaming and Security E2E

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

The owner can monitor and control a broker-owned terminal from the Teams mobile client with incremental output, correct session targeting, secure authorization, and clear failure states on the real gateway path.

**Blocked by:** 05 — Teams Control-Channel Adapter Integration.

**Status:** done

- [x] Terminal output reaches Teams incrementally through the existing streaming/edit path.
- [x] Streaming updates remain one logical edited reply and do not create duplicate progress/footer messages.
- [x] Teams read-back matches the actual terminal output.
- [x] Output cursors do not cause missing or duplicate content.
- [x] Unauthorized conversation and unauthorized sender paths are both denied.
- [x] Stop affects only the requested session.
- [x] Gateway restart, child exit, and PTY failure produce explicit user-visible states.
- [x] Real Teams E2E evidence is separated from local unit and harness evidence.
- [x] The result records whether the next Codex, Claude Code, and Hermes TUI investment is justified.
