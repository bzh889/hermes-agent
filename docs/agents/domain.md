# Domain Docs

How engineering skills consume this repo's domain documentation.

## Before exploring, read these

- `CONTEXT-MAP.md` at the repo root, when present. It identifies the relevant
  context documents.
- The `CONTEXT.md` files for every context touched by the task.
- `docs/adr/` for system-wide architectural decisions.
- The relevant context-local `docs/adr/` directory.

This repo uses these logical contexts:

- Core: root `CONTEXT.md`
- Gateway: `gateway/CONTEXT.md`
- Desktop: `apps/desktop/CONTEXT.md`
- TUI: `ui-tui/CONTEXT.md`
- Web: `web/CONTEXT.md`

Cross-surface work must read every affected context. Work involving
`apps/shared/` must read the Desktop and Web contexts unless `CONTEXT-MAP.md`
specifies a narrower rule.

If these files do not exist, proceed silently. Do not flag their absence or
create empty placeholders. `/domain-modeling` creates them lazily when terms or
decisions are actually resolved.

## File structure

```text
/
├── CONTEXT-MAP.md
├── CONTEXT.md                         # Core
├── docs/adr/                          # System-wide decisions
├── gateway/
│   ├── CONTEXT.md
│   └── docs/adr/
├── apps/desktop/
│   ├── CONTEXT.md
│   └── docs/adr/
├── ui-tui/
│   ├── CONTEXT.md
│   └── docs/adr/
└── web/
    ├── CONTEXT.md
    └── docs/adr/
```

## Use the glossary's vocabulary

When output names a domain concept—in an issue title, refactor proposal,
hypothesis, or test name—use the term defined in the relevant `CONTEXT.md`. Do
not drift to synonyms that the glossary explicitly avoids.

If a needed concept is absent, either reconsider whether the project uses that
term or record the gap for `/domain-modeling`.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly
rather than silently overriding it:

> Contradicts ADR-0007 — worth reopening because...
