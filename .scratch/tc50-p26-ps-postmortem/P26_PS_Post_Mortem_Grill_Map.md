# TC50 P26 PS Post-Mortem — Grill Map

> Independent working document for the Hermes copilot session.
> This is not a PKB wiki page, not a PKB synthesis, and not the final presentation.
> PKB is used only as a read-only evidence source.

## Purpose

Review the P26 PS-involved collaboration experience and convert the findings into practical improvements for the Alcedo–Zion collaboration model in P27/P28.

The material is for Clare and Justin to prepare for the 10/E Zion workshop.

## Scope and boundaries

- Final material is split into External (jointly discussable with Zion) and Internal (Alcedo-only).
- P26 review covers all PS-involved activities, not only MWI ECC/OOS/Call Performance/Registration/eSIM.
- Scope includes customization features, metrics, AI features, AP-IMS, SIM, feature alignment, issue/RCA/fix/validation/release activities, and relevant collaboration mechanisms.
- Zion PS (PMW) and Zion SIM are separate collaboration streams with overlap at selected interfaces.
- MWI is one P26 execution activity, not the full P26 PS scope.
- Primary analytical axis is the collaboration operating model and the lifecycle from intake through closure.

## Grill-with-docs operating commitment

For every question:

1. Ask exactly one question.
2. Keep it tied to a preparation-deck requirement or a direct prerequisite.
3. Wait for the user's answer.
4. Query PKB for supporting, contradictory, or missing evidence.
5. Record user input, PKB verification, reasoning, exclusions, PPT mapping, and downstream implications here.
6. Restate the consolidated understanding and wait for confirmation.
7. Keep unresolved matters instead of silently dropping them.
8. Create slides only after the working map and evidence ledger are confirmed.

## Confirmed interview decisions Q1–Q11

### Q1 — Purpose, audience, owner, and scope

**User decision:** Use Review B to improve Alcedo–Zion collaboration for P27/P28. Deliver material to Clare/Justin for the 10/E Zion workshop. Split the material into External and Internal.

**Owner context:** Aoss was PS Lv1 DRI before 2025. Hsuanchang became the effective PS Lv1 DRI from 2025 onward and leads this review; Hsuanchang's earlier Lv2 scope included L4, including IMS/SIM context.

**Scope correction:** ECC/OOS/Call Performance/Registration/eSIM are MWI area categories. The review must cover the broader P26 PS-involved lifecycle, including customization features, metrics, AI features, AP-IMS, SIM, feature alignment, issue handling, validation, release, and collaboration.

**PKB verification:** The preparation page assigns PS to Hsuanchang with Aoss, names Justin/Clare for overall project alignment, and lists many project topics beyond PS. P26 project, FLD2, PS customization, and PS/SIM sync records confirm the broader project and activity scope.

**Interpretation:** This is a TC50/P26 PS-involved collaboration post-mortem, not a P26 MWI-only report.

**Excluded interpretation:** Do not treat MWI categories as the full PS scope; do not imply every reviewed activity was PS-owned.

**PPT mapping:** Scope, co-working model, good points, improvements, lessons learned, internal/external optimization.

### Q2 — Time range and phases

**User decision:** Phase boundaries must be derived from PKB events, not assumed from calendar years. The resulting structure was broadly accepted.

**PKB-derived working phases:**

1. Customization scope and collaboration foundation — approximately 2023/7–2024/4.
2. Feature execution and operating-model formation — approximately 2024/9–2025/7.
3. P26 execution, MWI and MP support — approximately 2026/3–2026/8.
4. Post-MP learning and P27/P28 carry-forward — from 2026/8 through workshop preparation.

**Limitation:** Exact boundaries remain adjustable if stronger event records are found.

**PPT mapping:** Key events, established model, lessons learned.

### Q3 — Analytical focus

**User decision:** Analyze feature collaboration, issue collaboration, and project operating model, with collaboration operating model as the main axis.

**Lifecycle:** Requirement/issue intake → scope/priority → owner assignment → technical discussion → analysis/decision → implementation/fix → validation → release/closure.

**PPT mapping:** All required preparation areas.

### Q4 — External/Internal boundary

**User decision:** External examines the Alcedo–Zion interface; Internal examines Alcedo's complete path from customer input to technical closure.

**Interpretation:** The same case may have two views, but Internal implementation details and unconfirmed ownership conflicts must not be copied into External.

**PPT mapping:** External and internal optimization.

### Q5 — External workshop sequence

**User decision:** 1) align the current situation using shared evidence; 2) discuss P27/P28 joint improvements; 3) capture Zion feedback and commitment as action items.

**Audience rule:** Final External material is high-level and jointly discussable. It does not mention PKB, Teams, personal computers, or private-source mechanics; commonly known dates are summarized macroscopically.

### Q6 — Evidence handling

**User correction:** During preparation, every question and consolidation step must return to PKB for supporting, contradictory, or missing evidence. Final reporting abstracts the evidence into project-level observations without exposing private-source infrastructure.

**Per-question record:** user context; PKB evidence; Fact/Pattern/Interpretation/Open Question; contradictions/limitations; PPT mapping; External/Internal implication; P27/P28 implication.

### Q7 — Analysis unit

**User decision:** Main analysis is collaboration mechanisms and lifecycle; representative feature and issue cases validate the model.

**Interpretation:** Avoid both a process-only document and an unstructured case list.

### Q8 — Established co-working model

**User decision:** Four categories are complete:

1. Feature collaboration — PS customization sync, SIM feature sync, requirement/scope/DRI/validation alignment.
2. Issue collaboration — issue coordinator, NDA/public CR, DRI/RD co-working, MWI review, customer updates.
3. Technical collaboration — small-group discussions, technical deep dives, log/RCA/workaround discussions.
4. Project operating model — Area TL/domain DRI, HQ/MUS follow-the-sun, handoff/escalation, release/check-in/customer validation.

**PPT mapping:** Established co-working model.

### Q9 — Good points assessment

**Strong candidates:** feature scope/interface/ownership/validation alignment; recurring PS/SIM cadence; joint-development/customer-validation boundary; Coordinator/DRI/RD separation; P26/P27 feature/release continuity; scope discipline/out-of-scope control.

**Conditional:** HQ/MUS follow-the-sun continuity; MWI cadence/priority tracking; small-group technical discussion.

**Not yet confirmed as strengths:** static Area TL/domain DRI mapping; customer transparency/log-backed analysis.

**PKB basis:** FLD2 feature follow-up, PS/SIM recurring sync, issue-co-working, P26/P27 DRI/release records.

### Q10 — Partner account / firewall issue

**User decision:** Limited partner accounts were intentionally controlled by Clare/Justin as a firewall/access-boundary design. This is not an External failure and should not be framed as a request for broad access.

**Operational side effect:** Access, meeting, chat, and document requests concentrated around Hsuanchang as PS Lv1 DRI, creating an internal routing bottleneck and mixing access coordination with technical ownership.

**Improvement direction:** Preserve the firewall; establish primary/backup/coordinator routing and scoped direct collaboration capability for appropriate technical peers.

**Audience wording:** First acknowledge the governance design and then neutrally describe the operational side effect; do not blame the policy or an individual.

### Q11 — Improvement taxonomy

**User decision:** Four first-level themes:

1. R&R and routing clarity.
2. Technical coverage and time-zone continuity.
3. End-to-end lifecycle ownership.
4. Cross-module convergence.

Partner-account concentration is supporting evidence under R&R/routing and technical coverage, not a standalone main pain point. The US-daytime issue is not customer decision delay; it is the possible lack of a matching MUS technical peer/RD for the available Zion DRI.

## Confirmed PS key-event working set

Key events must be anchored to actual meetings, workshops, reviews, or clearly identifiable execution events. The following eight groups are provisionally accepted as the working set.

1. **PS customization workshop and recurring collaboration** — E1.
2. **P26 customization governance: FLD1/FLD2/Exception Features** — E5 + E11.
3. **AP-IMS/AP-DS/Modem hybrid architecture workshop** — E2.
4. **Relay Metrics requirement and delivery review** — E3.
5. **PS DRI/US support model and MWI execution** — E10 + E4; security hot-fix is an MWI substream.
6. **eSIM-only/extra-bytes debugging and verification** — E6; do not use “MEP” in the final title until its meaning is confirmed.
7. **SIM Lock: first major post-MP/in-market issue** — E7.
8. **QPR, workaround-to-next-program handoff, and long-tail support** — E9 + E12.

### Evidence audit

- E1: PKB has multiple dated PS customization workshop, internal-sync, customer-sync, and feature-review records; exact canonical title/date still to select.
- E2: Dedicated 2024/11/4–11/6 three-day workshop was read in full; strong evidence.
- E3: 2024/3/5 Relay Metrics requirement review was returned/read; additional project/reference/patch records exist.
- E4: MWI records, dated PS DRI reviews, ECC cases, Call Performance synthesis, and hot-fix records exist; Call Performance non-convergence remains user-confirmed and needs case consolidation.
- E5: FLD2 list/follow-up, dated reviews, DRI assignment records, and Exception Feature process exist and were read.
- E6: Dedicated P26 extra-bytes page was read; related SIM sync records exist; “MEP” remains unresolved.
- E7: Dedicated SIM Lock page and issue records were read; strong evidence.
- E9: QPR/patch, P26/P27 support, workaround/long-term-fix, and post-MP records exist; exact seven-year wording still needs authoritative confirmation.

### Additional sub-events

- **E10:** PS DRI sync-up / US support model and on-site execution planning; a distinct supporting anchor under MWI execution.
- **E11:** Exception Feature governance and technical-versus-commercial commitment boundary; a sub-event of customization governance.
- **E12:** QPR/workaround-to-next-program handoff; a sub-event of long-tail support and lifecycle ownership.

### Important corrections

- Security fix is part of MWI execution, not a separate post-MP discovery.
- QPR and long-tail support must be included because MP is not the end of the P26 collaboration lifecycle; P26 has a long support horizon.

## Current next frontier

### E1 decision record — PS customization workshop

**Question / frontier:** Which concrete event should anchor the PS customization collaboration key event, while keeping FLD1/FLD2/Exception Feature governance as a separate later event?

**User decision:** Use the **2024/9/24 PS customization workshop** as the primary E1 anchor. It represents the point at which the PS collaboration model became established. Treat FLD1/FLD2/Exception Feature as a separate subsequent feature-governance event, not as part of E1.

**PKB verification:** PKB returned and the session read the 2024/9/24 internal-sync and T900/Zion PS-customization workshop records, plus the surrounding 2024–2025 PS customization discussion family. PKB also returned the 2024/4/29 FLD2 feature follow-up separately, supporting the decision to keep FLD2 governance distinct from the 2024/9/24 collaboration-model anchor.

**Fact:** A dated 2024/9/24 PS customization workshop and related internal/customer discussion records exist. A separate 2024/4/29 FLD2 feature follow-up record also exists.

**Pattern:** The 2024/9/24 event belongs to the recurring PS customization collaboration stream; later records show this continued through feature status, DRI, customer sync, and follow-up discussions.

**Interpretation:** E1 should describe the establishment of a recurring PS collaboration interface. It should not attempt to summarize all later feature-governance controls.

**Deliberately excluded interpretation:** Do not merge the FLD2/Exception Feature governance event into E1 merely because both concern customization. Do not claim that 2024/9/24 was the first-ever P26 collaboration meeting; it is the selected anchor for the collaboration-model event.

**PPT mapping:** Established co-working model; key event; good point; lessons learned.

**External implication:** Present at a high level as the establishment of a recurring PS customization collaboration forum between Alcedo and Zion.

**Internal implication:** Examine whether the forum had sufficient preparation, decision ownership, and follow-through; keep private access/routing details out of External.

**P27/P28 implication:** Retain a recurring PS collaboration forum, while defining its connection to feature governance, DRI assignment, decision records, and closure tracking.

**Confirmation status:** Confirmed by user after PKB verification.

**Next frontier:** Validate E2 — the AP-IMS/AP-DS/Modem hybrid-architecture workshop and the specific collaboration decision it should represent.

### E2 correction and detailed workshop decomposition

**User correction:** The three-day workshop covered many independent topics. AP-IMS/AP-DS was only one topic. Only that topic produced the hybrid-architecture / responsibility-split conclusion; the other topics must retain their own conclusions and must not be blended into it.

**PKB verification:** The dedicated workshop page was read in full. It records topic-level objectives, discussions, decisions, actions, owners, and open items across the three days.

**Workshop topics recorded in PKB:**

1. Emergency domain selection / emergency-call flow — fail-cause handling, network-service scan, limited attach, RAT scan behavior, and AP/MD information responsibilities.
2. Airplane-mode emergency-call flow — `setRadioPower`, subscription preference, limited-attach logs, and normal-attach verification.
3. Access-network RAT parameters — AVAILABLE_RAT/PREFER_RAT and the split between modem capability and AP-side preference handling.
4. IMS media / voice-engine / RTP timing — SRVCC speech status, VoWiFi→VoLTE no-audio timing, ADSP_READY/CI_VALID behavior, RTP session timing, and audio-path refinement.
5. PDN / IWLAN / handover — PDN readiness, APN changes, MIPC proposals, and phased bearer-selection implementation.
6. DSDS / MSPM priority and control — same-priority procedures, RIL reference-count proposal, and modem implementation constraints.
7. PSI API / MIPC interface management — API support gaps, customer requirement input, and design-feedback ownership.
8. Testing / certification planning — SFN/PTN coverage, carrier pre-certification, non-IMS targets, blockers, and validation risk.

**Topic-specific interpretation:** Only the AP-IMS/AP-DS/Modem responsibility topic should be described as producing a hybrid architecture / responsibility split. The other topics should be consolidated separately according to their own decisions, proposals, owners, and open items.

**PPT mapping:** This remains one PS key event, but the working material must preserve the topic-level decomposition. The final slide may show the workshop as a multi-topic event with one highlighted architecture outcome and separate topic outcomes in notes/appendix.

