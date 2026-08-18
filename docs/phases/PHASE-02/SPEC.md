# PHASE-02 — Technical Skeleton

## 1. Phase identity

- Phase number: 02
- Phase name: Technical Skeleton
- Spec version: v1.1 — §12 clarified to name `uv.lock` as an allowed companion
  file to `pyproject.toml` (non-material clarification; rationale in
  `docs/phases/PHASE-02/REVIEW.md` §"uv.lock scope clarification"). Nothing
  else in v1 changed.

## 2. Objective

Implement the complete, business-logic-free technical skeleton of the pipeline
described in `docs/phases/PHASE-01/SPEC.md`: domain models, the rule-engine and
narrative/report-context interfaces, the state-transition validator, the
configuration schema for every deferred business surface, the `ReadinessGate`
fail-closed check, adapter interfaces with fake/in-memory implementations, and
the repository layout — so that later phases can plug in real rule content, real
prompts/templates, real recipients, and real infrastructure adapters without any
further architectural change.

This phase exists because PHASE-01 produced an approved architecture and 13
approved ADRs but zero code. Nothing here invents a business decision; every
placeholder and default traces directly to a specific SPEC.md §16 config point
or an approved ADR.

## 3. Scope

- Repository scaffolding per `docs/phases/PHASE-01/SPEC.md` §6.12.
- Domain layer: `RawFormSubmission`, `NormalizedApplication`, `Assessment`,
  `NarrativeContext`, `Narrative`, `Report` (internal/client), `Delivery`,
  `SubmissionState` as typed models (§6.3).
- `RuleEngine` interface + an empty/no-op ruleset registry (BR-1 placeholder,
  fails closed — no rule content).
- `NarrativeContext` builder (allow-list mechanism, §6.6) and the
  `MIN_NARRATIVE_CONTEXT_FIELDS` floor (ADR-012).
- `InternalReportContext` / `ClientReportContext` builders (allow-list
  mechanism, §6.7, empty client allow-list default per BR-4).
- State-transition validator (`is_valid_transition`, §9).
- Post-generation semantic validator interface (§6.8) with the deny-list
  mechanism implemented generically (empty deny-list content, since real
  categories are content, not structure).
- Configuration schema for every §16.2 config point (`RuleSet`,
  `FormSchemaMapping`, `ClientReportAllowlist`, `RecipientRouting`,
  `PromptTemplate`, `ReportTemplate`, `AlertChannel`, `RetentionPolicy`,
  `RetryPolicy`, `LLMProviderConfig`), each carrying `approved_for_production`.
- `ReadinessGate` (§6.13): per-stage fail-closed check, with `reason_code`s
  matching `docs/phases/PHASE-01/SPEC.md` §10/§16.
