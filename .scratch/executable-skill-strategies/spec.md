# Executable Skill Strategies

## Problem Statement

Hermes 的 skill 可以描述一條已知最佳工作路徑，但目前這些內容仍是模型可重新解讀的提示。即使某個 capability 已有可重複、唯一且可驗證的 provider sequence，Agent 仍可能在每個中間步驟重新呼叫模型、嘗試 alternative、越過停止條件，或把 authentication、provider failure 與 strategy defect 混成同一類錯誤。這增加 Gateway latency、模型成本與不可預測性，也讓使用者明明已把正確流程寫進 skill，仍必須反覆糾正 Agent。

Hermes 目前也沒有正式表示 Capability Strategy 的 machine-readable contract。把完整 state machine 寫進 `SKILL.md` prose 無法驗證與強制執行；把它塞進 frontmatter 會膨脹 discovery index；把它放進 provider 則會錯置 ownership，因為 provider 應負責 credential、session、operation 與 normalized outcome，而不是決定何時採用哪條產品工作路徑。

此外，同一 Teams conversation 可能在相隔很久後收到 follow-up、對既有要求的 correction，或完全無關的新問題。以 TTL、turn、session、chat ID 或 reply ID 判定 strategy 是否延續都會出錯。Strategy continuity 還必須與 Execution Authority 分離：本機 TUI 與 owner 的 Teams MTK control conversation 可以執行完整 owner workflow，但其他 Gateway conversation 或使用者不得因為引用舊問題、載入 skill 或共用 cached Agent 而取得相同權限。

最後，當 contract 不完整或 provider 真正故障時，Hermes 缺少一致的 fail-closed 與 durable repair route。模型不應在 Contract Gap 時臨時發明 fallback；Background Review 也不應直接修改任意 provider source。這些失敗必須留下可去重、可稽核、可由 Foreground Agent 以 TDD 接手的證據。

## Solution

Hermes 將引入 **Executable Skill Strategies**：由 skill 擁有、Core 執行、provider 提供 normalized operations 的三層 capability execution 模型。

每個參與此機制的 skill 會在 frontmatter 放置小型、版本化的 strategy index，指向 lazy-loaded、data-only strategy manifest。Manifest 將 capability 拆成 Contracted、Adaptive 或 Hybrid Strategy Nodes。Contracted nodes 由通用 Contract Executor 依 normalized provider outcomes 連續推進，不在唯一合法 transition 之間再次呼叫模型；Adaptive nodes 才明確 handoff 給模型，並受 manifest 與 Core guardrails 限制。

Strategy 只有在 skill 被明確載入後才 activation。未 activation 時，既有 direct provider/tool call 保持 Adaptive，不會被某個 skill 隱性接管。Activation 綁定語意上的 Intent Thread，沒有 TTL。主模型在正常 turn 中回看相關 user/assistant exchange，判斷 `new`、`follow_up` 或 `correction`，並在需要時指定穩定 Intent Reference；Core 只驗證 reference、activation、authority 與 contract structure，不以時間 heuristic 取代語意判斷。

有 executable manifest 且目前 session 在啟動時符合條件時，Hermes 會固定暴露 service-gated `strategy_execute` interface。模型以它提交 capability、Intent Relation、Intent Reference 與 normalized user inputs。Core 接著重新計算當前 turn 的 Execution Authority、載入並驗證 manifest snapshot、執行 contracted transitions、處理 adaptive handoff，並產生完整 trace。Tool schema 不在 conversation 中途改變。

Execution Authority 永遠來自當前 trusted runtime origin，而不是 skill、Intent Thread 或模型參數。本機 TUI 是 owner surface。Teams MTK 只有「exact configured control conversation 加 immutable owner sender identity」可取得 owner-equivalent authority；其他 Gateway origins 不得執行 Contract Executor operations。所有既有 approval、credential、destructive-action、tool availability、platform policy 與安全封鎖仍然適用。

Contract Gap 會 fail closed，不自動退回 Adaptive、換 provider 或讓模型探索。Core 會建立或更新 de-duplicated Contract Repair Task。已觀察到的 provider/tool defect 則建立或更新 Provider Repair Task。兩者都進入既有 Kanban `triage`，不自動 dispatch，由 Foreground Agent 驗證 ownership 後以 TDD 修復。Background Review 可在繼承有效 Skill Write Authority 時非破壞性地改善任何可解析、可載入的 skill，但不得把未驗證 workaround 當永久 contract，也不得自行修改任意 provider repository。

