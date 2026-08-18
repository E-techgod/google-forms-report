You are acting as the senior software architect for this project.

Do **not write implementation code yet**.

Review the current Google Forms → insurance report generator architecture as if it will become a production system that must remain maintainable for several years.

Your objective is not to add unnecessary complexity. Your objective is to identify the minimum architecture required to make the system reliable, auditable, testable, secure, and easy to change.

Before proposing a final architecture, analyze the system in the following order:

1. **Domain boundaries**

   * Identify the core business/domain logic.
   * Separate domain logic from infrastructure and third-party services.
   * Identify which parts must remain pure/deterministic.

2. **System invariants**
   Define the rules that must never be violated, including:

   * LLMs cannot determine or modify classification.
   * retries cannot create duplicate reports or emails;
   * raw submissions are immutable;
   * classification results must be explainable from deterministic rules;
   * client-facing reports cannot expose internal-only information;
   * generated narratives cannot introduce facts absent from source data or deterministic assessment;
   * external service failures cannot result in lost submissions.

3. **Data lifecycle**
   Design the complete lifecycle:
   RawFormSubmission → NormalizedApplication → Assessment → Narrative → Report → Delivery.

   Clearly define what information exists at every stage and which stages are immutable.

4. **Processing state machine**
   Define explicit processing states, valid transitions, terminal states, retryable failures, and non-retryable failures.

5. **Idempotency**
   Design how duplicate Google Form events, webhook retries, worker retries, LLM retries, PDF retries, and email retries are handled without creating duplicate side effects.

6. **Persistence**
   Determine what state must be stored in order to:

   * resume interrupted processing;
   * retry individual stages;
   * audit previous results;
   * diagnose failures;
   * determine which reports and emails were already generated/sent.

7. **Async execution**
   Evaluate whether the webhook should execute the full report pipeline synchronously or whether it should validate/persist/enqueue the submission and return quickly.

8. **Failure analysis**
   Produce an edge-case/failure matrix covering at minimum:

   * duplicate submission;
   * malformed payload;
   * missing optional data;
   * missing required data;
   * changed Google Form fields;
   * LLM timeout;
   * malformed LLM structured output;
   * hallucinated information;
   * primary provider outage;
   * PDF rendering failure;
   * Gmail failure;
   * Gmail quota/rate limit;
   * partial delivery;
   * Cloud Run restart;
   * deployment during processing;
   * queue retry;
   * persistence failure.

   For every failure specify:

   * whether it is retryable;
   * what state remains persisted;
   * what side effects may already have happened;
   * how duplicate side effects are prevented;
   * whether human intervention is required.

9. **Classification engine**
   Design deterministic, versioned and explainable business rules.

   Each classification should record:

   * rule version;
   * rules evaluated;
   * rules triggered;
   * reasons;
   * resulting internal qualification.

   Do not invent underwriting or qualification rules. Treat rule definitions as business inputs that must be approved by Quirón.

10. **LLM boundary**
    Define a strict NarrativeContext containing only the data required to produce prose.

    The LLM must never:

    * create flags;
    * remove flags;
    * change the classification;
    * infer unprovided medical facts;
    * make an insurer underwriting decision.

    Define post-generation semantic validation in addition to JSON/schema validation.

11. **Information boundaries**
    Define separate InternalReportContext and ClientReportContext models so internal fields cannot accidentally appear in the client report.

12. **Provider strategy**
    Design a common LLM provider interface, but recommend the minimum number of providers required for v1. Avoid implementing unnecessary provider integrations simply because the abstraction permits them.

13. **Versioning**
    Determine what should be versioned:

    * form schema;
    * classification rules;
    * prompts;
    * report templates;
    * application releases.

14. **Observability**
    Define structured events and metrics that allow us to answer:

    * How many submissions were received?
    * How many completed?
    * Where are failures occurring?
    * Which provider/model was used?
    * How long does each stage take?
    * Were any duplicate submissions detected?
    * Were any deliveries retried?

    Do not log sensitive form answers.

15. **Test architecture**
    Design:

    * unit tests;
    * rule truth-table tests;
    * integration tests;
    * contract tests;
    * workflow tests;
    * failure/retry tests;
    * end-to-end tests.

16. **Architecture Decision Records**
    Identify the architectural decisions that should be recorded as ADRs before implementation.

17. **Project structure**
    After completing the analysis, propose a repository structure that cleanly separates:

    * API/transport;
    * domain;
    * workflows/application layer;
    * persistence;
    * external adapters;
    * report templates;
    * configuration;
    * tests;
    * architecture documentation.

Do not optimize prematurely and do not introduce unnecessary frameworks.

Favor:

* explicitness over magic;
* simple abstractions over clever abstractions;
* deterministic behavior over implicit behavior;
* recoverability over assuming success;
* testable pure logic over tightly coupled services.

At the end, produce:

1. Proposed architecture.
2. Revised data-flow diagram.
3. Domain model.
4. State machine.
5. Failure matrix.
6. Invariants.
7. Repository structure.
8. ADR list.
9. Test strategy.
10. Unresolved decisions that require human/business input.

Do **not** begin implementation until these items have been reviewed and approved.

Agent workflow

Claude
- owns architecture, phase design, contracts, invariants, and final architectural review
- does not delegate implementation until the phase specification is approved

Codex Builder
- implements only the approved phase scope
- writes and runs tests
- may not change architecture or business rules
- must stop and escalate if implementation conflicts with approved architecture

Codex Reviewer
- reviews the Builder's actual diff and tests
- performs adversarial testing
- checks scope, invariants, edge cases, and regressions
- does not approve based only on the Builder's summary

Required loop:
Claude spec → human approval → Codex Builder → Codex Reviewer → Claude review → human approval → next phase


## Phase File Contract

Every phase must live under:

`docs/phases/PHASE-XX/`

Each phase uses the following files:

* `SPEC.md`
* `REVIEW.md`
* `STATUS.md`

These files have different purposes and must not duplicate each other unnecessarily.

---

### `SPEC.md` — Authoritative Phase Specification

`SPEC.md` defines **what the phase is supposed to accomplish before implementation begins**.

It is the authoritative contract for the phase.

Claude owns the creation and maintenance of this file.

It must contain, when applicable:

#### 1. Phase identity

* Phase number
* Phase name
* Current spec version

#### 2. Objective

* What this phase is intended to accomplish
* Why this phase exists

#### 3. Scope

* What is included in this phase

#### 4. Out of scope

* What must not be implemented or changed during this phase

#### 5. Dependencies

* Previous approved phases
* Required architectural decisions
* Required business inputs
* Required external services or interfaces

#### 6. Relevant architecture

* System components involved
* Domain boundaries involved
* Data flow for this phase
* Interfaces/contracts affected

#### 7. Data contracts

When applicable:

* Input models
* Output models
* Required fields
* Optional fields
* Validation behavior
* Error behavior

#### 8. Invariants

List the project invariants relevant to this phase.

The phase may not weaken or bypass an invariant.

#### 9. State behavior

When applicable:

* States involved
* Allowed transitions
* Invalid transitions
* Retry behavior
* Terminal states

#### 10. Failure behavior

Define expected behavior for important failure cases.

For each relevant failure specify:

* what fails;
* whether it is retryable;
* what state remains persisted;
* whether side effects may already have occurred;
* how duplicate side effects are prevented;
* whether human intervention is required.

#### 11. Security and privacy requirements

When applicable:

* sensitive information involved;
* what may be logged;
* what must never be logged;
* trust boundaries;
* secrets handling;
* data minimization requirements.

#### 12. Allowed implementation surface

Specify which files, packages, modules, or directories may be created or modified.

Implementation agents must not expand this scope without escalation.

#### 13. Prohibited changes

Explicitly identify architecture, business rules, interfaces, or unrelated areas that must not be modified.

#### 14. Acceptance criteria

Define objective conditions that must be true for the phase to be considered complete.

Acceptance criteria must be testable or verifiable.

#### 15. Required tests

When implementation is part of the phase, define the minimum required:

* unit tests;
* integration tests;
* contract tests;
* workflow tests;
* failure/retry tests;
* regression tests.

#### 16. Business decisions required

Any unresolved business logic must be clearly marked:

`BUSINESS INPUT REQUIRED`

Claude and Codex may not invent these decisions.

#### 17. Architectural questions

Any unresolved engineering decision must be explicitly listed.

Do not silently resolve significant architectural ambiguity during implementation.

#### 18. Implementation authorization

State whether implementation is currently:

* `NOT AUTHORIZED`
* `AUTHORIZED`

If authorized, identify the agent permitted to implement it.

---

### `REVIEW.md` — Evidence, Findings, and Adversarial Review

`REVIEW.md` records **what was examined, what was tested, what failed, what changed, and whether the phase actually satisfies its specification**.

It is not a replacement for `SPEC.md`.

The Codex Reviewer performs implementation-level review when implementation exists.

Claude performs the final architecture-compliance review.

It must contain, when applicable:

#### 1. Review target

* Phase number
* Spec version reviewed
* Implementation commit/diff reviewed
* Reviewer role

#### 2. Spec compliance

For each major requirement in `SPEC.md`, record:

* satisfied;
* partially satisfied;
* failed;
* not applicable.