**Open question:** Which of these eight workshop topic groups were within the PS review boundary, and which topic-level conclusions should appear in the main material versus appendix?

### E1 detailed evidence and decision support

**PKB records read for E1 and surrounding context:**

- 2024/9/24 internal sync on Zion PS customization features;
- 2024/9/24 T900/Zion PS customization sync workshop record;
- 2024/7/31 PS customization discussion as the immediate precursor;
- 2024/10/8, 10/15, and 10/22 PS customization / weekly-sync families as follow-through;
- 2024/11/19 internal preparation/follow-up record.

**What the 2024/9/24 material actually covered:**

1. **Workshop timing and preparation:** the Zion PS onsite workshop was moved from mid-October to early November so Alcedo could first conclude P0 customization interface design; internal target was end of October.
2. **Interface-document convention:** capture interface definition plus high-level interaction/message flow for external/internal alignment; do not provide full detailed module design externally.
3. **Internal versus external documentation:** external requirement/interface documents were to remain in the restricted external location; internal versions added MAL guidance and internal keyword conversion.
4. **MAL architecture direction:** keep the protocol core free of TC50-specific options where possible; use MAL interfaces and a design-principle decision flow to guide placement of customer-specific behavior.
5. **AOSP requirement influence:** RadioLinkValidation and Cellular Identifier/Cipher Transparency were discussed as examples of customer requirements affecting the wider platform/API boundary.
6. **IMS issue escalation:** an AP-notifying-modem gap led to customer escalation; the proposed direction involved EX IMS interface discussion and a prepared cross-team response.
7. **Feature tracker:** P0 joint-development features included Data Connectivity Monitoring, System Selection Monitoring, E911 Stuck Monitoring, Recovery Center, and Relay Metrics; other PS-involved items included UE capability/customization, scan, MEP/SIM disable, roaming cause conversion, and thermal/power topics.
8. **Delivery pressure:** P0 features were estimated at FC, while earlier ES2 delivery was discussed because of customer need, joint-development scope, and resource availability.
9. **Message-exchange flow:** Zion confirmed existing material covered message exchange and function calls; Alcedo preferred per-handle MAL APIs over a general send API, with no customer objection recorded.

**Consolidated interpretation:** E1 is more than “a recurring meeting was established.” It was a **collaboration-model design event** that set the working rules for feature scope, interface documentation, information boundary, MAL placement, customer requirement routing, joint-development status, and delivery discussion. The later PS customization meetings are the execution of this model.

**Good-point candidate:** The event established a structured, repeatable way to turn customer customization requests into requirement/interface artifacts, named DRIs, high-level message flows, and follow-up meetings without exposing full internal design.

**Improvement candidate:** The event also exposed that interface decisions, documentation boundaries, AOSP influence, customer escalation, feature tracking, and delivery timing were tightly coupled. P27/P28 should retain a single structured view linking requirement, interface, owner, information boundary, delivery milestone, and validation/closure.

**Recommendation:** Keep E1 as a major PS key event, but title it more precisely:

> **2024/9/24 PS Customization Workshop — Establishing the Feature Collaboration and Interface-Alignment Model**

Do not describe it only as “weekly sync established,” and do not merge FLD1/FLD2/Exception Feature governance into this event.

## Retrospective review of Q1–Q11 after expanded workshop inventory

The expanded read of workshop and meeting material changes several earlier
working assumptions. The changes below are updates to the decisions, not a
new interview round. They must be confirmed with the user before being treated
as final.

### Q1 — Scope needs a more explicit “workshop and technical-enablement” layer

**Adjustment:** The original scope already included feature, issue, technical,
and project-operating activities, but the workshop inventory shows that this
was too abstract. The scope must explicitly include:

- customer-facing technical workshops and deep dives;
- joint-debugging workflow and log/metric enablement;
- AP/MD interface and architecture alignment;
- cross-layer protocol walkthroughs (NAS/RRC/L2);
- training / Q&A streams that transfer operating knowledge and clarify APIs;
- exception, dump/recovery, PCIe, and power/integration discussions when they
  contain PS-involved AP/MD behavior or customer-facing technical decisions.

**Reason:** PKB contains concrete records for the 2023 Exception Workshop,
2024 T900 Workshop preparation, 2024 PS customization discussion, 2024
AP-IMS workshop, 2024 T900 PS Deep Dive Workshop, AP-IMS MIPC API training/Q&A,
and related integration workshops. These are not merely examples of meetings;
they are part of how the P26 collaboration model was built.

### Q2 — Phase boundaries should be workshop/event anchored, not only date ranges

**Adjustment:** Retain the four broad phases, but revise the first two to
reflect actual workshop anchors:

1. **Collaboration and technical-integration foundation** — at least
   2023/11 Exception Workshop through 2024/4 integration, workshop, and
   feature-alignment activity.
2. **PS collaboration model and feature execution formation** — 2024/7
   PS customization discussion, 2024/9/24 PS workshop, 2024/11 AP-IMS and
   2024/11 PS Deep Dive, followed by 2025 DRI/status/feature execution.
3. **P26 execution, MWI, certification, and MP support** — 2026/3–8.
4. **Post-MP, QPR, and P27/P28 carry-forward** — from MP onward.

The exact dates remain subject to the complete inventory. The important change
is that workshops are phase-defining events, not just background references.

### Q3 — Operating model remains the main axis, but workshops are lifecycle gates

**Adjustment:** The lifecycle model remains valid, but workshops must be
treated as explicit collaboration gates where the lifecycle moves between
states:

```text
Requirement / scenario
→ workshop / deep dive / training
→ interface and ownership decision
→ implementation or joint debugging
→ validation / release / follow-up
```

This prevents us from treating meetings as generic cadence. A workshop is
important when it changes the shared technical model, ownership, evidence,
or next action.

### Q4–Q5 — External/Internal boundary and workshop sequence remain valid

**Adjustment:** No change to the boundary or the External sequence. The
expanded workshop material reinforces the need to separate:

- externally shareable topic-level decisions and joint outcomes;
- internal preparation, architecture constraints, ownership friction, and
  unresolved items.

The final External report should describe workshop outcomes at a project level,
not expose private preparation artifacts or detailed internal source trails.

### Q6 — Evidence requirement is strengthened

**Adjustment:** For a workshop to become a key event, the working map must
retain the actual meeting/workshop anchor and topic-level evidence. A concept
summary alone is insufficient.

Required evidence fields now include:

- canonical meeting/workshop title;
- date or date range;
- source-family identity in the private working map;
- topic list;
- decision / proposal / open item per topic;
- participants or role boundary when relevant;
- PS-scope classification;
- PPT mapping.

### Q7–Q8 — Add “workshop / deep-dive collaboration” as an explicit mechanism

**Adjustment:** The four top-level categories remain, but Technical
collaboration must explicitly include two different mechanisms:

1. **Structured workshops / deep dives** — multi-day or agenda-driven
   architecture, protocol, integration, API, and debugging sessions.
2. **Recurring/ad-hoc operating discussions** — weekly syncs, small groups,
   issue reviews, and follow-ups.

Examples now in the working inventory include:

- T900 Exception Workshop;
- 2024 T900 Workshop / integration preparation;
- PS customization workshop;
- AP-IMS workshop;
- T900 PS Deep Dive Workshop (NAS/RRC/L2/Misc);
- AP-IMS MIPC API training/Q&A.

This distinction is necessary because workshop outcomes and recurring status
meetings have different collaboration value and should not be analyzed as one
generic “meeting cadence.”

### Q9 — Good points: add workshop-enabled technical convergence candidates

**Adjustment:** In addition to the previous good-point candidates, the
expanded inventory supports these candidates:

- Multi-day workshops created a shared technical vocabulary and direct
  Alcedo/Zion working context.
- The T900 PS Deep Dive agenda explicitly aimed to establish a joint-debugging
  workflow, including logs, metric exposure, and issue triage.
- AP-IMS MIPC API training/Q&A created a persistent clarification mechanism
  for registration, call, EPS fallback, SRVCC, voice engine, emergency/domain
  selection, and telephony integration.
- Workshop outcomes could establish concrete AP/MD interface proposals,
  phased implementation, owners, and follow-up actions.

These are still **candidate good points**, not final conclusions; their
effectiveness must be tested against later issue and feature cases.

### Q10 — Partner-account finding remains Internal-only; workshop access is a
supporting concern, not a new External problem

**Adjustment:** The workshop inventory shows that access and preparation are
prerequisites for technical workshops, but this does not change the previous
decision that the firewall/account policy belongs in Internal. Do not turn the
workshop inventory into a request for broad access. Instead, examine whether
scoped access, primary/backup routing, and preparation ownership allowed the
right Alcedo technical peers to participate without bypassing governance.

### Q11 — Improvement taxonomy remains, with a possible cross-cutting principle

The four themes remain valid:

1. R&R and routing clarity.
2. Technical coverage and time-zone continuity.
3. End-to-end lifecycle ownership.
4. Cross-module convergence.

The expanded workshop evidence adds a cross-cutting principle rather than a
fifth theme:

> **Workshop decisions need an explicit bridge to execution ownership,
> evidence readiness, validation, and closure.**

This principle can explain why a technically successful workshop may still be
followed by issue re-routing, incomplete validation, or analysis-to-fix gaps.

## Revised status after retrospective review

- Q1: **Needs scope wording expansion** — add workshops, deep dives, training,
  and technical-enablement activities explicitly.
- Q2: **Needs phase wording adjustment** — anchor early phases to actual
  workshops and technical events.
- Q3: **Confirmed with refinement** — workshops are lifecycle gates.
- Q4: **Confirmed**.
- Q5: **Confirmed**.
- Q6: **Strengthened** — concept pages alone are not sufficient event evidence.
- Q7: **Confirmed with refinement**.
- Q8: **Needs mechanism refinement** — distinguish structured workshops from
  recurring/ad-hoc discussions.
- Q9: **Expanded candidate good points** — workshop-enabled convergence and
  joint-debugging capability.
- Q10: **Confirmed** — Internal-only firewall/access consideration.
- Q11: **Confirmed with cross-cutting principle** — decision-to-closure bridge.

### E2 correction — do not treat one AP-IMS page as the four-year workshop inventory

**User correction:** The prior E2 analysis was premature. Reading only the dedicated AP-IMS concept page cannot establish the complete workshop inventory for P26. The source scope is `E:\mySharePointDownloader\Antica\30_External_Meeting_Preparation`; the correct next step is to inventory all workshop/meeting material from that source family as represented in PKB, then determine which events belong to PS and which are only background or other workstreams.

**PKB inventory search results so far:**

- `[[sources/zion-t900-workshop-preparation-20240311|Zion T900 Workshop preparation 20240311]]` — preparation for the 2024/3/19–3/21 T900 workshop; includes PS-relevant IMS integration, system verification, bring-up, and project-level topics.
- `[[sources/2024-07-31-alcedo-zion-ps-customization-discussion-2024-07-3|Alcedo-Zion PS customization discussion 2024/7/31]]` — actual external PS customization meeting with feature request DRI mapping, system-selection, modem health monitoring, relay metric, thermal/low-power, and other PS-involved topics.
- `[[sources/2024-10-30-tc50-ap-ims-procedure-deep-dive-material-preparation|TC50 AP-IMS procedure deep-dive preparation]]` — preparation coordination for a subsequent AP-IMS deep dive; useful as a lead-in record, not necessarily the main workshop event.
- `[[concepts/process/alcedo-zion-protocol-ap-ims-workshop|Alcedo-Zion Protocol/AP-IMS workshop]]` — the 2024/11/4–11/6 multi-topic workshop; must be decomposed topic-by-topic.
- `[[concepts/process/t900-ps-deep-dive-workshop-agenda|T900 PS Deep Dive Workshop Agenda]]` — 2024/11/11–11/14 four-day NAS/RRC/L2 deep dive, including relay-metric interface, debugging workflow, log collection, and issue triage.
- `[[concepts/process/t900-exception-workshop|T900 Exception Workshop]]` — 2023/11/28 exception/dump/recovery workshop covering AP/MD/HKM/PCIe integration and joint debugging flows.
- `[[concepts/sw-arch/t900-pcie-power-optimization|T900 PCIe Power Optimization]]` — 2024/4/3 workshop record; likely relevant to PS-involved AP/MD integration but needs scope classification before inclusion.
- `[[concepts/process/ap-ims-mipc-api-training-guideline-qa-alcedozion|AP IMS MIPC API Training Guideline Q&A]]` — an extended customer Q&A / training-follow-up stream covering registration, call, EPS fallback, SRVCC, voice engine, emergency/domain selection, and telephony integration. It may represent a workshop family rather than one meeting.
- P26 PS customization workshop family, including the 2024/9/24 workshop and 2024/7/31 meeting, plus later 2024–2025 follow-ups.

**Important limitation:** The above is an initial PKB-returned inventory, not yet an exhaustive enumeration of `30_External_Meeting_Preparation`. Several queries returned many `list` candidates and `unread_count` values, so the inventory must be expanded with larger budgets and topic-specific queries before selecting final key events. One attempted query also used the wrong working directory and failed; no conclusion was based on that failed call.

**Revised method:**

1. Enumerate workshop/meeting families from PKB, not just concept pages.
2. Read each non-stub candidate fully.
3. Tag each record as PS, PS-involved, adjacent/background, or out of PS scope.
4. Extract actual date, title, participants/roles, topics, decisions, and follow-up.
5. Group repeated meetings only after the actual inventory is complete.
6. Present the user a candidate inventory for validation before calling anything a PS key event.

## Expanded Zion workshop / meeting inventory review

This review was rerun from PKB using broad Zion/Alcedo, T900 workshop, PS
customization, PS deep-dive, AP-IMS, SIM/eSIM, Relay Metrics, MWI, and QPR
queries. The combined result produced 83 unique candidates before filtering.
Several broad queries still reported unread/list candidates, so this is a
substantially expanded inventory, not a mathematical proof that no source is
missing. Candidate discovery and final evidence read-back remain separate.

