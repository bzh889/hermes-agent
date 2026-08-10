# 02 — Establish per-turn owner Execution Authority through skill maintenance

**What to build:** Establish one trusted per-turn authority model through an observable skill-maintenance workflow. A local TUI owner and the immutable owner sender in the exact configured Teams MTK control conversation can non-destructively maintain every exact skill target Hermes can resolve and load, while all other origin combinations are denied without contaminating later turns.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] One canonical non-secret Teams MTK control-conversation policy supplies both Execution Authority and Skill Write Authority; home-channel delivery is not treated as authorization.
- [x] Execution Authority is derived from trusted runtime platform, conversation, and immutable sender identity rather than display names, transcript text, model arguments, or persisted Agent state.
- [x] A local TUI turn can create, patch, and edit an eligible skill through the public skill-management boundary.
- [x] The immutable owner sender in the exact configured control conversation receives the same non-destructive skill-maintenance authority as TUI.
- [x] The owner in another conversation, another sender in the control conversation, and an ordinary Gateway origin are denied the same mutation.
- [x] Authorized maintenance works for local, bundled, Hub-installed, external, plugin-provided, and symlinked skills when Hermes can resolve and load the exact target; legacy provenance metadata does not narrow patch/edit authority.
- [x] Every write is bound to the resolved target and current read state; authorization for one target cannot be reused for another.
- [x] Delete and archive remain subject to separate Destructive Curation Consent and are not implied by patch/edit authority.
- [x] Sequential and concurrent turn tests prove authority is reset and isolated when one cached Agent processes different senders.
- [x] Existing TUI approvals and safety checks remain observable and unchanged for authorized operations.

## Comments

- 2026-08-10: Re-verified after a live local-TUI maintenance request was denied later in a turn that had manually run a cron job. `cron.run_job()` opened a nested session context, then `clear_session_vars()` replaced every outer ContextVar with an explicit empty value instead of restoring its tokens. The same TUI turn therefore lost `source=tui` before `skill_manage` evaluated authority.
- The gateway-integration regression follows `tui_gateway._set_session_context()` through the nested cron context boundary into the public `skill_manage(action="patch")` handler. It failed with `untrusted_runtime` before the fix and passed after session and runtime-cwd tokens became stack-safe; top-level cleanup still converts `_UNSET` string values to explicit empty values so stale process environment mirrors remain fail-closed.
- Fresh verification ran 78 affected test cases across 9 files with file retry disabled and no failures. A separate fresh Python runtime then bound a real TUI session, dispatched an actual no-agent cron run through `model_tools.handle_function_call`, patched and read back an existing loadable skill through the public tools, reverted and read it back again, and verified the cron execution completed successfully. The temporary job, scripts, child process, and skill marker were removed; unauthorized-source authority tests remained green.
