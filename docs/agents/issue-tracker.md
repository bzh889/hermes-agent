# Issue tracker: Local Markdown

Engineering-skill issues for this repo live as Markdown files under `.scratch/`.

Existing OpenSpec changes under `openspec/changes/` remain the authoritative
source for their proposal, design, requirements, and task status. When local
tickets implement an OpenSpec change, link to the relevant OpenSpec artifact
instead of copying its specification into `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- For work without an OpenSpec change, the spec is
  `.scratch/<feature-slug>/spec.md`
- For work governed by OpenSpec, tickets link to
  `openspec/changes/<change-name>/` and do not duplicate its spec
- Implementation issues are one file per ticket at
  `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`
- Never combine all implementation tickets into one file
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new ticket file under `.scratch/<feature-slug>/issues/`, creating the
directory if needed.

When publishing a standalone spec with no OpenSpec change, create
`.scratch/<feature-slug>/spec.md`. When an OpenSpec change already exists, link
to it instead.

## When a skill says "fetch the relevant ticket"

Read the referenced file. The user will normally provide its path or ticket
number. If the ticket links to an OpenSpec change, read the relevant OpenSpec
artifacts before acting.

## Wayfinding operations

Used by `/wayfinder`. The map has one child file per ticket.

- Map: `.scratch/<effort>/map.md`
- Child ticket: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`
- `Type:` records `research`, `prototype`, `grilling`, or `task`
- `Status:` records `claimed` or `resolved`
- `Blocked by: NN, NN` records blocking edges
- Frontier: scan for open, unblocked, unclaimed tickets; first number wins
- Claim: set `Status: claimed` and save before work
- Resolve: append the answer under `## Answer`, set `Status: resolved`, then
  append a context pointer to the map's Decisions-so-far