#### 3. Invariant review

Verify relevant `INVARIANTS.md` rules individually.

Any invariant violation automatically blocks phase approval.

#### 4. Architecture compliance

Check whether implementation:

* respects approved boundaries;
* preserves dependency direction;
* avoids hidden coupling;
* avoids unauthorized architecture changes;
* stays within allowed scope.

#### 5. Edge-case review

Attempt to break the phase using relevant boundary conditions and abnormal inputs.

#### 6. Failure-path review

Test or inspect expected behavior for failures defined in `SPEC.md`.

#### 7. Test review

Record:

* tests added;
* tests executed;
* commands run;
* test results;
* missing coverage;
* suspicious or weak tests.

Passing tests alone do not imply approval.

#### 8. Diff review

Inspect the actual changed files.

Do not rely solely on the implementation agent's summary.

Check for:

* scope creep;
* unrelated edits;
* unnecessary dependencies;
* duplicated logic;
* dead code;
* shortcuts around abstractions;
* temporary hacks;
* sensitive-data logging;
* hardcoded secrets.

#### 9. Adversarial findings

List:

* bugs found;
* architectural weaknesses;
* security/privacy issues;
* failure cases not handled;
* regression risks;
* technical debt introduced;
* assumptions discovered.

#### 10. Required corrections

Every blocking issue must have:

* description;
* severity;
* required correction;
* responsible agent;
* status.

#### 11. Deferred issues

Non-blocking issues may be deferred only if:

* explicitly documented;
* impact is understood;
* deferment is approved.

#### 12. Architecture conflicts

If implementation reveals that the approved architecture must change:

`ARCHITECTURE ESCALATION REQUIRED`

Implementation must stop until Claude reviews the issue and human approval is obtained when necessary.

#### 13. Final review result

Use one of:

* `PASS`
* `PASS WITH APPROVED DEFERMENTS`
* `FAIL`
* `BLOCKED`

Include the reason.

---

### `STATUS.md` — Current Phase Gate

`STATUS.md` is a short operational file.

It answers only:

**Where is this phase right now, and who is allowed to act next?**

SPEC.md says what must be true; REVIEW.md proves whether it is true; STATUS.md says whether the project is allowed to move.

Do not turn `STATUS.md` into a design or review document.

It should contain:

#### Phase

* Phase number
* Phase name

#### Current state

Use one primary state such as:

* `PLANNING`
* `SPEC_IN_REVIEW`
* `BLOCKED_BUSINESS_INPUT`
* `BLOCKED_ARCHITECTURE`
* `READY_FOR_IMPLEMENTATION`
* `IMPLEMENTATION`
* `READY_FOR_CODE_REVIEW`
* `CODE_REVIEW`
* `READY_FOR_ARCHITECTURE_REVIEW`
* `ARCHITECTURE_REVIEW`
* `READY_FOR_HUMAN_APPROVAL`
* `APPROVED`
* `REJECTED`

#### Gates

Record:

* Spec approved: Yes/No
* Business blockers resolved: Yes/No/N/A
* Architecture approved: Yes/No
* Builder complete: Yes/No/N/A
* Codex Reviewer complete: Yes/No/N/A
* Claude review complete: Yes/No
* Human approval: Yes/No

#### Agent authorization

Explicitly state:

* Claude: authorized action
* Codex Builder: authorized / not authorized
* Codex Reviewer: authorized / not authorized

Only one implementation/review role should normally be active at a time.

#### Blocking issues

List only current blockers or write:

`None`

#### Next required action

Exactly one clear next action.

#### Next phase

State:

`NOT AUTHORIZED`

until the current phase receives explicit human approval.

---

## Phase Gate Rules

A phase may not advance only because code exists or tests pass.

The normal lifecycle is:

`SPEC → HUMAN ARCHITECTURE APPROVAL → IMPLEMENTATION → CODEX REVIEW → CLAUDE ARCHITECTURE REVIEW → HUMAN APPROVAL → NEXT PHASE`

For architecture-only phases, implementation and Codex steps may be marked `N/A`.

No agent may mark human approval as complete.

Only the human project owner may authorize progression to the next phase.

No agent may silently change an approved `SPEC.md`.

If implementation requires a material specification or architecture change:

1. Stop the affected work.
2. Record the conflict in `REVIEW.md`.
3. Mark `STATUS.md` as `BLOCKED_ARCHITECTURE`.
4. Escalate to Claude.
5. Revise the specification only after review.
6. Obtain human approval when the change is material.
7. Resume implementation only after authorization.

**Do not optimize for finishing quickly. Optimize for correctness, clarity, testability, and the smallest maintainable design. Do not proceed beyond this phase without my explicit approval.**