# 02 — Establish per-turn owner Execution Authority through skill maintenance

**What to build:** Establish one trusted per-turn authority model through an observable skill-maintenance workflow. A local TUI owner and the immutable owner sender in the exact configured Teams MTK control conversation can non-destructively maintain every exact skill target Hermes can resolve and load, while all other origin combinations are denied without contaminating later turns.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] One canonical non-secret Teams MTK control-conversation policy supplies both Execution Authority and Skill Write Authority; home-channel delivery is not treated as authorization.
- [ ] Execution Authority is derived from trusted runtime platform, conversation, and immutable sender identity rather than display names, transcript text, model arguments, or persisted Agent state.
- [ ] A local TUI turn can create, patch, and edit an eligible skill through the public skill-management boundary.
- [ ] The immutable owner sender in the exact configured control conversation receives the same non-destructive skill-maintenance authority as TUI.
- [ ] The owner in another conversation, another sender in the control conversation, and an ordinary Gateway origin are denied the same mutation.
- [ ] Authorized maintenance works for local, bundled, Hub-installed, external, plugin-provided, and symlinked skills when Hermes can resolve and load the exact target; legacy provenance metadata does not narrow patch/edit authority.
- [ ] Every write is bound to the resolved target and current read state; authorization for one target cannot be reused for another.
- [ ] Delete and archive remain subject to separate Destructive Curation Consent and are not implied by patch/edit authority.
- [ ] Sequential and concurrent turn tests prove authority is reset and isolated when one cached Agent processes different senders.
- [ ] Existing TUI approvals and safety checks remain observable and unchanged for authorized operations.
