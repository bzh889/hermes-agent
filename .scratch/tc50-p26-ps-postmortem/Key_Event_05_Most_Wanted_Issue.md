# Key Event #5 — Most Wanted Issue

## Recommended event title

**Most Wanted Issue Execution**

Optional subtitle:

```text
ECC / OOS / Call Performance hot-spot execution with customer-linked DRI follow-up
```

## What was discussed and what was decided

- P26 Most Wanted moved into a high-frequency execution model:
  - weekly review during the initial period;
  - daily review from 2026/3/30 through the P26 certification/MP support window;
  - daily internal status tracking and customer-facing review/follow-up;
  - Area TL / domain DRI ownership and release-gate tracking.
- ECC, OOS/Registration and Call Performance were major PS hot-spot areas. The exact convergence pattern differed by area:
  - ECC/OOS had repeated daily execution through scenario review, log analysis, patch discussion, customer retest and RC/FRC/SU0 disposition;
  - Call Performance had a high issue volume and dedicated ownership, but did not converge at the same pace as the recurring ECC/OOS execution stream.
- The formal review cadence was supplemented by ad-hoc small-group discussions between the corresponding Zion and Alcedo DRIs when an issue required deeper technical discussion, log review, cross-module analysis, workaround agreement or a decision before the next formal review.
- These small groups were used to move specific issues forward rather than treating the daily review as the place to complete every technical analysis.
- The MWI process connected customer issue tracking to release gates and decisions, including:
  - RC / LE0 / LE1 classification;
  - FRC lockdown;
  - SU0 candidate selection;
  - temporary patch and customer retest;
  - QPR deferral;
  - waiver or permanent deferral where appropriate.
- The process also made the scale of the execution visible. The 2026/4/21 snapshot recorded 218 Most Wanted issues, with 111 open under debugging; Call Performance, OOS/Registration and ECC were among the tracked areas.
- Daily reviews did not mean every issue was closed in the meeting. The intended collaboration path was:

```text
Customer scenario / issue
→ area DRI triage
→ ad-hoc technical deep dive where needed
→ RCA / workaround / patch direction
→ customer retest and validation
→ RC/FRC/SU0/QPR disposition
```

- Security fixes that occurred during this period were handled as urgent items within the MWI execution stream, not as a separate post-MP discovery.

## Recommended lesson

> **Zion’s field, carrier and user-scale data exposed scenarios that were not always covered by Alcedo’s standard turnkey experience. The MWI collaboration therefore created value beyond issue closure: it provided real-world feedback that allowed Alcedo to improve modem behavior and make the design more robust.**

## Stronger lesson wording for the slide

```text
Zion's field and carrier data exposed scenarios beyond the historical turnkey
experience. A close DRI-to-DRI and small-group collaboration loop turned these
cases into opportunities to improve user experience and strengthen the
robustness of the modem design.
```

## Why this is a meaningful P26 lesson

The value of MWI was not simply that it created more meetings or a larger bug list. Zion contributed:

- large-scale user and field observations;
- carrier-specific behavior and data;
- real network and device scenarios;
- customer-side reproduction and validation;
- priority and certification impact.

Alcedo gained exposure to cases that its standard turnkey deployments might not have triggered or revealed at the same scale. This helped identify gaps in:

- carrier-specific handling;
- ECC/OOS scenario chains;
- registration and network behavior;
- Call Performance conditions;
- AP/Modem interaction;
- release and regression coverage.

## Internal lesson / optimization

Alcedo should preserve an internal loop that turns MWI cases into reusable engineering improvement:

1. Capture the customer scenario, carrier and environment.
2. Separate customer-specific behavior from a general modem robustness issue.
3. Identify whether the issue is limited to one module or crosses the complete scenario chain.
4. Record the confirmed root cause, workaround, permanent fix and validation evidence separately.
5. Feed reusable findings into regression, design guideline, module-owner review and next-program planning.
6. Keep MUS / DRI / RD / HQ boundaries explicit so the issue does not stop at triage.

This prevents customer data from being used only for one-off patch delivery.

## External lesson / optimization

Alcedo and Zion should maintain the close DRI-to-DRI and small-group loop, but make the input package consistent:

- carrier / network;
- device / AP / SIM configuration;
- exact scenario and expected behavior;
- logs and reproduction result;
- customer impact and priority;
- requested decision or next experiment;
- owner for customer retest;
- release / QPR disposition.

This lets Zion’s field data produce reusable modem improvements while reducing repeated clarification cycles.

## P27/P28 implication

Treat MWI as both:

- a certification / launch execution mechanism; and
- a structured field-learning input to improve the next modem design.

For each high-value MWI case, add a disposition beyond “fixed/closed”:

- customer-specific workaround;
- reusable modem robustness improvement;
- regression test / design guideline update;
- next-program action;
- limitation accepted with rationale.

## Quantified evidence for the slide

Use the following with explicit snapshot labels:

```text
2026/4/21 MWI snapshot:
218 total issues; 111 open under debugging.

Area counts in the same snapshot:
Call Performance 20; OOS/Registration 15; ECC 15.
```

Do not present these as the complete four-year P26 issue count. They are a dated execution snapshot.

## Slide-table version

### Key Event

```text
Most Wanted Issue Execution
(ECC / OOS / Call Performance hot-spots)
```

### What was discussed and what was decided

```text
MWI moved to daily execution with Area/Domain DRI ownership, customer
updates and RC/LE0/LE1/FRC/SU0 release gates. ECC/OOS and Call Performance
were high-volume PS hot-spots. Formal reviews were supplemented by ad-hoc
DRI-to-DRI small groups for deep dives, log/RCA review, workaround/patch
direction and customer retest.

The 2026/4/21 snapshot recorded 218 MWI issues, including 111 open under
debugging; Call Performance, OOS/Registration and ECC were major tracked
areas. Security fixes were handled within the MWI execution stream.
```

### Lesson

```text
Zion's field and carrier data exposed scenarios beyond the historical turnkey
experience. A close DRI-to-DRI and small-group collaboration loop turned
these cases into opportunities to improve user experience and strengthen the
robustness of the modem design.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: daily review + ad-hoc DRI small groups
- Good point: field data and customer-linked technical convergence
- Improvement: carry issue learning from triage/patch into reusable design and regression improvements
- Internal optimization: scenario-to-RCA-to-reusable-learning loop
- External optimization: consistent field-data and reproduction package
- P27/P28 artifact: MWI learning / robustness disposition register
