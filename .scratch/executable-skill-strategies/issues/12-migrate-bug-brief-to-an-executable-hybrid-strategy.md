# 12 — Migrate bug-brief to an executable Hybrid Strategy

**What to build:** Make the real `bug-brief` capability use the generic executable-strategy system. Provider credentials, sessions, API operations, and normalized outcomes remain provider-owned; the skill owns the proven request, authentication-recovery, stopping, and evidence-review sequence; Core executes the contract without any `bug-brief` special case.

**Blocked by:** 07 — Resume Hybrid Strategies through bounded Adaptive handoffs; 08 — Enforce Teams MTK owner control-conversation execution; 09 — Preserve semantic continuity across compression and strategy versions; 10 — Escalate contract and provider failures to durable Kanban triage; 11 — Validate executable strategy packages before activation.

**Status:** ready-for-agent

- [ ] The existing live provider boundary exposes stable normalized outcomes required by the `bug-brief` strategy without moving credential or session logic into the skill.
- [ ] The owning skill publishes a compact strategy index and a validated lazy Hybrid Strategy manifest using only generic contract concepts.
- [ ] The normal successful lookup follows the declared contracted sequence and avoids model decisions between uniquely determined operations.
- [ ] An observed authentication-expired outcome follows the declared provider-owned recovery and retry transitions within finite budgets.
- [ ] Evidence interpretation or genuinely semantic routing occurs only at an explicit bounded Adaptive node and resumes the same run afterward.
- [ ] Legitimate stopping conditions terminate honestly and do not disguise an unverified workaround or fabricated fallback as success.
- [ ] Explicit activation works from local TUI and the owner Teams MTK control conversation; no-activation direct use remains Adaptive.
- [ ] Non-control Gateway origins cannot invoke the contracted `bug-brief` workflow or gain owner authority by following up on an older control-conversation intent.
- [ ] Contract Gaps and observed provider defects produce the correct de-duplicated repair-task class with real redacted evidence.
- [ ] Focused tests and a real credentialed read-only verification prove operation order, model-call boundaries, outcome normalization, trace persistence, and response correctness without logging secrets.
