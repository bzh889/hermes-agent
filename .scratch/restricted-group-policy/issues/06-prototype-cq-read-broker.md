# Prototype the CQ Read Broker and prove export safety

Type: prototype
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

What is the narrowest credential-owning ALPS/MOLY broker that exposes only approved read capabilities without giving the agent `WitsSession`, `WitsHTTP`, arbitrary query objects, write facades, credentials, or owner filesystem access? Build a disposable executable prototype around explicit fields, notes, dependency, history, attachment-list, and download-to-task-root operations; separately force CQ export against harmless ALPS and MOLY fixtures to determine whether it is mutation-free and bounded. Decide session refresh ownership, identifier/query validation, attachment handling, response limits without business truncation, and the evidence required to prove zero CQ mutation by independent readback.

## Comments
