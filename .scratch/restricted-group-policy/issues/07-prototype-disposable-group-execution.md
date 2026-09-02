# Prototype disposable per-group execution and cleanup

Type: prototype
Status: resolved
Assigned: dev
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

Which existing Hermes terminal/code-execution backend can be extended into a hard per-group and per-task boundary on Windows and remote backends, with only the task root mounted, no owner files or credentials, normalized path and reparse-point containment, controlled network access, and policy-stamped background descendants? Build the cheapest executable prototype that forces absolute-path, traversal, symlink/junction, subprocess, delayed-write, restart, `/stop`, task-end, stale-root, and daily 03:00 cases; decide lease semantics and prove exact deletion/retention without cross-group damage.

## Comments

- 2026-08-17: Disposable asset is in the uncommitted `prototype/restricted-group-execution-isolation` worktree: [README](file:///D:/01_Job/Tool/Hermes%20Agent%20Worktrees/restricted-group-execution-isolation-prototype/.scratch/restricted-group-policy/prototypes/group-execution-isolation/README.md), [interactive model](file:///D:/01_Job/Tool/Hermes%20Agent%20Worktrees/restricted-group-execution-isolation-prototype/.scratch/restricted-group-policy/prototypes/group-execution-isolation/index.html), [executable model](file:///D:/01_Job/Tool/Hermes%20Agent%20Worktrees/restricted-group-execution-isolation-prototype/.scratch/restricted-group-policy/prototypes/group-execution-isolation/isolation_model.py), and [screenshot](file:///D:/01_Job/Tool/Hermes%20Agent%20Worktrees/restricted-group-execution-isolation-prototype/.scratch/restricted-group-policy/prototypes/group-execution-isolation/prototype.png). No production Hermes code, commit, push, or deployment was made.
- 2026-08-17: The owner accepted the task-scoped disposable-sandbox lifecycle described below.

## Answer

Use a fresh disposable sandbox for each task while keeping one independently keyed Temp root for each exact Restricted Group. Each task receives a fresh sub-root under that group root; neither sandbox instances nor task roots transfer to later, queued, resumed, or other-group work.

- The sandbox mount manifest contains only the current task root. It contains no owner cwd/files, other group roots, Windows system TEMP, Hermes home/config/logs/memory/skills/cache, credentials, cookies, tokens, or arbitrary operator volumes. Relative paths are normalized beneath the task root and absolute, traversal, symlink, junction, reparse-point, stale-root-epoch, and policy-stamp mismatches fail closed. Path checking is defense in depth; the hard boundary must come from the backend sandbox rather than host-local cwd checks.
- Direct sandbox network is disabled. Authenticated ALPS/MOLY/CQ access and approved exact-origin Teams reply/artifact return stay in credential-owning, origin-bound policy brokers outside the sandbox. Credentials never enter model-visible state, generated code, mounts, environment, artifacts, audit, or group output.
- Bind every Environment Lease to the exact group identity, durable task id, policy id/version/fingerprint, root epoch, backend type and stable instance id, image/runtime fingerprint, mount manifest, no-network posture, and non-persistence posture. Re-check the current stamp at every executable boundary; mismatch revokes the lease and requires destructive teardown before new work.
- `/stop`, normal task completion, abort, and merge use the same end state: stop/destroy the backend instance so all descendants and delayed writers die, wait for teardown, delete the task root, record the cleanup verdict, and mark the lease destroyed. Do not treat `ProcessRegistry` PID tracking alone as the security guarantee.
- Startup reconciliation compares durable leases with backend inventory and force-destroys stale running/stopping instances and task roots before accepting new work. Production recovery keys on stable backend instance identity plus the policy stamp, not a bare host PID that may have been recycled.
- At daily 03:00, remove each idle group's entire Temp root. If that group has an active task, skip that whole group for the sweep and delete the active task directory immediately when it later stops or ends; other idle/stale group roots still clean independently. Artifacts already uploaded to the exact origin are outside local cleanup, while all local staging copies remain disposable.
- `LocalEnvironment` and bare `SSHEnvironment` cannot satisfy a hard boundary and must be rejected. `DockerEnvironment` is the nearest Windows/local seam only after an explicit restricted mode removes its implicit credential/skill/cache mounts, cross-process reuse, persistence, extra volumes, inherited sensitive environment, and direct network, and always force-removes the instance. Modal and Daytona may implement the same remote contract only through restricted adapters that disable Hermes-home sync/sync-back/snapshot/persistence and prove disposable instance identity plus egress control. No current backend may silently fall back to Local.

The executable prototype forces host-local cwd breakout, missing-engine fail-closed behavior, mount/network/persistence/secret-sync rejection, cross-group root separation, absolute/traversal/junction containment, policy revocation, descendant delayed-write termination, `/stop`, task completion, restart reconciliation, stale-root cleanup, and 03:00 active-group skipping without cross-group or owner-root damage. A fresh read-only audit re-ran `python -m unittest -v test_isolation_model.py`: 18 passed, 0 failed, 0 skipped in 31.371 seconds; it also found no missing child target, dependency cycle, duplicate decision pointer, resolved child absent from the map, or open child indexed as a decision before this resolution.

This is a lifecycle and contract decision, not proof of container escape resistance: this Windows host has no runnable Docker, Podman, or WSL backend. Implementation and production activation remain fail-closed until real target-backend adversarial E2E proves filesystem, owner/group/credential, subprocess/descendant, delayed-write, restart, direct-network, mount, policy-revocation, and cleanup escapes fail. That evidence belongs to the implementation/E2E and production go-live gates, not a new Wayfinder decision ticket.
