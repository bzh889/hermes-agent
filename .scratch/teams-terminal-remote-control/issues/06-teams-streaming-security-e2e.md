# 06: Teams Streaming and Security E2E

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

The owner can monitor and control a broker-owned terminal from the Teams mobile client with incremental output, correct session targeting, secure authorization, and clear failure states on the real gateway path.

**Blocked by:** 05 — Teams Control-Channel Adapter Integration.

**Status:** ready-for-agent

- [ ] Terminal output reaches Teams incrementally through the existing streaming/edit path.
- [ ] Streaming updates remain one logical edited reply and do not create duplicate progress/footer messages.
- [ ] Teams read-back matches the actual terminal output.
- [ ] Output cursors do not cause missing or duplicate content.
- [ ] Unauthorized conversation and unauthorized sender paths are both denied.
- [ ] Stop affects only the requested session.
- [ ] Gateway restart, child exit, and PTY failure produce explicit user-visible states.
- [ ] Real Teams E2E evidence is separated from local unit and harness evidence.
- [ ] The result records whether the next Codex, Claude Code, and Hermes TUI investment is justified.
