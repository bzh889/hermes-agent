Fix the v19 Gateway restart false failure while preserving the MTK integration and user data.

- Current state: fixed and live-verified. `bash .\hermes.sh gateway restart` cleanly stopped and started PID 60808; Teams MTK and API are connected, and the supplied Teams 1-to-1 chat completed a real receive/reply round trip.
- Verified surfaces: TUI Node + Python gateway stayed ready without timeout; dashboard and desktop `serve` returned v0.19.0 health; TUI, Web, and Desktop builds passed.
- Next: present the exact commit scope and wait for one closing authorization before commit/push/archive.
- Guardrails: preserve all memories, sessions, improved skills, the 44 Junctions into .claude/skills, provider config, and pre-existing user worktree changes.
- Deferred: pre-existing Teams MTK and other user worktree changes remain intentionally uncommitted unless separately authorized.