### Non-negotiable PS filter

This is a **PS Post-Mortem**, not a general TC50/Zion collaboration
post-mortem. A Zion-related workshop is not included merely because it is
customer-facing, technically important, or stored under the external-meeting
source family.

An event may enter the PS working inventory only when at least one of these is
true:

1. The primary topic is PS / Protocol Stack, including NAS, RRC, L2, data
   path, registration, system selection, ECC/OOS, call performance, eSIM/SIM,
   or PS customization.
2. A PS DRI, PS domain owner, or PS-defined interface is a material owner or
   decision participant.
3. The event defines or changes a PS-involved customer interface, API,
   metric, debugging flow, validation path, or lifecycle handoff.
4. A non-PS topic has a direct, material dependency on PS behavior or PS
   collaboration, and that dependency is explicitly recorded.

Events that are only RF, GNSS, NTN, desense, power, PCIe, security, factory,
or other workstreams remain excluded unless the record demonstrates a direct
PS-involved collaboration or dependency. They may be retained as “reviewed
but excluded” for auditability, but must not become PS key events, good
points, or improvement evidence.

Every candidate receives one classification:

```text
PS-core / PS-involved / Adjacent-background / Out of PS scope / Evidence insufficient
```

Only PS-core and PS-involved candidates proceed to PS key-event selection.

### Newly confirmed or elevated event families after PS filtering

| Event family | Evidence status | PS relevance / use |
|---|---|---|
| 2023/12 IMS deep-dive training-guideline discussion | Dedicated summary read; API/deep-dive guideline pages also returned | Early AP-IMS/MIPC collaboration, requirement controversy, API clarification, domain-selection and carrier requirements. Important foundation event. |
| 2024/3/19–3/21 T900 workshop | Preparation and March action-item update read | **PS-involved portions only:** IMS integration, system verification, PS milestone/feature criteria. General HW/RF schedule is excluded. |
| 2024/3 Relay Metrics requirement reviews | 2023/11/24, 2024/3/5 records returned/read; later reference and patch families found | Should be a Relay Metrics event family, not only the 2024/3/5 internal record. |
| 2024/4/3 PCIe Power Optimization workshop | PKB record exists as a source stub/concept family | **Evidence insufficient / likely adjacent.** Do not include until direct PS dependency is read back. |
| 2024/7/31 PS customization discussion | Full 46-line record read | Direct PS event: DRI mapping, modem-health/recovery, system selection, relay metrics, thermal/low-power, and customer requirements. This is an important precursor to E1. |
| 2024/9/24 PS customization workshop | Multiple dated records returned | Confirmed E1 canonical anchor by user. |
| 2024/10/29–11/7 PS Deep Dive planning/rehearsal | Full planning record read | Shows a deliberate shift from design introduction to issue debugging and joint-analysis flow. This is a key event in its own right. |
| 2024/11/11–11/14 PS Deep Dive execution/summary | Agenda and outcome summary read | Four-day NAS/RRC/L2/Misc event; outcomes include joint-debugging workflow, code/trace information requests, Relay Metrics agreement, and follow-up ownership. Strong PS key event. |
| 2024/11/4–11/6 Protocol/AP-IMS workshop | Full concept page read | **PS-involved by topic only:** include AP-IMS/domain-selection/registration/voice/DSDS/PS-interface portions; exclude unrelated material. |
| AP-IMS MIPC API training/Q&A family | Full guideline/Q&A pages read | Should be modeled as an extended enablement stream, not automatically collapsed into the November workshop. |
| AGPS meeting-note family, 2024/7/30–9/2 | Records exist, but several failed image/text conversion | Event existence is confirmed; substantive conclusions are not reliable enough for key-event selection without re-extraction. |
| 2025/7/16 Alcedo–Zion F2F | Full 34-line record read | **PS-involved items only:** L1 metrics, VoNR/L2 power feature, PS/API or customer-feature feasibility and commitment. RF/antenna/GAAM/6Rx/SpaceX items are excluded. |
| 2026 PS DRI/MWI/QPR support families | Multiple project, source, and meeting families returned | Execution, MWI, support, patch, release, and long-tail lifecycle events. |

### Important inventory correction

The 2024/11 PS Deep Dive is not merely an agenda. PKB contains both the plan
and a 2024/11/19 outcome summary. The outcome records:

- Zion's onsite PS DRI broadly accepted the responses without escalation;
- Zion requested additional code/trace visibility for selected scenarios;
- a MAC coverage concern was raised because some functions sit in L1/DSP;
- Relay Metrics on-demand ICD proposal was agreed;
- approximately 450 metric items required continuing item-by-item review and
  phased delivery;
- remaining NAS procedures and PS-related UAI/thermal topics were deferred to
  subsequent sessions.

This changes the interpretation of the workshop: it was both a successful
technical enablement event and an early signal of later access, coverage,
scope-boundary, and follow-through issues. It should not be described only as
“design sharing.”

### Inventory-based calibration of earlier questions

#### Q1 — Scope

**Calibrated:** “All PS-involved activities” must explicitly include
workshops, deep dives, training/Q&A, joint-debugging enablement, metric
interface definition, and AP/MD integration where PS DRIs or PS scenarios are
involved. It does not mean every Zion meeting in the external folder is in PS
scope; each event needs a PS-involved classification.

#### Q2 — Phases

**Calibrated phase anchors:**

1. **Foundation and enablement:** 2023/11 exception event, 2023/12 IMS
   training, 2024/3 T900 workshop and Relay Metrics reviews.
2. **PS collaboration model formation:** 2024/7/31 PS customization,
   2024/9/24 PS workshop, 2024/10–11 PS Deep Dive planning/execution, and
   AP-IMS workshop.
3. **Feature execution / transition:** 2025 DRI/status/customization
   execution and 2025/7/16 F2F early-enablement discussion.
4. **P26 execution, MWI, certification, MP and QPR:** 2026/3 onward.
5. **Post-MP long-tail / P27-P28 carry-forward:** QPR, in-market issues,
   workaround-to-next-program handoff, and future-program support.

This is now a five-phase working model rather than the earlier four broad
phases. The fifth phase separates 2025 feature execution/transition from the
2026 MWI/MP pressure period.

#### Q3 — Operating model

**Calibrated:** Workshops are not just lifecycle gates; they are sometimes
the first place where the parties establish the debugging workflow, decide
what information can be shared, define metric delivery, and expose gaps in
coverage or access.

#### Q7/Q8 — Mechanisms

**Calibrated:** Technical collaboration must distinguish:

- architecture / protocol workshops;
- enablement / training / Q&A;
- structured PS deep dives with joint-debugging flow;
- recurring feature/status syncs;
- issue/MWI reviews;
- post-workshop follow-up and closure tracking.

#### Q9 — Good points

**Calibrated candidates:**

- PS Deep Dive created a common protocol vocabulary and joint-debugging
  workflow.
- Relay Metrics on-demand ICD direction was agreed and assigned a framework /
  phased-delivery follow-up.
- The 2024/11 workshop responses were broadly accepted by Zion's PS DRI.

**Conditional rather than unconditional:** Code/trace access requests,
coverage concerns, and deferred NAS/UAI/thermal topics show that enablement
was useful but not complete. Therefore “workshop technical enablement” is a
good point with an attached improvement lesson, not a pure success claim.

#### Q11 — Improvements

The four themes remain, but the workshop inventory adds a cross-cutting
requirement:

> **Every workshop decision needs an explicit execution bridge: owner,
> information/access boundary, evidence or log readiness, validation method,
> delivery milestone, and closure follow-up.**

This is stronger and more specific than a generic “decision-to-closure bridge.”

## PPT alignment correction — Lessons Learned must be split Internal / External

**User correction:** The previous lesson-learned question was too generic and
did not explicitly follow the preparation deck's required split. Lessons
learned / suggestions beyond project must be developed separately as:

- **Internal lessons learned / internal optimization:** what Alcedo should
  change in its own R&R, preparation, technical coverage, handoff, escalation,
  decision, validation, release, and long-tail support model.
- **External lessons learned / external optimization:** what Alcedo and Zion
  should jointly change in their collaboration interface, requirement
  readiness, meeting/deep-dive preparation, information exchange, technical
  counterpart model, validation, decision, and closure alignment.

The shared evidence and root cause may be related, but the recommendations,
wording, owners, and requested commitments must remain separate. The External
section must first align shared evidence, then discuss joint improvement, then
capture Zion feedback/commitment. The Internal section may contain Alcedo-only
coverage, access-control side effects, handoff, staffing/capacity, and
ownership details.

The generic “execution bridge” lesson is therefore only a **candidate common
principle**. It is not yet a completed Lessons Learned answer until it is
decomposed into an Internal version and an External version and mapped to the
preparation deck requirements.

## E2 detailed evidence and decision support — IMS enablement family

**Event family under review:** 2023/12 IMS deep-dive training-guideline discussion and the continuing AP-IMS/MIPC API training/Q&A stream. This is kept separate from the 2024/11 multi-topic Protocol/AP-IMS workshop.

**PKB records read:**

- `Zion-IMS-deep_dive_training_guideline_summary_20231211`;
- `AP IMS MIPC API Training Guideline Q&A (Alcedo/Zion)`;
- `IMS AP Domain Selection` training guideline;
- related AP-IMS deep-dive/training records returned by the PS-filtered inventory.

**What the family actually covered:**

1. **Modem-control sequence and ownership:** SCM/UAC/MSPM resource ordering, session status, registration status, and the boundary between radio HAL and IMS HAL.
2. **Call/session procedures:** start/stop IMS traffic, EPS fallback, SRVCC, RTP session setup, speech control, early media, and voice-engine behavior.
3. **Registration:** registration-start/final-state updates, emergency registration versus emergency call status, RAT support, and deregistration reasons.
4. **Emergency/domain selection:** emergency network scan, airplane-mode emergency behavior, RAT preference, emergency callback, limited service/OOS scenarios, and AP-to-modem information flow.
5. **DSDS/MSPM:** RF-resource session priority, multiple IMS services, emergency call/SMS priority, and dual-stack resource contention.
6. **Telephony / RIL / AP integration:** call status, bearer information, IMS PDN setup, modem-unavailable handling, and AP resend behavior.
7. **Carrier-specific requirements:** AT&T 2G enable/disable indication, Verizon IMS deregistration behavior, T-Mobile paging/MT-call behavior, and whether a request was valid, unsupported, or required escalation.
8. **Training and follow-up status:** items were classified as fixed, ongoing, won’t fix, or reopen; the Q&A remained a continuing clarification mechanism rather than a single closed workshop.

**Concrete outcomes recorded:**

- A defined MIPC command sequence for common IMS traffic setup and teardown.
- Clarification that no single MIPC interface replaces the multi-command `startImsTraffic()` sequence.
- Explicit separation of emergency registration and emergency call status.
- Emergency/domain-selection API-to-MIPC mapping and scan/cancel behavior.
- Clear responsibility boundaries for AP/HAL behavior versus modem behavior.
- Multiple fixed items, while other items remained ongoing or required new customer requirements / further analysis.

**Consolidated interpretation:** This is a **PS-involved technical-enablement and interface-alignment family**, not merely a training event. It established shared vocabulary and operating knowledge for the AP/IMS team to interact with the modem, while also exposing the boundary between what Zion AP/IMS owns, what Alcedo modem owns, and what requires joint decision or customer clarification.

**Good-point candidate:** A persistent enablement mechanism was created: Alcedo could explain modem/AP interfaces and Zion could raise scenario-specific questions, with status tracked as fixed/ongoing/won’t-fix/reopen. This reduced the need to rediscover basic interface behavior in every later issue.

**Improvement candidate:** The Q&A also shows that training/interface clarification did not automatically close the full lifecycle. Some requests remained ongoing, invalid, or dependent on clearer customer scenarios; later issues still required AP/Modem boundary analysis. P27/P28 should connect each interface clarification to scenario, owner, test evidence, decision status, and closure—not only maintain a guideline.

**PPT mapping:**

- Key event: early PS/AP-IMS collaboration foundation.
- Established model: technical enablement and API clarification.
- Good point: shared vocabulary and persistent Q&A mechanism.
- Improvement: interface decision-to-debug/validation closure bridge.
- P27/P28: maintain an interface knowledge / scenario / ownership / validation loop.

**Recommended event title:**

> **2023/12 IMS Deep-Dive Enablement — Establishing the AP/Modem Interface and Joint Clarification Model**

This title is more accurate than calling it simply “AP-IMS workshop,” because the evidence describes a continuing training/Q&A family with both resolved and unresolved items.

**Next frontier:** Confirm whether E2 should remain a separate early-foundation event from the 2024/11 Protocol/AP-IMS workshop, or whether the final presentation should show them as two milestones within one AP-IMS collaboration stream.

### E2 decision record — AP-IMS collaboration evolution

**User decision:** Use option B. In the main timeline, combine the 2023/12 IMS enablement family and the 2024/11 Protocol/AP-IMS workshop into one **AP-IMS collaboration evolution** event. In the working map, retain two milestones:

- **E2-A — 2023/12 IMS Deep-Dive Enablement:** established the AP/Modem interface, MIPC vocabulary, procedure clarification, and continuing Q&A mechanism.
- **E2-B — 2024/11 Protocol/AP-IMS Workshop:** extended the collaboration into a multi-topic workshop with topic-specific decisions; the hybrid architecture conclusion applies only to the relevant AP-IMS/AP-DS/Modem topic.

**Consolidated interpretation:** E2 is an evolution of the AP-IMS collaboration model, not one workshop with one conclusion. The main timeline should show the evolution; the evidence map and appendix must preserve the two milestones and their separate outcomes.

**PPT mapping:** Key event; established co-working model; technical collaboration; lessons learned; P27/P28 interface and R&R improvement.

**Confirmation status:** Confirmed by user.

