# PHASE-01 — Architecture Foundation

## 1. Phase identity

- Phase number: 01
- Phase name: Architecture Foundation
- Spec version: v3 — v2 (business-item reclassification, §6.13/§16) plus §17
  architectural questions now each resolved to a PROPOSED ADR under
  `docs/architecture/` (ADR-000 through ADR-012), pending human approval. No ADR
  has been implemented; nothing here authorizes code.

## 2. Objective

Define the minimum production-safe architecture for the Google Forms → insurance
report generator: domain boundaries, invariants enforcement, data lifecycle,
processing state machine, idempotency strategy, persistence model, failure handling,
LLM/classification boundaries, and repository structure.

This phase exists because the repository currently contains no architecture — only a
placeholder `main.py`. No design decision may be made implicitly during
implementation; this document is that decision record. No implementation code is
written in this phase.

## 3. Scope

- Domain model for the submission → report → delivery lifecycle.
- Processing state machine (states, transitions, retry/terminal semantics).
- Idempotency strategy for webhook delivery, worker retries, LLM/PDF/email retries.
- Persistence model (what is stored, not a specific schema/DDL).
- Async execution boundary (webhook vs. worker).
- Deterministic classification engine contract (interface + versioning, not rule
  content).
- LLM boundary: `NarrativeContext`, prohibited LLM behaviors, post-generation
  semantic validation.
- Information boundary: `InternalReportContext` vs `ClientReportContext`.
- Provider strategy (interface + v1 provider recommendation).
- Versioning strategy (form schema, rules, prompts, templates, releases).
- Observability event/metric design (structure only, no sensitive payloads).
- Test architecture (test types and what each must cover).
- ADR backlog required before implementation.
- Proposed repository structure.

## 4. Out of scope

- Any application code, including `main.py`.
- Actual underwriting/classification rule content (Quirón business logic).
- Actual report copy, branding, or legal/disclaimer language.
- Concrete infrastructure provisioning (Terraform, service creation, IAM bindings).
- Selecting a specific LLM vendor/model, Gmail sending identity, or PDF library —
  these are named as ADRs to resolve, not resolved here.
- Codex Builder / Codex Reviewer activity of any kind.

## 5. Dependencies

- Previous approved phases: none — this is the first phase.
- Required architectural decisions: the ADR backlog in §9 of this document must be
  resolved (at least provisionally) before implementation can begin; unresolved ADRs
  block `READY_FOR_IMPLEMENTATION`.
