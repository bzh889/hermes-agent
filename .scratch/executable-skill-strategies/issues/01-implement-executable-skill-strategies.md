---
title: Implement executable skill strategies
status: ready-for-agent
type: feature
priority: high
spec: ../spec.md
---

# Implement executable skill strategies

Implement the behavior defined by the standalone [Executable Skill Strategies spec](../spec.md).

This is the umbrella issue for the accepted capability-execution, semantic-continuity, origin-authority, fail-closed, and durable-repair contract. Do not duplicate or reinterpret the spec in this issue; `/to-tickets` should decompose the authoritative user stories, implementation decisions, and testing seams into independently verifiable child issues.

Completion requires the spec's focused hermetic suites, highest-seam Agent and Gateway behavior tests, real local TUI verification, real Teams MTK control/non-control verification, persisted execution-trace evidence, and Kanban repair-task read-back. Partial failures and flaky retries must remain visible.