**Next frontier:** Proceed to E3 — Relay Metrics requirement and delivery collaboration family.

### E3 decision record — Relay Metrics as a continuously evolving collaboration stream

**User correction:** Relay Metrics must not be described as a 2023–2025 activity or as a completed historical project. It is a continuously evolving feature. Even after the core design direction was established, Zion continued to propose new metric fields and clarifications.

**PKB evidence read for the current stream:**

- Relay Metrics reference revision history lists repeated Zion and Alcedo updates from 2024/12 through 2025/2, including new fields and comments across NTN, Power, ENAS/NNAS, ERRC/NRRC, RTP, IP, PDCP, RLC, MAC, and L1.
- The reference contains more than 1,200 metric definitions and records support type, interface, status, delivery phase, Alcedo category, and Zion/Alcedo comments.
- Examples of continuing/new requests include paging metrics added in the January 2025 revision, new Protocol Init/Service Acquisition/First Attach/NAS service/SIM status events, UAI-related fields, RTP quality metrics, TCP/IP metrics, RLC/MAC/L1 counters, and ongoing changes to NTN/NAS/RRC items.
- The 2025/4 final-escalation records show continued request changes: RTP metric removal after Zion confirmed existing ICD was sufficient, Hiking/Airport Mode metric definitions, DMF collection strategy, ICD/MAL alternatives, proprietary-information boundary, and customer-side metric interpretation.
- The Relay Metric Framework defines continuing timer-based and event-based collection, callback/event lists, status semantics, stack_id, bounded-delay requirements, and Type A–D behavior. This is a living design/specification, not a closed delivery artifact.

**Fact:** Relay Metrics continues to receive new fields, clarifications, support classifications, delivery-phase decisions, and customer feedback after the initial design discussions.

**Pattern:** The collaboration is iterative and backlog-like: Zion adds or refines metric requirements; Alcedo evaluates architecture, support type, timing, privacy, performance, and delivery phase; both sides update the reference and follow-up decisions.

**Interpretation:** E3 should be modeled as a **continuous feature evolution and governance stream** spanning P26 and the post-MP/P27/P28 lifecycle. The key event is not “2023–2025 Relay Metrics activity”; the key learning is how a living, expanding cross-layer feature is governed over time.

**Good-point candidate:** A shared, versioned reference with status classes, support types, delivery phases, and comments created a durable collaboration surface for a very large metric set.

**Improvement candidate:** The living reference still requires strong governance to prevent requirement expansion from becoming unbounded follow-up. Each new metric should carry semantics, freshness/timing requirement, collection mechanism, owner, privacy boundary, validation method, delivery target, and explicit disposition.

**P27/P28 implication:** Treat Relay Metrics as a managed product/interface backlog with an agreed change-control cadence, not as a one-time feature delivery. New requests after design baseline need classification as new requirement, clarification, limitation acceptance, or future-program scope.

**Recommended title:**

> **Relay Metrics — Continuous Feature Evolution and Cross-Layer Delivery Governance**

**PPT mapping:** Key event / continuing collaboration stream; feature collaboration; good point; improvement area; lessons learned; P27/P28 governance.

**Confirmation status:** Pending user confirmation of the current/new metric examples that should be highlighted in the working material.

### E4 decision record — Most Wanted execution and PS issue-operating model

**Event family under review:** 2026 PS DRI sync-up, Most Wanted review, US-support planning, and the daily ECC/OOS/certification execution stream.

**PKB records read:** P26 PS DRI sync-up (2026/3/10), P26 Most Wanted Issue Review, dated daily-review records from 2026/6/18 and 2026/6/30, and the Call Performance DRI synthesis.

**What the records actually show:**

1. **Operating model formation:** weekly review moved to daily review from 2026/3/30; two external customer reviews per day were planned; Area TL/domain DRI mapping and TW/US time-zone relay were defined for P26 DVT/MP support.
2. **Scale and urgency:** the April snapshot recorded 218 Most Wanted issues, 111 open under debugging, and high concentration in data performance, call performance, OOS/registration, ECC, and certification.
3. **Issue classification and gates:** RC/LE0/LE1/FRC/SU0 gates defined which issues required a patch, customer waiver, QPR, or permanent deferral.
4. **ECC/OOS high-frequency stream:** daily records show repeated carrier-specific ECC/OOS decisions, AP/Modem/NW behavior clarification, temporary patches, customer retest, and SU0 lock pressure.
5. **Security substream:** security hot-fixes, such as the unsecured-redirection SBP item, occurred inside the MWI execution stream; security is not a separate post-MP discovery event.
6. **Call Performance stream:** Call Performance had substantial issue volume and ownership, but the current evidence plus user confirmation indicate that the stream had not converged to the same degree as the recurring ECC/OOS execution rhythm.
7. **Support constraint:** the original 24/7 global rotation was postponed because both sides were overloaded, DRI time was consumed by daily meetings, and premature rotation risked increasing confusion. HQ remained the primary support point, with US support case-by-case until the later support model.
8. **Customer collaboration expectations:** Zion requested frequent intermediate updates, log snippets and analysis logic, and advance warning for issue bursts.

**Consolidated interpretation:** E4 should not be called only “MWI daily review.” It is the **P26 PS issue-operating model under execution pressure**. ECC/OOS demonstrates a high-frequency, gate-driven operating rhythm; Call Performance demonstrates a less-converged stream; security hot-fix demonstrates urgent work within MWI; and the postponed global rotation shows the cost of scaling the model before roles and capacity were ready.

**Good-point candidates:**

- The model established a visible issue cadence, priority gates, named area ownership, customer review points, and release decision points.
- ECC/OOS issues could be driven through daily review, temporary patch, customer retest, SU0/FRC decision, and release gate.
- The model made issue scale and urgency visible to project leadership.

**Improvement candidates:**

- Daily cadence and area mapping do not by themselves guarantee cross-module technical convergence.
- Support rotation needs readiness criteria, capacity, role clarity, and matching technical peer coverage before launch.
- Call Performance requires a clearer convergence path than repeated status review.
- The issue lifecycle must preserve scenario, evidence, owner, technical decision, patch status, customer validation, and release disposition across time-zone handoffs.

**P27/P28 implication:** Define the support model before the high-pressure phase, including named primary/backup technical peers, cross-module convergence owner, US-daytime scope, HQ fallback, customer update rule, and release/QPR disposition. MWI should be treated as a stress test of the operating model, not as the entire PS collaboration model.

**Recommended title:**

> **P26 PS Issue Execution — Most Wanted Operating Model Under Certification and MP Pressure**

**PPT mapping:** Key event; issue collaboration; project operating model; good points; improvement areas; internal/external optimization; P27/P28 support model.

**Confirmation status:** Pending user confirmation of the proposed E4 interpretation, especially the separation of ECC/OOS high-frequency execution from Call Performance non-convergence.

### E6 decision record — eSIM-only / eSIM debugging and verification stream

**Event family under review:** P26 eSIM-only customization, SIM/eSIM feature discussions, and the 2026 eSIM IO-line extra-bytes/BWT debugging stream.

**PKB records read:** P26 eSIM extra-bytes issue, P26 SIM/eSIM feature-sync records, and the eSIM-only SKU slotmap design review.

**What the records actually show:**

1. **eSIM-only customization was a real P26 feature stream:** slot status, primary-IMEI/NV control, SIM simulator behavior, SIM protocol mapping, and related AP/Modem/SIM boundary decisions were discussed.
2. **A slotmap design review exposed implementation-boundary risk:** customer-side SIM slotmap customization was suspected to be placed in the wrong hook; the correct hook placement had to be re-confirmed with the customer.
3. **The extra-bytes issue was a P0 partner-visible issue:** unexpected bytes and BWT violation during eSIM recovery caused temporary mute and factory-retest failures.
4. **Reproduction was distributed:** Taipei, Shenzhen, and Mountain View participated; 6 of 8 monitored devices reproduced the extra-bytes behavior.
5. **Debugging crossed software and hardware boundaries:** hypotheses included IO drive/pull-up, FIFO residue, and hardware design; DOE templates combined BWT and Clock Stop Mode fixes with resistor/drive/debug variations.
6. **Verification environments differed:** Zion's driver stress environment differed from Alcedo's; missing eSIM/MVPD test coverage, circuit diagrams, and customer device access delayed early convergence.
7. **Joint follow-up was required:** customer template-image integration, weekend testing, circuit review, and possible joint software/hardware on-site escalation were defined.

**Consolidated interpretation:** E6 is not only an eSIM bug. It is a PS/SIM collaboration and verification event showing how customer-specific eSIM behavior can cross AP, Modem, SIM, software, hardware, test-environment, and factory boundaries.

**Good-point candidates:**

- Cross-site reproduction and vendor analysis were brought into a common debugging stream.
- The issue was decomposed into BWT, Clock Stop Mode, extra bytes, garbage data, IO behavior, and possible hardware causes instead of treating it as one undifferentiated failure.
- DOE templates and joint circuit review were used to make the next experiment explicit.

**Improvement candidates:**

- P26 did not have sufficiently aligned eSIM/MVPD verification coverage or equivalent test environments early enough.
- Customer device, circuit information, and simulation fidelity should be treated as prerequisites for eSIM debugging, not late escalation inputs.
- Software, SIM, AP, and hardware ownership needs a defined convergence owner for issues crossing the IO / timing / protocol boundary.
- The path from experiment result to patch selection, customer template integration, validation, and release needs explicit lifecycle tracking.

**P27/P28 implication:** Establish an eSIM/SIM joint verification readiness package before execution: representative customer device, circuit/interface data, ATR simulation fidelity, shared DOE template, log/debug ownership, software/hardware escalation path, and customer-validation criteria.

**Recommended title:**

> **P26 eSIM-only and eSIM Debugging — Cross-Environment Verification and Convergence**

**PPT mapping:** Key event; technical collaboration; issue collaboration; cross-module convergence; lessons learned; P27/P28 verification model.

**Confirmation status:** Pending user confirmation of the E6 scope and whether the slotmap review should be presented together with the extra-bytes debugging stream or retained as a separate eSIM sub-event.

### E6 decision record — scope split

**User decision:** Use option B.

- **Main E6 event:** focus on the P26 eSIM IO-line extra-bytes / BWT debugging and cross-environment verification stream.
- **Supporting sub-event:** retain the eSIM-only SKU slotmap design review as a supporting eSIM feature-design alignment case.

**Consolidated interpretation:** The two records belong to the same broader eSIM/SIM collaboration domain but represent different lifecycle moments. Extra-bytes/BWT is the main cross-environment debugging and convergence event; slotmap is supporting evidence for customer customization implementation-boundary alignment.

**PPT mapping:** E6 main event supports issue/technical collaboration, verification gaps, and P27/P28 joint-debugging readiness. The slotmap case supports feature/interface alignment and lifecycle ownership in speaker notes or appendix.

**Confirmation status:** Confirmed by user.

**Next frontier:** Proceed to E7 — SIM Lock, the first major post-MP/in-market PS/SIM issue.

### E7 decision record — SIM Lock as first major post-MP/in-market PS/SIM event

**Event family under review:** 2026/8/25 deep-dive review, 2026/8/27 urgent external discussion, and the related in-market issue records for ALPS11585308 and ALPS11585456.

**PKB records read:** dedicated deep-dive summary, urgent external issue record, P26 SIM Lock project record, and the SIM Lock GID1 `0xFF` process page.

**What the records actually show:**

1. **Customer-specific feature context:** Google SIM Lock / Carrier Restriction was a Zion-only P26 customization controlled by the SIM Lock server rather than factory programming.
2. **AP/Modem interface:** AP used `setAllowedCarriers` / `getAllowedCarriers` through MIPC/AT command paths; the AP re-verified modem read-back and rewrote data on mismatch.
3. **ALPS11585308:** a valid GID1 ending in `FF` was mistaken for an NVRAM end marker, causing read-back truncation, repeated AP writes, SIM power-cycles, and IMS-registration failures.
4. **ALPS11585456:** Verizon eSIM profiles became restricted/disabled in the field; the causal link to repeated GID1-related writes remained a hypothesis requiring time-of-occurrence NVRAM/log evidence.
5. **Customer impact:** the records describe large commercial impact, including 45 operators/MVNOs for the GID1 pattern and more than 1,300/3,000 reported eSIM cases in different status records. These counts should not be combined without reconciling the report date and source version.
6. **Short-term response:** a modem temporary patch was released and verified for ALPS11585308; Zion preferred a server-side/QPR fix as a lower-risk path, with carrier negotiation.
7. **Deeper design issues:** the review identified not only `FF` termination ambiguity but also read-buffer contamination from carrier-entry ordering, requiring sorting by GID1 length or removing GID1 for affected carriers.
8. **Long-term actions:** atomic NVRAM write, backup partitions, rollback on interrupted write, eliminating SIM silent reboot, and pending SIM reads during internal eSIM power cycles.

**Consolidated interpretation:** E7 is a genuine post-MP/in-market collaboration event because it connected a customer-specific P26 feature, AP/Modem interface behavior, NVRAM integrity, SIM/eSIM behavior, IMS impact, urgent customer response, server-side mitigation, modem patching, and P27+/QPR design carry-forward.

**Good-point candidates:**

- A dedicated deep-dive and urgent external review converted a field symptom into a detailed causal chain and separated confirmed findings from hypotheses.
- Short-term patch, server-side mitigation, and longer-term modem-design options were considered separately rather than forcing one risky fix.
- The issue was carried into P27+/QPR design actions instead of treating the temporary patch as the final solution.

**Improvement candidates:**

- Customer-specific features need end-to-end design review across AP, Modem, NVRAM, SIM/eSIM, server policy, and recovery behavior before MP.
- Read-back/self-healing mechanisms need bounded retry, atomicity, rollback, and observability requirements.
- In-market issue response needs a defined evidence package: exact symptom timeline, MD logs, NVRAM snapshot, server configuration, customer validation, and release/QPR disposition.
- Short-term mitigation and long-term ownership must be tracked as separate lifecycle items.

