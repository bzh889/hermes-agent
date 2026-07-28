# MTK Hermes upstream upgrade runbook

Read this file before every official Hermes upgrade. The goal is to place the
existing MTK integration on the new upstream version without losing committed
customization, uncommitted work, runtime data, packages, providers, or skills.

## 1. Freeze and inventory the starting point

1. Record the current branch, commit, remotes, status, staged diff, unstaged
   diff, and untracked files.
2. Create a timestamped backup branch at the original commit.
3. Save the exact working-tree bytes outside the repository and create a stash
   without dropping the external copy.
4. Run `hermes backup` to an external directory and validate the ZIP. It must
   cover configuration, memories, sessions, physical skills, and external
   memory-provider paths.
5. Record installed Python and Node packages.
6. Inventory every skill link or Junction, including link type, resolved
   target, and target-content hash. This checkout had 44 `.claude/skills`
   Junctions during the v19 upgrade; never replace them with copied folders.

Do not update until every item above is independently recoverable.

## 2. Update a clean source tree

1. Fetch official upstream and verify the intended release or commit.
2. Apply the upstream update to the clean committed line. Preserve the original
   MTK commit history; do not rewrite it.
3. Install only dependencies required by the new source. Compare the package
   inventories afterward so an older MTK dependency does not silently vanish.
4. Do not add startup synchronization, migration, or compatibility machinery
   merely to make the merge appear successful. First prove the clean upstream
   surfaces work as upstream designed them.

## 3. Restore MTK customization

1. Apply the stash without dropping it.
2. Resolve overlap against the new upstream behavior while keeping the external
   byte-for-byte backup.
3. Restore and verify providers, model choices, memories, sessions, improved
   skills, physical skills, and all recorded Junction targets.
4. Keep unrelated user work uncommitted unless the owner explicitly includes it
   in the upgrade commit.

## 4. Verify behavior, not just files

Verify each surface separately:

- `gateway`: the command exits successfully, the exact PID remains alive,
  `gateway_state` is `running`, and every enabled platform reports
  `connected`. For MTK, prove the supplied Teams 1-to-1 chat receives and sends
  a real message.
- `tui`: start it in a real terminal, confirm the provider picker is present,
  submit a prompt, and confirm no `gateway ready timeout`.
- `dashboard`: open the real server and exercise its chat/backend path.
- `desktop`: launch the packaged or development app and exercise its own
  headless backend path.

Static imports, unit tests, a PID alone, or a printed “started” line do not prove
these surfaces work.

## 5. Performance checks

Measure these separately so one cost is not blamed on another:

- Git Bash startup and launcher overhead.
- Windows controller startup.
- Gateway Python import time.
- Platform authentication and first message fetch.
- TUI Node startup and Python JSON-RPC readiness.

Never run a full bundled-skill synchronization on every application start.
Skills should be synchronized only when their source changes or during an
explicit install/update action. Loading disabled platform adapters is also not
part of startup; retain their configuration bridges without importing their
heavy runtime modules.

## 6. Closing gate

Before commit or push, show the exact upgrade-owned file list and keep unrelated
user changes out. Preserve the backup branch, external backup, and stash until
all four surfaces and the MTK Teams round trip have been proven. Commit and push
only after the owner approves the final scope.

## v19 lessons

- A longer readiness timeout hid startup cost but did not fix it. Readiness must
  match the exact spawned PID and `gateway_state=running`, while slow imports
  and platform connection are measured independently.
- Windows Scheduled Task queries are expensive; do not repeat the same query in
  one status call.
- Shutdown must preserve active work but should not spend the full drain window
  on an idle Gateway.
- Cleanup code must not import unused tool modules or scan empty environments
  during shutdown.
- The Bash launcher sets `HERMES_HOME=~/.hermes`; bare Python measurements that
  skip the launcher are not equivalent and can inspect a different default
  data directory.
