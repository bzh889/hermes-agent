## Context

The current branch is `mtk-integration` at commit `2f8b5671296e30caa2c28f678504da5d45497828`, tracking `fork/mtk-integration` with no committed divergence. The worktree has two modified tracked files and no untracked files. The local `origin/main` reference is stale, so the current official tip must be fetched before its exact divergence can be measured.

The owner selected the official `main` tip rather than the `v0.19.0` release tag.

## Goals / Non-Goals

**Goals:**

- Preserve every existing commit with its current commit ID.
- Preserve the exact pre-upgrade bytes in independent backups and preserve the effective changes in the upgraded worktree.
- Preserve Hermes memories, sessions, configuration, and improved physical and linked skills.
- Preserve every currently installed Python and Node package, with env left untouched as a fallback.
- Integrate the newest fetched `origin/main`.
- Leave a clear, independently recoverable pre-upgrade state.
- Prove preservation and run focused tests before reporting success.

**Non-Goals:**

- Rebase or otherwise rewrite the existing branch.
- Push the upgraded result without separate owner approval.
- Refactor MTK-specific code while resolving conflicts.
- Automatically migrate or change the user's `~/.hermes` configuration.

## Decisions

1. **Use a merge, not a rebase or cherry-pick reconstruction.**
   A `--no-ff` merge keeps every current commit ID and makes the upstream integration boundary explicit.

2. **Create redundant recovery points before changing history.**
   Create a timestamped local backup branch at the original `HEAD`. Export the binary worktree diff and exact copies of modified files outside the repository, then stash the edits. The already-synchronized `fork/mtk-integration` remains the remote copy of all committed pre-upgrade work.

3. **Do not disable HTTPS certificate verification.**
   The current Windows Git HTTPS path reports an enterprise certificate/credential failure. Fetching will use a trusted enterprise certificate path, WSL Git, or another verified transport. `http.sslVerify=false` is not an acceptable workaround.

4. **Resolve conflicts by behavior, not by choosing one side wholesale.**
   For each conflict, inspect the upstream change and the MTK-specific intent. Keep both where compatible. Avoid unrelated cleanup.

5. **Restore uncommitted work only after the upstream merge is complete.**
   Apply the stash without dropping it first, verify the restored changes against the independent backup, and retain the stash until all checks pass. If upstream changed the same lines, adapt the edit to the new base while retaining the exact pre-upgrade bytes in the external backup.

6. **Keep the final two edits uncommitted.**
   The merge itself may create one merge commit, as approved. The pre-existing uncommitted edits remain uncommitted.

7. **Use Hermes' full backup path for runtime data.**
   Run `hermes backup` to a dedicated `D:\tmp` upgrade directory before the merge. This path uses SQLite's online backup API for `*.db`, excludes transient WAL/SHM files, and includes configuration, memories, sessions, physical skills, and active external memory-provider paths. Validate the resulting ZIP before relying on it.

8. **Inventory linked skill sources separately.**
   `~/.hermes/skills` contains Windows junctions into `~/.claude/skills`. Record each link name, target, and target content hash before the merge, then verify the same links and hashes afterward. The source merge must not replace or remove either side of those links.

9. **Preserve installed packages without destructive synchronization.**
   Export `pip freeze --all` for both `.venv` and `venv`, plus top-level Node package inventories for the repository workspaces. Do not run `git clean`, `uv sync`, `pip uninstall`, `npm ci`, or any command that recreates a dependency directory. If the new source needs Python dependencies, update only `.venv` with additive installation and keep `venv` untouched as the rollback environment.

## Execution Flow

1. Record the original branch, `HEAD`, status, modified-file hashes, and binary diff.
2. Create the timestamped Git safety branch and external worktree backup.
3. Create and validate the full Hermes home backup.
4. Record package inventories and linked-skill targets and hashes.
5. Stash tracked and untracked work, then verify the worktree is clean.
6. Fetch the official `main` and tags over a verified HTTPS or SSH path.
7. Record the fetched upstream commit and divergence.
8. Merge `origin/main` with `--no-ff`.
9. Resolve merge conflicts and complete the merge commit.
10. Apply the saved worktree edits without dropping the saved copy.
11. Resolve any restoration conflicts.
12. Verify source history, runtime backup, package sets, linked skills, and focused tests.

## Verification

- The original `HEAD` is an ancestor of the upgraded branch.
- The fetched `origin/main` tip is an ancestor of the upgraded branch.
- The timestamped safety branch still points to the original `HEAD`.
- All original commits remain reachable without rewritten IDs.
- The two original modified files remain modified and preserve the same intended changes; any adaptation required by the new upstream base is documented, while the exact pre-upgrade bytes remain independently recoverable.
- No original untracked file is lost; the initial inventory currently contains none.
- The full Hermes backup ZIP passes integrity validation and contains state.db, memories/, sessions/, and physical skill content.
- Every pre-upgrade linked skill still resolves to the same target with the same target hash.
- Every pre-upgrade Python and top-level Node package remains installed; the fallback env is unchanged.
- Focused Teams MTK and upgrade-sensitive tests pass, or failures are reported with evidence.
- No remote push occurs.

## Rollback

- Reset only after explicit owner approval, using the timestamped safety branch.
- Restore the worktree from the retained stash or external binary patch/file copies.
- Because the current committed branch is already synchronized to `fork/mtk-integration`, the pre-upgrade committed state also remains available remotely.

## Risks / Trade-offs

- The upstream gap is large, so the merge may contain many conflicts.
- Keeping original commit IDs produces a non-linear history, which is intentional.
- Tests may reveal upstream changes that require a follow-up fix; such fixes must remain narrowly tied to making the preserved MTK behavior work on the new upstream.
- The local Git HTTPS trust problem may delay the fetch, but certificate checking will remain enabled.