**P27/P28 implication:** Establish a customer-specific feature readiness and post-MP support checklist covering architecture review, failure atomicity, retry limits, observability, rollback, server/device coordination, emergency patch path, customer validation, and long-term owner.

**Recommended title:**

> **P26 SIM Lock — First Major Post-MP/In-Market Collaboration and Lifecycle Lesson**

**PPT mapping:** Key event; post-MP/QPR; issue collaboration; end-to-end lifecycle ownership; cross-module convergence; lessons learned; P27/P28 carry-forward.

**Confirmation status:** Pending user confirmation of the main emphasis: customer impact, design/lifecycle gap, or post-MP support model.

### E7 decision record — selected framing

**User decision:** Use option D: combine the customer-specific design/lifecycle gap with short-term mitigation, QPR, and long-term ownership. The main message is that customer-specific features require end-to-end lifecycle review before MP.

**Final E7 framing:**

> **P26 SIM Lock — Customer-Specific Design Requires End-to-End Lifecycle Review Before MP**

**Supporting chain:**

```text
Customer-specific requirement
→ AP/Modem interface and data schema
→ NVRAM read/write and retry behavior
→ SIM/eSIM and IMS impact
→ pre-MP validation / failure injection
→ in-market response
→ temporary mitigation / QPR
→ long-term owner and next-program design
```

**PPT mapping:** Key event; issue collaboration; end-to-end lifecycle ownership; cross-module convergence; lessons learned; P27/P28/QPR improvement.

**Confirmation status:** Confirmed by user.

**Next frontier:** Proceed to E8 — QPR / post-MP long-tail support and workaround-to-next-program handoff, while keeping security hot-fix under E4/MWI.

### E8 decision record — QPR and long-tail support

**Event family under review:** P26 QPR / post-MP support, including workaround-to-next-program handoff and continued P26 customer support.

**PKB evidence read:** P26 QPR / Most Wanted patch follow-up, P26/P27 support records, and the P26 workaround / P27 long-term-fix record for the APN backoff scenario.

**What the records actually show:**

1. MP was not the end of the lifecycle. P26 issues continued through QPR, customer validation, patch qualification, and post-MP support.
2. A P26 workaround translated ESM cause #33 to #50/#51 under SBP/MCF control, while a P27 long-term fix was planned to reset/remove the backoff when APN profile changes.
3. The P26 workaround had a known risk: the network/OTA cause and modem-visible cause could differ, creating a cross-layer interpretation problem.
4. The P26 workaround had to be retired after the P27 long-term fix landed; ownership and migration therefore span programs.
5. Release, branch, patch-back, customer validation, and QPR disposition remain part of the P26 support model after MP.

**Consolidated interpretation:** E8 is not one post-MP bug. It is the **P26 long-tail support and inter-program handoff model** required by a long-lived product. QPR is where temporary P26 workarounds, customer-facing behavior, release constraints, and P27/P28 long-term fixes must remain connected.

**Good-point candidates:**

- P26 workaround and P27 long-term fix were explicitly distinguished.
- The migration condition—retire the workaround after the next-program fix—was recognized.
- QPR and post-MP support were treated as part of the product lifecycle rather than as an unowned afterthought.

**Improvement candidates:**

- Every workaround needs an explicit expiry/retirement condition, successor fix, owner, validation plan, and customer communication path.
- P26/P27 branch and patch-back records need one lifecycle view so a temporary workaround does not become an undocumented permanent behavior.
- QPR intake and prioritization need to preserve scenario, customer impact, technical owner, release target, and validation evidence.
- The seven-year support horizon should be reflected in support R&R and knowledge-transfer planning; the exact contractual wording still requires authoritative confirmation before External presentation.

**P27/P28 implication:** Define a long-tail support model at project start: named lifecycle owner, QPR governance, workaround registry, retirement criteria, cross-program patch-back rule, customer-validation ownership, and technical knowledge transfer.

**Recommended title:**

> **P26 QPR and Long-Tail Support — Preserving Ownership from Workaround to Next-Program Fix**

**PPT mapping:** Key event; lessons learned / suggestions beyond project; internal optimization; P27/P28 support model; end-to-end lifecycle ownership.

**Confirmation status:** Pending user confirmation of the E8 framing and whether the seven-year support horizon should appear in the main External material or remain an Internal planning assumption.

### E8 decision record — audience wording for support horizon

**User decision:** Use option C.

- **External:** describe the need for a long product-support lifecycle at a macro level without stating the contractual seven-year figure.
- **Internal:** retain the seven-year support horizon as a planning input for QPR governance, ownership, knowledge transfer, and long-tail support capacity.

**Consolidated wording:**

> P26 MP is a transition point, not the end of the collaboration lifecycle. The P27/P28 model should preserve ownership and technical context across QPR, post-MP support, and future-program handoff.

**Confirmation status:** Confirmed by user.

**Next frontier:** E8 is complete. The next work is to review the consolidated E1–E8 set for duplication, missing PS event families, and consistency with the PPT requirements before moving to the next major section.

## Consolidated E1–E8 review

### Duplication check

- **E1 vs E5:** Keep separate. E1 establishes the PS customization/interface-alignment model; E5 governs FLD1/FLD2/Exception Feature scope, approval, and commitment.
- **E2 vs E1:** Keep separate. E2 is AP-IMS interface enablement/evolution; E1 is the broader PS customization collaboration model.
- **E2 vs E4:** Keep separate. E2 establishes AP/Modem interface knowledge and topic decisions; E4 tests issue execution under certification/MP pressure.
- **E3 vs E1/E5:** Keep separate. Relay Metrics is a continuously evolving cross-layer feature/backlog, not just one customization request.
- **E4 vs E8:** Keep separate. E4 is MP-window issue execution; E8 is post-MP QPR and long-tail ownership.
- **E6 vs E7:** Keep separate. E6 is eSIM verification/debugging; E7 is in-market SIM Lock lifecycle failure and post-MP response.

### Missing-event check

The PS-filtered inventory does not currently show an additional event that should be promoted to a new top-level key event. The most important items that remain as sub-events or evidence are:

- PS Deep Dive planning/rehearsal → supporting milestone under E2/technical enablement.
- 2024/11 PS Deep Dive outcome → evidence supporting E2 and Relay Metrics E3.
- 2025/7/16 F2F PS items → transition/carry-forward evidence, not a separate P26 execution event.
- eSIM slotmap review → E6 supporting sub-event.
- Security hot-fix → E4 MWI substream.
- QPR workaround-to-next-program handoff → E8 supporting lifecycle case.

### PPT requirement coverage

| Preparation requirement | E1–E8 support | Remaining work |
|---|---|---|
| Established co-working model | E1, E2, E3, E4, E5, E6 | Consolidate into one model diagram without turning it into a meeting list. |
| Good points | E1, E2, E3, E4, E5, E6, E7, E8 | Separate confirmed strengths from conditional strengths and attach case evidence. |
| Improvement areas | E1, E2, E3, E4, E5, E6, E7, E8 | Consolidate under the four approved improvement themes. |
| Key events | E1–E8 | Select main-slide versus notes/appendix level. |
| Lessons learned / beyond project | E2, E3, E4, E6, E7, E8 | Convert event findings into reusable principles. |
| Internal optimization | E4, E5, E6, E7, E8 | Detail Alcedo R&R, coverage, access, handoff, and support design. |
| External optimization | E1, E2, E3, E5, E6, E8 | Phrase as joint discussion topics and Zion feedback/commitment questions. |

### Main-message consolidation

The eight events collectively support one operating-model conclusion:

> **P26 established many effective collaboration forums and technical interfaces, but the bridge from shared discussion to distributed execution, cross-module convergence, validation, release, and long-tail ownership was not consistently explicit.**

This is a synthesis for later use, not yet the final External wording.

### Current event disposition

- **Main key-event groups:** E1, E2, E3, E4, E5, E6, E7, E8.
- **Supporting cases / sub-events:** PS Deep Dive outcome, eSIM slotmap review, security hot-fix, QPR workaround handoff, 2025 F2F PS items.
- **Excluded:** non-PS workshops and topics without explicit PS dependency.

**Review status:** E1–E8 coverage and duplication review complete; synthesis still requires user confirmation before moving to the next PPT-aligned section.

## Lessons Learned candidates — Internal / External split

The following are concrete, implementable candidates derived from E1–E8 and
cross-checked against peer post-mortem patterns in PKB. They are deliberately
written as operating changes, not generic statements such as “improve
communication.”

### Lesson 1 — Convert every customer-facing decision into an execution contract

**Evidence:**

- E1 established interface-document conventions, MAL placement, DRI mapping,
  delivery discussion, and P0 joint-development scope.
- E2 created AP/Modem interface decisions and fixed/ongoing Q&A items.
- E3 has a living metric reference with support type, delivery phase, and
  status, but continues to receive new fields and clarifications.
- E5 separates technical feasibility from management delivery commitment.
- E6 and E7 show that implementation boundary, validation evidence, and
  post-release behavior can remain open after a technical direction exists.
- Peer post-mortems use concrete common keys, early test plans, named owners,
  and explicit action/target fields rather than meeting summaries alone.

**Internal lesson / optimization:**

Before Alcedo confirms a customer-facing feature or technical direction, the
internal record must contain a minimum execution contract:

```text
Requirement / scenario
→ interface / architecture decision
→ Alcedo technical owner
→ customer technical owner
→ supporting module owners
→ required evidence / log / device
→ validation owner and method
→ target milestone / release
→ closure criteria
→ post-MP or QPR owner
```

The PS Lv1 DRI should be the owner of contract completeness, not the permanent
owner of every technical action.

**External lesson / optimization:**

For each major feature or issue, Alcedo and Zion should confirm the same
minimum fields at the collaboration boundary: scenario, interface direction,
technical owners, required inputs, validation responsibility, target phase,
and closure criteria. This is a joint alignment artifact, not a request to
expose internal design.

**Implementation:** Add a mandatory “execution contract” section to the
feature/issue tracker and workshop action-item template. An item cannot move
to committed delivery until the required fields are populated or explicitly
marked as an accepted open risk.

**PPT mapping:** Lessons learned; internal optimization; external
optimization; P27/P28 operating model.

### Lesson 2 — Design the coverage and routing matrix before the execution peak

**Evidence:**

- E4 records US/TW relay, Area TL/domain DRI mapping, postponed global
  rotation, and US-daytime technical-depth gaps.
- Partner-account control intentionally limited access, but operational work
  concentrated around the PS Lv1 DRI.
- E6 required software, SIM, AP, hardware, customer device, and circuit
  participation.
- Peer post-mortem material recommends common resource pools, onboarding
  playbooks, named 24/7 escalation owners, and early device/test-plan
  alignment.

**Internal lesson / optimization:**

Before DVT/TA/MP, build a coverage matrix for each PS scenario or hotspot:

```text
Scenario / module
→ customer counterpart
→ MUS daytime technical peer
→ HQ module owner
→ cross-module convergence owner
→ primary / backup
→ access route
→ decision authority
→ escalation trigger
```

The matrix must be reviewed at the start of each execution phase, not created
after the first urgent issue. Firewall controls remain unchanged; scoped
access and routing are designed around the roles.

**External lesson / optimization:**

Alcedo and Zion should agree on the customer-time technical counterpart and
backup for each high-risk scenario, including who can provide logs, make a
technical recommendation, approve a test direction, and confirm validation.

**Implementation:** Make “coverage ready” a gate before the first high-volume
test or certification phase. The gate requires named people, time-window
availability, access readiness, test assets, and escalation path.

**PPT mapping:** Lessons learned; internal optimization; external
optimization; technical coverage improvement.

### Lesson 3 — Treat joint verification assets as prerequisites, not escalation outputs

**Evidence:**

- E6 extra-bytes debugging was delayed by differences between Zion and Alcedo
  stress environments, missing customer device/circuit data, and insufficient
  eSIM/MVPD coverage.
- E1/E5 repeatedly distinguish customer validation, internal test, and joint
  development.
- Peer post-mortems identify shift-left, early benchmarking, common onboarding,
  and early device/test-plan alignment as actionable improvements.

**Internal lesson / optimization:**

For customer-specific PS/eSIM/SIM features, Alcedo must define a pre-execution
readiness package:

- representative customer device or agreed equivalent;
- scenario and expected behavior;
- log configuration and capture method;
- simulator/ATR/circuit assumptions;
- test template and pass/fail criteria;
- customer-side validation owner;
- known limitations and fallback evidence.

**External lesson / optimization:**

Alcedo and Zion should agree these assets and criteria before implementation
or certification testing begins. If an asset is unavailable, the limitation
and its impact on confidence must be explicitly recorded rather than discovered
after a P0 escalation.

**Implementation:** Add a “joint verification readiness” checklist to the
feature onboarding process; block formal delivery commitment for high-risk
customer-specific features until the checklist is accepted or an explicit
management risk decision is recorded.

**PPT mapping:** Lessons learned; internal/external optimization; eSIM and
cross-module improvement.

### Lesson 4 — Manage living features and long-tail support as products, not tickets

**Evidence:**

- E3 Relay Metrics continues to receive new metrics and clarifications after
  its core design direction.
- E5 Exception Features require late-request governance, tiered approval,
  technical/commercial separation, and P26/P27 deferral.
- E7 SIM Lock required temporary mitigation, server-side/QPR handling, and
  long-term modem redesign.
- E8 P26 workaround must be retired after the P27 long-term fix; QPR and
  patch-back continue after MP.
- Peer post-mortems use explicit next-program actions, common traceability
  keys, and named follow-up ownership.

**Internal lesson / optimization:**

Maintain two linked records for every living feature or workaround:

1. Current release behavior / workaround / patch status.
2. Successor design / retirement condition / next-program owner.

The PS Lv1 DRI reviews the transition list at every P26/P27/P28 milestone,
but individual technical owners remain accountable for their items.

