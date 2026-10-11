# Key Event #2 — PS Customization Workshop

## Recommended event title

**PS Customization Workshop**

## What was discussed and what was decided

- The workshop established the working model for Alcedo–Zion PS customization rather than reviewing feature status only.
- For each customization feature, the discussion covered and documented:
  - customer requirement and use case;
  - scope and interface definition;
  - feature DRI on each side;
  - message flow / high-level interaction where needed;
  - implementation boundary;
  - default enable/disable behavior;
  - carrier or scenario-specific enablement;
  - validation responsibility;
  - delivery milestone and follow-up.
- Requirement and interface information was maintained as documentation, with an external-facing level of detail and an internal version containing additional implementation guidance. The external document was intended to support integration and alignment without exposing the full internal module design.
- The workshop distinguished two different feature collaboration models:
  - **Joint development:** Alcedo and Zion jointly define or implement the feature, with the validation scope and system test responsibility agreed case by case.
  - **Alcedo self-contained / interface delivery:** Alcedo delivers the modem logic, API or interface shell and performs the agreed UT/RDIT scope; Zion owns the customer-specific AP/IMS/device/system integration and IT where the behavior depends on the customer environment.
- The workshop and follow-up process also covered how to handle issues found after delivery:
  - classify the item as a bug, design limitation, new feature or scope change;
  - assign the technical DRI and supporting owners;
  - record the requirement, interface and action in the agreed tracker / CR documentation;
  - determine whether Alcedo, Zion or both sides need to reproduce and validate;
  - route unresolved or late/high-risk requests through the appropriate escalation and schedule decision;
  - continue the item through fix, customer validation, release/check-in and closure.
- FLD1/FLD2 follow-up provided concrete governance examples:
  - scope and interface confirmation before the feature-lock deadline;
  - effort estimation for each item;
  - joint-development and customer-verified features treated differently from self-contained features;
  - features outside the locked scope deferred or handled through formal change control;
  - feature-off behavior defined, including fallback to the MTK public behavior when the customer requirement was not explicit.
- The workshop therefore established a shared collaboration model for feature definition, implementation, verification, bug-fix ownership and closure. It was not only a recurring meeting arrangement.

## Recommended lesson

> **The PS customization workshop established the collaboration foundation for P26: Alcedo and Zion needed one jointly understood model covering documented requirements and interfaces, feature ownership, enablement, validation responsibility, bug-fix routing and closure.**

## Stronger lesson wording for the slide

```text
A mutually understood collaboration model is a prerequisite for scalable
customization development: document the requirement and interface, classify
joint-development versus Alcedo self-contained scope, define each side's
verification responsibility, and keep bug-fix ownership through release and
closure.
```

## Why this matters for P27/P28

The workshop created the basic structure on which later customization work could proceed. Without a jointly accepted model, the same feature can be interpreted differently by the two sides:

```text
Alcedo: interface / modem logic delivered
Zion: customer AP / device / carrier behavior not yet validated
```

or:

```text
Alcedo: customer-specific self-contained feature
Zion: joint-development feature requiring shared implementation and tuning
```

The collaboration model prevents these differences from being discovered only during integration, certification or bug escalation.

## Internal lesson / optimization

For P27/P28, the Alcedo DRI should complete a feature collaboration record before delivery commitment. The record should link:

- requirement and use case;
- requirement / interface document;
- default enable state and carrier/scenario scope;
- Alcedo and Zion technical owners;
- joint-development or self-contained classification;
- Alcedo UT/RDIT scope;
- SV/FO decision and rationale;
- Zion device/AP/network/SIM IT scope;
- bug-fix and escalation owner;
- release/check-in target;
- customer acceptance and closure evidence.

The PS Lv1 DRI owns completeness and routing; the feature/module DRI owns technical correctness and the actual fix.

## External lesson / optimization

Alcedo and Zion should jointly agree, before implementation starts:

1. What the feature is expected to do and in which carrier/scenario.
2. Whether the feature is joint development or Alcedo self-contained.
3. Which side owns implementation, tuning and system integration.
4. What Alcedo can verify without the Zion device/AP environment.
5. What requires Zion device/system IT.
6. How a failure is classified and routed.
7. What evidence is required for acceptance.
8. How the item moves from implementation to bug fix, release and closure.

This is a joint operating model, not a request to expose Alcedo's internal module implementation.

## P27/P28 implication

Retain the PS customization workshop and weekly forum, but make the collaboration model explicit and reusable through a shared feature record / execution contract. The record should be reviewed at:

- feature baseline;
- interface freeze;
- implementation readiness;
- validation readiness;
- release/check-in;
- post-MP or QPR handoff.

## Quantified / dated evidence that may support the slide

- **2024/9/24:** selected anchor for the PS customization collaboration model.
- **2024/4/29 FLD2 follow-up:** scope/interface confirmation, effort estimation and validation classification were due by the stated deadline.
- **P26 FLD2 feature list:** tracked through a shared feature list and NDA Jira, with multiple feature and DRI categories.
- **P26 customization inventory:** use the verified count only after confirming the counting scope; do not use the 271 figure without reconciling its denominator.

## Slide-table version

### Key Event

```text
PS Customization Workshop
```

### What was discussed and what was decided

```text
Established a documented Alcedo–Zion model for PS customization:
requirement and interface documentation, feature DRI and scope, default
feature behavior, joint-development vs. Alcedo self-contained classification,
validation responsibility, delivery follow-up, and bug-fix routing.

The model distinguished Alcedo UT/RDIT from Zion device/AP/system IT and
defined how unresolved scope, late requests and post-delivery issues move
through escalation, release/check-in and closure.
```

### Lesson

```text
A jointly accepted collaboration model is the foundation for scalable
customization development. Requirement/interface documentation, ownership,
verification responsibility and bug-fix-to-closure routing must be agreed
before implementation is committed.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: PS customization forum and documentation model
- Good point: documented feature / R&R / validation structure
- Improvement: make the model mandatory and complete before commitment
- Internal optimization: feature collaboration record and DRI completeness gate
- External optimization: jointly accepted requirement, interface and validation contract
- P27/P28 artifact: Feature Verification & Enablement Matrix + Execution Contract