## User Stories

1. As a Hermes owner, I want proven skill workflows to execute deterministically, so that I do not pay repeated model latency for transitions that have only one legitimate next action.
2. As a Hermes owner, I want adaptive reasoning to remain available where judgment is genuinely required, so that deterministic execution does not destroy useful flexibility.
3. As a Hermes owner, I want one capability to combine contracted and adaptive nodes, so that an entire skill is not forced into an all-or-nothing mode.
4. As a Hermes owner, I want a skill to govern a provider only after explicit activation, so that installing or discovering a skill does not silently change unrelated provider calls.
5. As a Hermes owner, I want direct provider calls to remain Adaptive when no matching skill strategy is active, so that legitimate exploratory work continues to function.
6. As a Hermes owner, I want an active Contracted Strategy to block direct bypass of its underlying operation, so that the model cannot route around a strategy after selecting it.
7. As a Hermes owner, I want strategy activation to follow the semantic work thread rather than elapsed time, so that a late reply can correctly resume old work.
8. As a Hermes owner, I want an immediately adjacent but unrelated question to start a new Intent Thread, so that same-chat recency does not leak an old strategy into new work.
9. As a Hermes owner, I want a correction to amend prior work without rewriting transcript history, so that execution can be corrected while prompt-cache and audit invariants remain intact.
10. As a Hermes owner, I want several old Intent Threads to coexist in one Teams conversation, so that a later follow-up can target the correct earlier topic.
11. As a Hermes owner, I want the model to inspect relevant prior user and assistant exchanges before classifying intent continuity, so that the decision is based on meaning rather than metadata shortcuts.
12. As a Hermes owner, I want a platform reply reference to act as evidence rather than an absolute verdict, so that an unrelated reply can still be classified as new work.
13. As a Hermes owner, I want a message without reply metadata to resume old work when its semantics are clear, so that Teams UI behavior does not control product meaning.
14. As a Hermes owner, I want ambiguous side-effecting continuation to ask me which prior intent I mean, so that an uncertain classification cannot mutate durable state.
15. As a Hermes owner, I want low-risk read-only continuation to proceed with an explicit interpretation, so that uncertainty does not create unnecessary questions.
16. As a local TUI user, I want Contracted Strategies to use the same enabled tools and approvals available to me, so that deterministic execution does not arbitrarily reduce my owner workflow.
17. As the owner in my configured Teams MTK control conversation, I want the same Contracted Strategy authority as my TUI, so that Teams can be a first-class control surface.
18. As the owner in another Teams conversation, I want owner-equivalent contract execution to remain denied, so that trust is tied to the exact control surface rather than my identity alone.
19. As another participant in the control conversation, I want my turn to remain denied owner-equivalent authority, so that knowing or entering the control conversation is not sufficient privilege.
20. As another authorized Gateway user, I want to read and follow normal skill guidance without gaining Contract Executor authority, so that useful shared assistance remains available without privilege escalation.
21. As a security operator, I want Execution Authority recomputed on every inbound turn, so that a trusted turn cannot bless the next turn on a cached Agent.
22. As a security operator, I want authority derived from immutable platform, conversation, and sender identities, so that display names, prompts, tool arguments, and transcript text cannot forge it.
23. As a security operator, I want delegated and background work to inherit no more authority than its commissioning turn, so that descendants cannot self-upgrade.
24. As a security operator, I want scheduled or redirected work to require an explicit trusted execution contract, so that references to old trusted messages cannot create authority.
25. As a security operator, I want normal approvals and dangerous-action controls to remain active inside Contract Executor, so that deterministic does not mean pre-approved.
26. As a security operator, I want unavailable operations to return authorization or availability failures rather than Contract Gaps, so that security policy is not misdiagnosed as a broken strategy.
27. As a skill author, I want compact strategy metadata in frontmatter, so that discovery stays fast and prompt-cache friendly.
28. As a skill author, I want the full executable strategy in a separate lazy-loaded manifest, so that complex workflows remain reviewable without bloating `SKILL.md`.
29. As a skill author, I want versioned manifest schemas, so that contracts can evolve with explicit compatibility behavior.
30. As a skill author, I want data-only manifests without scripts or executable expressions, so that strategy review does not become arbitrary code review.
31. As a skill author, I want explicit contracted and adaptive node declarations, so that responsibility for every decision point is visible.
32. As a skill author, I want every contracted outcome to map to one legal target, so that a deterministic node cannot hide model choice.
33. As a skill author, I want semantic conditions represented as Adaptive nodes or handoffs, so that natural-language judgment is not disguised as a deterministic transition.
34. As a skill author, I want contract validation before the first side effect, so that malformed or unreachable state machines fail safely.
35. As a skill author, I want path-safe manifest resolution for local, external, bundled, Hub-installed, and symlinked skills, so that all resolvable skills behave consistently without traversal escapes.
36. As a skill author, I want prose and manifest drift to be detectable, so that human instructions and executable behavior do not silently contradict each other.
37. As a Capability Provider author, I want to own credentials and session lifecycle, so that skills never need to copy token refresh logic.
38. As a Capability Provider author, I want operations to return stable normalized outcomes, so that contracts branch on observable behavior instead of parsing error prose.
39. As a Capability Provider author, I want provider-specific logic outside the Contract Executor, so that Core remains domain-neutral.
40. As a Capability Provider author, I want unknown outcomes surfaced explicitly, so that new backend behavior cannot silently select an unintended fallback.
41. As a Hermes maintainer, I want one generic Contract Executor, so that each provider does not implement a private workflow engine.
42. As a Hermes maintainer, I want each run to use an immutable validated manifest snapshot, so that a mid-run skill edit cannot change the state machine under execution.
43. As a Hermes maintainer, I want later follow-ups to use the latest valid manifest while historical traces retain old digests, so that fixes apply without losing reproducibility.
44. As a Hermes maintainer, I want execution budgets and stopping conditions enforced by Core, so that loops cannot continue merely because the model keeps requesting more work.
45. As a Hermes maintainer, I want state, outcome, transition, handoff, budget, and manifest digest in the run trace, so that execution can be diagnosed from evidence.
46. As a Hermes maintainer, I want Intent Thread identifiers and compact summaries to survive persistence and compression, so that long-delayed continuation remains possible.
47. As a Hermes maintainer, I want Intent metadata stored outside the assistant/user role stream, so that strict role alternation and prompt caching remain intact.
48. As a Hermes maintainer, I want the strategy toolset frozen at session creation, so that skill installation cannot mutate tool schemas mid-conversation.
49. As a Hermes maintainer, I want existing skills without manifests to remain Adaptive, so that this feature is backward-compatible and does not require a mass migration.
50. As a Hermes maintainer, I want unsupported manifest versions to fail closed with a precise diagnostic, so that silent schema reinterpretation is impossible.
51. As a Foreground Agent, I want Contract Gaps recorded as durable Kanban triage tasks, so that unresolved contracts survive restarts and compression.
52. As a Foreground Agent, I want observed provider failures recorded separately from Contract Gaps, so that the repair owner can be determined from evidence rather than assumption.
53. As a Foreground Agent, I want repair tasks to preserve skill, capability, operation, normalized outcome, contract version, trace, expected behavior, and source session, so that I can reproduce before changing code.
54. As a Foreground Agent, I want repeated equivalent failures appended to one open task, so that Kanban does not fill with duplicate incidents.
55. As a Foreground Agent, I want repair tasks to begin in `triage` and never auto-dispatch, so that speculative root causes cannot launch unattended source changes.
56. As a Foreground Agent, I want provider repairs performed through TDD in the owning workspace, so that the root cause is proven and the fix covers the actual boundary.
57. As a Background Review, I want to non-destructively improve any skill I could resolve and use when my parent turn carried Skill Write Authority, so that learning is not blocked by legacy authorship metadata.
58. As a Background Review, I want exact-target read-before-write enforcement, so that external or symlinked skill updates modify the intended target with current content.
59. As a Background Review, I want provider defects escalated instead of patched directly, so that unattended review cannot modify arbitrary repositories.
60. As a Background Review, I want a legitimate stopping condition recorded in the skill when appropriate, so that future agents stop honestly without encoding an unverified workaround.
61. As a skill owner, I want deletion and archival to require separate Destructive Curation Consent, so that permission to improve a skill is not permission to remove it.
62. As an operator, I want Kanban task creation failure reported separately from the original execution failure, so that an outage in the repair queue cannot hide the Contract Gap or provider defect.
63. As an operator, I want traces and tasks to redact credentials, secret payloads, and raw immutable identities, so that observability does not create a data-leak path.
64. As an operator, I want the control conversation configured in `config.yaml` rather than a new non-secret environment variable, so that deployment policy follows Hermes configuration conventions.
65. As an operator, I want home-channel delivery and owner control authority to remain separate concepts, so that changing where notifications arrive does not silently change privileges.
66. As a user, I want clear user-facing results that distinguish success, provider failure, authorization denial, Contract Gap, budget exhaustion, and human/model handoff, so that I know what actually happened.

