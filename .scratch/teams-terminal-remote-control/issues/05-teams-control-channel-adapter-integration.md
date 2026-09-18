# 05: Teams Control-Channel Adapter Integration

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

The owner can operate a broker-owned terminal session from the exact Teams control conversation using a narrow command surface for status, output, input, mode switching, and stop. The integration uses the existing Teams MTK transport and only reaches the broker after per-turn authorization succeeds.

**Blocked by:** 02 — Terminal Session Broker with Explicit Handoff; 03 — Local/Remote Handoff Acceptance Harness.

**Status:** ready-for-agent

- [ ] Remote commands target an explicit session ID.
- [ ] Status, output, input write, local/remote mode switch, and stop are supported.
- [ ] A request from any other conversation is denied.
- [ ] A request from any other sender OID is denied.
- [ ] Display name, message text, prior turns, and cached Agent identity cannot grant authorization.
- [ ] Denied requests cause no terminal input or state mutation.
- [ ] The existing Teams MTK authentication and transport are reused.
- [ ] Production gateway integration is attempted only after broker and handoff evidence passes.