- Required business inputs: see §16.
- Required external services/interfaces (assumed, not yet confirmed — see
  Architectural Questions): Google Forms, an LLM provider, a PDF rendering
  mechanism, Gmail (send), a durable datastore, a task queue, a secrets manager, and
  a compute host with restart/redeploy semantics (the prompt's mention of "Cloud Run
  restart" is treated as a strong signal, not yet a confirmed decision — see AQ-1).

## 6. Relevant architecture

### 6.1 Domain boundaries

**Pure / deterministic (domain layer — no I/O, no network, no wall-clock
dependency beyond explicit timestamps passed in):**

- `NormalizedApplication` construction from `RawFormSubmission` (a pure mapping
  function parameterized by a form-schema version).
- The classification/rule engine: `NormalizedApplication → Assessment`.
- `NarrativeContext` construction: `Assessment + NormalizedApplication (allow-listed
  subset) → NarrativeContext`. Building the context is pure; calling the LLM is not.
- `ClientReportContext` / `InternalReportContext` construction from `Assessment` +
  `Narrative` (allow-list projection, pure).
- State machine transition validation (`is_valid_transition(from, to) -> bool`).
- Post-generation semantic validation of LLM output (pure — it is a check against
  already-known facts, not a network call).

**Infrastructure / third-party (adapters — impure, replaceable, mockable):**

- Inbound webhook/transport (receiving the Google Forms event).
- Persistence (repository implementations).
- Queue/task dispatch.
- LLM provider adapter (network call).
- PDF rendering adapter (I/O: template render → bytes).
- Gmail send adapter (network call).
- Secrets access.

The domain layer must be importable and testable with zero network access and zero
credentials. This is the architectural line implementation must not cross: no
adapter logic embedded in domain functions, no domain decisions embedded in
adapters.

### 6.2 Data flow (revised)

```
Google Form submit
      │
      ▼
[Webhook receiver] ──validate shape, compute idempotency key──▶ [Persist RawFormSubmission]
      │                                                                 │
      │ (return 2xx fast — no pipeline work happens inline)             │
      ▼                                                                 ▼
  HTTP response                                              [Enqueue processing task]
                                                                         │
                                                                         ▼
                                                          ┌─────────────────────────────┐
                                                          │           Worker            │
                                                          │  (idempotent, resumable,     │
                                                          │   driven off persisted state)│
                                                          └─────────────────────────────┘
                                                                         │
                              ┌───────────────┬───────────────┬─────────┼───────────┬──────────────┐
                              ▼               ▼               ▼         ▼           ▼              ▼
                        Normalize      Classify        Build Narrative  Render     Send Client   Send Internal
                        (pure)         (pure, rule      Context (pure)  Reports    Report Email  Report Email
                                        engine)              │          (PDF x2)   (Gmail)       (Gmail)
                                                              ▼
                                                        Call LLM provider
                                                        (impure) → validate
                                                        JSON schema + semantic
                                                        grounding (pure check)
```

Every arrow after "Enqueue processing task" is a **resumable stage**, not a single
transaction. A crash between any two stages must leave the system able to resume
from the last persisted state without re-executing completed stages or re-sending
anything already sent (see §9, §10).

### 6.3 Domain model

| Entity | Mutability | Created by | Key fields (representative, not exhaustive) |
|---|---|---|---|
| `RawFormSubmission` | Immutable once written | Webhook receiver | `submission_id` (internal UUID), `form_id`, `response_id` (Google's ID — dedup key), `received_at`, `raw_payload` (as received), `form_schema_version_at_receipt` |
| `NormalizedApplication` | Immutable once written | Normalization stage | `submission_id`, `form_schema_version`, typed/mapped fields, `normalization_warnings[]` |
| `Assessment` | Immutable once written | Classification stage | `submission_id`, `rule_version`, `rules_evaluated[]`, `rules_triggered[]`, `reasons[]`, `qualification`, `classified_at` |
| `NarrativeContext` | Immutable, derived | Narrative stage (pre-LLM) | allow-listed fields only — see §6.6 |
| `Narrative` | Immutable once written (new row on regeneration, never overwritten) | Narrative stage (post-LLM) | `submission_id`, `attempt_number`, `provider`, `model`, `prompt_version`, `raw_output`, `validation_result`, `text` |
| `Report` (Internal, Client) | Immutable once written | Report stage | `submission_id`, `report_type`, `template_version`, `artifact_ref` (storage pointer), `generated_at` |
| `Delivery` | Append-only, one row **per recipient** | Delivery stage | `submission_id`, `report_type`, `recipient`, `message_id`, `status`, `attempted_at`, `sent_at` |
| `SubmissionState` | Mutable (the only mutable row) | Webhook receiver, updated by worker | `submission_id`, `status`, `attempt_counts{}`, `last_error`, `updated_at` |

All entities except `SubmissionState` are append-only/immutable — this directly
implements INVARIANT 7 (raw submissions immutable) and generalizes it to every
downstream artifact, which is what makes INVARIANT 15 (reconstructable from stored
metadata) achievable: nothing is ever overwritten, so the exact inputs and versions
behind any historical report are always recoverable.

### 6.4 Interfaces/contracts affected

- `RuleEngine.classify(application: NormalizedApplication) -> Assessment` — pure,
  synchronous, no I/O.
- `LLMProvider.generate_narrative(context: NarrativeContext, prompt_version: str) ->
  NarrativeResult` — the only interface allowed to reach an LLM.
- `NarrativeValidator.validate(result: NarrativeResult, context: NarrativeContext,
  assessment: Assessment) -> ValidationOutcome` — pure, runs after every LLM call,
  before a narrative is accepted.
- `ReportRenderer.render(context: InternalReportContext | ClientReportContext,
  template_version: str) -> bytes`.
- `EmailSender.send(report: Report, recipient: str, idempotency_ref: str) ->
  DeliveryResult`.
- `SubmissionRepository` / stage-specific repositories — persistence access is only
  ever through repository interfaces, never raw client calls from workflow code.

### 6.5 Classification engine

`RuleEngine.classify(application) -> Assessment` is a pure function over versioned
rule definitions. Each individual rule is itself a pure function:
`rule(application) -> RuleResult{code, triggered: bool, reason}`. `classify()` runs
every rule for the active `rule_version`, collects `rules_evaluated` (all of them)
and `rules_triggered` (the subset where `triggered=True`), and derives
`qualification` from the triggered set via a versioned, equally deterministic
mapping (triggered-rule-codes → qualification). No rule content is defined here —
see BR-1. The architectural commitment is only: rules are code or declarative
config (not LLM prompts), every rule fires independently and is individually
inspectable, and `rule_version` is bumped on any change to rule logic or the
triggered→qualification mapping (ADR-010 covers *how* the version bump is enforced,
e.g. a content hash check in CI).

### 6.6 LLM boundary — `NarrativeContext`

`NarrativeContext` is built by one function with a narrow signature:
`build_narrative_context(application: NormalizedApplication, assessment: Assessment)
-> NarrativeContext`. It may only read an explicit allow-list of fields from each
input — not "everything except denied fields." Concretely it contains:

- A small set of non-sensitive identifying fields needed for tone/greeting (exact
  set is BR-3/BR-4, but architecturally: no free-text medical answers pass through
  verbatim unless a business decision explicitly allow-lists a specific field for
  narrative use).
- `assessment.reasons[]` and `assessment.qualification` — already deterministic,
  safe to narrate.
- `assessment.rule_version`, for prompt/version traceability (not for the model to
  reason about — it does not change what the model is told to conclude).

The LLM interface (`LLMProvider.generate_narrative`) has **no write path** to
`Assessment`, `rules_triggered`, or `qualification` — those are function inputs to
the prompt, not outputs the model can alter. This is what makes INVARIANT 3
structurally true rather than merely a prompt instruction: even a fully
prompt-injected model response cannot reach the classification, because the code
path from `NarrativeResult` back into `Assessment` does not exist.

### 6.7 Information boundaries

`InternalReportContext` is a superset assembled from `Assessment` (full detail:
`rules_triggered`, `reasons`, `rule_version`), `NormalizedApplication`, `Narrative`,
and submission metadata (provider/model, timestamps). `ClientReportContext` is
**not** derived by redacting fields from `InternalReportContext`. It is built by a
separate function that only ever reads an explicit allow-list: applicant-facing
fields, the narrative text, and the qualification outcome in whatever client-safe
phrasing BR-3 defines. It structurally cannot include `rules_triggered`,
`rule_version`, or provider/model names, because those fields are never in scope of
the function that builds it. Allow-list-by-construction is chosen over
deny-list-by-redaction specifically because a deny list silently leaks any new
internal field added later that a developer forgets to redact; an allow list
silently omits it instead — the safe failure direction (INVARIANT 4).

### 6.8 Post-generation semantic validation

Schema/JSON validation (does the LLM response parse into the expected structured
shape) is necessary but not sufficient — it cannot catch a well-formed narrative
that states something ungrounded. A second, deterministic pass runs after schema
validation and before a `Narrative` is accepted:

- **Qualification-consistency check**: the narrative must not state or imply a
  qualification/outcome different from `assessment.qualification` (e.g. simple
  keyword/phrase checks tied to the known qualification vocabulary — this does not
  require another LLM call).
- **Grounding check**: flag narratives that introduce specific claims (numbers,
  named conditions, dates) not present in `NarrativeContext`. A precise generic
  fact-checker is out of scope for v1 (see REVIEW.md — flagged as a known
  limitation, not solved); the minimum viable version is a deny-list of
  categories that must never appear unless sourced from `NarrativeContext`
  (specific diagnoses, monetary amounts, dates, named third parties).
- Any failure here is treated as a **validation failure**, not a transient error —
  it does not retry the same prompt expecting a different result indefinitely; see
  §10 "Hallucinated information" row.

### 6.9 Provider strategy

Define one interface, `LLMProvider`, with `generate_narrative(context,
prompt_version) -> NarrativeResult`. **v1 recommendation: exactly one concrete
provider adapter.** A multi-provider abstraction is easy to design and expensive to
actually validate (prompt behavior, structured-output reliability, and semantic
validation would all need re-proving per provider); building it before there is a
proven need is exactly the kind of overengineering this phase is asked to avoid.
The interface exists so a provider swap later is a new adapter, not an architecture
change — it does not imply v1 ships with more than one. Which provider is BR-9.

### 6.10 Versioning

Five independent version axes, each stored on the record it governs so any
historical artifact is reconstructable (INVARIANT 15):

- `form_schema_version` — on `RawFormSubmission`/`NormalizedApplication`.
- `rule_version` — on `Assessment`.
- `prompt_version` — on `Narrative`.
- `template_version` — on `Report`.
- Application release version (git SHA or semver) — on the `SubmissionState` or
  logged per stage transition, for correlating behavior with a deployed build.

These are independent on purpose: a prompt change must not require a rule-version
bump, and vice versa — coupling them would force unrelated re-approvals.

### 6.11 Observability

Structured events (no sensitive payloads — see §11): `submission_received`,
`submission_deduplicated`, `stage_transition{from, to, duration_ms}`,
`classification_completed{rule_version, qualification, rules_triggered_count}`,
`narrative_generated{provider, model, prompt_version, latency_ms,
validation_result}`, `report_generated{report_type, template_version}`,
`delivery_attempted{recipient_ref, attempt}`, `delivery_succeeded`/
`delivery_failed{reason_code}`, `retry_exhausted{stage}`.

Metrics derived from these events answer exactly the questions §14 of
`docs/PROMPT.md` requires: submissions received vs. completed (funnel from
`submission_received` to `stage_transition{to=COMPLETED}`), failure location
(`stage_transition{to=*_FAILED}` grouped by stage), provider/model in use
(`narrative_generated`), per-stage latency (`duration_ms`), duplicate detection
(`submission_deduplicated` count), and delivery retries
(`delivery_attempted{attempt>1}`).

### 6.12 Proposed repository structure

Informational for this phase (no files created). For a future implementation
phase to scope against:

```
src/
  api/            # webhook transport: request validation, idempotency-key
                   # extraction, enqueue. No business logic.
  domain/          # pure: models, RuleEngine, NarrativeContext builder,
                   # report-context builders, state-transition validator,
                   # semantic validator. Zero I/O, zero network imports.
  workflows/        # application layer: orchestrates domain + adapters per
                   # stage; owns the compare-and-swap claim logic.
  persistence/      # repository implementations (one per entity in §6.3),
                   # datastore client setup, migrations.
  adapters/
    llm/             # LLMProvider implementation(s)
    pdf/             # ReportRenderer implementation
    gmail/            # EmailSender implementation
    forms/           # inbound Google Forms payload parsing
  templates/        # report templates (client/, internal/), versioned
  config/           # settings, versioned rule configs, prompt configs,
                   # form-schema mapping definitions
tests/
  unit/
  integration/
  contract/
  workflow/
  e2e/
docs/
  architecture/     # ADRs
  phases/
main.py             # thin entrypoint only
```

Dependency direction: `api` and `adapters` depend on `domain`; `domain` depends on
nothing else in this tree. `workflows` is the only layer allowed to import both
`domain` and `adapters` together.

### 6.13 Configuration surface and fail-closed validation

Every business decision deferred in §16 is deferred *only because* it has a
concrete, versioned configuration point defined here — none are deferred by
leaving a gap. Two mechanisms make deferral safe:

**A. Config-point contract.** Each deferred business surface is a named,
versioned configuration object (a `RuleSet`, a `FormSchemaMapping`, a
`ClientReportAllowlist`, a `RecipientRouting`, a `PromptTemplate`, a
`ReportTemplate`, an `AlertChannel`, a `RetentionPolicy`, a `RetryPolicy`, an
`LLMProviderConfig`). Each carries an explicit `approved_for_production: bool`
flag set by whoever supplies the real value — the system never infers approval
from "a value is present." A populated-but-unapproved config point behaves
identically to an absent one.

**B. `ReadinessGate` — stage-level fail-closed check, not app-wide.** Before a
worker executes a given pipeline stage, it checks that stage's required config
points are present *and* `approved_for_production=true` whenever
`ENV=production`. If not, the stage refuses to run: it transitions the
submission to that stage's `*_FAILED` state with `reason_code` naming the exact
missing config point (e.g. `RULES_NOT_CONFIGURED`, `LLM_PROVIDER_NOT_CONFIGURED`,
`RECIPIENTS_NOT_CONFIGURED`), marks it non-retryable-until-configured, and raises
an alert (via whatever `AlertChannel` *is* configured — if even that is missing,
this is the one case that also fails app startup, since a production deployment
with no alert path at all cannot safely fail closed anywhere else).

This check is deliberately **per-stage, not a single startup gate on the whole
service**, for one load-bearing reason: `RECEIVED` (accept + durably persist the
raw submission) must keep working even when every downstream config point is
missing. Blocking ingestion on unrelated missing config would violate INVARIANT 11
(external/config failure cannot cause data loss) — a submission with no rule set
configured yet must still be safely captured, not rejected. Fail-closed applies to
*producing an outcome*, never to *accepting and durably storing input*.

In non-production environments (`ENV != production`), missing config points use
their documented safe placeholder (§16) so local/dev/staging work end-to-end
without real business data — but the placeholder's identity is always visible in
output (e.g. a rule_version literally named `unconfigured-dev-only`) so a
placeholder-produced artifact can never be mistaken for a real one, including in
existing test fixtures or accidentally-exported staging data.

## 7. Data contracts

### 7.1 `RawFormSubmission` (input to the system)

- Required: `form_id`, `response_id`, `received_at`, `raw_payload`.
- Validation: reject (do not persist as valid) if `response_id` or `form_id` is
  missing, or `raw_payload` is not parseable — see Failure Behavior §10 for what
  "reject" means operationally.
- Optional: none at this stage — this is the raw envelope, not the business data.

### 7.2 `NormalizedApplication` (output of normalization)

- Required fields: determined by the form-schema version's mapping definition
  (BUSINESS INPUT REQUIRED for which Google Form fields exist and which are
  mandatory — see §16).
- Missing **required** field → `NORMALIZATION_FAILED`, non-retryable without a
  schema/mapping fix (see §10).
- Missing **optional** field → recorded in `normalization_warnings[]`, processing
  continues.
- Error behavior: normalization must fail loudly and specifically (name the missing
  field), never silently substitute a default for a required business field.

### 7.3 `Assessment` (output of classification)

- Required: `rule_version`, `rules_evaluated[]`, `rules_triggered[]`, `reasons[]`,
  `qualification`.
- Must be fully derivable from `NormalizedApplication` + the named `rule_version`
  alone — no hidden inputs, no LLM involvement (INVARIANT 3, INVARIANT 6).

### 7.4 `NarrativeContext` (input to the LLM — see §6.6 for the allow-list)

- Every field must trace to either `NormalizedApplication` (allow-listed subset) or
  `Assessment` (reasons/qualification, already deterministic).
- No field may originate from anywhere else. This is enforced by construction (the
  builder function's signature only accepts these two sources), not by convention.

### 7.5 `InternalReportContext` / `ClientReportContext`

- `ClientReportContext` is built via an explicit **allow-list** projection, not by
  redacting from `InternalReportContext`. See §6.7.

## 8. Invariants

All 15 invariants in `docs/INVARIANTS.md` apply to this phase; this phase's job is
to establish the structures that make each one enforceable. Direct mapping:

| Invariant | Architectural mechanism |
|---|---|
| 1. At-most-once logical processing | Stage-level compare-and-swap claims on `SubmissionState.status` (§9, §10) |
| 2. Retry never duplicates delivery | Per-recipient `Delivery` records + pre-send state claim (§10, delivery failure row) |
| 3. LLM never decides/modifies classification | `Assessment` is finalized before `NarrativeContext` is built; the LLM interface has no write path to `Assessment` |
| 4. Client reports exclude internal metadata | Allow-list `ClientReportContext` builder (§6.7) |
| 5. Internal reports may include client-facing info | `InternalReportContext` is a superset by construction |
| 6. Classification explainable by triggered rules | `Assessment.rules_triggered[]` + `reasons[]` always populated |
| 7. Raw submissions immutable | No update path exists on `RawFormSubmission` — insert-only |
| 8. Rule changes require new rule version | `rule_version` is a required field on every `Assessment`; CI must reject an `Assessment`-producing change that doesn't bump it (ADR-010) |
| 9. Model/provider changes can't alter classification | Classification happens before the LLM is ever called; the LLM has no path back into `Assessment` |
| 10. No unsupported facts in reports | `NarrativeContext` allow-list (source-of-truth boundary) + post-generation semantic validation (§6.8) |
| 11. External failure ≠ data loss | `RawFormSubmission` persisted durably before any external call is made (§11 async execution) |
| 12. Secrets never committed/logged | Secrets manager only; no secret values in structured events (§13) |
| 13. Sensitive form data never logged | Structured events carry IDs/enums/durations only, never raw answers (§13) |
| 14. No email before artifact exists | State machine forbids `DELIVERY_*` states before `REPORT_READY` (§9) |
| 15. Reconstructable from stored metadata | Append-only entities + version fields on every stage (§6.3) |

## 9. State behavior

### 9.1 States

Deliberately coarse — one state per stage outcome, not per sub-step — to avoid
over-modeling. Per-attempt detail lives in `attempt_counts`/`last_error` fields, not
in additional states.

```
RECEIVED
  → NORMALIZED
  → CLASSIFIED
  → NARRATIVE_READY
  → REPORTS_READY
  → COMPLETED   (terminal — all required deliveries sent)

Failure siblings (one per stage, entered instead of the success state):
  NORMALIZATION_FAILED
  CLASSIFICATION_FAILED     (should be unreachable in practice — see REVIEW.md AF-1)
  NARRATIVE_FAILED
  REPORT_FAILED
  DELIVERY_FAILED

Other terminal states:
  REJECTED_DUPLICATE        (short-circuited at ingestion, not a failure)
  REJECTED_INVALID          (malformed payload, never entered the pipeline)
  FAILED_PERMANENT          (retry budget exhausted on any *_FAILED state — requires
                             human intervention)
```

### 9.2 Transition table

| From | To (success) | To (failure) | Retryable in place? |
|---|---|---|---|
| (none) | `RECEIVED` | `REJECTED_INVALID` / `REJECTED_DUPLICATE` | n/a — ingestion-time decision |
| `RECEIVED` | `NORMALIZED` | `NORMALIZATION_FAILED` | Yes, if retry is a code/mapping fix; no, if it's the same bad payload replayed unchanged |
| `NORMALIZED` | `CLASSIFIED` | `CLASSIFICATION_FAILED` | Yes (should always succeed given valid `NormalizedApplication`; failure implies a bug) |
| `CLASSIFIED` | `NARRATIVE_READY` | `NARRATIVE_FAILED` | Yes, bounded retry budget (LLM timeout, malformed structured output, failed semantic validation) |
| `NARRATIVE_READY` | `REPORTS_READY` | `REPORT_FAILED` | Yes, bounded retry budget (PDF render error) |
| `REPORTS_READY` | `COMPLETED` | `DELIVERY_FAILED` | Yes, bounded retry budget, **per recipient** |
| any `*_FAILED` | (same stage retried) | `FAILED_PERMANENT` | Only until attempt budget exhausted |

Invalid transitions (must be rejected by `is_valid_transition`): any transition that
skips a stage (e.g. `RECEIVED → REPORTS_READY`), any transition out of a terminal
state, any transition into `COMPLETED` while an expected recipient's `Delivery` is
not `sent`.

### 9.3 Terminal states

`COMPLETED`, `REJECTED_DUPLICATE`, `REJECTED_INVALID`, `FAILED_PERMANENT`. Nothing
transitions out of these automatically; `FAILED_PERMANENT` requires a human-invoked
recovery action (which itself re-enters the normal transition table, it does not
bypass it).

### 9.4 Retry behavior

- Every `*_FAILED` state carries `attempt_counts[stage]`. A worker picking up a
  failed-stage job increments the count, retries with backoff, and moves to
  `FAILED_PERMANENT` once a per-stage max is exceeded (max value: BUSINESS/OPS INPUT
  REQUIRED — see §16, propose 5 as a placeholder default).
- Retrying a stage always re-derives that stage's output from the immutable inputs
  of prior stages; it never re-runs prior stages.

## 10. Failure behavior

For every case: **retryable**, **state persisted**, **possible side effects
already occurred**, **duplicate-prevention mechanism**, **human intervention
required**.

| Failure | Retryable | State persisted | Side effects possible before failure | Duplicate prevention | Human intervention |
|---|---|---|---|---|---|
| Duplicate submission (same `response_id` redelivered) | n/a — short-circuited | `RawFormSubmission` insert is a no-op on conflict; state → `REJECTED_DUPLICATE` | None | Unique constraint on `(form_id, response_id)` | No |
| Malformed payload | No | Nothing beyond a rejection log entry (no `RawFormSubmission` row — envelope itself unparseable) | None | n/a | No, unless malformed payloads recur (signals upstream Form/integration break) |
| Missing optional data | n/a — not a failure | `NormalizedApplication.normalization_warnings[]` | None | n/a | No |
| Missing required data | No (same payload) | `RawFormSubmission` (already immutable), state → `NORMALIZATION_FAILED` | None | n/a — nothing downstream has run | Yes — data is incomplete at the source |
| Changed Google Form fields (schema drift) | No, until mapping updated | `RawFormSubmission` intact; state → `NORMALIZATION_FAILED` for every affected submission | None | Schema version pinned per submission; new mapping gets a new `form_schema_version` | Yes — requires a mapping update + redeploy, then bulk-retry affected submissions |
| LLM timeout | Yes, bounded | Prior stages' rows intact; state stays `CLASSIFIED` (retry re-enters `NARRATIVE_*`) | None (no partial `Narrative` row written until a full result is validated) | Attempt is idempotent — same inputs, new attempt row | No, until budget exhausted |
| Malformed LLM structured output | Yes, bounded | Failed attempt optionally logged (metadata only, see §13) | None | Never written as an accepted `Narrative` | No, until budget exhausted |
| Hallucinated information | No — treated as a validation failure, not a transient error | Same as above | None — semantic validator rejects before persistence/use | Post-generation semantic check against `NarrativeContext` allow-list (§6.8) | Yes, after budget exhausted — likely a prompt/model problem, not a retry problem |
| Primary provider outage | Yes, bounded, then `FAILED_PERMANENT` | Prior stages intact | None | Same as LLM timeout | Yes — see AQ-3 (fallback provider is out of scope for v1; outage stalls affected submissions) |
| PDF rendering failure | Yes, bounded | `Narrative` intact; state stays `NARRATIVE_READY` | None (no artifact written on failure) | Artifact write only recorded after successful render | No, until budget exhausted |
| Gmail failure (transient) | Yes, bounded | `Report` intact | Possibly none, possibly send-accepted-but-ack-lost (see REVIEW.md AF-2) | Per-recipient `Delivery` row claimed before send attempt | No, until budget exhausted |
| Gmail quota/rate limit | Yes, with longer backoff | Same as above | None | Same as above | No initially; yes if sustained (capacity problem) |
| Partial delivery (client sent, internal cc fails, or vice versa) | Yes, per recipient | Per-recipient `Delivery` rows independently reflect sent/failed | Client (or internal) copy may already be delivered | `Delivery` is keyed per `(submission_id, report_type, recipient)`; retry only targets the failed row | No, until that recipient's budget exhausted |
| Cloud Run restart mid-stage | Yes | Whatever the last successfully persisted stage was | None beyond that stage's already-committed writes | Compare-and-swap claim means an interrupted worker never left a stage half-committed | No |
| Deployment during processing | Yes | Same as above | None | Same as above — deploys don't need a drain step because state is durable, not in-memory | No |
| Queue retry (task redelivered) | Yes | Unchanged | Possibly a stage was already completed by the first delivery | Worker re-checks `SubmissionState.status` before doing any work; a task for an already-completed stage is a no-op | No |
| Persistence failure (write fails) | Yes, by the caller | Whatever was durably committed before the failure — nothing "in flight" is trusted | None — a write that fails is not treated as done | The stage is simply retried; nothing was claimed since the claim write itself failed | No, unless persistence itself is down (ops incident) |

## 11. Security and privacy requirements

- Sensitive information involved: applicant health/personal data submitted via the
  form (this is an insurance intake — treat all form answers as sensitive by
  default, not just fields that look obviously medical).
- May be logged: submission/entity IDs, enum values (`qualification`, `status`),
  durations, counts, provider/model names, rule/prompt/template version strings.
- Must never be logged: raw form answers, `NarrativeContext` contents, LLM
  prompt/response bodies, rendered report contents, recipient email addresses in
  plaintext structured logs (use a hashed or truncated reference if correlation is
  needed), secrets/credentials.
- Trust boundaries: the Google Forms webhook payload is untrusted input (validate
  shape before use); LLM output is untrusted input (validate schema + semantics
  before use, per INVARIANT 3/10); nothing from either boundary is trusted to
  self-report as safe.
- Secrets handling: LLM API keys, Gmail credentials, and datastore credentials come
  from a secrets manager, injected at runtime, never in source or config files
  (INVARIANT 12).
- Data minimization: `NarrativeContext` is the concrete mechanism for minimization —
  the LLM provider (a third party) only ever receives the allow-listed subset, never
  the full `NormalizedApplication` or raw payload.
- Retention: BUSINESS INPUT REQUIRED (§16) — how long raw submissions and reports
  are retained is a regulatory question, not an engineering default.

## 12. Allowed implementation surface

None. This phase is architecture and documentation only. No files under an
application source tree may be created or modified. `main.py` is explicitly
untouched.

## 13. Prohibited changes

- No changes to `main.py`.
- No creation of application source directories (no `src/`, `tests/`, etc. yet).
- No invented business rules, report content, or provider selections presented as
  final — anything not architecturally forced must be flagged, not decided.
- No delegation to Codex Builder or Codex Reviewer.

## 14. Acceptance criteria

Phase 1 is complete when:

1. `docs/phases/PHASE-01/SPEC.md`, `REVIEW.md`, and `STATUS.md` exist and follow the
   contract in `docs/PROMPT.md`.
2. Every invariant in `docs/INVARIANTS.md` has an explicit architectural mechanism
   named in §8 above.
3. The failure matrix (§10) covers every case listed in `docs/PROMPT.md` step 8.
4. Every unresolved business decision is marked `BUSINESS INPUT REQUIRED` (§16) —
   none are silently assumed.
5. Every unresolved engineering decision is listed as an architectural question
   (§17) — none are silently resolved.
6. `REVIEW.md` contains a genuine adversarial pass (not a restatement of the spec).
7. `STATUS.md` correctly reflects that human approval is pending and that Codex
   agents remain unauthorized.
8. No application code was written or modified.

## 15. Required tests

Not applicable to this phase (no implementation). The **test architecture** that
future phases must satisfy is specified below as forward-looking design, not as
tests executed in this phase:

- **Unit tests**: rule engine functions (pure), `NarrativeContext` builder (pure),
  `ClientReportContext`/`InternalReportContext` builders (pure), state-transition
  validator (pure), form-schema normalization mapping.
- **Rule truth-table tests**: a fixed set of `NormalizedApplication` fixtures with
  hand-verified expected `Assessment` output (rules triggered + qualification),
  re-run against every `rule_version` to catch unintended drift.
- **Integration tests**: repository implementations against a real (test-instance)
  datastore; queue enqueue/claim semantics under concurrent workers.
- **Contract tests**: `LLMProvider` adapter against a fake conforming to the
  interface's schema; `EmailSender` and `ReportRenderer` adapters similarly.
- **Workflow tests**: full pipeline through fake adapters, asserting every state
  transition, including a duplicate-submission run and a mid-pipeline crash
  simulation (resume from persisted state).
- **Failure/retry tests**: one test per row of the §10 failure matrix, asserting no
  duplicate side effects and correct terminal/retry state.
- **Readiness-gate tests**: one test per §6.13 config point, asserting the
  relevant stage fails closed with the correct `reason_code` when that point is
  absent/unapproved under `ENV=production`, and that ingestion (`RECEIVED`) is
  never blocked by a downstream config gap.
- **End-to-end tests**: staged environment, synthetic Form payload, sandbox email
  account — run in CI on a slower cadence than unit/contract tests, not per-commit.

## 16. Business decisions required

Every item below was tested against one question: **does not knowing the answer
change the fundamental architecture (entities, state machine, interfaces), or can
the system be fully built against a defined config/interface point with a safe
placeholder?** None of the ten changed the fundamental architecture — each already
plugs into a structure §6 defines independently of its content (rule engine,
schema mapping, allow-list, routing, template/prompt versioning, retry policy,
provider interface). Two caveats where a *specific, currently-unconfirmed* answer
*could* force a redesign are called out inline (BR-2, BR-9) but are not assumed.

`BUSINESS INPUT REQUIRED` still applies to all business content below — nothing in
this reclassification invents rule content, copy, recipients, or policy values.
Reclassifying does not resolve a single item; it separates "must be answered to
write code" (none) from "must be answered to launch" (all of them, eventually).

### 16.1 Classification summary

| ID | Item | Bucket |
|---|---|---|
| BR-1 | Underwriting/classification rule content | Implementation-safe-to-defer |
| BR-2 | Google Form field IDs/labels/required set | Implementation-safe-to-defer* |
| BR-3 | Client narrative/report content & tone | Implementation-safe-to-defer |
| BR-4 | Internal vs. client report field split | Implementation-safe-to-defer |
| BR-5 | Recipient list(s) per submission | Implementation-safe-to-defer |
| BR-6 | Data retention period | Implementation-safe-to-defer |
| BR-7 | SLA / latency target | Implementation-safe-to-defer |
| BR-8 | Human-intervention notification channel | Implementation-safe-to-defer |
| BR-9 | LLM provider/model selection | Implementation-safe-to-defer* |
| BR-10 | Expected submission volume | Production-launch-blocking |

\* See caveat under the item — a specific real-world answer could turn this into an
architecture question, but nothing currently known suggests it will.

**Architecture-blocking: none identified.** If Quirón's real Form turns out to
require file/document uploads (BR-2 caveat) or a hard "no third-party LLM may see
applicant data" constraint (BR-9 caveat), those specific findings — not the general
items — would need to come back through this SPEC before implementation continues
in that area. Nothing currently on record indicates either is the case.

### 16.2 Implementation-safe-to-defer — config point, placeholder, production requirement

**BR-1 — Rule content.**
- Config point: `RuleSet` registered under `RULE_SET_VERSION`; the `RuleEngine`
  resolves the active version at classification time (§6.5).
- Placeholder / fail-closed: no ruleset registered/approved →
  `CLASSIFICATION_FAILED`, `reason_code=RULES_NOT_CONFIGURED`, non-retryable,
  alerts (§6.13). Never defaults to an "auto-approve" or "auto-decline" ruleset.
- Before production: Quirón-approved rule v1 content, registered and marked
  `approved_for_production=true`.

**BR-2 — Form field mapping.**
- Config point: `FormSchemaMapping` keyed by `form_schema_version` (§6.10, §7.2).
- Placeholder / fail-closed: no mapping registered for the incoming `form_id` →
  `NORMALIZATION_FAILED`, `reason_code=SCHEMA_NOT_CONFIGURED`. The
  `RawFormSubmission` is still durably persisted first (§6.13) — only normalization
  stalls, nothing is lost.
- Before production: real field mapping for Quirón's live Form, with required vs.
  optional set confirmed.
- Caveat: if the real Form includes file/document uploads (e.g. ID or document
  scans), that introduces a binary-attachment data type not currently modeled in
  `NormalizedApplication`/`RawFormSubmission` and would need a SPEC addendum before
  that specific capability is built — flagged, not assumed either way.

**BR-3 — Narrative/report content.**
- Config point: `PromptTemplate` (keyed by `prompt_version`) and `ReportTemplate`
  (keyed by `template_version`, per report type) — both already versioned per
  §6.10.
- Placeholder / fail-closed: a `DRAFT-UNAPPROVED` prompt/template version is usable
  in dev/staging; selecting an unapproved version while `ENV=production` fails the
  narrative/report stage closed (§6.13) rather than sending unapproved copy to a
  client.
- Before production: Quirón-approved copy (including any required disclaimer
  language), marked `approved_for_production=true`.

**BR-4 — Client/internal field split.**
- Config point: `ClientReportAllowlist` — the explicit field list §6.7's
  `ClientReportContext` builder is permitted to read.
- Placeholder / fail-closed: default allow-list is **empty** beyond the
  structurally-required narrative text and qualification label — the safe
  direction is under-inclusion, never over-inclusion, since a missing field is a
  visibly incomplete report while an extra field is a silent invariant-4 breach.
  Not marked `approved_for_production` → client delivery stage fails closed.
- Before production: Quirón-approved allow-list.

**BR-5 — Recipients.**
- Config point: `RecipientRouting` — `internal_report_recipients: list[email]` and
  the `NormalizedApplication` field designated as the client's own address.
- Placeholder / fail-closed: empty/unmapped → `DELIVERY_FAILED`,
  `reason_code=RECIPIENTS_NOT_CONFIGURED`, per recipient class independently (an
  internal-recipient gap doesn't block a correctly-configured client send, and vice
  versa — consistent with the per-recipient `Delivery` model in §6.3).
- Before production: real recipient list(s)/routing rule.

**BR-6 — Retention.**
- Config point: `RetentionPolicy` per entity type (`raw_submission`, `narrative`,
  `report`, etc.).
- Placeholder / fail-closed direction: **no automatic deletion** until a policy is
  explicitly set. This is the deliberate fail-closed direction — auto-deleting
  under an assumed default risks violating INVARIANT 15 (reconstructable from
  stored metadata) and destroying data Quirón may be legally required to retain;
  retaining data slightly longer than ideal is a correctable compliance gap,
  deletion is not. This does not block any stage from running — it's a background
  purge job that simply doesn't run until configured, and its absence is logged as
  a loud warning rather than a hard stage failure.
- Before production: real retention period per entity type (likely an LFPDPPP
  compliance input, jurisdiction to be confirmed).

**BR-7 — SLA / retry budget.**
- Config point: `RetryPolicy` per stage (max attempts, backoff schedule).
- Placeholder / fail-closed: conservative default already proposed in §9.4 (5
  attempts, exponential backoff) — explicitly labeled a placeholder, not a
  commitment. This default is self-contained and safe to run in production as-is
  (it fails toward earlier human escalation, never toward infinite silent retry),
  so it does not need to be `ReadinessGate`-blocked — only flagged for
  confirmation.
- Before production: confirm or replace with SLA-derived values.

**BR-8 — Human-intervention notification.**
- Config point: `AlertChannel` (adapter interface + destination config).
- Placeholder / fail-closed: no-op/log-only sink permitted in dev, with a loud
  startup warning. In production, this is the one config point whose absence
  escalates beyond a single stage — with no alert path, a stage that fails closed
  would fail *silently*, which is worse than not starting. See §6.13.
- Before production: real alert channel + on-call destination.

**BR-9 — LLM provider/model.**
- Config point: `LLMProviderConfig` selecting a registered `LLMProvider` adapter +
  credentials via the secrets manager (§6.9, §11).
- Placeholder / fail-closed: no concrete provider configured/authorized →
  `NARRATIVE_FAILED`, `reason_code=LLM_PROVIDER_NOT_CONFIGURED`. A fake/test
  provider may exist for dev but is excluded from selection when
  `ENV=production`.
- Before production: contracted provider/model + credentials.
- Caveat: if Quirón's compliance posture turns out to forbid sending any applicant
  data to a third-party LLM at all, the same `LLMProvider` interface still holds —
  the concrete adapter becomes a deterministic template-only narrative generator
  (no external call) rather than a hosted-model client. That's a new adapter, not
  an architecture change, so it doesn't move this item to architecture-blocking;
  it's flagged so the interface isn't accidentally designed assuming an external
  call is mandatory.

### 16.3 Production-launch-blocking

**BR-10 — Expected submission volume.**
- Not a code interface question: the queue/worker design already scales
  horizontally regardless of volume (§6.2, §9). Nothing about the skeleton depends
  on this number.
- Before production: confirm expected peak rate to validate that Gmail send quota
  (§10, "Gmail quota/rate limit" row) is actually a non-issue at real volume, and
  to size worker concurrency. This is a capacity-planning input to be confirmed
  before go-live, not a design blocker now.

## 17. Architectural questions

Every item below now has a recommended resolution recorded as a PROPOSED ADR
under `docs/architecture/` — none are implemented, none are silently decided;
each is a specific recommendation with alternatives, open for the human owner to
approve, amend, or reject. This section stays as an index; the ADR is the
authoritative record.

- AQ-1: Hosting platform → **ADR-000** (Google Cloud Run, proposed).
- AQ-2: Persistence technology → **ADR-001** (Cloud SQL for PostgreSQL, proposed).
- AQ-3: Secondary LLM provider for outage resilience → resolved within
  **ADR-004** (none for v1, proposed; revisit only after a real outage or a
  contractual multi-provider requirement).
- AQ-4: Queue/dispatch technology → **ADR-002** (Cloud Tasks, proposed).
- AQ-5: Gmail sending mechanism → **ADR-006** (service-account domain-wide
  delegation, proposed — carries an operational dependency on Quirón IT
  provisioning, not purely a technical choice).
- AQ-6: PDF rendering approach/library → **ADR-005** (Jinja2 + WeasyPrint,
  proposed).
- AQ-7: Retry budget and backoff schedule → **ADR-011** (5 attempts, exponential
  backoff, proposed placeholder pending BR-7).
- AQ-8: Form-schema drift detection → **ADR-008** (declarative versioned config,
  reactive-only detection for v1, proposed).
- AQ-9: Minimum viable `NarrativeContext` floor → **ADR-012** (configurable
  threshold + deterministic fallback narrative, proposed).

Two additional decisions were formalized as ADRs during this pass, beyond the
original AQ list, because the reclassification work in §16 surfaced them as
needing an explicit mechanism rather than an assumption:

- **ADR-003**: Worker/orchestration approach (single resumable worker, no
  external orchestration engine — already reasoned through in REVIEW.md finding
  AF-4, now formalized).
- **ADR-007**: Email idempotency/reconciliation strategy for the Gmail dual-write
  window (REVIEW.md findings AF-2/AF-3, now formalized as a decision rather than
  an open risk).
- **ADR-009**: Secrets management approach (Google Secret Manager).
- **ADR-010**: Rule/prompt/template-version enforcement mechanism (CI content-hash
  check — also answers REVIEW.md finding AF-6).

## 18. Implementation authorization

`NOT AUTHORIZED`.

This phase is architecture-only. No agent is authorized to implement application
code as a result of this document. Authorization for a future implementation phase
requires: (a) human approval of this SPEC, (b) resolution or explicit acceptance of
the ADR backlog, and (c) a new phase SPEC scoped to a concrete implementation slice.
