## 1. Preservation

- [x] 1.1 Record the original `HEAD`, branch, upstream tracking state, full worktree inventory, and modified-file hashes.
- [x] 1.2 Create a timestamped safety branch at the original `HEAD`.
- [x] 1.3 Export an external binary patch and exact file copies for every uncommitted modification.
- [x] 1.4 Create a full hermes backup ZIP in the external upgrade directory and validate its ZIP integrity and required runtime-data entries.
- [x] 1.5 Export `pip freeze --all` from `.venv` and `venv`, and export top-level Node package inventories.
- [x] 1.6 Record all skill junction names, targets, and target content hashes; preserve physical skills in the full Hermes backup.
- [x] 1.7 Stash tracked and untracked work and verify a clean worktree.

## 2. Upstream integration

- [x] 2.1 Establish a certificate-verified GitHub transport without disabling HTTPS verification.
- [x] 2.2 Verify and fetch the exact latest official `main` commit.
- [x] 2.3 Record the fetched upstream commit and exact divergence from the preserved branch.
- [x] 2.4 Merge official `main` with `--no-ff`.
- [x] 2.5 Resolve conflicts while preserving upstream behavior and MTK-specific intent.

## 3. Worktree restoration

- [x] 3.1 Apply the retained stash without dropping it.
- [x] 3.2 Resolve restoration conflicts, if any.
- [x] 3.3 Compare the restored edits with the external patch, copies, and pre-upgrade change fingerprints.

## 4. Verification

- [x] 4.1 Prove the original `HEAD` and fetched official `main` are both ancestors of the upgraded branch.
- [x] 4.2 Prove the safety branch still names the original `HEAD` and all original commits remain reachable.
- [x] 4.3 Confirm the original uncommitted edits remain present and uncommitted.
- [x] 4.4 Validate the full Hermes backup and prove memories, sessions, and physical skills are recoverable.
- [x] 4.5 Compare Python and Node package inventories and prove the fallback `venv` was not changed.
- [x] 4.6 Verify all 44 pre-upgrade linked skills retain their recorded link type and target; retain the target content hashes and physical skills in the validated backup.
- [x] 4.7 Run focused Teams MTK tests and other checks selected from the actual conflict surface.
- [x] 4.8 Confirm no remote push occurred and report the exact final branch state.

## 5. Post-upgrade startup repair (reopened after rollback)

- [x] 5.1 Add a failing test proving optional-skill relocation builds one active-skill index instead of rescanning the full tree for every absent optional skill.
- [x] 5.2 Add a failing test proving external skill directories and Junction-backed skills are not claimed as official optional installs.
- [x] 5.3 Replace the repeated optional-skill scan with one reusable index while preserving ambiguity and content-hash checks.
- [x] 5.4 Add a failing startup test proving an existing bundled-skill manifest skips automatic full sync while explicit update/setup/manual sync paths still run it.
- [x] 5.5 Remove the duplicate management-process sync from `gateway restart`; retain guarded first-install seeding in the real gateway process.
- [x] 5.6 Add failing tests proving a web- or TUI-scoped dependency repair does not prune sibling desktop packages.
- [x] 5.7 Make workspace-scoped dependency repair additive and lockfile-preserving; do not run root `npm ci`, delete dependency directories, or touch the fallback `venv`.
- [x] 5.8 Restore missing TUI and Electron packages from existing local state/cache where possible, then build web, TUI, and desktop once.
- [x] 5.9 Update Windows launchers to prefer `.venv` with `venv` fallback and resolve Electron from both workspace-local and hoisted locations.
- [x] 5.10 Verify all 44 Junctions retain the same type and target and that no `.claude/skills` content changed.
- [x] 5.11 Perform real gateway + Teams, dashboard HTTP/assets, desktop backend/window, and TUI ready/session/provider checks.
- [x] 5.12 Measure three warm starts per surface and prove normal startup performs neither a full skill sync nor npm install/build.
- [x] 5.13 Reproduce the exact Windows `bash .\hermes.sh --tui` path and separate Git Bash, full CLI parsing, TUI build, Node, and Python gateway timings.
- [x] 5.14 Skip unchanged production TUI builds on Windows and add direct exact-`--tui` paths to the MTK Bash and native Windows launchers.
- [x] 5.15 Confirm the repaired launcher in a real interactive terminal after closing the pre-fix TUI process.
- [x] 5.16 Route Windows terminal tool calls through the real Git Bash executable and verify it with a live gateway restart and a real `LocalEnvironment` command.
