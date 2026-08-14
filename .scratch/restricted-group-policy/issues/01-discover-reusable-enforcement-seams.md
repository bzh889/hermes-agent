# Discover reusable enforcement seams and bypass paths

Type: research
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by:

## Question

Which existing Hermes mechanisms can be reused to enforce a per-turn, per-operation Restricted Group Policy across Teams MTK ingress, group authorization, tool-schema exposure, dispatch, terminal/browser/code execution, plugins/MCP, delegation, cron/background work, model and auxiliary routing, same-group history retrieval, origin-bound egress, owner approval, and temporary-workspace lifecycle? Identify every runtime bypass that a capability taxonomy and authority check must cover, and separate reusable mechanisms from missing enforcement seams.

The answer must cite executable call paths and behavioral tests rather than relying on docs, names, or schemas alone. It must also inspect the existing ALPS/MOLY clients to determine whether a narrow credential-owning read broker can reuse them without exposing their write surface.

## Comments

- Research dispatched to a background agent. Findings target: [`../research/01-enforcement-seams.md`](../research/01-enforcement-seams.md).
- Fresh-context citation audit: [`../research/01-enforcement-seams-verification.md`](../research/01-enforcement-seams-verification.md). Verdict: the first artifact is not acceptable for resolution (8 verified, 7 partial, 6 unsupported, 5 false); the ticket remains claimed while the artifact is rebuilt from executable sources.
- The rebuilt artifact's self-verification also failed local sanity checks before resolution: it still contains approximate/TBD citations, broad or line-less source references, an invalid duplicated external path, an unchecked verification checklist, and an allow-list recommendation that conflicts with the map's chosen deny-list capability policy. A second fresh-context audit is required.
- Second fresh-context audit: [`../research/01-enforcement-seams-verification-2.md`](../research/01-enforcement-seams-verification-2.md). Verdict: not acceptable; the artifact was rebuilt again in the parent session from narrow executable evidence.
- Final fresh-context acceptance audit: [`../research/01-enforcement-seams-verification-3.md`](../research/01-enforcement-seams-verification-3.md). Verdict: **ACCEPTABLE FOR TICKET RESOLUTION** (47 verified, 8 partial, 0 unsupported, 0 false; 78/78 enumerated Python citations valid).

## Answer

The executable seam inventory is [`../research/01-enforcement-seams.md`](../research/01-enforcement-seams.md).

Reuse the trusted per-turn origin ContextVars, extend `ExecutionAuthority` for versioned policy resolution, and place a core-owned capability check around the existing tool execution middleware. Keep toolset/schema filtering as defense-in-depth exposure control, not authorization. Reuse approval correlation/transport, exact-conversation Teams fetching, and shared plugin/MCP registry routing only after mandatory capability metadata and per-operation authority checks are added.

The enforcement design must separately close authority domains that do not inherit one tool call: delegation, cron, background-process completion, all model/fallback/auxiliary routes, normal/stream/progress/relay/artifact egress, and isolated execution/cleanup. Generic Hermes memory/session search is not an acceptable substitute for exact-group semantic Teams history.

The existing CQ client can supply audited ALPS/MOLY read implementations, but `WitsSession` is not a safe model surface because one credentialed object also exposes arbitrary query state, record/note mutation, and attachment upload/delete. A narrow credential-owning broker must expose explicit read operations only; query export remains blocked until a prototype and independent CQ readback prove it mutation-free and bounded.

Implementation acceptance requires controlled pre-gate violation, post-gate denial, and independent side-effect readback across direct and indirect tools, CQ, provider routes, private sources, egress, cleanup/restart, and rollout canary/rollback. Static evidence resolves this seam-discovery ticket but does not claim the Restricted Group Policy is implemented or deployed.
