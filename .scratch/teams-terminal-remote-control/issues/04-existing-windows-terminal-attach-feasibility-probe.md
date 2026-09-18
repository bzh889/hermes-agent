# 04: Existing Windows Terminal Attach Feasibility Probe

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

An independent probe determines whether an arbitrary Windows Terminal tab that was not started through the broker can provide reliable bidirectional text I/O while preserving the user's local operation. A clear unsupported result is a valid deliverable.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The probe distinguishes process discovery, visible text capture, stdout access, and stdin injection.
- [ ] It evaluates documented Windows Terminal CLI, console, PTY, process, and UI Automation capabilities without relying on unsupported injection.
- [ ] If supported, the probe demonstrates bidirectional I/O on the same existing session without restart.
- [ ] If unsupported, it returns `unsupported` with evidence rather than using screenshot/OCR as a substitute for text I/O.
- [ ] `indeterminate` is reported separately and is not counted as a pass.
- [ ] The probe does not extract credentials, bypass authorization, or damage the existing terminal.
- [ ] The result is independent of and does not block the broker-owned POC.
