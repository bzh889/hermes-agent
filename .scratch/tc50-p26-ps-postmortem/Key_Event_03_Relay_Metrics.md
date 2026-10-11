# Key Event #3 — Relay Metrics

## Recommended event title

**Relay Metrics — Cross-Layer Metric Design and Delivery Governance**

## What was discussed and what was decided

- Relay Metrics covered a large set of requirements spanning multiple modem domains and protocol layers, including:
  - NTN;
  - GNSS;
  - Power;
  - ENAS / NNAS;
  - ERRC / NRRC;
  - RTP;
  - IP;
  - EPDCP / NPDCP;
  - ERLC / NRLC;
  - EMAC / NMAC;
  - EL1.
- The collaboration was not limited to collecting a list of counters. The parties had to define, for each metric or event:
  - semantic meaning and unit;
  - reporting frequency or freshness requirement;
  - instance scope, such as RAT, CellGroup, CC or bearer;
  - collection mechanism;
  - interface name and owner;
  - support status and delivery phase;
  - validation and customer-consumption expectation.
- The shared Relay Metrics reference used a field-level review status and delivery model, including:
  - Agree;
  - Disagree;
  - Escalate;
  - Limitation;
  - delivery phase / gate;
  - Zion comment;
  - Alcedo comment.
- The parties classified each metric/event according to the most suitable delivery mechanism rather than forcing every request through one interface:
  - **Ordinary ICD** for periodic or event reporting;
  - **On-demand ICD** for customer-triggered collection;
  - **MAL API** for an abstraction-layer interface;
  - **Primitive / existing interface** where the required data already existed at a lower layer;
  - **New ICD / new interface** where an additional modem-side data path was required;
  - **Not Support / Limitation** where the platform, architecture, performance or information boundary did not justify implementation.
- The collaboration compared Zion's original collection expectations with Alcedo's existing architecture and delivery constraints. The selected mechanism for a metric was therefore based on the metric's timing, layer, data lifetime, performance impact, interface availability and customer-use scenario.
- The Relay Metrics design evolved through repeated reviews and remained a living reference. New fields, clarifications, changes of support type, delivery-phase decisions and removals continued after the initial architecture direction.
- The design direction included using existing ICD mechanisms where they were sufficient, applying on-demand ICD or MAL abstraction where appropriate, and reserving new ICD/interface work for requirements that could not be satisfied by the existing design.
- The collaboration also identified cases where the requested data semantics needed refinement, for example:
  - NAS-level versus RRC-level OOS definition;
  - cumulative counters that must survive bearer release or MAC reset;
  - converting some high-volume metrics into event-based reporting;
  - GNSS/platform metrics requiring another owner or collection path;
  - platform, thermal, power or security limitations that constrained modem-side support.

## Quantified evidence

Use the number that matches the chosen source snapshot:

```text
1,200+ metric definitions in the living Relay Metrics reference.
```

Additional scale evidence:

```text
Approximately 450 metric items required item-by-item follow-up in the
2024/11 PS Deep Dive context.
```

These figures must not be added together. The 450 figure is a review/follow-up subset; the 1,200+ figure is the broader living catalogue.

## Recommended lesson

> **The customer's first proposal is not automatically the most sustainable P26 implementation. A scalable solution comes from jointly mapping each metric to the right existing or new delivery mechanism, maximizing reuse of the existing design while preserving the customer's required observability.**

## Stronger lesson wording for the slide

```text
A sustainable metric solution is negotiated, not copied from the initial request:
reuse the existing ICD/MAL design where it meets the scenario, introduce new
interfaces only where necessary, and make the trade-off visible to both sides.
```

## What made this a win-win design

### Zion benefit

- Receives the required visibility for debugging, relay monitoring and performance analysis.
- Gets a consistent field-level status and delivery-phase view.
- Avoids relying on a single collection mechanism for metrics with different timing and lifetime requirements.

### Alcedo benefit

- Reuses existing ICD / MAL / primitive capabilities where sufficient.
- Avoids unnecessary new modem-side interfaces and associated performance or maintenance cost.
- Makes unsupported or limited items explicit rather than leaving ambiguous commitments.
- Maintains a sustainable delivery model as new metrics continue to be requested.

### Shared benefit

- The parties can discuss a metric based on its semantics and use case, not only on the requested API form.
- Every accepted item has a support type, owner, delivery phase and validation expectation.
- The design can continue evolving without reopening the entire architecture for every new metric.

## Internal lesson / optimization

For P27/P28, every new metric request should be evaluated using a standard decision record:

- metric / event definition;
- layer and data owner;
- customer scenario and consumer;
- freshness / timing requirement;
- existing interface candidate;
- ordinary ICD / on-demand ICD / MAL / primitive / new ICD assessment;
- performance and memory impact;
- privacy / security / information boundary;
- validation owner and method;
- delivery phase;
- disposition: agree, limitation, future-program, not support or escalate.

Relay Metrics should be managed as a **living product/interface backlog**, not a one-time feature list.

## External lesson / optimization

Alcedo and Zion should jointly evaluate a new metric request in this order:

1. What customer scenario requires the metric?
2. What decision or debug action will the metric support?
3. What timing, freshness and lifetime are required?
4. Can an existing ICD, on-demand ICD, MAL API or primitive satisfy it?
5. If not, what new interface is required and what is the cost/risk?
6. Who owns collection, consumption and validation?
7. What delivery phase and disposition are accepted by both sides?

This creates a win-win conversation: the customer requirement remains visible, while the implementation uses the most sustainable mechanism available.

## P27/P28 implication

Keep a versioned shared Relay Metrics reference, but add explicit change-control rules:

- baseline / cutoff for each delivery phase;
- new-request intake and review cadence;
- metric semantic and timing definition;
- support-type decision;
- cross-layer owner;
- customer-consumer / validation owner;
- delivery gate;
- limitation or future-program disposition.

## Slide-table version

### Key Event

```text
Relay Metrics — Cross-Layer Metric Design and Delivery Governance
```

### What was discussed and what was decided

```text
Relay Metrics crossed multiple modem domains/layers and grew to 1,200+
metric definitions in the living reference. For each metric/event, Alcedo
and Zion aligned the definition, timing, instance scope, interface, support
status, delivery phase and validation expectation.

Each item was mapped to the most suitable delivery form — ordinary ICD,
on-demand ICD, MAL API, existing primitive/interface, new ICD/interface,
or limitation/not support — instead of forcing every requirement through
one mechanism. Existing design was reused where sufficient; new interfaces
were reserved for requirements that could not be met sustainably otherwise.
```

### Lesson

```text
Zion's initial proposal is not automatically the most suitable P26 solution.
A sustainable win-win design reuses existing ICD/MAL capabilities where they
meet the scenario, introduces new interfaces only when necessary, and makes
the support, performance and delivery trade-offs explicit to both sides.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: cross-layer requirement / interface / delivery review
- Good point: versioned shared reference and mechanism classification
- Improvement: change control for a continuously expanding metric backlog
- Internal optimization: metric decision record and sustainable interface reuse
- External optimization: scenario-first metric negotiation and shared disposition
- P27/P28 artifact: Relay Metrics managed backlog / change-control register