**External lesson / optimization:**

Alcedo and Zion should classify new requests as one of:

- clarification;
- baseline correction;
- new requirement;
- limitation acceptance;
- QPR fix;
- next-program feature.

Each classification must have an owner, target phase, validation plan, and
explicit disposition of the old behavior or workaround.

**Implementation:** Create a P26/P27/P28 carry-forward register covering
Relay Metrics additions, Exception Features, SIM Lock/QPR, and other active
workarounds. Review it in the recurring PS sync and at MP/QPR gates.

**PPT mapping:** Lessons learned / suggestions beyond project; internal and
external optimization; long-tail P27/P28 model.

### Candidate lesson prioritization

For the main material, prioritize:

1. **Execution contract for every major decision** — broadest and directly
   links E1–E8.
2. **Coverage/routing matrix before execution peak** — directly addresses
   the US-daytime and partner-account side effects.
3. **Joint verification readiness gate** — directly grounded in E6 and useful
   for customer collaboration.
4. **Living-feature / long-tail register** — directly grounded in E3, E5, E7,
   and E8.

These candidates are intentionally concrete: each has a record/template,
required fields, a gate or cadence, and a proposed owner boundary.

## Additional lesson candidate — feature verification and enable-state contract

**User correction:** The previous four lessons did not make a critical P26
customization collaboration issue explicit enough: for each feature, the
parties need to know the default enable state, carrier-specific enable/disable
configuration, ownership model, and verification boundary.

**PKB evidence:** The TC50 Customized Feature Validation Process defines:

- System Test/SV support is **not needed by default**;
- the DRI decides whether SV support is required and completes a questionnaire
  when it is;
- public/common features generally require SV/full-system regression;
- customer-specific AP/IMS/interface-shell features generally receive MTK
  UT/RDIT while Zion owns customer-device/system integration validation;
- the customer validates behavior in its specific AP/hardware environment.

The FLD1/FLD2 and feature-status records additionally show:

- feature-off behavior may fall back to MTK public parameters when customer
  requirements are not explicit;
- features may be carrier-specific or controlled by configuration/NV/SBP/MAL;
- joint-development, customer-driven test, Alcedo self-contained validation,
  and full SV-supported validation are different categories;
- the P26/P27 customization status survey tracks DRI, enable/compatibility
  status, and forward/backward compatibility.

**Concrete P26 lesson:** A customization feature is not fully defined when
only its implementation scope and DRI are known. The feature contract must
also state:

```text
Default state: ON / OFF / conditional
→ carrier / scenario enablement
→ Alcedo self-contained or joint-development
→ Alcedo UT/RDIT scope
→ SV scope, if any
→ Zion device/system IT scope
→ required customer device / AP / network / SIM environment
→ acceptance criteria
→ P26/P27 compatibility and release disposition
```

### Internal lesson / optimization

The Alcedo DRI must complete a **Feature Verification & Enablement Matrix**
before committing delivery. It should be reviewed by the appropriate SV/FO
owner and linked to the feature tracker. “SV not needed” must be a deliberate
classification with a reason, not an empty field.

### External lesson / optimization

Alcedo and Zion should jointly confirm, for every customer customization:

- default ON/OFF behavior;
- carrier/scenario-specific enablement;
- whether it is joint-development or Alcedo self-contained;
- what Alcedo can validate without Zion hardware/AP;
- what requires Zion device/system IT;
- who supplies test assets and who accepts the result.

This directly avoids later disputes where both sides believe a feature is
“done” because one side validated an interface while the other expected full
system behavior.

### P27/P28 implementation

Add the matrix as a mandatory feature-onboarding and milestone-gate artifact:

| Field | Required decision |
|---|---|
| Enable state | Default ON/OFF/conditional |
| Carrier scope | Carriers/scenarios where enabled or disabled |
| Ownership | Alcedo / Zion / joint development |
| Alcedo verification | UT/RDIT scope and result |
| SV/FO | Required / not required, with rationale |
| Zion IT | Device/AP/network/SIM test required? |
| Acceptance | Pass criteria and accepting party |
| Release | P26/P27/QPR/check-in disposition |
| Closure | Evidence link and final owner |

**PPT mapping:** This is a major Internal/External lesson learned,
customization-feature improvement, and P27/P28 operating-model action. It is
more specific than the generic execution-contract lesson and should likely be
promoted into the top three.

### Lesson decision record — Feature Verification & Enablement Matrix

**User decision:** Confirmed as a **Priority 1 lesson**, to be included in both
Internal and External lessons learned / optimization.

**Accepted implementation direction:** Make the matrix a mandatory feature-
onboarding and milestone-gate artifact covering enable state, carrier/scenario
scope, ownership, Alcedo verification, SV/FO decision, Zion device/system IT,
acceptance, release disposition, and closure.

**Accepted wording boundary:** Internal material may show Alcedo's detailed
R&R and SV/FO decision logic. External material should present the joint
feature enablement and verification contract without exposing internal design
or private process details.

**Confirmation status:** Confirmed by user.

**Next frontier:** Validate Priority 2 — Coverage & Routing Matrix before the
execution peak, including the US-daytime technical-peer gap and the intentional
partner-account firewall side effect.

### Lesson decision record — Coverage & Routing Matrix

**PKB evidence reviewed:**

- 2026/3/10 PS DRI sync-up: TW/US relay, Area TL/domain DRI model, US support
  timeline, and customer request for frequent updates and transparent analysis.
- Partner-account approval record: a US PS DRI peer account was requested to
  enable real-time discussion with Zion's US TL during US business hours.
- MUS role record: MUS provides US-time-zone triage, customer communication,
  urgent issue handling, and coordination; formal code fixes and deep module
  ownership remain with RD/HQ.
- MWI records: the initial 24/7 rotation was postponed because capacity and
  meeting load made the early model likely to increase confusion.

**Concrete lesson:** A named DRI list or time-zone relay does not by itself
constitute technical coverage. Coverage must specify who can perform triage,
who can perform technical analysis, who can decide, who owns the fix, and who
can communicate with the customer during each support window.

**Internal lesson / optimization:** Establish a phase-gated Coverage & Routing
Matrix before DVT/TA/MP. Required fields:

```text
Area / customer scenario
→ Zion counterpart
→ Alcedo coordinator
→ MUS daytime technical peer
→ HQ/domain owner
→ cross-module convergence owner
→ primary / backup
→ access route
→ analysis boundary
→ decision authority
→ escalation trigger
→ expected response / handoff rule
```

The matrix must distinguish:

- coordination/triage;
- technical analysis;
- code-fix ownership;
- final technical approval;
- customer update and validation.

The partner-account firewall remains intact. Scoped access, primary/backup
routing, and coordinator delegation are used to avoid making the PS Lv1 DRI
the default access and scheduling gateway for every request.

**External lesson / optimization:** Alcedo and Zion should jointly identify,
for each high-risk PS scenario, the customer-time technical counterpart,
backup, communication path, expected first response, escalation trigger, and
validation owner. This is a working interface agreement, not a request to
expose internal staffing or private access policy.

**Implementation gate:** “Coverage ready” must be reviewed before the first
high-volume test/certification phase and again when the issue mix or release
phase changes. A support window is not ready if it has a contact but no
technical decision path or HQ fallback.

**Success measures:**

- Every PS hotspot has a named primary, backup, technical owner, and decision
  owner before the execution peak.
- US-daytime issues can be classified as triage-only, technically actionable,
  or HQ-dependent at intake.
- Handoff records retain scenario, evidence, current analysis, next action,
  and release/QPR disposition.
- Partner-account requests do not all route through the PS Lv1 DRI.

**PPT mapping:** Improvement areas; internal optimization; external
optimization; lessons learned; P27/P28 collaboration model.

**Confirmation status:** Pending user confirmation.

### Priority 2 confirmation record

**User decision:** Confirmed.

**Accepted lesson:** P27/P28 must establish a Coverage & Routing Matrix before
the execution peak. A time-zone relay or DRI list is not sufficient unless it
also defines technical analysis, decision authority, fix ownership, customer
validation, primary/backup, and HQ fallback.

**Accepted boundary:** Keep the partner-account firewall. Improve the operating
model through scoped access, coordinator delegation, primary/backup routing,
and appropriate technical-peer participation.

**Confirmation status:** Confirmed by user.

**Next frontier:** Priority 3 — Joint Verification Readiness Gate.

### Priority 3 confirmation record

**User decision:** Confirmed.

**Accepted lesson:** Joint verification assets and acceptance criteria must be
ready before high-risk customer-specific feature implementation/certification
or an explicit management risk decision must be recorded.

**Accepted boundary:** Internal material defines Alcedo/SV/FO readiness and
risk ownership; External material jointly defines Zion device/system IT,
assets, acceptance, and limitations without exposing private internal details.

**Confirmation status:** Confirmed by user.

**Next frontier:** Priority 4 — Living Feature / QPR / Long-tail Register.

## Quantified-evidence requirement for the future presentation

**User direction:** When the working evidence supports a number, the final
material should include the number as corroboration rather than relying only
on qualitative wording. Numbers must retain their date, scope, and source
context; conflicting snapshots must not be combined as if they were one value.

### Current quantified evidence candidates

| Area | Candidate figure | Scope / date qualification |
|---|---:|---|
| P26 customization | 271 total customization features | P26 project summary; confirm whether this is total project customization or only the cited project feature inventory before final slide use. |
| P26 Most Wanted | 218 total; 111 open under debugging | 2026/4/21 snapshot; do not represent as the full four-year issue count. |
| P26 MWI area concentration | Call Performance 20, OOS/Registration 15, ECC 15 | Same 2026/4/21 snapshot; use only with its snapshot context. |
| Relay Metrics | More than 1,200 metric definitions | Living reference; number reflects the reference catalogue and continues to evolve. |
| Relay Metrics deep dive | Approximately 450 metric items requiring item-by-item review | 2024/11 PS Deep Dive outcome; this is a working review subset/scale and must not be added to the 1,200 catalogue total. |
| SIM Lock impact | 45 major operators/MVNOs cited for GID1-FF pattern | 2026/8 issue review; source/date must be shown in internal evidence, and not conflated with eSIM user-report counts. |
| SIM Lock eSIM impact | 1,300+ or 3,000+ reports in different records | Conflicting snapshots; reconcile before presentation, or state only “large in-market impact” externally. |
| eSIM extra-bytes reproduction | 6 of 8 monitored devices reproduced | P26 extra-bytes debugging record; use with test-site and test-cycle context. |
| PS Deep Dive | 4 days; NAS/RRC/L2/Misc | 2024/11/11–11/14 execution; useful as collaboration-scale evidence. |

### Quantification rules

- Every number in the final deck gets an “as of” date or phase label.
- Counts from different snapshots are not summed without a defined common
  denominator.
- A catalogue count (e.g. Relay Metrics) is not the same as a review subset
  (e.g. items discussed in one workshop).
- If evidence conflicts, either reconcile it through PKB/source review or
  present the conflict explicitly; never select the larger or more convenient
  number silently.
- External slides use only numbers that are useful for shared understanding;
  Internal material may retain more detailed counts and snapshot context.

### PPT mapping

Quantified evidence can support the preparation requirements for good points,
improvement areas, key events, lessons learned, and the P27/P28 justification.
This is supporting evidence, not a substitute for the collaboration analysis.

### Priority 4 confirmation record

**User decision:** Confirmed.

**Accepted lesson:** P26/P27/P28 living features, workarounds, QPR items, and
post-MP issues require a carry-forward register with current state,
successor/retirement state, owner, validation, release target, and migration
condition.

**Accepted wording boundary:** External material describes long-term support and
context continuity at a macro level; Internal material retains the detailed
long-tail planning input, including the seven-year support horizon.

**Confirmation status:** Confirmed by user.

**Next frontier:** Review the completed lessons against the preparation deck
and propose the PPT agenda strictly mapped to the deck's required sections.

## PPT agenda proposal — strictly mapped to preparation-deck requirements

This is an agenda proposal only, not slide production. The preparation deck
requires the topic owner to cover: established co-working model, good points,
areas for improvement, key P26 events, lessons learned/suggestions beyond the
project, internal optimization, and external optimization. The agenda below
preserves those required sections and does not replace them with the five
implementation artifacts.

### Part 0 — Scope and review framing

1. **PS Post-Mortem scope, owner, audience, and review objective**
   - P26 PS-involved activities, not MWI-only.
   - Hsuanchang as 2025+ effective PS Lv1 DRI; Aoss historical context.
   - Review B → P27/P28 Alcedo–Zion collaboration improvement.
   - Material for Clare/Justin and the 10/E Zion workshop.
   - External/Internal split.

### Part 1 — Required item: Established co-working model recap

2. **P26 established co-working model**
   - Feature collaboration.
   - Issue collaboration.
   - Structured technical workshops/deep dives and recurring/ad-hoc discussions.
   - Project operating model: DRI, handoff, time-zone support, escalation,
     release/check-in, and validation.
   - One lifecycle diagram from intake to closure.

### Part 2 — Required item: Good points

3. **What worked well in P26**
   - Structured PS customization/interface alignment.
   - Feature scope/ownership/validation classification.
   - AP-IMS enablement and persistent clarification mechanism.
   - Relay Metrics shared evolving reference.
   - MWI cadence, priority gates, and release decision points.
   - Good points must distinguish confirmed strengths from conditional strengths.

### Part 3 — Required item: Areas for improvement

4. **P26 improvement areas**
   - R&R and routing clarity.
   - Technical coverage and time-zone continuity.
   - End-to-end lifecycle ownership.
   - Cross-module convergence.
   - Partner-account concentration appears here only as an Internal supporting
     example; it is not an External criticism.

### Part 4 — Required item: Key events in P26

