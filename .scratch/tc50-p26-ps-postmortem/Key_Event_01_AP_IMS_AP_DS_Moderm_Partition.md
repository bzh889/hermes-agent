# Key Event #1 — AP-IMS / AP-DS vs. Modem Partition and Deep Dive

## Recommended event title

**AP-IMS / AP-DS vs. Modem Partition and Deep Dive**

Alternative shorter title for the slide table:

**AP-IMS / AP-DS–Modem Partition Deep Dive**

## What was discussed and what was decided

- The deep-dive covered the AP/Modem partition and related control flows, including:
  - domain selection;
  - emergency-call flow;
  - PDN establishment;
  - network search and RAT selection;
  - EPS fallback;
  - MSPM/resource priority;
  - MIPC / HAL interface mapping;
  - registration and voice-related interactions;
  - validation and follow-up ownership.
- The three-day workshop covered multiple topics. The hybrid-architecture conclusion applies specifically to the **Domain Selection partition** topic; other topics retain their own decisions and follow-up items.
- For the Domain Selection partition, P26 selected a **hybrid AP/Modem architecture** rather than placing the complete domain-selection responsibility in only AP or only Modem.
- The related interface definition, message flow and call flow were adapted to the selected hybrid partition.
- The decision clarified which functions remain on AP, which functions remain on Modem, and where MIPC/HAL is required to connect the two sides.
- The decision also established the basis for handling related scenarios such as emergency service, RAT/network search, EPSFB and resource-control interactions.

## Recommended lesson

> **A cross-layer architecture decision is not complete when the partition is agreed; the interface contract, scenario call flow, validation boundary and follow-up owner must be updated together.**

## Why this is a lesson from P26

The topic required repeated AP/Modem discussion because the customer scenario was organized around end-to-end behavior, while the implementation responsibilities were divided by software layer. A partition decision without the corresponding interface and validation definition would leave the same ambiguity to reappear during implementation or integration testing.

## Internal lesson / optimization

For P27/P28, every AP/Modem partition decision should produce a compact **Partition Decision Record** containing:

- responsibility boundary by function;
- MIPC/HAL interface owner;
- message and call-flow diagrams;
- normal and exceptional scenarios;
- Alcedo UT/RDIT scope;
- Zion AP/device/system-IT scope;
- cross-module owner;
- open items and decision authority;
- release and closure criteria.

The PS Lv1 DRI should track completeness of the record, while AP, Modem and domain owners remain responsible for their technical areas.

## External lesson / optimization

For an AP/Modem feature, Alcedo and Zion should jointly confirm before implementation:

- which side owns each function;
- which interface and message flow are normative;
- which scenarios are covered by the decision;
- what Alcedo can verify independently;
- what requires Zion AP/device/system IT;
- who owns unresolved cross-layer behavior;
- what evidence is required before acceptance.

## P27/P28 implication

Add a **Partition Decision Record** to the feature onboarding / architecture deep-dive process. Do not close the workshop action merely because the architecture direction is accepted; close it only when the partition, interface, call flow, validation and owner fields are complete.

## Evidence / scope guardrail

- Use the workshop's topic-level decision accurately: only the Domain Selection topic is described as producing the hybrid AP/Modem architecture.
- Do not imply that every topic in the three-day AP-IMS/Protocol workshop reached the same architectural conclusion.
- Keep detailed individual names and private source mechanics out of the External main slide unless separately approved.

## Slide-table version

### What was discussed and what was decided

```text
Multi-topic AP-IMS / Protocol deep dive covering AP/Modem domain selection,
emergency call flow, PDN establishment, network search, EPSFB, MSPM and
MIPC/HAL mapping. For the Domain Selection partition, P26 selected a hybrid
AP/Modem architecture and adapted the related interface and call flow.
Other workshop topics retained separate decisions and follow-up items.
```

### Lesson

```text
For cross-layer architecture decisions, align the partition, interface,
scenario call flow, validation boundary and follow-up owner as one decision
package — not as separate follow-up activities.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: structured technical deep dive
- Good point: cross-layer architecture convergence
- Improvement: decision-to-interface / validation / closure bridge
- Internal optimization: Partition Decision Record and owner boundary
- External optimization: joint AP/Modem responsibility and validation alignment
- P27/P28 artifact: Partition Decision Record