- Adapter **interfaces** (Protocols/ABCs) for `LLMProvider`, `ReportRenderer`,
  `EmailSender`, `SubmissionRepository` (+ per-entity repositories), inbound
  form-payload parsing — each with a fake/in-memory or null implementation
  sufficient for tests (ADR-004's `NullLLMProvider`/template-only fallback,
  ADR-012's deterministic fallback narrative).
- Webhook receiver (`api/`) and worker (`workflows/`) wired against the
  interfaces above — validate → persist → enqueue → claim → execute-one-stage,
  per §6.2/§9.
- `main.py` becomes a thin entrypoint wiring the API layer, per §6.12.
- Test suite: unit tests for the domain layer, readiness-gate tests (one per
  config point), and workflow tests using the fakes (full lifecycle, duplicate
  submission, simulated crash-and-resume).

## 4. Out of scope

- Any real business content: rule thresholds/flags (BR-1), Form field mapping
  (BR-2), narrative/report copy (BR-3), client allow-list content (BR-4),
  recipients (BR-5), retention period (BR-6), confirmed SLA numbers (BR-7),
  alert destination (BR-8), LLM vendor/model (BR-9).
- Real infrastructure wiring: an actual Cloud SQL connection, actual Cloud Tasks
  queue, actual Gmail API calls, actual LLM provider calls, actual Secret
  Manager access. ADR-000/001/002/006/009 are approved *directions*; standing up
  the real services and credentials is provisioning/ops work this phase does not
  attempt, and none of it is required to build or test the skeleton (everything
  here is tested against fakes/in-memory implementations).
- Integration and end-to-end tests against real external services (SPEC.md
  PHASE-01 §15's integration/contract/e2e tiers) — only the unit/workflow tier
  runs in this phase, against fakes. Real-adapter contract tests are written
  alongside the real adapter in the phase that implements it.
- Proactive Form-drift polling (explicitly deferred to a fast-follow by
  ADR-008).
- Any change to `docs/PROMPT.md`, `docs/INVARIANTS.md`, `docs/agents/*.md`, or
  the PHASE-01 files.

## 5. Dependencies

- Previous approved phases: PHASE-01 (`SPEC.md` v3, `REVIEW.md`, all 13 ADRs) —
  approved.
- Required architectural decisions: all resolved as PROPOSED-and-approved ADRs
  (`docs/architecture/ADR-000` through `ADR-012`).
- Required business inputs: none — this is precisely what PHASE-01 §16
  established as implementation-safe-to-defer.
- Required external services/interfaces: none for the skeleton itself (fakes
  only). Real GCP project/credentials are a dependency of a *future* phase, not
  this one.

## 6. Relevant architecture

Directly implements `docs/phases/PHASE-01/SPEC.md` §6 (all subsections), §9,
§10 (as fail-closed reason codes, not real recovery automation), and §6.13. No
architectural change is introduced; this phase is the literal construction of
what PHASE-01 specified. Where PHASE-01 named an interface, this phase defines
it in code with a fake implementation; where PHASE-01 named a config point, this
phase defines its schema and its `ReadinessGate` check, with content left empty/
placeholder.

Concrete stage-to-code mapping (worker path, §9.1):

| Stage | Domain function (pure) | Adapter used (fake in this phase) |
|---|---|---|
| `RECEIVED` → `NORMALIZED` | `normalize(raw, schema_mapping)` | `FormSchemaMapping` lookup — absent ⇒ fail closed |
| `NORMALIZED` → `CLASSIFIED` | `RuleEngine.classify(application)` | Ruleset registry — empty ⇒ fail closed |
| `CLASSIFIED` → `NARRATIVE_READY` | `build_narrative_context`, `validate_narrative` | `LLMProvider` — `NullLLMProvider`/fallback per ADR-012 |
| `NARRATIVE_READY` → `REPORTS_READY` | `build_internal_report_context`, `build_client_report_context` | `ReportRenderer` — fake/no-op renderer |
| `REPORTS_READY` → `COMPLETED` | per-recipient claim | `EmailSender` — fake/no-op sender recording calls |

## 7. Data contracts

All entities and their required/optional fields are exactly as defined in
`docs/phases/PHASE-01/SPEC.md` §6.3 and §7 — this phase does not alter any data
contract, it implements them as typed models (dataclasses or Pydantic models,
Codex Builder's choice, consistent within the codebase). Validation/error
behavior for each (missing required field, malformed payload, etc.) must match
§7 and §10 exactly, including `reason_code` naming used by tests.

## 8. Invariants

All 15 invariants in `docs/INVARIANTS.md` apply. This phase is where several
become testable claims for the first time:

- INVARIANT 1/2 (at-most-once, no duplicate delivery): the compare-and-swap
  claim (§9) and per-recipient `Delivery` model must be implemented exactly as
  specified — this is the first point at which these invariants can be violated
  by a bug, so `docs/phases/PHASE-02/REVIEW.md` must verify them with an actual
  concurrent-claim test, not just a code read.
- INVARIANT 3/9 (LLM never decides classification): verify by construction — the
  `LLMProvider` interface's return type must have no field that a caller could
  route into `Assessment`, and `grep`-level verification that no such path exists
  is required in review.
- INVARIANT 4 (client reports exclude internal metadata): verify the default
  empty `ClientReportAllowlist` actually produces a `ClientReportContext`
  containing only narrative + qualification label, nothing else, by test.
- INVARIANT 7 (raw submissions immutable): verify no `UPDATE`/mutation method
  exists on the `RawFormSubmission` repository interface — only `insert`/`get`.
- INVARIANT 12/13 (secrets/sensitive data never logged): verify by test — assert
  that no test fixture's synthetic PII string appears in any captured log output
  across the full workflow test.
- INVARIANT 14 (no email before artifact exists): verify by test — attempt to
  force a delivery-stage claim while `REPORTS_READY` has not been reached and
  assert it is rejected by the state-transition validator.
- INVARIANT 15 (reconstructable from stored metadata): verify by test — run a
  synthetic submission through to `COMPLETED`, then assert every stage's output
  (including `rule_version`, `prompt_version`, `template_version`) is
  independently retrievable from the (fake) persistence layer.
- All other invariants apply as previously documented; this phase does not
  weaken any of them.

## 9. State behavior

Implements `docs/phases/PHASE-01/SPEC.md` §9 exactly: the 6 success states, one
failure sibling per stage, and the terminal states (`COMPLETED`,
`REJECTED_DUPLICATE`, `REJECTED_INVALID`, `FAILED_PERMANENT`). The
transition-validator function is the single source of truth for legality — no
stage-execution code may transition `SubmissionState.status` without going
through it. Retry behavior uses the ADR-011 placeholder (5 attempts, exponential
backoff) — implemented, tested, and explicitly labeled non-final in code
comments/config, consistent with ADR-011's status.

## 10. Failure behavior

Every fail-closed case defined in `docs/phases/PHASE-01/SPEC.md` §10 and §16.2
must be implemented with its exact `reason_code`:

`RULES_NOT_CONFIGURED`, `SCHEMA_NOT_CONFIGURED`, `LLM_PROVIDER_NOT_CONFIGURED`,
`RECIPIENTS_NOT_CONFIGURED`, plus the `DRAFT-UNAPPROVED`/`approved_for_production`
gate for prompt/template/allowlist versions (§16.2 BR-3/BR-4). Each must:

- Never block `RECEIVED` (raw-submission persistence) — tested explicitly per
  §6.13.
- Transition to the correct stage-specific `*_FAILED` state, non-retryable-
  until-configured, per §9.2.
- Fire through whatever `AlertChannel` is configured (the fake in this phase) —
  or, if none is configured at all under a simulated `ENV=production`, surface
  as a startup-time failure per §6.13, not a silent no-op.

`docs/phases/PHASE-01/SPEC.md` §10's transient-failure rows (LLM timeout, PDF
render failure, Gmail failure, queue retry, persistence failure, Cloud Run
restart/deployment) are exercised via the fakes' ability to simulate a failure
on command (e.g. `FakeLLMProvider.fail_next_call()`), proving the retry/resume
mechanics work — not by inducing real infrastructure failures, which require
real infrastructure this phase doesn't stand up.

## 11. Security and privacy requirements

- All test fixtures use clearly synthetic data (e.g. `test-applicant-001`, never
  realistic-looking names/addresses/health data) to avoid any ambiguity about
  whether a log line or fixture file contains real PII.
- Logging discipline (§11 of PHASE-01 SPEC) is implemented now, not deferred:
  structured event emission (§6.11) must never include full model dumps of
  `RawFormSubmission`, `NormalizedApplication`, `NarrativeContext`, or rendered
  report bytes — only the fields §6.11 names.
- No secret material exists in this phase (no real credentials are configured),
  so INVARIANT 12 is enforced structurally by the config schema requiring
  secrets to come from an injected `SecretProvider` interface (faked in tests),
  never a literal in code or config files — verified by review, not just by
  absence of a `.env` file.

## 12. Allowed implementation surface

Per the repository structure in `docs/phases/PHASE-01/SPEC.md` §6.12:

```
src/api/            (new)
src/domain/          (new)
src/workflows/        (new)
src/persistence/       (new — interfaces + in-memory implementation only)
src/adapters/llm/        (new — interface + Null/fake + ADR-012 fallback only)
src/adapters/pdf/         (new — interface + no-op fake only)
src/adapters/gmail/        (new — interface + no-op fake only)
src/adapters/forms/         (new — inbound payload parsing)
src/templates/                (new — placeholder DRAFT-UNAPPROVED templates only)
src/config/                    (new — schema + ReadinessGate)
tests/unit/                     (new)
tests/workflow/                  (new)
main.py                           (may be modified — thin entrypoint only)
pyproject.toml                     (may be modified — add dependencies only)
uv.lock                             (companion-only — see note below)
```

`uv.lock` is a generated lockfile that `uv run`/`uv sync` update automatically
whenever `pyproject.toml`'s declared dependencies change. It may change only
as that automatic, mechanical consequence of an approved `pyproject.toml`
edit — never for an unrelated reason, and never hand-edited. It is not a
meaningful scope expansion: forbidding it while allowing `pyproject.toml`
dependency changes produces a self-contradictory requirement (the moment
anyone actually runs the test suite via `uv run`, the lockfile is regenerated
regardless). See `docs/phases/PHASE-02/REVIEW.md` for how this was
discovered.

No other file or directory may be created or modified without a scope
escalation per `docs/PROMPT.md`'s phase gate rules.

## 13. Prohibited changes

- No real business content of any kind (see §4).
- No real external-service SDK calls (Cloud SQL, Cloud Tasks, Gmail API, any
  LLM API, Secret Manager) — interfaces and fakes only.
- No modification to `docs/PROMPT.md`, `docs/INVARIANTS.md`,
  `docs/agents/*.md`, `docs/phases/PHASE-01/*`, or any file under
  `docs/architecture/`.
- No expansion of scope beyond §12 without stopping and escalating per
  `docs/PROMPT.md`'s "If implementation requires a material specification or
  architecture change" procedure.
- No test that depends on network access or real credentials.

## 14. Acceptance criteria

1. Every domain entity, interface, and config schema in §3 exists, typed, and
   is importable with zero network/credential dependency.
2. `RuleEngine` with an empty ruleset registry produces `RULES_NOT_CONFIGURED`,
   not a crash and not a silent default classification.
3. `ReadinessGate` has a passing/failing test for every config point in
   PHASE-01 SPEC.md §16.2, and a test proving ingestion (`RECEIVED`) is
   unaffected by any of them being unconfigured.
4. A full synthetic submission (fake data, fake adapters) traverses
   `RECEIVED → NORMALIZED → CLASSIFIED → NARRATIVE_READY → REPORTS_READY →
   COMPLETED`, with every stage's output independently queryable afterward
   (INVARIANT 15 check).
5. A duplicate submission (same synthetic `response_id`) is rejected as
   `REJECTED_DUPLICATE` without re-running any stage or re-invoking any fake
   adapter a second time.
6. A simulated crash-and-resume (worker invocation interrupted after a stage
   commits, before the next is claimed) resumes correctly from persisted state
   without re-executing the completed stage.
7. `ClientReportContext` built with the default empty allow-list contains only
   narrative text and qualification label — verified by test, not by code
   inspection alone.
8. No test fixture's synthetic PII string appears in captured log output.
9. `main.py` runs the webhook receiver against the fakes end-to-end locally
   (documented run instructions), without requiring any real credentials.
10. All tests in §15 pass; Codex Reviewer's adversarial pass finds no invariant
    violation.

## 15. Required tests

- **Unit tests**: every pure domain function (`RuleEngine.classify` with 0 and
  with a trivial synthetic test-only rule; `is_valid_transition` including every
  invalid transition named in PHASE-01 SPEC.md §9.2; `build_narrative_context`
  allow-list enforcement; `build_client_report_context` /
  `build_internal_report_context` allow-list enforcement; ADR-012's
  minimum-context-floor fallback trigger).
- **Readiness-gate tests**: one per PHASE-01 SPEC.md §16.2 config point (see
  Acceptance Criteria #3), plus the ingestion-not-blocked test.
- **Contract tests**: each fake adapter (`NullLLMProvider`, no-op
  `ReportRenderer`, no-op `EmailSender`, in-memory repositories) verified
  against its interface's declared contract, so a later real adapter can be
  swapped in with confidence the interface itself was exercised correctly.
- **Workflow tests**: full lifecycle (Acceptance Criteria #4), duplicate
  submission (#5), crash-and-resume (#6), and one test per PHASE-01 SPEC.md §10
  failure-matrix row that this phase can meaningfully simulate with fakes
  (excludes rows that require real infrastructure, e.g. actual Cloud Run
  restart — those are validated architecturally, not by test, until real
  infrastructure exists).
- **Regression tests**: none yet (first implementation phase).

## 16. Business decisions required

None block this phase. All ten items from PHASE-01 SPEC.md §16 remain
`BUSINESS INPUT REQUIRED` for their real content/values; none are needed to
build or test the skeleton, per the reclassification already approved in
PHASE-01.

## 17. Architectural questions

None open for this phase — all resolved as approved ADRs in PHASE-01. If
implementation surfaces a genuine new architectural question not covered by an
existing ADR, Codex Builder must stop and escalate per `docs/PROMPT.md`, not
resolve it silently.

## 18. Implementation authorization

`NOT AUTHORIZED`.

Pending human approval of this SPEC. Once approved: **Codex Builder** is
authorized to implement strictly within §12's surface; **Codex Reviewer**
performs the adversarial review; Claude performs the final architecture-
compliance review. Claude does not implement this phase directly, per the
project's agent workflow (`docs/agents/CLAUDE.md`, `docs/PROMPT.md`).
