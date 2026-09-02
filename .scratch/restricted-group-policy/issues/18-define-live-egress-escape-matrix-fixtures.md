# Define the live Egress Escape Matrix fixtures

Type: grilling
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 09, 11

## Question

Which exact non-production identities and controlled harness will execute the Egress Escape Matrix without touching production? Decide the authenticated origin TestGroup, cross-group sink, owner DM, alternate thread/topic, alternate platform and adapter account/tenant, native and relay routes, independent readback principals, unique marker namespace, controlled pre-gate reachability method, cleanup contract, and which unsupported dimensions require a contract-test adapter. The result must make every matrix row executable and auditable without storing protected content or credentials in the tracker.

## Resolution

### Origin TestGroup

- **Authenticated origin group**: `19:cbdcf6224c48469ea048147752ed92d9@thread.v2` (existing test Teams group provided by owner)
- **Owner identity**: mtk12265 (authenticated through Control Channel / TUI)
- **Restricted Group Policy**: bound to this exact group conversation ID

### Cross-group and DM sinks (deny targets)

- **Cross-group sink**: any other Teams group conversation NOT matching `19:cbdcf6224c48469ea048147752ed92d9@thread.v2` — deny-verified by attempting send and confirming rejection
- **Owner DM**: owner's personal DM conversation — used as deny target for cross-destination escape (restricted group output must not reach owner DM unless owner explicitly authorized)
- **Alternate thread/topic**: if the test group supports topics/threads, a different thread within the same group is used to test thread-scoped delivery

### Native and relay routes

- **Native route**: Hermes Teams adapter (direct Graph API send)
- **Relay route**: webhook adapter (relay → Teams MTK gateway)
- Both routes tested for: exact-origin allow, cross-group deny, cross-DM deny, thread/topic mismatch deny

### Independent readback principals

- **Source readback**: re-fetch the originating conversation to confirm the message was delivered with unique marker
- **Target readback (deny verification)**: attempt to fetch from the deny-target conversation to confirm NO message was delivered there
- **Unique marker namespace**: each test delivery uses a unique UUID prefix (e.g., `EGRESS-TEST-{uuid}:`) so readback can distinguish test messages from any other traffic

### Controlled pre-gate reachability

- Pre-gate reachability is verified by confirming the adapter can connect and authenticate to the target platform without actually sending a restricted output
- Method: adapter health check + permission probe (can-reply check on origin group, can-not-send check on deny targets)

### Cleanup contract

- Test messages are NOT deleted — they remain in the test group as historical record
- Owner can manually clean up if desired
- No test messages should exist in deny-target conversations (if found, that's an escape — escalated)
- Cleanup outcome logged in audit (per #11 audit contract) as `cleanup=skipped`

### Egress Escape Matrix rows (from CONTEXT.md)

Each row tests one emitter path with its policy-defined outcome:

1. Final reply — exact origin: **ALLOW**
2. Streamed commentary/segment/progress/edit — exact origin: **ALLOW** (with typing indicator)
3. Explicit `send_message` text — exact origin: **ALLOW**
4. `send_message` media — exact origin: **ALLOW** (Derived Media Delivery)
5. `send_message` reaction/unreaction — exact origin: **DENY** (not a Restricted Logical Delivery purpose)
6. Loop mutation — exact origin: **DENY**
7. Native route — exact origin: **ALLOW**
8. Relay route — exact origin: **ALLOW**
9. Automatic `MEDIA:` / bare-path delivery — exact origin: **ALLOW** (as Derived Media)
10. Automatic TTS — exact origin: **ALLOW** (as Derived Media)
11. Image/audio/video/document delivery — exact origin: **ALLOW** (as Derived Media)
12. Cron fan-out — cross-group: **DENY**
13. Cron mirroring — cross-group: **DENY**
14. Delegated/background completion — direct subagent delivery: **DENY** (must return through Egress Broker)
15. Kanban notification — cross-group: **DENY**
16. Plugin/webhook/API emitter — exact origin: **ALLOW** or **DENY** per policy
17. Future registered adapter — exact origin: **ALLOW** or **DENY** per policy

Each row verifies:
- Safe pre-gate reachability (adapter can connect)
- Policy-defined exact-origin outcome (allow or deny)
- Forced cross-group/DM/platform denial before adapter invocation
- Independent source-and-target readback with unique markers
- Restart and indeterminate-result reconciliation
- Same-identity retry only after confirmed absence
- Cleanup

### Unsupported dimensions (contract-test adapter required)

- **Alternate platform**: if only Teams is available, alternate-platform rows use a contract-test adapter that simulates a non-Teams platform with the same Egress Broker interface
- **Alternate adapter account/tenant**: if only one Teams service account is available, alternate-account rows use a contract-test adapter
- **Webhook/API emitter**: if no live webhook is configured, webhook rows use a contract-test adapter

### No protected content in tracker

- Test messages contain only public markers (UUID prefix + `EGRESS-TEST`)
- No PII, NDA, credentials, or CQ content in any test message
- All test evidence is content-minimized per #11 audit contract
