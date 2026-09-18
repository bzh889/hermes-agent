# 01: Windows PTY Bridge POC Contract

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

The POC can create a Windows PTY session around a deterministic shell fixture and expose reliable text input/output, resize, process identity, and close behaviour without opening or raising an unrelated foreground window.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] A deterministic Windows shell fixture can be spawned through the public POC seam.
- [ ] The harness reads a known output marker from the child.
- [ ] The harness writes a known input marker and reads the corresponding response.
- [ ] The seam exposes process/session identity and running/exited state.
- [ ] Resize and close complete without crashing or leaking the child.
- [ ] Missing/unusable PTY dependency produces an explicit diagnostic and cannot be reported as PTY success.
- [ ] The POC does not create an unrelated foreground window or steal focus.
