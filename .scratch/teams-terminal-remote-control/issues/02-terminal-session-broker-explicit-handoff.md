# 02: Terminal Session Broker with Explicit Handoff

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

The POC can manage one or more named terminal sessions, report their state, route input to the explicitly selected session, and switch exclusive input authority between local and remote control without restarting the child process.

**Blocked by:** 01 — Windows PTY Bridge POC Contract.

**Status:** ready-for-agent

- [ ] Every session receives a unique opaque session ID.
- [ ] Status exposes running/exited, PID, uptime, working directory, dimensions, and last-output information.
- [ ] Input is serialized so concurrent writers cannot interleave bytes.
- [ ] Local mode accepts local input and rejects remote input.
- [ ] Remote mode accepts remote input and rejects local input.
- [ ] Switching modes preserves the same child process identity.
- [ ] Output has monotonic cursor/sequence metadata for incremental consumers.
- [ ] Closing one session does not affect another session.
