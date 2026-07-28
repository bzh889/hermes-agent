## ADDED Requirements

### Requirement: Preserve committed history

The integration SHALL retain the original `mtk-integration` commit as an ancestor of the upgraded branch and SHALL NOT rewrite existing commit IDs.

#### Scenario: Official main is integrated

- **WHEN** the latest fetched `origin/main` is integrated into `mtk-integration`
- **THEN** both the original `mtk-integration` `HEAD` and fetched `origin/main` tip are ancestors of the resulting branch
- **AND** a timestamped safety branch still points to the original `HEAD`

### Requirement: Preserve uncommitted work

The integration SHALL preserve exact pre-upgrade bytes for every tracked and untracked working-tree change in independent backups and SHALL restore the effective changes as uncommitted work on the upgraded base.

#### Scenario: Existing edits are restored

- **WHEN** the upstream merge is complete
- **THEN** the effective original edits to `gateway/platforms/teams_mtk.py` and `tests/gateway/platforms/test_teams_mtk_reliability.py` remain present as uncommitted changes
- **AND** independent binary patch and file-copy backups remain available until verification succeeds
- **AND** any adaptation required by overlapping upstream edits is documented without replacing the exact backups

### Requirement: Use verified upstream transport

The integration SHALL fetch official upstream data without disabling TLS certificate verification.

#### Scenario: Enterprise certificate interception affects Git

- **WHEN** the default Windows Git HTTPS path cannot verify or acquire the required enterprise credentials
- **THEN** the operator uses a trusted enterprise certificate path, WSL Git, or another verified transport
- **AND** does not set `http.sslVerify=false`

### Requirement: Do not push automatically

The integration SHALL leave all upgraded commits local until the owner separately authorizes a push.

#### Scenario: Local verification completes

- **WHEN** the merge and verification steps finish
- **THEN** `fork/mtk-integration` remains unchanged
- **AND** the local branch may be ahead by the new merge commit and any explicitly approved conflict-resolution commits
### Requirement: Preserve Hermes runtime data

The integration SHALL create and validate a full Hermes home backup before changing source history, using SQLite-safe snapshots for active databases.

#### Scenario: Gateway is using the main state database

- **WHEN** the pre-upgrade backup is created while the Gateway is running
- **THEN** `state.db` and other `*.db` files are captured through SQLite's backup API rather than copied with live WAL state
- **AND** the backup contains memories, sessions, configuration, and physical skill content
- **AND** the backup ZIP passes integrity validation before the merge begins

### Requirement: Preserve installed packages

The integration SHALL preserve every installed Python and top-level Node package and SHALL keep the existing `venv` environment untouched as a rollback environment.

#### Scenario: New upstream dependencies are required

- **WHEN** the upgraded source requires additional Python dependencies
- **THEN** only `.venv` receives additive package installation
- **AND** no pre-upgrade package disappears from `.venv`
- **AND** `venv` remains unchanged
- **AND** dependency directories are not deleted or recreated

### Requirement: Preserve improved skills

The integration SHALL preserve both physical skills under `~/.hermes/skills` and skills exposed through Windows junctions.

#### Scenario: Skills include junctions to another skill root

- **WHEN** a skill entry points into `~/.claude/skills`
- **THEN** its pre-upgrade link target and target content hash are recorded
- **AND** the post-upgrade link resolves to the same target with the same target hash
- **AND** physical non-junction skills remain recoverable from the full Hermes backup
