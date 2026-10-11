# Key Event #4 — Customization Features (FLD1 / FLD2 / Exception Features)

## Recommended event title

**Customization Feature Governance (FLD1 / FLD2 / Exception Features)**

The original title can remain in the table if the preparation template requires it:

```text
Customization Features (FLD1 / FLD2 / Exception Features)
```

## What was discussed and what was decided

- **Scope lock:** The feature list, scope and interface for FLD2 were reviewed against the agreed lockdown boundary. Items not confirmed before the deadline were treated as out of scope, moved to a later phase, or required formal change control instead of being silently added to the current release.
- **DRI assignment:** Each feature required a named technical DRI and supporting owners so that feasibility, interface definition, effort and follow-up were not left as a general team responsibility.
- **Effort estimation:** Effort had to be recorded for every item, including items tracked through a bug/CR or another project, so that technical feasibility, resource demand, billing/scope discussion and schedule impact could be reviewed together.
- **Bug / feature classification:** Customer-reported behavior was evaluated against the agreed behavior and customer impact. For example, the MCC band-learning issue was treated as a bug only if it caused a low-power KPI failure; otherwise it was treated as a design limitation or a later enhancement.
- **Joint-development classification:** Joint-development features were separated from self-contained features and from customer-driven test features. For joint development, the parties needed to define what Alcedo would provide, what Zion would implement or tune, and which side would perform system-level validation.
- **Validation classification:** The process distinguished:
  - Alcedo self-contained implementation and UT/RDIT;
  - features requiring SV/FO support and broader regression;
  - customer-specific interface/shell features where Zion owns AP/IMS/device/system IT;
  - joint-development or customer-verified features that follow a different test path.
- **Feature enablement:** The feature contract also needed to define default ON/OFF behavior and carrier/scenario enablement. When the customer requirement was not explicit, the FLD2 discussion used MTK public behavior as the default for the feature-off state.
- **Exception handling:** Late or high-risk requests were not treated as normal feature additions. They required technical feasibility, risk and effort assessment, status/approval level, schedule negotiation and a decision to implement, defer to P27, or reject.
- **Documentation:** The requirement, interface, scope, DRI, effort, validation category, action items and final decision were recorded through the shared feature list, requirement/interface documentation, NDA Jira/CR and release/check-in tracking.
- **Post-delivery handling:** The collaboration model also had to define how a failure or new requirement after delivery would be classified and routed: bug, design limitation, new feature, scope change, QPR or next-program item, with a technical owner and a customer validation / closure path.

## Recommended lesson

> **Customization development requires a jointly accepted governance model, not only a feature list: scope, DRI, effort, bug/feature classification, joint-development boundary, design/interface documentation, verification responsibility and post-delivery bug-fix routing must be agreed and recorded before commitment.**

## Stronger lesson wording for the slide

```text
Joint-development details and boundaries must be explicit and documented.
For every customization, both sides must agree on the requirement/interface,
R&R, verification path and how issues move from bug-fix to release and closure.
```

## Why this matters for P27/P28

The feature list alone does not answer the questions that determine whether a customization can be delivered predictably:

```text
What is in scope?
Who owns the technical work?
Who estimates the effort and accepts the risk?
Is it joint development or Alcedo self-contained?
Who tests the modem interface?
Who tests the customer AP/device/carrier behavior?
What happens when the result is a bug or a new request?
Who owns the fix through release and closure?
```

If these questions are not resolved before commitment, the same feature can be interpreted differently during implementation, customer IT, certification or later bug fixing.

## Internal lesson / optimization

For P27/P28, the Alcedo feature record should link:

- requirement and use case;
- interface document and message flow;
- scope-lock status;
- Alcedo technical DRI and supporting module owners;
- effort and risk estimate;
- bug/feature/limitation classification;
- joint-development or self-contained classification;
- Alcedo UT/RDIT and SV/FO decision;
- Zion device/AP/system IT responsibility;
- escalation and schedule commitment authority;
- release/check-in target;
- bug-fix, QPR and closure owner.

Technical DRI provides feasibility, interface and effort conclusions. Management/EPN decides schedule commitment, risk acceptance and final delivery commitment.

## External lesson / optimization

Alcedo and Zion should jointly document, for each customization:

1. Requirement and expected behavior.
2. Interface and high-level message flow.
3. Scope and carrier/scenario enablement.
4. Joint-development vs. Alcedo self-contained boundary.
5. Implementation, tuning and verification responsibility on each side.
6. Required customer device/AP/network/SIM test environment.
7. Bug-fix and change-request routing.
8. Release, acceptance and closure criteria.

This is the collaboration model that both sides can use; it is not only an Alcedo internal process.

## P27/P28 implementation

Make the following a mandatory feature-commitment package:

- Feature Verification & Enablement Matrix;
- documented requirement and interface package;
- joint-development / self-contained decision;
- verification and acceptance plan;
- risk / effort / schedule decision;
- post-delivery bug-fix and QPR routing.

A feature should not be marked committed until the required fields are completed or the remaining gap is explicitly accepted as a management risk.

## Slide-table version

### Key Event

```text
Customization Features (FLD1 / FLD2 / Exception Features)
```

### What was discussed and what was decided

```text
Reviewed and governed customization scope through scope lock, DRI assignment,
effort estimation, bug-versus-feature classification, joint-development vs.
Alcedo self-contained classification, and validation responsibility.

Requirement/interface documents, feature decisions and action items were
tracked through the shared feature list, NDA Jira/CR and release/check-in flow.
Late or high-risk requests required documented feasibility, risk, escalation,
schedule and P26/P27 disposition before commitment.
```

### Lesson

```text
Joint-development details and boundaries must be explicit and documented.
Both sides must agree on the requirement/interface, R&R, verification path,
and bug-fix-to-release/closure model before customization is committed.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: feature governance and documentation flow
- Good point: scope / DRI / validation / effort classification
- Improvement: make joint-development boundary and post-delivery routing mandatory
- Internal optimization: feature-commitment package and DRI completeness gate
- External optimization: jointly accepted requirement/interface/R&R/verification model
- P27/P28 artifact: Feature Verification & Enablement Matrix + documented execution contract
