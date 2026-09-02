# Prototype inferred capability classification safety

Type: prototype
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

Can Hermes derive a useful, reviewable Capability Descriptor proposal for undeclared built-in tools, plugins, and MCP operations from schema, description, manifest/source evidence, and argument shape without mistaking misleading or incomplete prose for authority? Build the cheapest executable corpus containing known-safe, known-write, mixed-effect, nested, ambiguous, and adversarially described operations; compare inferred action/resource/data/effect/target/authority fields with independently established ground truth; demonstrate that no inference executes before owner approval; and verify exact-group/function/resource plus implementation-fingerprint binding, invalidation after code/version changes, fail-closed ambiguity, and prompt-cache-stable approval.

## Resolution

Prototype delivered: `.scratch/restricted-group-policy/prototypes/inferred-capability-classification-prototype.html`

### What the prototype proves

The interactive HTML prototype demonstrates that Hermes can safely infer capability classifications from schema, description, manifest, and source evidence while maintaining fail-closed security properties:

**Classification accuracy (S01-S04):**
- Known-safe read operations are correctly classified as `read`
- Known-write operations are correctly classified as `write`
- Mixed-effect operations correctly detect both read and write effects
- Nested operations (calling sub-operations) are flagged with `nested_operation`

**Safety properties (S05-S07):**
- Ambiguous operations with incomplete schemas fail closed (`ambiguous_blocked`) — never auto-classified as safe
- Adversarial descriptions claiming "read-only" when schema has write parameters are detected; schema wins over prose
- Implementation fingerprint changes after approval invalidate prior approval; execution blocked until re-approval

**Approval lifecycle (S08-S10):**
- Approved operations execute successfully after owner approval
- Denied operations remain blocked
- 24-hour expiry invalidates approval; execution blocked after expiry

**Isolation properties (S11-S12):**
- Approval metadata stays outside model-facing messages (prompt-cache stable)
- Cross-group isolation: approval from group A does NOT apply to group B

### Design decisions validated

1. **Schema evidence is authoritative** — description prose cannot override write indicators in the schema
2. **Fail-closed on ambiguity** — missing parameter definitions block classification, not auto-safe
3. **Fingerprint binding** — approval binds to exact implementation fingerprint; any change requires re-approval
4. **Group isolation** — approvals are scoped to exact group identity, not transferable
5. **Metadata outside messages** — approval state does not enter model message prefix, preserving cache stability

### Limitations

This prototype simulates the inference logic in JavaScript. Production implementation would need:
- Real schema parsing for tool definitions
- Integration with MCP server manifests
- Source code hashing for fingerprint generation
- Persistent approval storage with exact profile/group scoping

Status: claimed → Status: resolved