5. **P26 PS key events and what each changed**
   - PS customization/interface-alignment model.
   - AP-IMS collaboration evolution.
   - Relay Metrics continuous feature evolution.
   - MWI issue-operating model under certification/MP pressure.
   - FLD1/FLD2/Exception Feature governance.
   - eSIM extra-bytes/BWT verification stream.
   - SIM Lock post-MP/in-market lifecycle event.
   - QPR/long-tail and next-program handoff.
   - Use quantified evidence only with scope/date labels.

### Part 5 — Required item: Lessons learned and suggestions beyond project

6. **Lessons learned — common evidence and principle**
   - Transition from shared discussion to explicit execution/verification/
     closure must be designed, not assumed.
   - Introduce the four approved P27/P28 artifacts as implementation proposals:
     Feature Verification & Enablement Matrix; Coverage & Routing Matrix;
     Joint Verification Readiness Gate; Carry-forward/Long-tail Register.

7. **Lessons learned — Internal (Alcedo-only)**
   - Alcedo R&R, SV/FO decision, technical coverage, routing, handoff,
     escalation, release/QPR ownership, and seven-year support planning.
   - Preserve firewall; separate access, coordinator, technical ownership, and
     decision authority.

8. **Lessons learned — External (jointly discussable with Zion)**
   - Joint feature enablement/verification contract.
   - Customer-time technical counterpart and backup.
   - Joint verification assets and acceptance criteria.
   - Shared classification of new requirement/QPR/next-program items.
   - External sequence: shared evidence → joint improvement → Zion feedback and
     commitment → action items.

### Part 6 — Required item: Internal optimization

9. **P27/P28 Internal optimization proposal**
   - Internal operating artifacts, gates, owners, and review cadence.
   - Detailed Coverage & Routing Matrix and Feature Verification Matrix.
   - MUS/HQ/RD boundary and cross-module convergence owner.
   - QPR/long-tail register and knowledge transfer.

### Part 7 — Required item: External optimization

10. **P27/P28 External joint optimization proposal**
    - What Alcedo and Zion jointly align before feature/issue execution.
    - What must be ready before workshop, implementation, certification, and
      release.
    - Discussion questions for Zion and proposed commitment/action-item table.

### Part 8 — Required item: Other items / close

11. **Workshop discussion and requested decisions**
    - Confirm shared current-state observations.
    - Select P27/P28 joint improvements.
    - Capture Zion feedback, commitment, owner, and target timing.
    - Separate unresolved questions from agreed actions.

### Agenda compliance check

| Preparation-deck requirement | Agenda section |
|---|---|
| Established co-working model recap | Part 1 / item 2 |
| Good points | Part 2 / item 3 |
| Areas for improvement | Part 3 / item 4 |
| Key events in P26 | Part 4 / item 5 |
| Lessons learned / beyond-project suggestions | Part 5 / items 6–8 |
| Internal optimization | Part 6 / item 9 |
| External optimization | Part 7 / item 10 |
| Other items / workshop actions | Part 8 / item 11 |

**Status:** Agenda proposal drafted for user review. No PPTX created.

## Stage 3 — Central idea / narrative proposal

**Stage status:** Agenda approved by the user. No PPTX or slide manuscript has
been created. The current narrative is based on the confirmed evidence ledger;
some broad PKB searches still return unread/list candidates, so any later
PS-core source that changes a claim must reopen the affected narrative.

### Candidate A — Recommended: From collaboration forums to execution ownership

**Thesis:**

> P26 built effective Alcedo–Zion forums and technical interfaces; the P27/P28
> improvement is to make every feature/issue decision executable by defining
> enablement, verification, coverage, ownership, and long-tail closure.

**Audience value:** Explains why P27/P28 needs operating-model changes without
implying that P26 collaboration was unsuccessful.

**Emphasizes:** established mechanisms, concrete gaps exposed by execution,
and four implementable artifacts.

**De-emphasizes:** a chronological issue dump and private access-policy detail
in External material.

**Likely objection:** “We already had meetings, DRI lists, and trackers.”

**Response:** The evidence distinguishes the existence of coordination from
technical decision, verification, release, and long-tail ownership. The
proposal adds gates and fields rather than simply adding meetings.

### Candidate B — Feature-to-lifecycle control

**Thesis:**

> P26 demonstrated that a customer customization is not complete at feature
> implementation; default enablement, carrier scope, validation boundary,
> release, and post-MP ownership must be defined as one lifecycle.

**Audience value:** Concrete and immediately actionable for feature and
requirement governance.

**Emphasizes:** Feature Verification & Enablement Matrix, Relay Metrics,
Exception Features, SIM Lock, and QPR.

**De-emphasizes:** broader US-daytime coverage and issue-operating-model
problems unless restored as supporting material.

**Likely objection:** It may sound like a feature-process review rather than a
full PS collaboration post-mortem.

### Candidate C — Coverage and convergence under execution pressure

**Thesis:**

> P26's main collaboration challenge was not the absence of contacts or
> meetings, but the lack of consistently matched technical coverage and
> cross-module convergence from customer scenario to fix and release.

**Audience value:** Makes the US-daytime/HQ/MUS issue and MWI evidence central.

**Emphasizes:** MWI, ECC/OOS, Call Performance, US-daytime peer gap, and
Coverage & Routing Matrix.

**De-emphasizes:** positive feature-governance and AP-IMS/Relay Metrics
evolution unless deliberately restored.

**Likely objection:** It could be heard as an internal support complaint rather
than a balanced joint post-mortem.

### Narrative recommendation

Recommend **Candidate A**, with B and C as two proof threads:

```text
P26 established collaboration mechanisms
→ E1–E8 show where mechanisms worked and where execution exposed gaps
→ two proof threads: feature/verification lifecycle + coverage/convergence
→ Internal and External lessons learned
→ four P27/P28 operating artifacts
→ Zion workshop decisions and commitments
```

This keeps the deck aligned to the preparation requirements while preserving
the collaboration-operating-model axis.

### Narrative decision requested

Choose one narrative direction:

- **A (recommended):** From collaboration forums to execution ownership.
- **B:** Feature-to-lifecycle control.
- **C:** Coverage and convergence under execution pressure.
- **A with a different emphasis:** retain A's structure and specify which proof
  thread should lead.

### Narrative decision record

**User decision:** Select **Candidate B — Feature-to-lifecycle control**.

**Approved thesis:**

> P26 demonstrated that a customer customization is not complete at feature
> implementation; default enablement, carrier scope, validation boundary,
> release, and post-MP ownership must be defined as one lifecycle.

**Approved emphasis:** Feature Verification & Enablement Matrix leads the
narrative. Relay Metrics, Exception Features, SIM Lock, QPR, and selected
coverage/convergence cases serve as evidence and supporting threads.

**Narrative constraint:** Candidate B must still cover the full PS
Post-Mortem requirements. It is not a feature-process-only report; the
established co-working model, good points, improvement areas, key events,
Internal lessons/optimization, External lessons/optimization, and workshop
actions remain mandatory agenda sections.

**Confirmation status:** Confirmed by user.

**Next frontier:** Stage 4 — create the complete slide outline and narrative
chain, with each slide mapped to the preparation-deck requirement and the
approved B thesis. No slide manuscript or PPTX yet.

## Stage 4 — Slide outline proposal under approved B narrative

**Outline status:** Proposal only. No slide manuscript, PPTX, rendering, or
layout work has been authorized or created.

### Approved thesis

> **P26 demonstrated that a customer customization is not complete at feature
> implementation; default enablement, carrier scope, validation boundary,
> release, and post-MP ownership must be defined as one lifecycle.**

### Narrative chain

```text
P26 had multiple collaboration mechanisms
→ customization requirements became increasingly complex and living
→ implementation alone did not define enablement/verification/closure
→ execution exposed coverage, convergence, and long-tail ownership gaps
→ P27/P28 need explicit feature-to-lifecycle control artifacts
→ External joint decisions and Internal Alcedo actions
```

### Proposed slide outline

#### S01 — Title / review objective

- **Audience question:** Why are we reviewing P26 PS collaboration now?
- **Takeaway:** Use P26 Review B to improve P27/P28 Alcedo–Zion collaboration.
- **Evidence:** Scope decision Q1; preparation-deck purpose.
- **PPT mapping:** Scope / framing.
- **Next:** Establish what PS collaboration actually covered.

#### S02 — Scope, owner, and External/Internal boundary

- **Audience question:** What is included in this PS review?
- **Takeaway:** This is a P26 PS-involved collaboration review, not an MWI-only
  report; customization is the lead lens, while the evidence spans PS feature,
  issue, AP-IMS, metrics, eSIM/SIM, MWI, release, and long-tail activities.
- **Boundary visual:** External = jointly discussable Alcedo/Zion interface and
  commitments; Internal = Alcedo-only R&R, coverage, access side effects,
  handoff, escalation, and decision details.
- **Evidence:** PS filter; owner transition; MWI boundary; PS/SIM stream split.
- **PPT mapping:** Scope / preparation context.
- **Next:** Show the operating model being reviewed.

#### S03 — Established co-working model recap

- **Audience question:** How did Alcedo and Zion work together in P26?
- **Takeaway:** Four connected mechanisms existed: feature collaboration,
  issue collaboration, technical workshops/deep dives, and project operating
  model.
- **Visual purpose:** One lifecycle diagram from intake to closure, with the
  four mechanisms placed on the lifecycle.
- **Evidence:** Q8; E1/E2/E3/E4/E5; feature validation process.
- **PPT mapping:** Required item — established co-working model.
- **Next:** Identify what should be retained.

#### S04 — Good points: what should be retained

- **Audience question:** What worked and should continue?
- **Takeaway:** P26 established useful scope/ownership/validation alignment,
  recurring forums, technical enablement, living metric reference, and issue
  priority/release gates.
- **Quantified support:** 1,200+ Relay Metrics definitions; 218 MWI items / 111
  open as of 2026/4/21, only if their snapshot qualifiers are visible.
- **PPT mapping:** Required item — good points.
- **Next:** Show where the same mechanisms were insufficient.

#### S05 — P26 collaboration gaps identified

- **Audience question:** What did P26 expose?
- **Takeaway:** The four improvement themes are R&R/routing, technical
  coverage/time-zone continuity, end-to-end lifecycle ownership, and
  cross-module convergence.
- **Visual purpose:** A lifecycle with breakpoints, not a list of complaints.
- **Evidence:** E4 US support/MWI; E6 eSIM; E7 SIM Lock; E8 QPR; Q11.
- **PPT mapping:** Required item — areas for improvement.
- **Next:** Ground the themes in actual events.

#### S06 — Key events: feature-to-lifecycle control formation

- **Audience question:** Which P26 events changed the collaboration model?
- **Takeaway:** Actual workshops and reviews progressively defined feature
  scope/interface, AP-IMS responsibilities, living metrics governance, and
  FLD1/FLD2/Exception Feature control.
- **Event anchors:** 2024/9/24 PS customization workshop; 2023/12–2024/11
  AP-IMS enablement/evolution; continuing Relay Metrics reviews; FLD1/FLD2 and
  Exception Feature reviews.
- **Evidence:** E1, E2, E3, E5.
- **Quantified support:** four-day PS Deep Dive; approximately 450 metric items
  in its item-level follow-up; 1,200+ living catalogue, not additive.
- **PPT mapping:** Required item — key events in P26.
- **Next:** Show execution pressure and post-MP consequences.

#### S07 — Key events: execution, verification, and post-MP long-tail

- **Audience question:** What happened when features entered execution and
  post-MP support?
- **Definition:** Long-tail means post-MP QPR support, workaround retirement,
  next-program handoff, and continuing product support.
- **Takeaway:** MWI/ECC-OOS, eSIM extra-bytes, SIM Lock, and QPR exposed the
  need to connect implementation to verification, release, and successor
  ownership.
- **Evidence:** E4, E6, E7, E8.
- **Quantified support:** MWI snapshot; eSIM 6/8 reproduction; SIM Lock impact
  numbers only after snapshot reconciliation.
- **PPT mapping:** Required item — key events in P26.
- **Next:** Convert events into lessons learned.

#### S08 — Lesson learned: Feature Verification & Enablement Matrix

- **Audience question:** What must be defined before a feature is committed?
- **Takeaway:** Implementation scope and DRI are insufficient; define default
  ON/OFF, carrier/scenario, ownership, Alcedo/SV/Zion verification, acceptance,
  release, and closure.
- **Visual purpose:** Editable matrix mockup with columns: feature /
  carrier-scenario, default ON/OFF, ownership, Alcedo UT/RDIT, SV/FO, Zion IT,
  acceptance, release, closure.
- **PPT mapping:** Required item — lessons learned / beyond project.
- **Next:** Address execution coverage.

#### S09 — Lessons learned: two readiness gates

- **Audience question:** What must be ready before execution pressure starts?
- **Takeaway:** Two independent readiness gates are needed before DVT/TA/MP or
  high-risk feature execution: (1) people/decision coverage ready; (2)
  test/evidence readiness. Both gate feature commitment.
- **Visual purpose:** Two linked gates: Coverage & Routing Matrix → Joint
  Verification Readiness Gate → feature commitment.
- **Evidence:** E4 coverage gap; E6 environment/device/circuit gap.
- **PPT mapping:** Required item — lessons learned / beyond project.
- **Next:** Separate Internal from External actions.

#### S10 — Internal lessons learned / Alcedo optimization

- **Audience question:** What must Alcedo change internally?
- **Takeaway:** Keep the firewall, but separate access coordination, primary/
  backup routing, technical ownership, decision authority, MUS/HQ/RD boundary,
  SV/FO classification, and long-tail ownership.
- **Evidence:** partner-account, MUS, E4, E5, E8.
- **PPT mapping:** Required item — Internal optimization and Internal lessons.
- **Next:** State what must be jointly aligned with Zion.

#### S11 — External lessons learned / joint optimization

- **Audience question:** What should Alcedo and Zion jointly change?
- **Takeaway:** Before feature/issue execution, jointly confirm enablement,
  counterpart/backup, test assets, validation, acceptance, target phase, and
  QPR/next-program disposition.
