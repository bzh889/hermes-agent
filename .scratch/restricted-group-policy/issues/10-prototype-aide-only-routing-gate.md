# Prototype the AIDE-only model-routing gate

Type: prototype
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

Where must one fail-closed Restricted Provider Authority gate be invoked so every main, fallback, auxiliary, vision, OCR, embedding, title-generation, delegated, and cron model request uses an approved MTK internal AIDE provider, host, model, and route class? Build a request-capture prototype that forces each fallback and override path, proves no request reaches a non-AIDE host when a compliant route is unavailable, and decides how policy/origin metadata propagates without changing the cached conversation prefix.

## Comments

- Input from [Decide the production go-live gate](04-decide-production-go-live-gate.md): include `Production Failure Triage` as a restricted control-plane model call. Failure evidence must be content-minimized and routed only to an approved AIDE host/model/route; unavailable, timed-out, or malformed inference follows the `<= 90%` held-operation path and must never fall back to a non-AIDE provider.
