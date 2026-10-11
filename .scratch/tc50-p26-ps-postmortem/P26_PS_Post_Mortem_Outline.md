# TC50 P26 PS Post-Mortem — Slide Outline

> Stage 4 outline revision after Round 1 audience rehearsal.
> Approved narrative: Feature-to-lifecycle control.
> This is an editable outline, not the slide manuscript or PPTX.

## Thesis

P26 demonstrated that a customer customization is not complete at feature implementation; default enablement, carrier scope, validation boundary, release, and post-MP ownership must be defined as one lifecycle.

## Recommended use

- Audience: Clare / Justin; preparation for the 10/E Zion workshop.
- Main lens: PS collaboration operating model, using feature-to-lifecycle control as the narrative spine.
- External: jointly discussable Alcedo/Zion interface, evidence, improvement, and commitments.
- Internal: Alcedo-only R&R, coverage, access side effects, handoff, escalation, decision, and long-tail planning.
- Page-count mode: story-led; target 13 slides plus optional appendix, pending workshop time confirmation.

## Slide outline

| ID | Title | Purpose / audience question | Single takeaway | Evidence / visual | PPT mapping | Next |
|---|---|---|---|---|---|---|
| S01 | P26 PS Post-Mortem: From Feature Implementation to Lifecycle Control | Why review P26 now? | Review B converts P26 PS experience into P27/P28 collaboration improvements. | Title + one-sentence thesis; no unsupported metrics. | Scope / framing | Define scope and boundary. |
| S02 | Scope and Review Boundary | What is included and what is not? | Customization is the lead lens; evidence spans PS feature, issue, AP-IMS, metrics, eSIM/SIM, MWI, release, and long-tail activities. | Two columns: External = joint Alcedo/Zion interface; Internal = Alcedo-only execution/R&R. | Scope; External/Internal | Show established model. |
| S03 | Established P26 Co-working Model | How did Alcedo and Zion work together? | Four connected mechanisms existed: feature, issue, structured technical collaboration, and project operating model. | Editable lifecycle diagram: intake → scope/owner → technical discussion → decision/fix → validation → release/closure; four mechanism labels. | Established co-working model | Show retained strengths. |
| S04 | Good Points to Retain | What worked and should continue? | P26 established useful scope/ownership/validation alignment, recurring forums, AP-IMS enablement, living metric reference, and issue/release gates. | 4–5 concise strengths; optional metric callouts: 1,200+ metrics; 218/111 MWI snapshot with as-of date. | Good points | Show gaps. |
| S05 | P26 Collaboration Gaps Identified | What did execution expose? | Four gaps: R&R/routing; technical coverage/time-zone continuity; end-to-end lifecycle ownership; cross-module convergence. | Lifecycle with four breakpoints; neutral wording, not blame. | Areas for improvement | Ground gaps in events. |
| S06 | Key Events: Feature-to-Lifecycle Control Formation | Which events changed the model? | Workshops/reviews progressively defined scope/interface, AP-IMS responsibility, living metrics governance, and feature control. | Event anchors: 2024/9/24 PS customization; 2023/12–2024/11 AP-IMS evolution; Relay Metrics reviews; FLD1/FLD2/Exception reviews. | Key events | Show execution/post-MP. |
| S07 | Key Events: Execution, Verification, and Post-MP Long-tail | What happened under execution and after MP? | MWI/ECC-OOS, eSIM extra-bytes, SIM Lock, and QPR exposed the need to connect implementation to verification, release, and successor ownership. | Define long-tail: post-MP QPR, workaround retirement, next-program handoff, continuing support. Use 6/8 eSIM and reconciled numbers only. | Key events | Derive lessons. |
| S08 | Lesson 1 — Feature Verification & Enablement Matrix | What must be defined before feature commitment? | Implementation scope and DRI are insufficient. | Editable matrix: feature/carrier-scenario; default ON/OFF; ownership; Alcedo UT/RDIT; SV/FO; Zion IT; acceptance; release; closure. | Lessons learned / beyond project | Readiness gates. |
| S09 | Lessons 2–3 — Coverage and Verification Readiness | What must be ready before execution pressure? | Two gates: people/decision coverage and test/evidence readiness; both feed feature commitment. | Two linked gate diagrams: Coverage & Routing Matrix → Joint Verification Readiness Gate → commitment. | Lessons learned / beyond project | Split Internal/External. |
| S10 | Internal Lessons Learned / Alcedo Optimization | What must Alcedo change? | Preserve firewall, but separate access coordination, primary/backup routing, technical ownership, decision authority, MUS/HQ/RD boundary, SV/FO classification, and long-tail ownership. | Internal RACI-style flow; no private source mechanics on slide. | Internal optimization; internal lessons | Joint interface. |
| S11 | External Lessons Learned / Joint Optimization | What should Alcedo and Zion jointly change? | Confirm enablement, counterpart/backup, test assets, validation, acceptance, target phase, and QPR/next-program disposition. | Joint checklist; sequence: shared evidence → improvement → Zion feedback/commitment → actions. | External optimization; external lessons | Artifacts and decisions. |
| S12 | P27/P28 Proposed Operating Artifacts | What changes operationally? | Four prioritized artifacts create measurable adoption: P1 Feature Matrix; P2 Coverage/Routing; P3 Verification Gate; P4 Carry-forward/Long-tail Register. | Four editable artifact cards + problem closed + proposed measure. | Internal/external optimization; beyond project | Request decisions. |
| S13 | Zion Workshop Decisions and Action Register | What must be agreed? | Capture explicit choices, owners, timing, capacity/dependencies, and open questions. | Editable table: recommendation; Zion input/choice; Alcedo owner; Zion owner; target phase; capacity/dependency; open question. | Other items / actions | Close with transition. |
| S14 | P26 → P27/P28: Feature-to-Lifecycle Control | What should the audience remember? | Retain P26 mechanisms; add explicit feature-to-lifecycle control. | Before/after operating model only if it adds measurable transition; otherwise merge into S13. | Beyond-project conclusion | Workshop action. |

## Narrative transitions

S01–S02 define the review and boundary → S03 shows the established model → S04 preserves strengths → S05 identifies neutral operating gaps → S06–S07 prove gaps with event evidence → S08 defines feature control → S09 defines coverage and evidence gates → S10/S11 split Internal and External actions → S12 turns lessons into artifacts → S13 requests decisions → S14 closes with the P26→P27/P28 transition.

## Audience rehearsal Round 1 dispositions

- S02: clarify External = joint Alcedo/Zion interface; Internal = Alcedo-only execution/R&R.
- S06: use actual event anchors and state what changed.
- S07: define long-tail at first use.
- S08: show matrix columns visually.
- S09: show two linked but distinct gates.
- S12: enumerate and prioritize all four artifacts.
- S13: use explicit choices, owners, target timing, dependency/capacity fields.
- S14: retain only if it adds measurable transition; otherwise merge with S13.
- Add proposed adoption measures; label them as proposals, not P26 achieved results.

## Evidence and wording constraints

- Quantified claims require as-of date, scope, denominator where relevant, and conflict qualification.
- External slides do not mention PKB, Teams, private source mechanics, or the intentional firewall rationale.
- “Long-tail” means post-MP QPR support, workaround retirement, next-program handoff, and continuing support.
- Security hot-fix remains an MWI substream, not a separate post-MP event.
- MEP remains unresolved and must not be expanded in a slide title without confirmation.
