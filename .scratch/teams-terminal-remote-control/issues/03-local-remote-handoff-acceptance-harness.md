# 03: Local/Remote Handoff Acceptance Harness

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

A deterministic local harness and remote-simulation client can operate the same persistent terminal session, switch control in both directions, and produce evidence that the child was not restarted and that output was neither duplicated nor lost.

**Blocked by:** 02 — Terminal Session Broker with Explicit Handoff.

**Status:** ready-for-agent

- [x] Local input produces a known response marker.
- [x] Remote-simulation input produces a different known response marker from the same child.
- [x] Local → remote → local handoff preserves the child identity.
- [x] The harness proves no restart occurred during mode transitions.
- [x] Output ordering is preserved.
- [x] Output contains no duplicate or missing markers.
- [x] The handoff does not create an unrelated foreground window.
- [x] The harness emits a clear PASS/FAIL verdict with diagnostic evidence.
- [x] The result is explicitly labelled local harness evidence, not Teams E2E evidence.
