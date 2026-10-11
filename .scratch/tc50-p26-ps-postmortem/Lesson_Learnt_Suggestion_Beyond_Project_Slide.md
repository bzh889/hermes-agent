# Lesson Learnt and Suggestion Beyond Project

## Recommended slide structure

Use the same three-column table style as the Key Event slides, but split the content into **Internal** and **External** sections within the slide.

| Lesson Learnt | Internal Optimization (Alcedo) | External Optimization (Alcedo + Zion) |
|---|---|---|
| **1. Feature enablement and verification must be defined up front**<br><br>A customization feature is not complete when implementation is complete. | Before delivery commitment, complete a **Feature Verification & Enablement Matrix** covering:<br>• default ON/OFF/conditional state<br>• carrier/scenario enablement<br>• Alcedo self-contained vs. joint development<br>• Alcedo UT/RDIT scope<br>• SV/FO support and rationale<br>• release, compatibility and closure owner | At feature baseline, jointly confirm:<br>• which carrier/scenario is enabled<br>• who implements, tunes and validates<br>• what Alcedo can verify without Zion hardware/AP<br>• what requires Zion device/system IT<br>• acceptance criteria and evidence required |
| **2. Cross-layer decisions need one documented decision package**<br><br>Architecture or feature direction alone is not sufficient. | Record the partition/interface decision, supporting module owners, evidence required, validation method, release target and unresolved-item owner in the feature/architecture record. | Alcedo and Zion jointly document the requirement, interface/message flow, responsibility boundary, validation boundary and follow-up owner before implementation is committed. |
| **3. Support coverage must be ready before execution peak**<br><br>A contact list or time-zone relay does not by itself provide technical coverage. | Establish a **Coverage & Routing Matrix** with primary/backup, MUS daytime peer, HQ/domain owner, convergence owner, decision authority, access route and escalation trigger. Preserve the partner-account firewall while separating access coordination from technical ownership. | For each high-risk scenario, agree on the customer-time counterpart, backup, communication path, expected response, escalation trigger and validation owner. |
| **4. Customer data should become reusable product learning**<br><br>Field and carrier data exposed scenarios beyond the historical turnkey experience. | Feed high-value MWI/eSIM/SIM findings into regression, design guidelines, robustness improvements and next-program planning—not only one-off patch closure. Maintain a P26/P27/P28 carry-forward and long-tail register. | Provide a consistent scenario/evidence package and jointly classify the outcome as reusable fix, customer-specific workaround, limitation, QPR fix or next-program feature. Keep owner, target phase, validation and retirement condition visible. |

## P27/P28 proposed artifacts

1. **Feature Verification & Enablement Matrix** — required before feature commitment.
2. **Partition / Feature Execution Decision Record** — links requirement, interface, R&R, validation and closure.
3. **Coverage & Routing Matrix** — required before DVT/TA/MP execution peak.
4. **Joint Verification Readiness Gate** — device, AP, SIM, network, logs, circuit, simulator and acceptance criteria.
5. **P26/P27/P28 Carry-forward & Long-tail Register** — QPR, workaround retirement, successor fix and long-term owner.

## Suggested bottom-line message

> **P26 established the collaboration forums. P27/P28 should make the collaboration model executable by defining feature enablement, verification, technical coverage and post-MP ownership before commitment.**

## Slide note

- External discussion sequence: **shared evidence → joint improvement → Zion feedback/commitment → action items**.
- Do not mention PKB, Teams, private source mechanics or the firewall rationale on the External slide.
- Keep the seven-year support horizon in Internal planning material; describe External support only as the long product-support lifecycle.