## Implementation Decisions

- **Responsibility boundary:** Capability Strategy is skill-owned; provider operations, credentials, sessions, and normalized outcomes are provider-owned; the generic Contract Executor, Execution Guardrails, authority enforcement, persistence, tracing, and repair escalation are Core-owned.
- **Execution modes:** Every Strategy Node declares `contracted` or `adaptive`. A Hybrid Strategy composes both. A node requiring semantic judgment cannot be declared contracted.
- **Contractibility rule:** A contracted node is valid only when its states are finitely enumerable and every observed `(state, outcome)` has one legal transition or an explicit terminal/handoff result.
- **Strategy index:** `SKILL.md` frontmatter contains a compact, versioned index of capability IDs and relative manifest references. Discovery reads the index but does not load full manifests.
- **Manifest location and format:** Full strategies are lazy-loaded from supporting YAML files below the resolved skill root. They are versioned, data-only, expression-free, and may not embed scripts, credentials, shell commands, or executable code.
- **Manifest invariants:** Validation covers schema version, path containment, unique capability IDs, node shape, operation references, outcome uniqueness, reachability, terminal states, handoffs, cycles, and finite budgets before the first side effect.
- **Operation inputs:** The contract uses a small declarative binding format over normalized user inputs, prior normalized results, and constants. It does not evaluate arbitrary expressions. Exact field names may evolve within the versioned schema without changing these constraints.
- **Provider interface:** An operation participating in contracted execution exposes a stable operation identity and normalized outcome vocabulary. Existing tools remain usable adaptively; they enter contracts only after their outcomes are made explicit and testable.
- **Contract Executor:** Core interprets the compiled manifest snapshot and repeatedly dispatches the declared operation, consumes the normalized outcome, and selects the sole declared transition. It stops on success, terminal failure, budget exhaustion, authorization/availability failure, Contract Gap, or explicit handoff.
- **Model-call boundary:** There is no model call between uniquely determined contracted transitions. Adaptive nodes return a bounded continuation to the normal agent loop, including the allowed objective, operations/providers, budgets, and resume point.
- **No bypass:** After Strategy Activation, an attempt to call the underlying contracted operation outside `strategy_execute` is rejected before side effects. The result explains that the active capability must resume through its strategy rather than silently degrading to Adaptive execution.
- **Explicit activation:** Loading the owning skill activates its strategies only for the current semantic Intent Thread. Skill listing, frontmatter discovery, provider availability, and subject-matter similarity do not activate a strategy.
- **Adaptive default:** Direct provider/tool calls made without a matching active skill strategy preserve current Hermes behavior and are treated as Adaptive execution.
- **Intent model:** Intent Threads have stable runtime identifiers. For each relevant user turn, the main model declares `new`, `follow_up`, or `correction`; follow-up and correction also identify the prior Intent Thread. Time, turn, session, and chat identity do not expire or establish continuity.
- **Evidence resolution:** An explicit reply/message relation provides the first candidate anchor, retained history and compression summaries provide nearby context, and same-conversation session retrieval provides older exchanges absent from active context. Reply metadata never replaces semantic classification.
- **Ambiguity policy:** When a wrong reference could authorize a side effect or durable mutation, the model asks the user. Read-only work may proceed with its interpretation stated explicitly.
- **Correction semantics:** A correction appends a new user turn and starts an amended capability run under the same strategy. Prior messages, traces, and outcomes are not rewritten.
- **Intent persistence:** Intent identifiers, semantic summaries, strategy activation references, and capability-run references are stored as structured session metadata outside the role-alternating model transcript. Compression preserves or regenerates the compact intent index without changing prior prompt bytes.
- **Strategy execution interface:** A service-gated `strategy_execute` model tool accepts capability ID, Intent Relation, optional Intent Reference, and normalized user inputs. It is present only when executable-strategy support is available and the session origin is eligible at Agent construction time.
- **Prompt-cache stability:** Tool schemas and the system prompt stay byte-stable for the session. Installing or changing strategy support is deferred to a new session by default; an explicit cache-invalidating path may exist but is not the default.
- **Conversation-scoped tool visibility:** TUI sessions with executable manifests may expose `strategy_execute`. Teams MTK exposes it only for configured control conversations at Agent construction. If a non-owner later speaks in that cached control-conversation Agent, dispatch still denies execution using per-turn sender authority.
- **Per-turn authority:** Execution Authority is recomputed from trusted runtime context on every turn and is propagated with concurrency-safe context. It is never accepted from model arguments, transcript data, display names, persisted Agent state, or Intent References.
- **Owner surfaces:** Local TUI is an owner surface. Teams MTK is owner-equivalent only when both exact conversation ID and immutable owner sender ID match configuration.
- **Shared control policy:** One non-secret `gateway.teams_mtk.control_conversations` policy supplies the exact control-conversation boundary for both Contract Executor authority and Skill Write Authority. Home-channel delivery may seed setup but is not itself authorization, and no duplicate skill-specific control list is created.
- **Non-control Gateway behavior:** Other Gateway origins may use read-only skill guidance and their existing adaptive capabilities, but Contract Executor invocation is denied and never auto-falls back to direct adaptive execution.
- **Existing security remains authoritative:** Tool enablement, credentials, approval prompts, dangerous-action checks, destructive curation consent, platform authorization, and provider policy all run normally inside contracted execution. A strategy can narrow but never expand them.
- **Failure taxonomy:** Contract Gap, provider failure, authorization denial, operation unavailability, budget exhaustion, and adaptive/human handoff are distinct terminal or resumable outcomes. User-facing and trace output must preserve this distinction.
- **Contract Gap policy:** Missing/invalid manifests, unsupported schema, nonexistent operation references, unreachable/malformed graphs, and undeclared provider outcomes fail closed. Core never chooses another provider, direct call, or model fallback automatically.
- **Run versioning:** Each run compiles one immutable manifest snapshot and records schema version plus content digest. A later follow-up resolves the latest valid manifest; historical runs retain their original digest.
- **Repair escalation:** Contract Gaps create/update Contract Repair Tasks; evidenced provider/tool failures create/update Provider Repair Tasks. Both use existing Kanban `triage`, carry redacted structured evidence, and are not automatically dispatched.
- **Repair deduplication:** An idempotency fingerprint includes owning layer candidates, skill/capability, operation, normalized error/outcome class, and compatible contract version. Later occurrences append evidence to the existing open task. Exact scoring and retention are reversible policy.
- **Background Review boundary:** An authorized Background Review may improve the selected skill non-destructively and may create/update repair tasks. It cannot directly patch arbitrary provider/project source, declare speculative root cause as fact, or permanently encode an unverified alternative route.
- **Skill write surface:** A turn with Skill Write Authority may non-destructively maintain every exact skill target it can resolve and load, including external and symlinked targets. Legacy `created_by` metadata does not gate patch/edit. Delete/archive still require separate Destructive Curation Consent.
- **Escape-hatch defense:** Unauthorized Gateway turns cannot bypass skill or strategy restrictions through direct file writes, symlink targets, terminal, code execution, delegation, cron, or desktop control. Schema hiding is an ergonomic layer; trusted dispatch/path enforcement is authoritative.
- **Observability:** A trace records intent, strategy activation, execution mode, capability, manifest digest, node/state, normalized operation and outcome, transitions, budgets, handoffs, authority class, repair-task linkage, and terminal classification. Credentials, secret payloads, and raw personal identifiers are excluded or redacted.
- **Backward compatibility:** Skills without strategy metadata and providers without normalized contract operations continue unchanged in Adaptive mode. No global migration of existing skills is required.
- **Configuration policy:** New behavioral settings belong in `config.yaml`; no new non-secret `HERMES_*` or `.env` setting is introduced. Credentials remain in the existing provider/authentication paths.

