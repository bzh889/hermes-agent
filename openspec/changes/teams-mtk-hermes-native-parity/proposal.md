## Why

The Teams MTK gateway adapter must provide the same dependable Hermes experience as native messaging adapters while operating through MTK's Skype-token, polling, and Trouter interfaces. The existing implementation grew across gateway, SDK, delivery, and test surfaces without a single behavior contract, allowing missing integration points, unsafe echo ownership heuristics, and false-positive E2E results to persist.

## What Changes

- Complete the Hermes platform integration surface for Teams MTK, including platform hints, status, cron delivery, contact targets, media delivery, reactions, safe deletion, search, and configuration-aware routing.
- Use `teams_skype_sdk` as the preferred transport implementation while retaining raw HTTP fallbacks for installations where the SDK is unavailable or a service operation is unsupported.
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

- **Gateway:** `gateway/platforms/teams_mtk.py`, shared platform helpers, platform registry, status/config/session integration, and cron delivery.
- **Agent:** Teams MTK platform hints and context-compression reliability where large tool results affect the next model request.
- **SDK:** the separately versioned `teams_skype_sdk` package and its polling runner.
- **Tests:** Teams MTK unit suites plus `openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py` for sequential real-gateway verification.
- **Configuration:** existing `config.yaml` and credential-provider paths; no new non-secret `.env` settings.
- **Compatibility:** SDK-first paths retain raw fallbacks, WebSocket never replaces catch-up polling, and existing whitelists remain the authorization boundary.