- **External sequence:** shared evidence → joint improvement → Zion feedback /
  commitment → action items.
- **PPT mapping:** Required item — External optimization and External lessons.
- **Next:** Make the P27/P28 artifacts concrete.

#### S12 — P27/P28 proposed operating artifacts and measurable adoption

- **Audience question:** What will change operationally?
- **Takeaway:** Four prioritized artifacts turn the lessons into an executable
  model and measurable adoption proposal.
- **Priority 1:** Feature Verification & Enablement Matrix — closes feature
  enablement/verification ambiguity.
- **Priority 2:** Coverage & Routing Matrix — closes technical-peer/decision
  coverage gap.
- **Priority 3:** Joint Verification Readiness Gate — closes late test-asset
  discovery.
- **Priority 4:** Carry-forward / Long-tail Register — closes QPR/handoff loss.
- **Proposed measures:** matrix complete before commitment; named primary/
  backup before execution peak; readiness gate completed or risk accepted;
  carry-forward items with owner and retirement status.
- **PPT mapping:** Internal/external optimization; beyond-project suggestions.
- **Next:** Ask for workshop decisions.

#### S13 — Zion workshop decisions and action register

- **Audience question:** What must be agreed in the workshop?
- **Takeaway:** Ask for explicit choices and capture Zion feedback, joint
  commitments, owner, target timing, capacity/dependency, and unresolved
  questions.
- **Decision table:** Recommendation | Zion input/choice | Alcedo owner |
  Zion owner | target phase | capacity/dependency | open question.
- **Decision choices:** adopt the four-artifact model as the P27/P28 working
  approach; accept/modify the feature verification boundary; nominate
  customer-time counterpart/backup; agree readiness-gate participation.
- **Visual purpose:** Action table with `Topic | Evidence/issue | Joint
  decision | Alcedo owner | Zion owner | Target | Open dependency`.
- **PPT mapping:** Other items / workshop actions.

#### S14 — Closing: P26 to P27/P28

- **Audience question:** What should the audience remember?
- **Takeaway:** P26's collaboration mechanisms are worth retaining; P27/P28
  should add explicit feature-to-lifecycle control.
- **Visual purpose:** One before/after operating-model summary. Retain this
  slide only if it adds the measurable P26→P27/P28 transition; otherwise merge
  its takeaway into S13.
- **PPT mapping:** Lessons learned / beyond-project conclusion.

### Narrative transitions

```text
S01–S02: define the review
S03: show the established model
S04: preserve what worked
S05: identify the operating gaps
S06–S07: prove the gaps through key events
S08–S09: derive the lessons
S10–S11: split Internal and External actions
S12: convert lessons to P27/P28 artifacts
S13–S14: obtain workshop decisions and close
```

### Outline compliance check

| Deck requirement | Slides |
|---|---|
| Established co-working model | S03 |
| Good points | S04 |
| Areas for improvement | S05 |
| Key events in P26 | S06–S07 |
| Lessons learned / beyond project | S08–S09, S14 |
| Internal optimization | S10 |
| External optimization | S11 |
| Other items / actions | S13 |

**Outline status:** Proposed for user review. Before manuscript writing, run
outline audience rehearsal and resolve evidence/coverage issues. No PPTX has
been created.

## Stage 4 outline audience rehearsal — Round 1

**round_id:** R1-outline-20261005
**audience profile:** Clare/Justin supervisor-manager preparation audience
**review mode:** independent fresh subagent; result pending at time of this
record; no prior defect list supplied.
**candidate:** current S01–S14 outline under approved Candidate B thesis.

The rehearsal packet asks the reviewer to cold-read the outline as the intended
audience and report the understood central message, requested action, breaks in
understanding, doubtful claims/numbers, removable content, and tone concerns.
The final result must be read and adjudicated before this stage can be called
complete. Until then, manuscript writing remains paused.

## Stage 4 audit / receipt

**Stage:** Slide outline under approved Candidate B narrative.

**Approved inputs:**

- TC50 P26 Post-Mortem preparation requirements;
- approved PS scope, audience, External/Internal boundary, and Review B purpose;
- PS-filtered E1–E8 event set;
- confirmed lessons and four P27/P28 artifacts;
- quantified-evidence rules and known number conflicts.

**Deliverable produced:** S01–S14 outline with audience question, takeaway,
evidence, visual purpose, PPT mapping, and narrative transitions.

**Not produced:** slide manuscript, PPTX, rendering, layout, speaker notes, or
visual assets.

**Self-audit mode:** `self-review; downgraded` — no independent audience
reviewer was used in this pass.

### Findings

| finding_id | severity | exact finding | earliest affected artifact | status |
|---|---|---|---|---|
| OUTLINE-001 | advisory | Meeting duration and page-count mode were not explicitly approved. | Stage 1 meeting brief / outline metadata | Open — ask user before manuscript. |
| OUTLINE-002 | advisory | S01–S14 contain the required content mapping, but density and speaking-time estimates are not yet assigned per slide. | Stage 4 outline | Open — add before manuscript approval. |
| OUTLINE-003 | clean | Required deck sections are all mapped; Internal/External lessons remain separate. | Stage 4 outline | Verified. |
| OUTLINE-004 | clean | The four artifacts are presented as proposals, not as already implemented P27/P28 capabilities. | Stage 3/4 wording | Verified. |
| OUTLINE-005 | clean | Private source mechanics and partner-account policy are kept out of External main content. | Q5/Q10 and S10/S11 | Verified. |
| OUTLINE-006 | clean | Quantified claims carry snapshot caveats or are marked for reconciliation. | S04/S06/S07 | Verified. |

**Audit result:** No workflow or evidence blocker found. OUTLINE-001 and
OUTLINE-002 must be resolved before writing the manuscript; they do not require
changing the approved thesis or slide sequence.

**Next decision required:** confirm presentation duration / page-count mode and
whether S01–S14 should be prepared for a specific workshop time budget. Until
that is known, manuscript writing remains paused.

## Stage 4 audience rehearsal adjudication — Round 1

**Reviewer result:** Read from the completed independent cold-read report at
`C:\Users\mtk12265\.hermes\cache\delegation\subagent-summary-0-20261005_091342_437352.txt`.

**Result:** The central thesis was understood clearly. The outline is not yet
ready for manuscript writing because the requested workshop decisions,
External/Internal boundary, artifact definitions, and measurable P27 impact
are not explicit enough for a manager audience.

### Findings and dispositions

| finding_id | severity | finding | disposition |
|---|---|---|---|
| REH-001 | blocker | External/Internal boundary may be read as an ambiguous team split. | Fix S02 main story with a two-column boundary: External = joint Alcedo/Zion interface; Internal = Alcedo-only execution/R&R. Keep examples concrete. |
| REH-002 | blocker | S06 “feature/interface formation” is too abstract. | Rename and anchor it to actual event groups: PS customization workshop, AP-IMS evolution, Relay Metrics, FLD1/FLD2 governance; state what each changed. |
| REH-003 | advisory | “Long tail” is ambiguous. | Define it at first use as post-MP QPR, workaround retirement, next-program handoff, and continuing support. |
| REH-004 | advisory | S08 matrix axes are not visible in the outline. | Show a compact editable matrix mockup with feature/carrier/scenario, ownership, enablement, and verification columns. |
| REH-005 | blocker | S09 combines Coverage & Routing Matrix with Joint Verification Readiness Gate without showing their relationship. | Split the visual into two gates: “people/decision coverage ready” and “test/evidence readiness”; explain both feed feature commitment. |
| REH-006 | blocker | S12 says four artifacts but does not enumerate or prioritize them clearly. | Name all four, mark Priority 1–4, and show which problem each closes. |
| REH-007 | blocker | S13 asks for workshop decisions but lacks explicit decision choices, owner, timing, and resource/capacity implication. | Convert S13 into a decision table with recommendation, Zion input, owner, target timing, dependency, and capacity question. |
| REH-008 | advisory | Thesis may sound narrower than the full PS review. | S01/S02 clarify that customization is the lead lens, while the evidence spans PS feature, issue, AP-IMS, metrics, eSIM/SIM, MWI, release, and long-tail collaboration. |
| REH-009 | advisory | “Improvement areas” may sound accusatory. | Use neutral wording such as “P26 collaboration gaps identified” or “Operating-model improvement opportunities” in the slide title; retain the deck's required concept in notes/coverage tags. |
| REH-010 | advisory | S04 good points may be overlong and could dilute the action thesis. | Keep one compact “retain” slide with 4–5 evidence-backed strengths; move detail to notes/appendix, not delete the required section. |
| REH-011 | advisory | S14 closing may duplicate S13. | Merge the closing takeaway into S13 or keep S14 only if it shows a clear before/after P26→P27/P28 model. |
| REH-012 | blocker | P26→P27/P28 measurable impact is not explicit. | Add measures to S12/S13: matrix completion before commitment; named primary/backup coverage; readiness-gate completion; carry-forward items with owner/retirement status. These are proposed measures, clearly labeled as proposals, not P26 achieved results. |

### Rehearsal conclusion

Round 1 is **not converged**. The thesis is acceptable, but the outline must be
revised before manuscript writing. The earliest affected layer is the outline,
not the evidence collection or approved thesis. A second fresh cold-read round
is required after the outline revision.

## Stage 4 audience rehearsal — Round 2

**round_id:** R2-outline-20261005
**reviewer:** fresh independent audience reviewer; no prior defect list supplied.
**result:** Converged for outline stage. The central message, scope, tone,
evidence chain, and requested actions were understood. Minor follow-up items:
confirm the final S14 merge decision and keep the matrix columns explicit in the
manuscript.

**Disposition:** Round 1 blockers were fixed at the outline layer. The outline
is approved for manuscript production under the approved Candidate B thesis.

## PS-filtered inventory consolidation — current result

After applying the non-negotiable PS filter, the inventory is no longer a
general Zion meeting list. The following records are the current PS-core or
PS-involved set to carry forward:

### PS-core / PS-involved workshops and deep dives

1. **2023/12 IMS deep-dive training-guideline discussion** — PS-involved AP-
   IMS/MIPC, registration, domain selection, voice, EPSFB, SRVCC, and carrier
   requirement clarification.
2. **2024/3 T900 workshop — PS portions only** — IMS integration, system
   verification, PS milestone/feature criteria, and related PS interfaces.
3. **2024 Relay Metrics requirement review family** — 2023/11/24 and
   2024/3/5 review records, plus subsequent metric/reference evolution.
4. **2024/7/31 PS customization discussion** — direct PS feature/DRI
   mapping, system selection, modem-health/recovery, relay metric, and
   related PS-involved requirements.
5. **2024/9/24 PS customization workshop** — confirmed E1 anchor for the
   recurring PS collaboration model.
6. **2024/10/29–11/7 PS Deep Dive planning/rehearsal** — joint-analysis and
   issue-debugging orientation.
7. **2024/11/11–11/14 PS Deep Dive execution and outcome** — NAS/RRC/L2/Misc,
   joint debugging, code/trace requests, Relay Metrics agreement, and
   follow-up ownership.
8. **2024/11/4–11/6 Protocol/AP-IMS workshop — PS topics only** — AP-IMS,
   domain selection, registration, voice, DSDS, and PS interface topics;
   hybrid architecture applies only to the relevant AP-IMS/AP-DS/Modem topic.
9. **AP-IMS MIPC API training/Q&A family** — persistent clarification and
   enablement stream, kept separate from the November workshop.
10. **2025/7/16 Alcedo–Zion F2F — PS topics only** — L1 metrics, VoNR/L2
    power feature, PS/API, and customer-feature feasibility/commitment.

### PS-core / PS-involved execution and lifecycle events

11. **2026 PS DRI sync-up / US support planning** — execution model anchor.
12. **2026 Most Wanted review execution** — ECC/OOS high-frequency stream,
    Call Performance not yet converged, and security hot-fix as an MWI
    substream.
13. **P26 FLD1/FLD2/Exception Feature governance** — separate from E1,
    covering scope, DRI, validation, escalation, and commitment boundary.
14. **P26 eSIM-only / extra-bytes debugging** — eSIM/BWT/verification and
    cross-site debugging stream.
15. **P26 SIM Lock first major post-MP/in-market issue** — AP/MD read-back,
    NVRAM, eSIM restriction, and P27+ carry-forward.
16. **P26 QPR / long-tail support** — QPR patch, workaround-to-next-program
    handoff, customer validation, and long-term support ownership.

### Reviewed but excluded or held back

- General RF, GNSS, NTN, desense, and factory workshops without an explicit
  PS dependency.
- 2024/4/3 PCIe Power Optimization: currently evidence-insufficient for PS
  inclusion; do not use as a PS key event yet.
- AGPS meeting-note family: meeting existence is known, but several source
  bodies failed conversion and do not provide reliable decisions.
- General P28/F2F items whose only topics are RF, antenna, GAAM, 6Rx, or
  SpaceX.

### Calibration conclusion

The earlier Q1–Q11 structure remains valid after this inventory pass, with
these concrete calibrations:

- **Q1:** “all PS-involved activities” is now operationalized by the PS
  filter; not all Zion meetings are included.
- **Q2:** use five event-anchored phases, with 2023/12 IMS enablement and
  2024/3 Relay Metrics/T900 PS-relevant activity as early anchors.
- **Q3:** keep collaboration operating model as the main axis; treat
  workshops, deep dives, training, recurring syncs, issue reviews, and QPR
  follow-up as distinct mechanisms.
- **Q7/Q8:** separate structured workshops/deep dives from recurring/ad-hoc
  meetings and from lifecycle follow-up.
- **Q9:** retain workshop-enabled vocabulary, joint-debugging, and metric
  agreement as conditional good points with follow-through caveats.
- **Q11:** retain the four improvement themes plus the execution-bridge
  principle.

No new top-level interview question is needed from this inventory pass. The
next grill frontier is to validate the first PS event family (E1) at the
topic/decision level, then proceed through the list one event family at a
time.
