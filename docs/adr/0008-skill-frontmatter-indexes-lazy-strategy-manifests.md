# ADR 0008: Skill frontmatter indexes lazy strategy manifests

## Status

Accepted

## Context

Hermes already provides three useful properties for executable skill strategies:

- `SKILL.md` frontmatter is parsed as nested YAML;
- the system-prompt skill index reads compact metadata and is cached independently; and
- `skill_view(name, file_path)` can load supporting files only when a skill is used.

Putting a full state machine in every `SKILL.md` frontmatter would bloat discovery, mix human guidance with machine execution data, and make large Hybrid Strategies hard to review. Keeping all strategy information in prose would not create an executable contract.

## Decision

`SKILL.md` frontmatter contains only a small, versioned **strategy index**. Each index entry names a capability and points to one strategy manifest under the skill's supporting files.

Illustrative shape:

```yaml
metadata:
  hermes:
    strategy:
      schema: hermes.strategy-index/v1
      manifests:
        - capability: bug-brief.lookup
          path: references/strategies/lookup.yaml
```

The external manifest is a data-only, versioned YAML document. It declares observable execution structure rather than credentials, arbitrary code, or natural-language pseudo-conditions.

Illustrative shape:

```yaml
schema: hermes.strategy/v1
capability: bug-brief.lookup
entry: lookup
budgets:
  tool_failures: 1
  elapsed_seconds: 600
nodes:
  lookup:
    mode: contracted
    operation: buganizer.lookup
    on:
      ok: done
      auth_expired: refresh_auth
      not_found: done
  refresh_auth:
    mode: contracted
    operation: buganizer.refresh_auth
    on:
      ok: retry_lookup
      denied: human_handoff
  review_evidence:
    mode: adaptive
    handoff: model
    constraints:
      providers: [buganizer]
```

Exact field names and the expression-free argument binding format are implementation details, but the following invariants are part of the contract:

- every contracted transition is selected from observable normalized outcomes;
- a contracted node has one legal target per declared outcome;
- semantic judgment is an explicit Adaptive node or human/model handoff;
- credentials and session refresh logic remain provider-owned;
- operation names are resolved against the current turn's Execution Authority;
- the manifest cannot embed scripts, shell commands, or executable expressions; and
- schema, references, reachability, budgets, and outcomes are validated before the first side effect.

The manifest is loaded lazily only when the skill is explicitly activated or when a semantic follow-up resumes that skill's Intent Thread. Discovery and `skills_list` do not load it, and strategy metadata is not added to the cached system-prompt skill index.

Each capability run compiles an immutable manifest snapshot and records its schema version and content digest in the execution trace. A later follow-up starts a new run using the latest valid manifest; it does not remain pinned forever to the version first loaded. Historical traces retain the prior digest for diagnosis.

Existing skills without a strategy index remain Adaptive and require no migration. Direct provider calls without Strategy Activation remain Adaptive under ADR 0006.

Loading the strategy through a tool result or slash-skill user turn preserves the existing system-prompt prefix. No new always-present model tool is required. A service-gated strategy execution tool may be frozen into the session's initial toolset only when executable strategy manifests are available; installation or schema changes take effect in a later session unless the user explicitly accepts cache invalidation.

## Consequences

### Positive

- Discovery stays compact and prompt-cache-safe.
- Humans can read `SKILL.md` without stepping through a large transition table.
- Contracts are independently validated, versioned, tested, and patched.
- Existing supporting-file lazy loading and path guards can be extended rather than duplicated.
- Old skills continue to work unchanged.

### Negative

- Skill loading must surface strategy-manifest validation failures clearly.
- `skill_view` linked-file discovery must include YAML files under `references/strategies/`.
- A manifest and its prose can drift, so tests and authoring validation must check their relationship.
- Plugin and external skills need the same safe manifest-resolution rules as local skills.

## Rejected alternatives

### Put the complete contract in `SKILL.md` frontmatter

Rejected because it bloats the index source, mixes machine data with human guidance, and scales poorly for Hybrid Strategies.

### Keep the contract in skill prose

Rejected because prose cannot be validated or deterministically interpreted.

### Store strategy in the provider

Rejected because strategy is skill-owned; providers own credentials, operations, and normalized outcomes.

### Add a new global model tool solely to start contracts

Rejected because explicit skill activation plus existing dispatch can start a run without permanently increasing every request's tool schema.
