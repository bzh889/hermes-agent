# Define the origin-bound egress contract

Type: grilling
Status: resolved
Assigned: dev
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

What single origin-equality contract must every reply, stream/progress edit, explicit message send, relay transport, artifact upload, cron delivery, delegated result, and background completion satisfy immediately before side effect? Decide the canonical `(policy, version, platform, chat, thread, operation, artifact-task)` identity, allowed exact-origin exceptions, file provenance rules, restart propagation, adapter integration points, denial/audit semantics, and forced pre-gate/post-gate readback matrix that proves zero cross-group, DM, platform, thread, or relay egress.

## Comments

- Input from [Define the owner approval protocol](03-define-owner-approval-protocol.md): a PII/NDA approval authorizes one exact-payload/exact-destination logical delivery. Retries share one idempotency identity, restart reconciles completion rather than replaying blindly, and any regenerated payload, destination, or provenance fingerprint requires a new Approval Request.
- Q1 — Bind every delivery to the exact profile, policy identity, native-or-relay route, platform adapter/account/tenant, chat, normalized thread/topic, and Durable Task. Recheck the current policy revision at each side-effect boundary; the ingress revision is audit evidence only.
- Q2 — Only a Primary Reply, Requested Artifact, Derived Media Delivery, or content-free Minimal Status Notice is a Restricted Logical Delivery. `send_message`, relay, cron, delegation, background completion, and media post-processing are producers, never independent authority.
- Q3 — Persist an Egress Intent before every side effect. Timeout or restart must read back the exact origin, adopt a confirmed delivery, retry only after confirmed absence with the same identity, and never resend or reroute an indeterminate result.
- Q4 — Upload only immutable exact bytes sealed in the active task sandbox with hash, detected type, size, and complete provenance. Mutable paths, symlinks, junctions, host files, byte changes, and unknown provenance fail closed.
- Q5 — Authorize the complete exact payload under the union of its provenance labels. Model editing or omission does not declassify content; blocked output may only be replaced by a separately constructed content-free status notice.
- Q6 — The transport route is part of origin identity. A native, relay, account, tenant, platform, chat, or thread failure never falls back to another route.
- Q7 — One Core Egress Broker owns the Restricted Task side-effect boundary. It persists the intent and issues a one-use permit bound to exact operation, destination, route, payload, and policy revision; adapters and plugins fail closed without it.
- Q8 — A denied target receives zero side effect. The exact origin may receive only a generic Minimal Status Notice with an opaque reference; detailed evidence stays in content-minimized audit and protected reconciliation state.
- Q9 — Production acceptance requires every real outbound path to prove its policy-defined exact-origin outcome, forced escape denial, independent source-and-target readback, timeout/restart behavior, and cleanup. Shared-gate tests, mocks, logs, or samples do not substitute for rows.
- Q10 — A Primary Reply has one remote text-message identity. Reliable progress/edit/final operations update it; platforms without reliable edit send only final, and an uncertain edit never falls back to appending a new message.
- Q11 — Automatic `MEDIA:`, safe task-path extraction, TTS, and other media post-processing may create a Derived Media Delivery at the exact origin even without an explicit member request. Each child delivery still needs sealed sandbox bytes, inherited provenance, a durable intent, current-policy recheck, and a one-use permit.

## Answer

Adopt one fail-closed **Origin-Bound Egress** contract, enforced by a Core-owned **Egress Broker**, for every outbound side effect reachable from a Restricted Task. This is a design decision and required future acceptance contract; it does not claim the Broker is implemented or that any Egress Escape Matrix row has passed.

### Canonical authority and identity

At restricted ingress, create an immutable `OriginEgressBinding` containing:

- active profile and Restricted Group Policy identity;
- ingress policy revision, retained only as audit evidence;
- exact transport kind and route identity, including native versus relay;
- platform, adapter instance, account, and tenant identity;
- exact chat/conversation identity and normalized thread/topic identity, including an explicit `none` value;
- Durable Task identity.

Each proposed side effect adds one immutable `EgressIntent` identity:

- logical-delivery ID and purpose;
- side-effect operation (`create_reply`, `edit_reply`, `finalize_reply`, `upload_artifact`, `deliver_media`, or `send_status`);
- artifact/task child identity where applicable;
- exact destination and route fingerprints;
- payload, provenance-union, and artifact-byte fingerprints;
- one idempotency identity;
- current policy revision selected atomically for the attempt.

Immediately before adapter invocation, the Broker reloads current authority and compares the complete binding. One operation is pinned to exactly the revision it checked, but the ingress revision never freezes authority for later operations. If the current revision changes before the permit is consumed, the permit is invalid and the operation must be rechecked. Unknown, missing, or unprovable identity fails closed.

### Eligible logical deliveries

Only four purposes can receive a permit:

1. **Primary Reply** — one remote text-message handle. Reliable progress, commentary, edit, and finalization mutate that handle. If reliable edit is unavailable, send only final. Never append as an edit fallback.
2. **Requested Artifact** — exact user-requested output represented by one sealed Requested Artifact Snapshot.
3. **Derived Media Delivery** — a policy-authorized child of the Primary Reply produced automatically by `MEDIA:`, a safe task-sandbox path, TTS, or another media post-processor. It has its own intent, permit, and remote handle even when the member did not explicitly request that representation.
4. **Minimal Status Notice** — fixed content-free pause, denial, failure, or indeterminate-delivery notice plus an opaque reference.

An arbitrary same-group send is not allowed merely because its destination matches. Reactions, unreactions, Loop mutation, forwarding, fan-out, unsolicited cron output, and output after task termination receive no permit. Delegated work, terminal background completion, cron, Kanban, relay, plugins, and explicit messaging tools may produce a candidate only while the original Durable Task remains eligible; they never deliver directly.

