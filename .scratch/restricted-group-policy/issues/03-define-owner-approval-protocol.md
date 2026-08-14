# Define the owner approval protocol for unknown capabilities

Type: grilling
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

What durable state machine coordinates one unknown-capability approval request across the exact owner control conversation and local TUI, accepts the first authenticated owner decision exactly once, permanently updates the bound policy, immediately re-checks authority, resumes the paused group task, and marks the duplicate surface as resolved? Decide interruption, restart, duplicate-response, revocation, audit, and cache-stability behavior.

## Comments