## Testing Decisions

- **Testing philosophy:** Tests assert externally observable contracts and relationships, not source text, implementation shape, catalog snapshots, exact enumeration counts, or private helper names. A good test proves which operation ran, which outcome was observed, whether another model call occurred, what durable state was written, and what an authorized or unauthorized caller could do.
- **Primary high-level seam:** Exercise a real `AIAgent.run_conversation` turn against an isolated temporary Hermes home, actual skill/frontmatter resolution, actual manifest validation, actual tool registry dispatch, actual session persistence, and scripted model responses. Capability operations use deterministic fake providers returning normalized outcomes; the Contract Executor itself is not mocked.
- **Primary-seam contracted scenario:** Activate a fixture skill whose contract receives `auth_expired`, performs the one declared refresh operation, retries, and succeeds. Assert operation order, exactly zero intermediate model decisions, final trace, budgets, and persisted manifest digest.
- **Primary-seam hybrid scenario:** Execute contracted nodes into an explicit Adaptive node, assert one bounded model handoff, then resume the declared contracted continuation without exposing an unrestricted provider fallback.
- **Primary-seam activation scenarios:** Prove skill discovery alone does not activate; explicit load does; a direct call without activation remains Adaptive; and a direct underlying-operation call after activation is rejected before side effects.
- **Primary-seam validation scenarios:** Invalid schema, traversal reference, duplicate capability, unreachable state, missing operation, cycle without budget, undeclared outcome, and unsupported version all stop before side effects and return a Contract Gap.
- **Primary-seam repair scenarios:** Read back Kanban storage to prove first Contract Gap creates one triage task, an equivalent recurrence appends evidence instead of duplicating, provider failures create the distinct repair-task class, and task-write failure does not hide the original execution result.
- **Primary-seam version scenarios:** Prove a run remains on its compiled digest despite a mid-run file change, while a later semantic follow-up uses the latest valid manifest and retains links to both historical digests.
- **Intent-continuity seam:** Run multiple turns with several old Intent Threads. Prove long-delay follow-up and correction resume the selected intent, immediate unrelated input creates a new one, corrections append rather than rewrite, reply metadata is only an anchor, and compressed/resumed sessions can retrieve the intended older exchange.
- **Gateway authority seam:** Exercise the real Gateway inbound/session-context binding with a fixture `SessionSource`, real authority computation, and the same strategy dispatch boundary. Cover local TUI allow, owner plus exact Teams MTK control conversation allow, owner in another conversation deny, another sender in control conversation deny, and ordinary Gateway origin deny.
- **Cached/concurrent authority scenarios:** Reuse one cached group/control Agent across sequential different senders and run two turns concurrently. Assert no owner authority, Intent Reference, approval routing, or session identity leaks between turns or worker threads.
- **Descendant authority scenarios:** Verify Background Review and delegation inherit no more than the parent turn, non-control origins cannot regain authority through a child, and background repair-task creation remains narrowly permitted only when commissioned by an authorized turn.
- **Toolset/cache seam:** Assert `strategy_execute` is service-gated at Agent construction, absent from ineligible sessions, stable across the conversation, isolated from shared tool-definition caches, and not dynamically added after a skill install until a new session.
- **Skill-maintenance seam:** Through the public skill management boundary, prove an authorized owner turn can patch local, external, and symlinked skill targets after exact read-before-write; prove unauthorized Teams turns are denied through skill APIs and protected direct-file escape paths; prove delete/archive still require separate consent.
- **Manifest-validator unit seam:** Keep a narrow table-driven suite for schema parsing, graph invariants, expression-free bindings, outcome normalization contracts, and digest stability. These tests call public validator/compiler behavior and do not read implementation source.
- **Provider contract tests:** For each migrated real provider, run its operation boundary and assert stable normalized outcomes for success, authentication expiry/denial, not-found, retryable transport failure, permanent failure, and unexpected response. Tests validate relationships rather than snapshotting provider catalogs.
- **Prior art:** Reuse the behavioral shapes established by the existing tool-call guardrail runtime tests, ContextVar propagation/isolation tests, tool-definition cache isolation tests, preloaded-skill tests, Gateway active-session tests, compression persistence tests, Background Review tests, Kanban tool tests, and Teams MTK authorization tests.
- **Hermetic verification:** Run Python tests only through the repository test wrapper with isolated credentials, locale, timezone, and Hermes home. Add focused suites first, then relevant Agent, tools, Gateway, skill, Kanban, and compression directories, followed by the full applicable suite.
- **Real execution gate:** Before declaring the feature complete, run a real local TUI scenario and a real Teams MTK scenario using a harmless read-only strategy. In Teams, verify both the configured owner control conversation and a non-control origin by observable Gateway responses and persisted traces; do not infer success from mocks or source inspection.
- **Real repair gate:** Trigger a safe fixture Contract Gap in a live development profile, read back the resulting Kanban task and trace, rerun the same fingerprint to verify deduplication, then clean up the fixture artifacts.
- **Failure reporting:** Any partial E2E failure, denied operation, repair-queue failure, flaky retry, or test that passes only on retry is reported explicitly and is not converted into a green completion claim.

