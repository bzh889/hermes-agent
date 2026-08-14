# Choose the capability taxonomy and enforcement contract

Type: grilling
Status: claimed
Assigned: dev
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 01

## Question

What capability vocabulary, declaration contract, unknown-capability state, and per-operation authority-check semantics will let policies default-allow classified reads while reliably denying owner-private data and all non-exempt writes? Decide how direct and indirect capabilities compose, how newly installed tools/plugins/MCP servers become classified, how revocation reaches in-flight tasks immediately, and how the design remains profile-safe and prompt-cache safe.

## Comments

- Grilling Q1: the canonical authorization unit is a structured `Capability Request` matched by policy selectors. Tool/toolset names and provider-defined permission strings are evidence about the request, not the security vocabulary.
- Grilling Q2: every `Capability Descriptor` uses a fixed Core semantic envelope plus validated namespaced typed extensions. Extensions may add policy-selectable detail but may not omit or redefine descriptor identity/version, action, resource and data class, effect class, normalized target scope, authority domain, or trusted policy/origin/principal/task lineage.
- Grilling Q3: a `Capability Request` carries an orthogonal set of effects rather than one primary effect or risk tier. Every effect must be independently authorized; any denied effect denies the request and any unclassified effect makes it unknown, so a read label cannot mask export, egress, mutation, credential, or descendant-authority consequences.
- Grilling Q4: the Core effect vocabulary is `read`, `compute`, `ephemeral_write`, `durable_internal_write`, `external_mutation`, `egress`, `authority_spawn`, `credential_use`, `credential_maintenance`, `policy_admin`, and `secret_exposure`. Credential use and maintenance are separate; `secret_exposure` is an invariant hard deny and `policy_admin` requires owner authority.
- Grilling Q5: data uses an orthogonal monotonic provenance-label set. Every derived value and artifact inherits the union of all input labels plus producer labels; no model, tool, transform, summary, or format conversion implicitly lowers classification. Label removal requires a separately registered and authorized declassifier, and the first version provides none.
- Grilling Q6 (product-level reframe): restricted-group use may automatically persist only de-identified `Optimization Records` containing capability/outcome/feedback evidence. Content-bearing `Shared Knowledge Candidates` require explicit owner approval before entering the owner's PKB. A group turn never gains skill-write, PKB-write, provider-source-write, or declassification authority, and raw Teams/CQ content is not automatically retained under an optimization label.
- Grilling Q7: only the owner may approve an unknown capability. The resulting `Capability Grant` is bound to the exact Restricted Group Policy and therefore only to the requesting Teams group; it never grants the capability to another group, policy, profile, or global Hermes installation. The approval request must reach the owner's exact Teams Control Channel; whether TUI is an additional transport remains part of the separate owner-approval-protocol decision.
- Grilling Q8: within that requesting group, owner approval grants one explicit function and normalized resource scope, such as read-only Jira queries for Project A. It does not approve a whole plugin, adjacent write/admin operations, other projects, credentials, or each request globally; subsequent matching requests remain allowed until the owner revokes the grant.
