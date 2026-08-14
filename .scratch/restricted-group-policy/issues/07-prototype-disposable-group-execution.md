# Prototype disposable per-group execution and cleanup

Type: prototype
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

Which existing Hermes terminal/code-execution backend can be extended into a hard per-group and per-task boundary on Windows and remote backends, with only the task root mounted, no owner files or credentials, normalized path and reparse-point containment, controlled network access, and policy-stamped background descendants? Build the cheapest executable prototype that forces absolute-path, traversal, symlink/junction, subprocess, delayed-write, restart, `/stop`, task-end, stale-root, and daily 03:00 cases; decide lease semantics and prove exact deletion/retention without cross-group damage.

## Comments
