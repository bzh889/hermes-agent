# 30 — CQ Read Broker: seven read-only operations

**What to build:** A host-side, credential-owning broker that exposes exactly seven read-only operations against ALPS/MOLY CQ systems: query, page, export, search, filter, sort, and aggregate. The broker authenticates to the CQ system using the owner's credentials but never exposes them to the model's context. INSERT, UPDATE, DELETE, raw-query, and credential-access operations are denied before any CQ system interaction. The model interacts with the broker's API, not with credentials. A unit test proves each of the seven read operations succeeds against a mock CQ system. Unit and integration tests prove write operations (INSERT, UPDATE, DELETE) fail closed, raw queries are denied, and credential access is denied.

**Blocked by:** 28 — Wire all emitter paths through the Egress Broker

**Status:** closed

- [ ] CQ Read Broker module with seven read-only operations: query, page, export, search, filter, sort, aggregate
- [ ] Broker authenticates to CQ system using owner credentials — credentials never in model context
- [ ] INSERT through broker → DENY (rejected before CQ interaction)
- [ ] UPDATE through broker → DENY
- [ ] DELETE through broker → DENY
- [ ] Raw SQL query → DENY
- [ ] Credential access → DENY
- [ ] Unit test: seven read operations succeed against mock CQ
- [ ] Unit test: INSERT/UPDATE/DELETE denied with `reason=write_operation_blocked`
- [ ] Unit test: raw query denied
- [ ] Unit test: credential access denied
- [ ] Integration test: broker authenticates to mock CQ and returns query results without exposing credentials
