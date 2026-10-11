# Key Event #8 — SIM Lock Issues

## Recommended event title

**SIM Lock Issues — First Major Post-MP / In-Market Event**

## What was discussed and what was decided

- This was the first major P26 post-MP/in-market SIM Lock event, involving two related but not yet proven-identical issues:
  - **ALPS11585308:** SIM Lock data read back from the Modem did not match the data set by the AP.
  - **ALPS11585456:** eSIM profiles unexpectedly entered a restricted state on commercial devices.
- The P26 Google SIM Lock mechanism was a Zion-specific customization with a different operating model from a traditional factory-programmed SIM Lock:
  - the SIM Lock server controlled carrier-restriction data;
  - the device downloaded the configuration after network connection;
  - AP used `setAllowedCarriers` / `getAllowedCarriers` through the MIPC/AT-command path;
  - the data was stored in Modem NVRAM;
  - AP read back the data and rewrote it when the returned value did not match the expected value.
- For ALPS11585308, a valid GID1 value ending in `0xFF` such as `20FF` was interpreted by the Modem read-back parser as an end-of-record marker. The returned value was truncated or corrupted, for example `20FF` being returned incorrectly instead of the original value.
- The AP detected the mismatch and repeatedly retried the SIM Lock write. Each write could trigger an intentional SIM power-cycle, which could interrupt SIM I/O and cause IMS registration failures.
- For ALPS11585456, the incomplete or corrupted SIM Lock state could lead to `CARD_RESTRICTED` behavior and eSIM profile disablement. The relationship to the GID1 retry/corruption chain was considered highly related but was not treated as fully proven without issue-time NVRAM and Modem-log evidence.
- The deep dive also identified a related data-handling risk: carrier-entry ordering and shared read-buffer handling could contaminate later entries, even apart from the `0xFF` terminator case.
- The short-term response separated two paths:
  - Modem temporary patch / GID-length handling correction;
  - server-side carrier-data mitigation, including removal/sorting of affected GID entries and QPR discussion.
- The longer-term direction included:
  - deeper review of the Google SIM Lock mechanism and data schema;
  - explicit GID length rather than sentinel-only parsing;
  - atomic NVRAM write;
  - backup and rollback on interrupted writes;
  - bounded retry / prevention of repeated write loops;
  - safer eSIM power-cycle handling;
  - longer-term security and integrity review.
- The customer impact was service-affecting: repeated SIM power-cycles could prevent IMS registration, while a persistent data mismatch or partial whitelist could cause the SIM/eSIM to remain restricted and prevent normal service use.

## Recommended lesson

> **Zion's Google SIM Lock is an AP-controlled, customer-specific mechanism that differs from the standard factory-programmed SIM Lock model. Because Alcedo had limited prior experience with this mechanism, P26 showed the need for an early deep dive using real carrier SIM Lock data and real AP/Modem read-back, retry, power-cycle and recovery scenarios.**

## Stronger lesson wording for the slide

```text
Customer-specific security features require domain-specific deep dive and
real-data validation before MP. For Google SIM Lock, AP-controlled carrier
restriction data, GID1/GID2 schema, read-back behavior, retry/power-cycle
handling and recovery must be validated with real carrier configurations —
not only with nominal or simplified test data.
```

## Why this is a meaningful lesson

The issue was not simply that one parser mishandled `0xFF`. The deeper lesson was a mismatch between:

```text
Google/Zion feature model
+ AP-controlled server configuration
+ variable-length carrier data
+ Modem NVRAM schema
+ AP read-back and self-healing retry
+ SIM/eSIM power and IMS behavior
```

and the assumptions carried by the original implementation.

Alcedo's previous experience with standard or internally used SIM Lock behavior did not fully cover the Google/Zion design. The feature therefore required a dedicated domain deep dive before MP, including actual carrier data such as GID1/GID2 values, entry ordering and extended-length cases.

## Confirmed facts vs. related hypothesis

### Confirmed / strongly supported

- `0xFF` at the end of a valid GID1 such as `20FF` was mishandled as a termination marker.
- AP read-back mismatch caused repeated SIM Lock writes.
- SIM power-cycles could affect IMS registration.
- A Modem patch corrected the GID-length/read-back handling for the primary issue and was reported effective, pending customer validation in the relevant records.
- The mechanism was Zion-specific and AP-controlled through MIPC/AT paths.

### Related but not fully identical / still requiring evidence

- Whether ALPS11585456's eSIM restriction was caused by the same GID1 retry chain and partial NVRAM write.
- The exact contribution of reboot timing, write interruption, NVRAM corruption and AP recovery logic.
- The final customer impact count, which differs between status records and must be reconciled before external presentation.

## Internal lesson / optimization

For P27/P28, any customer-specific security or carrier-restriction feature should require a pre-MP deep-dive package covering:

- mechanism and threat model;
- AP/Modem responsibility;
- data schema and legal value range;
- real carrier data set, including boundary values and variable lengths;
- read-back and retry behavior;
- power-cycle / reboot / interrupted-write scenarios;
- NVRAM integrity and rollback;
- Modem-log and customer observability;
- customer-device/system validation;
- short-term patch and long-term owner.

## External lesson / optimization

Alcedo and Zion should jointly provide and validate:

- real carrier restriction data;
- GID1/GID2 length and ordering cases;
- expected AP write/read-back behavior;
- retry and recovery limits;
- service-impact acceptance criteria;
- issue-time logs and NVRAM evidence;
- temporary mitigation versus long-term design decision.

The point is not to require Zion to expose unnecessary security implementation details. It is to ensure both sides test the same real data and agree on the expected behavior of a customer-specific mechanism.

## P27/P28 implication

Add a **Customer-Specific Security Feature Deep-Dive Gate** before MP. The gate should block final commitment until the mechanism, real-data test set, failure recovery, observability, security boundary, validation owner and long-term fix owner are documented.

## Quantified evidence for the slide

Use only after reconciling the source snapshot:

```text
45 major operators / MVNOs were cited as using GID1 values affected by the
0xFF parsing issue.

The eSIM restriction records cite different in-market report counts; do not
combine them without reconciling date and counting scope.
```

## Slide-table version

### Key Event

```text
SIM Lock Issues
(First Major Post-MP / In-Market Event)
```

### What was discussed and what was decided

```text
The first major post-MP/in-market issue involved Zion's AP-controlled,
customer-specific Google SIM Lock mechanism. For ALPS11585308, GID1=20FF
was misread by the Modem as a termination marker, so the AP repeatedly retried
SIM Lock writes. The resulting SIM power-cycles affected IMS registration.
A related restriction issue could leave the eSIM/SIM in CARD_RESTRICTED state,
preventing normal service; its complete causal link required issue-time NVRAM
and Modem-log evidence.

Short-term patch/server mitigation and longer-term actions were separated,
including explicit GID length, atomic NVRAM write, rollback, bounded retry and
safer eSIM power handling.
```

### Lesson

```text
Google SIM Lock is an AP-controlled, customer-specific mechanism rather than
the standard factory-programmed SIM Lock model. A dedicated deep dive using
real carrier data and real AP/Modem read-back, retry, power-cycle and recovery
scenarios is required before MP.
```

## PPT mapping

- Required item: **Key event in P26**
- Established co-working model: post-MP deep dive and urgent cross-team review
- Good point: temporary mitigation separated from long-term design correction
- Improvement: customer-specific security feature readiness and real-data validation
- Internal optimization: security-feature deep-dive gate and observability package
- External optimization: joint real-data test set and agreed recovery behavior
- P27/P28 artifact: Customer-Specific Security Feature Deep-Dive Gate