The authenticated owner ApprovalCoordinator's Control Channel/TUI projections remain the separately decided control-plane outbox from [Define the owner approval protocol](03-define-owner-approval-protocol.md). They are not cross-origin exceptions granted to a Restricted Task.

### Payload and file provenance

Every text, edit, final response, and media/file byte sequence becomes one immutable Restricted Egress Candidate carrying the union of all source and producer Data Provenance Labels.

- `secret`, `policy_control`, or `unknown` provenance blocks originating-group delivery.
- Owner-private, PII, or NDA content follows the existing exact-payload/exact-destination owner decision.
- Policy-authorized public, exact-origin-group, brokered-policy, and task-generated content may proceed.
- Model editing, summarization, or omission never lowers classification.

Before any upload, copy the exact bytes into the active Ephemeral Task Sandbox, reject links and external paths, freeze the bytes, and record content hash, detected media type, size, and complete provenance. The Broker authorizes that snapshot, not a mutable path. TTS and automatic media extraction gain no path-based authority and must use the same snapshot rule. Successful upload records the actual remote handle; local staging remains cleanup-bound to the Durable Task.

### Broker and adapter boundary

Every Restricted producer submits a candidate to the Broker. The Broker:

1. validates delivery purpose, origin equality, route equality, task liveness, provenance, content fingerprint, and current policy;
2. persists the pre-side-effect Egress Intent;
3. issues a one-use permit bound to the exact adapter operation, route, destination, content fingerprint, and current revision;
4. invokes the adapter edge;
5. records structured outcome and actual remote message/file handle.

Adapters, relays, standalone senders, uploads, edits, webhooks, API emitters, and plugins deny Restricted-context calls without a valid permit. They do not make their own policy decisions. A failed native route never switches to relay, and a failed relay never switches to native, another account, another thread, a DM, or another platform.

### Durability, retry, and denial

Persist intent before side effect and distinguish at least `prepared`, `dispatching`, `accepted_unconfirmed`, `delivered_confirmed`, `denied`, `failed_confirmed_absent`, and `indeterminate` outcomes.

- Confirmed existing delivery is adopted using its real remote handle.
- Confirmed absence may retry only the same immutable payload/destination/provenance under the same idempotency identity and a fresh current-policy check.
- Indeterminate outcome is never resent, appended, or rerouted automatically.
- Regenerated or changed bytes, destination, route, or provenance create a new candidate and, where protected content is involved, a new Approval Request.
- Edit uncertainty is reconciled against the original remote handle; it never creates another reply.

On denial, the attempted target must show no message, edit, reaction, Loop mutation, or file. If the exact origin route still works, the Broker may create a separate Minimal Status Notice. If that route cannot be proved, do not attempt a notice. Content-minimized audit records fingerprints, task/delivery IDs, ingress and egress revisions, purpose, operation, decision/reason, permit verdict, adapter-invocation verdict, structured outcome, and confirmed-absence evidence. Raw payload, file bytes, full destination IDs, credentials, and protected content do not enter audit; exact remote handles live only in protected reconciliation state.

### Required Egress Escape Matrix

The production-acceptance matrix covers every current and future emitter reachable from a Restricted Task, including:

- final reply, streamed commentary/segments, tool progress, edit, and typing/activity;
- explicit `send_message` text/media, reaction, unreaction, and Loop operations;
- native and upstream-relay transport;
- post-response `MEDIA:`, bare-path, TTS, image, audio, video, and document delivery;
- cron target delivery, fan-out, and session mirroring;
- delegated result and terminal-background completion;
- Kanban notification and artifact delivery;
- plugin, webhook, API, standalone-sender, and future adapter paths.

Each row must:

1. prove the path can cause the intended side effect in a safe pre-gate TestGroup fixture;
2. verify the policy-defined exact-origin result — success only for the four eligible delivery purposes, and denial for arbitrary sends/mutations even at exact origin;
3. attempt cross-group, DM, platform, account/tenant, thread/topic, and native/relay-route escape;
4. assert denial before adapter invocation where denial is expected;
5. independently read back source and every target with unique markers to prove no message, edit, mutation, or file appeared;
6. exercise restart before send, uncertain result after adapter request, confirmed delivery, same-identity retry after confirmed absence, and no append/reroute fallback;
7. independently verify cleanup.

Current code still has direct and fallback outbound seams that motivate this contract rather than satisfy it: transport fallback in `gateway/delivery.py:74-131`; status fallback in `gateway/run.py:682-692`; streaming/progress sends and edits in `gateway/stream_consumer.py:386-413` and `gateway/run.py:21554-21788`; explicit messaging and standalone/platform sends in `tools/send_message_tool.py:283-291,644-952`; automatic TTS/media delivery in `gateway/run.py:14951-14961,15960-16013`; cron delivery/mirroring in `cron/scheduler.py`; and Kanban text/artifact delivery in `gateway/kanban_watchers.py:447-477,832-857`. Notably, the current Telegram media path may retry without its thread in `tools/send_message_tool.py:1635-1663`; under this contract that fallback must be denied.

No implementation, live side effect, deployment, or E2E PASS is claimed by this resolution.

### Handoff

- [Implement the origin-bound Egress Broker](17-implement-origin-bound-egress-broker.md) owns runtime implementation and behavior-level unit/integration coverage.
- [Define the live Egress Escape Matrix fixtures](18-define-live-egress-escape-matrix-fixtures.md) owns the exact safe identities, routes, readback principals, and harness contract.
- [Prove the origin-bound egress boundary end to end](19-prove-origin-bound-egress-boundary-end-to-end.md) owns the forced pre-gate/post-gate live matrix and evidence after implementation and fixtures are ready.
