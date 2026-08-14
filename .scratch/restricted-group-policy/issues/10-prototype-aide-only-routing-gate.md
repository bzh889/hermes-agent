# Prototype the AIDE-only model-routing gate

Type: prototype
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

Where must one fail-closed Restricted Provider Authority gate be invoked so every main, fallback, auxiliary, vision, OCR, embedding, title-generation, delegated, and cron model request uses an approved MTK internal AIDE provider, host, model, and route class? Build a request-capture prototype that forces each fallback and override path, proves no request reaches a non-AIDE host when a compliant route is unavailable, and decides how policy/origin metadata propagates without changing the cached conversation prefix.

## Comments
