## Why

The Teams MTK adapter has a group-whitelist baseline (`teams-mtk-group-whitelist`) that admits a group and controls toolsets/keywords, and a native-parity baseline (`teams-mtk-hermes-native-parity`) that owns transport, streaming, reply, file, and E2E behavior. But there is no **per-operation capability authority** — once admitted, the model can call any enabled tool, send to any destination the adapter supports, fall back to a relay when a native route fails, retry without idempotency, resume blindly after restart, or route to a non-approved model provider. The only security boundary is `GATEWAY_ALLOWED_USERS` + `blocked_toolsets`, which is a coarse list, not a policy. An authenticated owner has no way to let members of a designated Teams group query and export internal systems (ALPS/MOLY) through the owner's account while enforcing:

- Global read-only behavior on CQ systems (no writes, no mutations, no raw queries)
- Per-group temporary storage with no cross-group leakage
- Origin-bound Teams egress (replies, streams, edits, files, reactions, TTS, cron, delegation results — everything stays in the originating group, never escapes to DM, another group, another platform, or a relay fallback)
- MTK-internal model routing only (no third-party providers)
- Privacy-preserving optimization capture and owner-approved knowledge promotion
- Durable approval state with restart-safe resume
- Confidence-gated production failure triage
- Content-minimized, tamper-evident audit

This change replaces toolset/keyword-only restriction with a **Restricted Group Policy** framework: a fail-closed, per-operation capability authority enforced by a Core-owned Egress Broker, a CQ Read Broker, a model-routing gate, and an append-only audit chain — activated through explicit owner approval and verified by adversarial E2E before production go-live.

## What Changes

- Introduce a new `gateway/restricted_origin.py` module that creates an immutable `OriginEgressBinding` at gateway ingress, binding every Restricted Task to its exact profile, policy identity/version, platform, adapter, account/tenant, chat/conversation, thread/topic, and Durable Task identity via ContextVar.
- Introduce a Core-owned **Egress Broker** that sits between every outbound emitter and the adapter edge. The Broker validates delivery purpose, origin equality, route equality, task liveness, provenance, content fingerprint, and current policy revision; persists a pre-side-effect `EgressIntent`; issues a one-use permit bound to the exact operation, destination, route, payload, and revision; invokes the adapter; and records the structured outcome and actual remote handle. Adapters deny Restricted-context calls without a valid permit.
- Introduce a **CQ Read Broker** that exposes exactly seven read-only operations against ALPS/MOLY systems and denies raw-query, mutation, credential, and all write operations. All member credentialed access goes through the broker; the model never sees the owner's credentials.
- Introduce an **AIDE-only model-routing gate** (`authorizeAndInvoke`) that reloads the current policy revision and matches the complete route identity (provider, model, base_url, route class) before every model invocation. A non-AIDE route never passes; a revision change between permit and invoke invalidates the permit.
- Introduce a **content-minimized, tamper-evident audit chain** — SQLite WAL, append-only, HMAC-SHA256-chained, fingerprints only (no raw prompts, CQ content, attachments, credentials, or generated code). Write-before-execute: an `intent` phase record is committed before any restricted operation; an `outcome` phase record after. Restart marks unmatched intents as `indeterminate`.
- Introduce a **disposable per-group execution sandbox**: each restricted task gets a fresh policy-stamped sandbox; all credentialed access is brokered; the sandbox is destroyed at task end.
- Introduce a **durable approval state and restart-safe resume**: owner approval is a metadata-only Durable Task; first-wins; zero raw sensitive persistence; restart reconciles completion rather than replaying blindly.
- Introduce **confidence-gated production failure triage**: >90% confidence blocks the inferred function while unrelated operations continue; ≤90% holds the triggering operation for 24h; adversarial error text cannot escalate authority.
- Introduce **privacy-preserving learning and knowledge promotion**: de-identified Optimization Records and Shared Knowledge Candidates with 30-day expiry and owner-approved PKB promotion.
- Introduce **CQ export consistency**: stable sort + duplicate/gap detection + 8 fail-closed conditions → `INCOMPLETE_RESULT` on inconsistency across changing pages.
- Introduce **exact-group semantic history retrieval**: reply-chain traversal + sliding-window recent messages, backwardLink pagination for full history; no mechanical pre-filter (LLM judges relevance); attachments as preview with two-phase broker fetch; no redaction; history injected as standalone user message with assistant ack for role alternation; identity bound to exact `conv_id` with three-layer forced marker tests for zero cross-conversation leakage.
- Introduce an **owner approval protocol**: profile-local canonical request with Control Channel/TUI projections; immutable first-wins; metadata-only restart; PII/NDA authorizes one exact-payload/exact-destination logical delivery.
- Introduce a **production go-live gate**: exact owner activation, scoped defect acceptance, progressive per-capability version visibility, and selective failure triage.
- Define a **live Egress Escape Matrix** (17 rows) and a **non-egress adversarial E2E matrix** (11 rows) as production-acceptance contracts, both using the existing test group as origin and contract-test adapters for unsupported dimensions.
- Define a **production rollout and post-deploy verification plan**: per-seam independent probes, auto-hold on violation with owner notification, 30 consecutive violation-free operations as exit criteria.
- Preserve the existing `teams-mtk-group-whitelist` admission/mention/config baseline. The group whitelist continues to control *who gets in*; Restricted Group Policy controls *what they can do once admitted*.

## Capabilities

### New Capabilities

- `restricted-group-policy`: Per-operation capability authority for Teams MTK restricted groups, including origin-bound egress, CQ read broker, model-routing gate, audit chain, disposable sandbox, durable approval, confidence-gated triage, privacy-preserving learning, CQ export consistency, semantic history retrieval, and production rollout verification.

### Modified Capabilities

- `teams-mtk-group-whitelist`: The group whitelist's `blocked_toolsets` and `blocked_keywords` remain as a first-pass coarse filter, but a group configured for Restricted Group Policy additionally binds a policy identity and version that the Egress Broker, CQ Broker, and model gate consult. The whitelist no longer serves as the security boundary for RGP-enabled groups — the per-operation capability authority does.

## Impact

- **Gateway**: new `gateway/restricted_origin.py` module; modifications to `gateway/session_context.py` (new ContextVars for policy/origin/task identity), `gateway/delivery.py` (broker gate before transport resolution), `gateway/stream_consumer.py` (broker gate before send/edit), `gateway/run.py` (broker gate for TTS/media, status notices, cron delivery, Kanban delivery), `gateway/kanban_watchers.py` (broker gate for Kanban notification/artifact delivery).
- **Tools**: modifications to `tools/send_message_tool.py` (broker gate for all send/react/loop operations).
- **Agent**: new `agent/restricted_authority.py` or extension of `agent/execution_authority.py` for Restricted Group capability resolution; new audit module under `get_hermes_home() / "audit" / "restricted_group.db"`.
- **Config**: new `restricted_group` section in `config.yaml` for policy definitions, capability grants, group bindings, and activation state.
- **CLI**: new CLI subcommands for policy management, audit reports, and activation control.
- **Cron**: modifications to `cron/scheduler.py` for broker-gated delivery and fan-out prevention.
- **Compatibility**: RGP-enabled groups gain per-operation enforcement; non-RGP groups continue with the existing whitelist behavior. No change to authenticated owner's local CLI/TUI full permissions.
- **Restart requirement**: gateway restart required to activate Restricted Group Policy for the first time.
