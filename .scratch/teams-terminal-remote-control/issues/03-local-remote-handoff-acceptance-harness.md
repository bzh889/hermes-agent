# 03: Local/Remote Handoff Acceptance Harness

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

A deterministic local harness and remote-simulation client can operate the same persistent terminal session, switch control in both directions, and produce evidence that the child was not restarted and that output was neither duplicated nor lost.

**Blocked by:** 02 — Terminal Session Broker with Explicit Handoff.

**Status:** ready-for-agent

- [ ] Local input produces a known response marker.
- [ ] Remote-simulation input produces a different known response marker from the same child.
- [ ] Local → remote → local handoff preserves the child identity.
- [ ] The harness proves no restart occurred during mode transitions.
- [ ] Output ordering is preserved.
- [ ] Output contains no duplicate or missing markers.
- [ ] The handoff does not create an unrelated foreground window.
- [ ] The harness emits a clear PASS/FAIL verdict with diagnostic evidence.
- [ ] The result is explicitly labelled local harness evidence, not Teams E2E evidence.