## Out of Scope

- Converting every existing skill to an executable strategy in this change.
- Hard-coding Buganizer, Teams, CorpSSO, `bug-brief`, or any other provider-specific state machine into Core.
- Moving provider authentication, token refresh, credential storage, or session lifecycle into skills or strategy manifests.
- Embedding Python, shell, templates with executable expressions, or arbitrary scripts in strategy YAML.
- Treating skill installation, skill discovery, same-chat history, reply IDs, user allowlists, display names, or Intent Threads as authorization.
- Granting Contract Executor authority to non-control Gateway conversations or users.
- Removing normal approval prompts or dangerous/destructive-operation protections from owner surfaces.
- Allowing Background Review to repair arbitrary provider/project source directly.
- Automatically promoting or dispatching Contract Repair Tasks or Provider Repair Tasks from Kanban triage.
- Automatically choosing a new provider or Adaptive fallback when a Contracted Strategy encounters an undefined state or outcome.
- Building a separate standalone workflow engine, repair queue, authentication manager, semantic-classifier service, or second agent loop.
- Adding a permanent global strategy tool to installations or sessions that do not enable executable strategies.
- Changing tool schemas or rebuilding the system prompt mid-conversation by default.
- Replacing the existing SessionDB, Kanban system, skill discovery model, tool registry, approval system, or Gateway platform authorization wholesale.
- Generalizing owner-equivalent control conversations to every messaging adapter in the first implementation; non-TUI/non-Teams-MTK origins remain denied until a later explicit trust design exists.
- Destructive skill curation policy beyond preserving the existing separate consent requirement.
- A visual contract-authoring editor or no-code workflow designer.

## Further Notes

- The normative vocabulary is defined by the project domain glossary: Capability Strategy, Strategy Activation, Intent Thread, Intent Relation, Intent Reference, Contracted Strategy, Adaptive Strategy, Hybrid Strategy, Strategy Node, Contract Executor, Capability Provider, Execution Guardrail, Execution Authority, Contract Gap, Contract Repair Task, Skill Write Authority, Teams Control Channel, Turn Capability, Destructive Curation Consent, and Provider Repair Task.
- This spec incorporates the accepted decisions covering visible-skill non-destructive maintenance, provider-defect Kanban escalation, Teams owner control-channel authority, Core-owned contracted transitions, fail-closed Contract Gaps, explicit skill activation, origin-derived Execution Authority, lazy strategy manifests, and main-model semantic continuity.
- Repository discovery found no existing OpenSpec change or `.scratch` spec for executable skill strategies. This is therefore a standalone issue-tracker spec rather than a duplicate of another authoritative change.
- The preferred build route after approval is `/to-tickets`, followed by `/implement` with TDD and final `/code-review`.
- Exact threshold defaults, repair fingerprints, error-normalization heuristics, and internal schema field spelling are reversible implementation choices. They may be optimized without changing the responsibility and authority boundaries in this spec.
