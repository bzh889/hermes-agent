# Restricted Group Policy

Labels: ready-for-agent, wayfinder:map

## Spec

Published at: `openspec/changes/restricted-group-policy/spec.md`
Proposal at: `openspec/changes/restricted-group-policy/proposal.md`

## Summary

Per-operation capability authority for Teams MTK restricted groups. Wraps every restricted task in a fail-closed enforcement framework: origin-bound egress broker, CQ read broker, AIDE-only model-routing gate, HMAC-chained audit, disposable sandbox, durable approval, confidence-gated triage, semantic history, and production rollout verification.

Synthesized from 21 resolved Wayfinder decision tickets (01-08, 09-16, 18, 20, 21, 22) under `.scratch/restricted-group-policy/`.

## Baselines cited

- `teams-mtk-group-whitelist` — admission/mention/config/toolset/keyword baseline (preserved)
- `teams-mtk-hermes-native-parity` — Teams transport, streaming, reply, file, E2E contracts (preserved)
- `Executable Skill Strategies` — Execution Authority, Capability Provider, Core guardrail, fail-closed vocabulary (extended, not redefined)

## Next step

Run `/to-tickets` to generate implementation tickets from the spec.
