## Why

The Teams MTK gateway adapter must provide the same dependable Hermes experience as native messaging adapters while operating through MTK's Skype-token, polling, and Trouter interfaces. The existing implementation grew across gateway, SDK, delivery, and test surfaces without a single behavior contract, allowing missing integration points, unsafe echo ownership heuristics, and false-positive E2E results to persist. In particular, an edited query keeps its message identity and is currently discarded by the monotonic cursor, while a native reply can expose only a truncated quote instead of the complete source question.

## What Changes

- Complete the Hermes platform integration surface for Teams MTK, including platform hints, status, cron delivery, contact targets, media delivery, reactions, safe deletion, search, and configuration-aware routing.
- Use `teams_skype_sdk` as the preferred transport implementation while retaining raw HTTP fallbacks for installations where the SDK is unavailable or a service operation is unsupported.
- Treat a same-identity message with a changed revision or deterministic content hash as one revised inbound query, while suppressing unchanged poll repeats.
- Promote native reply relations into the existing Hermes reply context by resolving the exact source message and preserving its complete content rather than treating a quote preview as authoritative.
- Route outbound `reply_to` delivery through the SDK's native reply operation, with explicit, observable flat-send degradation only when no native remote side effect could have started.
- Add WebSocket acceleration with reconnect and health tracking while retaining HTTP polling as the authoritative catch-up path.
- Define conversation-scoped outbound ownership and read-only inbound echo checks so quoted or forwarded Hermes content cannot be suppressed or deleted as if it were bot-owned.
- Keep dynamic contact lookup read-only unless external scopes authorize chat creation; use directory canonical names only to improve actionable fallback responses.
- Require real-gateway E2E assertions with API read-back, truthful failure handling, and cleanup for every completed live capability.
- Feed applicable gateway correctness fixes back into the external `teams_skype_sdk` polling runner, with independent tests and release history.

## Capabilities

### New Capabilities

- `teams-mtk-native-parity`: Teams MTK gateway integration, SDK-backed transport, real-time/catch-up delivery, safe message ownership, contact resolution, and real E2E acceptance contracts.

### Modified Capabilities

None. This change defines a new Teams MTK capability contract; there are no canonical specs under `openspec/specs/` whose requirements are being changed.

## Impact

- **Gateway:** the Teams MTK adapter, shared platform helpers, platform registry, status/config/session integration, and cron delivery.
- **Agent:** the existing normalized message-event reply context and Teams MTK platform hints; no second agent loop or new core tool.
- **SDK:** the separately versioned `teams_skype_sdk` package, including raw message normalization, exact message lookup, native reply delivery, and its polling runner.
- **Tests:** Teams MTK unit suites plus the change's named sequential real-gateway E2E harness.
- **Configuration:** existing `config.yaml` and credential-provider paths; no new non-secret `.env` settings.
- **Compatibility:** SDK-first paths retain raw fallbacks, WebSocket never replaces catch-up polling, and existing whitelists remain the authorization boundary.

## Out of Scope

- Replacing the Skype MSG/ChatSvc plus delegated Graph transport with the official Bot Framework adapter.
- Adding a public webhook, a second inbound source, a new Teams client, a new token cache, or a new core model tool.
- Treating the observed private Skype envelope as a Microsoft-guaranteed or cross-tenant-stable public contract.
- Native voice/video work, chat-native capability dispatch, and unrelated parity backlog items; those remain governed by their existing requirements.
