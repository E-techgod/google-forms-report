# PHASE-03 — Real Infrastructure Adapters

## 1. Phase identity

- Phase number: 03
- Phase name: Real Infrastructure Adapters
- Spec version: v3 — incorporates the human's second 2026-08-18 decision:
  Docker Compose approved as the default local development/integration/
  contract-test infrastructure mechanism, recorded as `ADR-013` and threaded
  through §11, §12, §13, §14, §15, §17 with its five binding constraints.
  v2 (SQLAlchemy 2.x + Alembic; mandatory 7-checkpoint adapter-by-adapter
  delivery with per-checkpoint + final cross-adapter review; the
  architecture-escalation rule) is otherwise unchanged — see §20 for the
  self-review performed on this revision.

## 2. Objective

Replace the fake/in-memory adapters built in PHASE-02 with real adapters
against the already-approved ADRs (`docs/architecture/ADR-000` through
`ADR-012`), behind the exact same interfaces PHASE-02 defined, so that no
architecture changes — only concrete implementations — are required. This
phase exists because PHASE-02 deliberately stopped at "interfaces + fakes,
tested end-to-end against fakes only" (`docs/phases/PHASE-02/SPEC.md` §4);
nothing here revisits that decision, it fulfills the deferral.

This phase does **not** implement the real LLM adapter (ADR-004 names the
concrete vendor as `BUSINESS INPUT REQUIRED` — BR-9 — and explicitly excludes
it from engineering scope) and does **not** perform actual cloud provisioning
(creating the Cloud SQL instance, Cloud Tasks queue, Secret Manager secrets,
or the Gmail Workspace service account) — those are operational/IT actions no
agent in this project has credentials or authorization to perform. This phase
writes and tests the *code* that will use that infrastructure once it exists.

**Architecture-escalation rule for this phase**: a real external service's
constraints (Cloud Tasks' delivery semantics, Gmail API quirks, SQLAlchemy/
Alembic's own conventions, Postgres-specific behavior, WeasyPrint's CSS
support) may turn out to be inconvenient relative to an approved interface,
domain model, workflow contract, state machine transition, or invariant.
Inconvenience is not authorization to change any of those silently. If a real
adapter genuinely cannot be implemented without altering one, implementation
on that checkpoint must stop; the conflict is recorded in REVIEW.md, the
checkpoint is marked `BLOCKED_ARCHITECTURE`, and it is escalated to Claude and
the human per `docs/PROMPT.md`'s procedure — this is `ARCHITECTURE ESCALATION
REQUIRED`, not a workaround to implement quietly. This is the single most
likely way this phase could go wrong, since every adapter here is meeting a
contract PHASE-01/PHASE-02 designed before any real infrastructure constraint
was known, and it is reinforced again in §13.

## 3. Scope

- **Persistence adapter (ADR-001)**: a Postgres-backed implementation of
  every Protocol in `src/persistence/interfaces.py`
  (`RawFormSubmissionRepository`, `NormalizedApplicationRepository`,
  `AssessmentRepository`, `NarrativeRepository`, `ReportRepository`,
  `DeliveryRepository`, `SubmissionStateRepository`, bundled as a
  `RepositoryBundle`), built on **SQLAlchemy 2.x** (per human decision,
  2026-08-18 — see §17), including the compare-and-swap claim
  (`SubmissionStateRepository.compare_and_set`) as
  `UPDATE submission_state SET status = $new WHERE submission_id = $id AND
  status = $expected`, checking rows-affected = 1 — the exact primitive
  ADR-001 specifies, expressed through SQLAlchemy Core (an explicit `update()`
  construct with a `WHERE` clause and a rowcount check), not an ORM
  session-merge pattern that could obscure whether the conditional write
  actually happened. Append-only semantics for every entity except
  `SubmissionState` (established in PHASE-02's fake, per PHASE-01 SPEC.md
  §6.3) must be preserved by the real schema (insert-only tables, no
  `UPDATE`/`DELETE` on historical rows).

  **ORM isolation (hard requirement)**: SQLAlchemy types, sessions,
  declarative models, and any Alembic artifact stay entirely inside
  `src/persistence/postgres/`. `src/domain/`, `src/workflows/`, and every
  other package continue to depend only on the plain-dataclass domain models
  (`src/domain/models.py`) and the Protocols in
  `src/persistence/interfaces.py` — exactly as PHASE-01 SPEC.md §6.1's
  dependency-direction rule already requires, now with a concrete ORM to
  keep out from behind that boundary. Repository methods accept and return
  domain dataclasses, never SQLAlchemy model instances or `Session` objects.
- **Schema/migrations**: **Alembic** migrations (per human decision,
  2026-08-18 — see §17) generated from the SQLAlchemy models for the
  seven-entity schema (`submission_id`-keyed, matching
  `src/domain/models.py`), versioned and applied via Alembic's standard
  revision mechanism — no hand-rolled migration runner.
- **Queue/dispatch adapter (ADR-002, ADR-003)**: a Cloud Tasks producer used
  by the webhook receiver to enqueue work (replacing
  `InMemoryTaskQueue`), and an OIDC-verified HTTP push endpoint on the worker
  side that Cloud Tasks calls — one task delivery = one worker invocation =
  one stage attempt, per ADR-003's re-entrant-per-submission model. No new
  orchestration logic; `Worker`'s existing "read state → execute next stage →
  return" shape (`src/workflows/worker.py`) does not change.
- **Secrets adapter (ADR-009)**: a `SecretProvider` (`src/config/secrets.py`)
  implementation backed by Google Secret Manager, replacing
  `InMemorySecretProvider` for any environment where `AppConfig.is_production`
  is true (and optionally for a "staging" env once one exists).
- **PDF rendering adapter (ADR-005)**: a WeasyPrint-backed `ReportRenderer`
  (`src/adapters/pdf/base.py`) that renders the existing Jinja2 templates
  (`src/templates/*.j2`, still `DRAFT-UNAPPROVED` placeholder content per
  BR-3 — content is not this phase's concern) to PDF bytes, replacing
  `FakeReportRenderer`. No template content changes.
- **Gmail adapter (ADR-006, ADR-007)**: an `EmailSender`
  (`src/adapters/gmail/base.py`) implementation using the Gmail API via a
  Workspace service account with domain-wide delegation, replacing
  `FakeEmailSender`. Must implement ADR-007's idempotency mechanism exactly:
  set `X-Submission-Delivery-Id: <submission_id>:<report_type>:<recipient>`
  on outgoing messages; before any retry-path send, call
  `find_existing(delivery_key)` implemented as a Gmail API search for that
  header value, and only call `send()` if no match is found.
- **Form schema mapping loader (ADR-008)**: a loader that reads versioned
  `FormSchemaMapping` config files from disk (format: see §17) into the
  `AppConfig.form_schema_mappings` dict PHASE-02 already defined — mapping
  *content* stays empty/placeholder (BR-2 is unresolved); this phase builds
  only the loading mechanism ADR-008 calls for.
- **Adapter selection wiring**: `AppConfig`/bootstrap wiring (extending what
  PHASE-02's `main.py` did for fakes) so the real vs. fake adapter for each
  of persistence, queue, secrets, PDF, and email is chosen by configuration
  (e.g. an `env`/`ADAPTER_MODE` setting), not by editing code — tests keep
  using the fakes from PHASE-02 unchanged; only a real deployment would ever
  select the real adapters.
- **Containerization (ADR-000, ADR-003)**: a `Dockerfile` building the
  application image, and Cloud Run service configuration (as committed
  config/manifest, e.g. a `service.yaml` or documented `gcloud run deploy`
  invocation) for both the webhook-receiver service and the worker push
  target — committed as code/config, **not executed** by any agent (see §4).
- **Contract tests** for every real adapter added in this phase (ADR-001,
  ADR-002's push-contract shape, ADR-009, ADR-005, ADR-006/007), runnable in
  CI without live GCP credentials — see §15 for exactly how each is made
  runnable, and §17 for the one item (Gmail's actual send call) that
  structurally cannot be fully contract-tested without either a sandbox
  Workspace account or recorded fixtures.

## 4. Out of scope

- The real `LLMProvider` adapter and any LLM vendor selection — blocked on
  BR-9 (ADR-004). `NullLLMProvider` remains the only implementation; the
  `LLM_PROVIDER_NOT_CONFIGURED` fail-closed gate continues to fire for any
  simulated production run, exactly as PHASE-02 left it. This is not a gap
  this phase is expected to close.
- All real business content: BR-1 (rule thresholds/flags), BR-2 (Form field
  mapping content), BR-3 (narrative/report copy), BR-4 (client allow-list
  content), BR-5 (recipients), BR-6 (retention period), BR-7 (confirmed SLA
  numbers — ADR-011's placeholder retry/backoff values are used as-is), BR-8
  (alert destination), BR-10 (production launch gate).
- Actual cloud provisioning or credential issuance: creating the Cloud SQL
  instance, Cloud Tasks queue, Secret Manager project/secrets, or the Gmail
  Workspace service account and granting it domain-wide delegation. These are
  Quirón IT/ops actions (ADR-006 already names the Workspace step as an
  operational dependency, not an engineering one). No agent runs `gcloud`,
  `terraform apply`, or any command that provisions or mutates real cloud
  infrastructure or real GCP IAM.
- Any live call to a real external service from a test or from CI. All
  automated tests in this phase run against local stand-ins (a local/
  dockerized Postgres, a local HTTP double for the Cloud Tasks push contract,
  recorded/mocked Gmail HTTP fixtures, an in-process or emulator-mode check
  for Secret Manager where available). Genuine end-to-end validation against
  live GCP services happens later, manually, in a staging environment Quirón
  provisions — that validation is explicitly not an acceptance criterion of
  this phase (see §14).
- Proactive Form-drift polling (still deferred per ADR-008 as a fast-follow,
  unchanged from PHASE-02).
- Rule-version/prompt-version/template-version CI hash enforcement (ADR-010)
  — deferred, as it was after PHASE-02, to "before the first real rule/
  prompt/template content is committed," which this phase does not do.
- Any change to `docs/PROMPT.md`, `docs/INVARIANTS.md`, `docs/agents/*.md`,
  `docs/phases/PHASE-01/*`, `docs/phases/PHASE-02/*`, or any file under
  `docs/architecture/` (an ADR may only change via the same escalation path
  named in `docs/PROMPT.md`, not as an incidental edit here).

## 5. Dependencies

- Previous approved phases: PHASE-01 (architecture, all 13 ADRs) and PHASE-02
  (technical skeleton, interfaces + fakes) — both approved.
- Required architectural decisions: ADR-000 (hosting), ADR-001 (persistence),
  ADR-002 (queue), ADR-003 (worker orchestration — unchanged, just now driven
  by a real queue), ADR-005 (PDF), ADR-006 (Gmail), ADR-007 (idempotency),
  ADR-008 (schema mapping representation), ADR-009 (secrets) — all approved
  in PHASE-01, none revisited here.
- Required business inputs: none block this phase (same posture as PHASE-02
  — real content for BR-1/2/3/4/5/6/8 remains deferred without blocking
  infrastructure work).
- Required external services/credentials — **explicit operational
  dependencies, not engineering tasks**:
  - A GCP project with Cloud SQL, Cloud Tasks, and Secret Manager enabled —
    needed only for genuine staging validation, not for this phase's
    automated tests (§4, §15).
  - A Google Workspace service account with domain-wide delegation for Gmail
    sending (ADR-006's named dependency) — without it, the Gmail adapter's
    code and contract tests can be completed, but no real email can ever be
    sent, in this phase or any later one, until Quirón IT provisions it. This
    phase does not wait on that provisioning to be considered complete; it
    is named here so it is not silently assumed to already exist.
  - None of the above block starting or finishing this phase's code and
    tests. They block only the first *real* send/write/enqueue against live
    infrastructure, which is explicitly not this phase's acceptance bar.

## 6. Relevant architecture

Directly implements the infrastructure-facing ADRs against the interfaces
PHASE-02 already defined. No new interface is introduced; every adapter in
this phase implements a Protocol that already exists in `src/persistence/`,
`src/adapters/*`, or `src/config/secrets.py`. Concrete mapping:

| ADR | Interface implemented | Module (new) |
|---|---|---|
| ADR-001 | `src/persistence/interfaces.py` (all Protocols) | `src/persistence/postgres/` |
| ADR-002/ADR-003 | `src/workflows/queue.py`'s queue Protocol (producer) + worker push endpoint | `src/adapters/queue/cloudtasks/`, `src/api/` (push endpoint) |
| ADR-009 | `src/config/secrets.py::SecretProvider` | `src/config/secrets_gcp.py` |
| ADR-005 | `src/adapters/pdf/base.py::ReportRenderer` | `src/adapters/pdf/weasyprint.py` |
| ADR-006/ADR-007 | `src/adapters/gmail/base.py::EmailSender` | `src/adapters/gmail/gmail_api.py` |
| ADR-008 | `AppConfig.form_schema_mappings` loading | `src/config/schema_loader.py`, `config/form_schemas/` |
| ADR-000/ADR-003 | Cloud Run hosting | `Dockerfile`, `deploy/` (config only) |

Dependency direction is unchanged from PHASE-01 SPEC.md §6.1: `src/domain/`
stays free of adapter/I/O imports; every new module here lives in
`src/adapters/*`, `src/persistence/*`, or `src/config/*` and depends on
domain types, never the reverse. `src/workflows/worker.py` continues to be
the only module wiring domain and adapter types together, unchanged in
shape — it receives whichever adapters it's constructed with, real or fake,
exactly as PHASE-02 already built it.

## 7. Data contracts

No data contract changes. Every entity, field, and validation rule is exactly
as defined in PHASE-01 SPEC.md §6.3/§7 and implemented in
`src/domain/models.py`. This phase adds persistence/transport/rendering
*implementations* of existing contracts; it does not add, remove, or rename a
field anywhere.

## 8. Invariants

All 15 invariants apply, unweakened. This phase is where several move from
"proven against a fake" to "proven against the real mechanism they were
designed for":

- INVARIANT 1/2 (at-most-once, no duplicate delivery): the real
  `compare_and_set` must be verified against genuine concurrent writers
  hitting the real Postgres instance (not just Python-level threading against
  an in-memory dict, as PHASE-02's test did) — a real DB-level race test is
  required (§15). ADR-007's idempotency-header search-before-send must be
  verified against the mocked/recorded Gmail transport, not asserted by
  reading code alone.
- INVARIANT 7 (raw submissions immutable): verify the real schema has no
  `UPDATE`/`DELETE` grant or code path for `raw_submissions` beyond insert/
  select.
- INVARIANT 11 (external failure ≠ data loss): verify that a Postgres
  connection drop or Cloud Tasks push failure mid-stage leaves the
  submission resumable from its last successfully persisted state — the same
  crash-and-resume property PHASE-02 proved against fakes, now proved (for
  persistence) against the real adapter, and (for queueing) against the local
  push-contract double.
- INVARIANT 12 (secrets never logged): verify the real `SecretProvider`
  never logs a retrieved secret value, and that Secret Manager resource
  names/refs (not values) are the only thing that may appear in logs.
- INVARIANT 15 (reconstructable from stored metadata): verify a full
  synthetic submission run through the real Postgres adapter is fully
  reconstructable via SQL query, not just via the repository API.
- All other invariants carry forward unchanged from PHASE-02's closure
  (`docs/phases/PHASE-02/REVIEW.md` §21) — this phase must not reintroduce a
  regression in any of the 13 already-Satisfied invariants, and does not
  attempt to resolve the two accepted deferrals (invariant 8, invariant 10 —
  still out of scope, per §4).

## 9. State behavior

Unchanged from PHASE-01 SPEC.md §9 / PHASE-02 SPEC.md §9. The state machine,
transition validator, and retry/backoff shape (ADR-011's placeholder: 5
attempts, exponential backoff, Gmail-specific longer quota-aware schedule) are
not modified by this phase — only the adapters that stage execution calls
into change from fake to real. `Worker` continues to own zero orchestration
logic beyond "read state, execute next stage, return."

## 10. Failure behavior

Every fail-closed case from PHASE-01 SPEC.md §10 / §16.2 continues to apply
unchanged (`RULES_NOT_CONFIGURED`, `SCHEMA_NOT_CONFIGURED`,
`LLM_PROVIDER_NOT_CONFIGURED`, `RECIPIENTS_NOT_CONFIGURED`, `DRAFT-UNAPPROVED`).
This phase adds real-infrastructure failure modes that must map onto the
*existing* retryable/non-retryable taxonomy, not a new one:

| Failure | Retryable? | Notes |
|---|---|---|
| Postgres connection failure / timeout | Yes | Standard transient-failure retry per ADR-011; raw submission already durably persisted before enqueue (PHASE-01 §9.1), so no data loss. |
| Cloud Tasks push delivery failure/timeout | Yes | Cloud Tasks' own retry re-delivers; worker re-entrancy (ADR-003) makes this safe by construction — same property already proven against the fake queue. |
| Cloud Tasks OIDC verification failure on the push endpoint | No (reject, alert) | Not a transient error — either misconfiguration or a spoofed request; must not silently retry, must alert per BR-8's channel. |
| Secret Manager read failure | Depends: startup vs. per-request. At startup, fails closed per `ReadinessGate.validate_startup()` (unchanged from PHASE-02); mid-stage, treated as a retryable transient adapter failure, same as an LLM/PDF/Gmail transient failure already is. |
| WeasyPrint render exception | Yes (bounded) | Same `ReportRendererError` path already defined in `src/adapters/pdf/base.py`; real exceptions from malformed template/context map to the same retry path the fake's `fail_next_call()` already exercises. |
| Gmail API failure (generic) | Yes | Existing `EmailSenderError` retry path. |
| Gmail quota/rate-limit failure | Yes, with ADR-011's distinct longer backoff schedule (`RetryPolicy.gmail_rate_limit_backoff_seconds`), already defined in `src/config/models.py`. |
| Gmail idempotency search itself fails (can't confirm existing send) | No — do not blindly send | Must surface as a distinct failure state requiring resolution before a retry send is attempted, per ADR-007's whole reason for existing; never fall back to "just send anyway." |

No new terminal state and no new `reason_code` taxonomy is introduced; this
table maps real-infrastructure error modes onto states and codes PHASE-01/02
already defined.

## 11. Security and privacy requirements

- Cloud Tasks push endpoint must verify the OIDC token on every request
  before doing anything else (including before touching persistence) — an
  unverified request must be rejected, not merely logged.
- Secret Manager is the only source of the Postgres connection credential,
  the Gmail service-account key, and any other credential this phase's
  adapters need; none may appear as a literal in code, `pyproject.toml`,
  `Dockerfile`, or any committed config file. `InMemorySecretProvider` (from
  PHASE-02) remains the only implementation used in tests.
- Structured logging discipline from PHASE-01 SPEC.md §11 / PHASE-02 SPEC.md
  §11 is unchanged: no full model dumps, no raw form answers, no rendered
  PDF bytes, no email body content, no secret values — only the fields
  already named. This applies identically whether the adapter behind the
  call is fake or real.
- The Gmail adapter must not log recipient email addresses or message bodies
  at a level broader than what PHASE-02's log-scrubbing test already
  enforces; the idempotency header value (which embeds `submission_id` and
  `recipient`) is an identifier for search purposes, not something to emit to
  logs beyond what's already permitted.
- Test fixtures continue to use only synthetic data (`test-applicant-001`
  style), including in any recorded Gmail HTTP fixture used for contract
  tests — no real applicant or Quirón-domain data may appear in a committed
  fixture.
- Per `docs/architecture/ADR-013`: no production secret or sensitive value
  (real Postgres credential, real Secret Manager ref, real Gmail credential,
  or any real Quirón data) may be committed into `docker-compose.yml` or any
  companion test-only env file — only synthetic/local-only credentials for
  the Compose-provisioned Postgres instance.

## 12. Allowed implementation surface

```
src/persistence/postgres/       (new — SQLAlchemy 2.x models + repository implementations; no sqlalchemy import outside this package)
alembic/                          (new — Alembic environment + versioned revisions)
alembic.ini                         (new)
src/adapters/queue/                   (new — Cloud Tasks producer)
src/api/                                (modified — add OIDC-verified push endpoint for the worker)
src/config/secrets_gcp.py                 (new — Secret Manager SecretProvider)
src/config/schema_loader.py                 (new — FormSchemaMapping file loader)
config/form_schemas/                          (new — mapping file format only, no real content)
src/adapters/pdf/weasyprint.py                  (new — WeasyPrint ReportRenderer)
src/adapters/gmail/gmail_api.py                   (new — Gmail API EmailSender + ADR-007 idempotency)
Dockerfile                                          (new)
deploy/                                               (new — Cloud Run service config/manifests, not executed)
docker-compose.yml                                      (new — local/CI test infra only, per ADR-013; no production secrets)
tests/contract/                                         (new — per-adapter contract tests)
tests/unit/, tests/workflow/                              (may be extended, not restructured)
pyproject.toml                                              (may be modified — add real adapter dependencies only: sqlalchemy, alembic, a Postgres driver (e.g. psycopg), google-cloud-tasks, google-cloud-secret-manager, a Gmail API client, weasyprint)
uv.lock                                                       (companion-only, per PHASE-02 SPEC.md §12's already-approved clarification)
main.py                                                         (may be modified — wire adapter selection by config, stay a thin entrypoint)
```

No other file or directory may be created or modified without a scope
escalation per `docs/PROMPT.md`'s phase gate rules. In particular:
`src/domain/`, `src/workflows/` (beyond what adapters it's constructed with),
and every file listed as prohibited in §4 stay untouched.

## 13. Prohibited changes

- No real `LLMProvider` implementation or LLM vendor selection (§4).
- No real business content of any kind (§4).
- No execution of any cloud-provisioning command (`gcloud`, `terraform
  apply`, or equivalent) against a real project by any agent.
- No live network call to a real external service from any automated test.
- No modification to `docs/PROMPT.md`, `docs/INVARIANTS.md`,
  `docs/agents/*.md`, `docs/phases/PHASE-01/*`, `docs/phases/PHASE-02/*`, or
  any file under `docs/architecture/`.
- No expansion of scope beyond §12 without stopping and escalating per
  `docs/PROMPT.md`'s architecture-change procedure.
- No change to the state machine, transition validator, retry/backoff
  values, or any interface signature defined in PHASE-02.
- No silent modification of an approved repository interface, domain model,
  workflow contract, state machine transition, or invariant to accommodate a
  real adapter's constraints (SQLAlchemy, Alembic, Cloud Tasks, the Gmail
  API, Secret Manager, or any other library/service). Any such conflict is
  `ARCHITECTURE ESCALATION REQUIRED` per `docs/PROMPT.md` and §2's
  escalation rule — not a workaround to implement quietly.
- No SQLAlchemy import (models, `Session`, `Engine`, or any ORM construct)
  outside `src/persistence/postgres/`.
- No production secret or sensitive value in `docker-compose.yml` or any
  companion test-only env file (ADR-013 constraint 3).
- No Compose/Docker-specific assumption (network hostnames, Compose's
  env-file mechanism, or any other Compose-specific detail) in
  `src/domain/`, `src/workflows/`, or any Protocol in
  `src/persistence/interfaces.py` (ADR-013 constraint 4) — Compose stays
  swappable local test infrastructure, never a contract dependency.
- No treatment of Compose as a production orchestration mechanism, and no
  change to the Cloud Run/GCP production architecture (ADR-000/001/002/003)
  on the strength of anything decided in ADR-013 (ADR-013 constraints 1-2).

## 14. Acceptance criteria

1. Every adapter named in §3 exists, implements its existing Protocol
   exactly (no signature drift), and is selected via configuration, not code
   edits, alongside the PHASE-02 fakes (which remain the default for tests).
2. The real persistence adapter passes every contract test PHASE-02 already
   wrote against the fake repositories' declared contract, run instead
   against a local/dockerized Postgres instance — including a genuine
   multi-connection concurrent-claim race test for `compare_and_set`.
3. Append-only semantics hold in the real schema: no `UPDATE`/`DELETE` code
   path exists for any entity except `SubmissionState`, verified by test
   (attempt an update, assert it's rejected or structurally impossible) and
   by schema review (no such grant/statement exists).
4. The real Cloud Tasks push endpoint rejects a request with a missing or
   invalid OIDC token, verified by test, before any persistence or business
   logic runs.
5. The real Secret Manager adapter never returns a cached/stale value beyond
   whatever caching policy this phase documents, and never logs a fetched
   value — verified by test (assert no fixture secret string appears in
   captured log output).
6. The real WeasyPrint adapter renders both report templates (internal and
   client, still `DRAFT-UNAPPROVED` placeholder content) to valid PDF bytes
   for a synthetic context, verified by a test that the output is a
   well-formed PDF (e.g. correct header bytes / parses with a PDF library),
   not just "did not throw."
7. The real Gmail adapter, exercised against recorded/mocked HTTP fixtures
   (not a live mailbox): (a) sets the `X-Submission-Delivery-Id` header
   exactly as ADR-007 specifies; (b) on a simulated retry, calls
   `find_existing()` before `send()` and does not call `send()` again when a
   match is found; (c) never sends when the idempotency search itself fails,
   per §10's row for that case.
8. A full synthetic submission traverses `RECEIVED → ... → COMPLETED` with
   every real adapter substituted in for its PHASE-02 fake (Postgres,
   Cloud-Tasks-shaped local push, WeasyPrint, mocked Gmail) in at least one
   end-to-end contract-level test — the same lifecycle PHASE-02 SPEC.md §14
   acceptance criterion 4 required against fakes, now proven against real
   adapters wherever a live credential is not required.
9. No test in this phase's suite requires network access to a real GCP
   service or a real Gmail mailbox to pass; `uv run --group dev pytest -q`
   (or equivalent) passes in an environment with zero cloud credentials
   configured.
10. `Dockerfile` builds successfully and the resulting image starts the
    webhook-receiver process locally against the fake adapters (a smoke
    check, not a deployment) — proving the container is viable without
    requiring a real Cloud Run deployment to validate it.
11. All tests in §15 pass; Codex Reviewer's adversarial pass finds no
    invariant violation and no scope violation against §12/§13.
12. No module outside `src/persistence/postgres/` imports `sqlalchemy`
    (verified by an import-boundary test, not code review alone) — the ORM
    stays fully isolated behind `src/persistence/interfaces.py`; every
    repository method's parameters and return values are plain domain
    dataclasses from `src/domain/models.py`, never a SQLAlchemy model or
    session.
13. Each of the seven checkpoints in §18 has its own independent, passing
    Codex Reviewer focused review, and §18's required final cross-adapter
    review has independently passed, before this phase is presented for
    human approval. No checkpoint's review may be skipped or merged into
    another's.
14. No checkpoint's implementation altered an approved repository interface,
    domain model, workflow contract, state machine transition, or invariant
    to work around a real adapter's constraints; any point where that was
    genuinely necessary is documented in REVIEW.md as
    `ARCHITECTURE ESCALATION REQUIRED` and was resolved through the human
    escalation path, not silently.
15. `docker-compose.yml` and any companion test-only env file contain no
    production secret or sensitive value — verified by review; only
    synthetic/local-only credentials for the Compose-provisioned Postgres
    instance appear (ADR-013 constraint 3).
16. No module under `src/domain/`, `src/workflows/`, or any Protocol in
    `src/persistence/interfaces.py` contains a Compose/Docker-specific
    assumption (e.g. a hostname only resolvable inside Compose's network, or
    a dependency on Compose's env-file mechanism) — the persistence
    adapter's connection configuration is injected the same way any other
    environment configuration is (`AppConfig`/`SecretProvider`), verified by
    review alongside the criterion 12 import-boundary check (ADR-013
    constraint 4).

## 15. Required tests

- **Contract tests — persistence (ADR-001)**: run against a local Postgres via
  `docker compose`, per `docs/architecture/ADR-013`. Cover every repository
  method through the SQLAlchemy-backed adapter, the compare-and-swap race
  (real concurrent connections against real Postgres, not just threads
  against a Python dict), and append-only enforcement — plus the
  import-boundary check for §14 criterion 12 (no `sqlalchemy` import outside
  `src/persistence/postgres/`) and the criterion 16 check that no
  Compose-specific assumption leaked above the adapter boundary.
- **Contract tests — queue push contract (ADR-002)**: a local HTTP server
  standing in for Cloud Tasks validates the push endpoint's request/response
  contract (payload shape, OIDC verification behavior, retry-triggering
  status codes) — this does not require a live Cloud Tasks queue, only
  validates the endpoint's side of the contract.
- **Contract tests — secrets (ADR-009)**: against the Secret Manager client
  library's local/emulator mode if one is available for the chosen client
  library; otherwise limited to the adapter's own error-handling/interface
  contract (documented which is used and why).
- **Contract tests — PDF rendering (ADR-005)**: fully live, local, no
  external dependency — WeasyPrint renders entirely offline.
- **Contract tests — Gmail (ADR-006/ADR-007)**: against recorded HTTP
  fixtures or a mocked transport layer (e.g. an injected HTTP client double);
  must include the idempotency-header and search-before-send behaviors as
  first-class assertions, not incidental ones.
- **Workflow tests**: re-run the PHASE-02 full-lifecycle, duplicate-
  submission, and crash-and-resume tests with real adapters substituted
  wherever §15's contract tests make that possible without a live credential.
- **Regression tests**: full PHASE-02 test suite (44 tests as of
  `docs/phases/PHASE-02/REVIEW.md` §20) must continue to pass unmodified
  against the fakes — this phase adds adapters, it does not remove or weaken
  the fake-backed test suite PHASE-02 already established.

## 16. Business decisions required

- BR-9 (LLM provider/model + contractual clearance) continues to block only
  the real `LLMProvider` adapter — explicitly out of scope for this phase
  (§4), not a blocker for anything in §3.
- BR-2 (real Form field mapping content) is not required to build the ADR-008
  loading mechanism (§3) — only real mapping *content*, still deferred.
- No other business decision is newly required by this phase; all remain as
  classified in PHASE-01 SPEC.md §16.

## 17. Architectural questions

- **Postgres access + migrations — RESOLVED** by human decision, 2026-08-18:
  SQLAlchemy 2.x (Core-style explicit statements for the compare-and-swap
  claim; ORM/declarative layer acceptable for the simpler append-only
  entities) + Alembic for migrations, isolated entirely behind
  `src/persistence/interfaces.py` (§3, §12, §14 criterion 12). This
  supersedes v1's proposal of a bare driver + hand-written SQL migrations.
- **Contract-test infrastructure — RESOLVED** by human decision, 2026-08-18
  (second round), recorded as `docs/architecture/ADR-013`: Docker Compose is
  the default local development/integration/contract-test infrastructure
  mechanism, provisioning a local Postgres instance for the persistence
  checkpoint's contract tests. Binding, not aspirational — five constraints
  from ADR-013 apply across this phase:
  1. Compose is development/test infrastructure only, never production
     orchestration (reinforces §4/§13 — production stays governed by the
     Cloud Run/GCP ADRs, unchanged by this decision).
  2. Compose-based tests must run without live GCP credentials (already
     required by §4/§14 criterion 9; this decision doesn't relax it).
  3. No production secret or sensitive value may be committed into
     `docker-compose.yml` or any companion env file (§11, §13).
  4. Local test infrastructure must remain replaceable and must not leak
     Docker-specific assumptions into `src/domain/`, `src/workflows/`, or
     any Protocol in `src/persistence/interfaces.py` (§6, §13, §14 criterion
     16).
  If CI in this project's actual pipeline cannot run Docker, that needs to
  surface during checkpoint 1 (persistence, §18), not be discovered later.
- **Delivery shape — RESOLVED** by human decision, 2026-08-18: adapter-by-
  adapter, per §18, superseding v1's "either shape is fine" framing.

If implementation surfaces a genuine new architectural question not covered
by an existing ADR, or a real adapter's constraints conflict with an approved
contract (§2's escalation rule), Codex Builder must stop and escalate per
`docs/PROMPT.md`, not resolve it silently.

## 18. Delivery checkpoints and review process

Per human decision, 2026-08-18: Phase 3 is implemented and reviewed as a
sequence of seven focused checkpoints, not one large diff. Each checkpoint is
its own small, reviewable unit of work per GIT_RULES.md §1/§5 — its own
focused commit(s) and its own Codex Reviewer pass before the next checkpoint
begins:

1. Persistence adapter (ADR-001) — SQLAlchemy 2.x models/session handling +
   Alembic migrations, isolated behind `src/persistence/interfaces.py`.
2. Queue/dispatch adapter (ADR-002/ADR-003) — Cloud Tasks producer + the
   OIDC-verified push endpoint.
3. Secrets adapter (ADR-009) — Secret Manager `SecretProvider`.
4. PDF rendering adapter (ADR-005) — WeasyPrint `ReportRenderer`.
5. Gmail adapter + idempotency (ADR-006/ADR-007) — Gmail API `EmailSender`,
   the `X-Submission-Delivery-Id` header, search-before-send.
6. Form schema mapping loader (ADR-008).
7. Container/runtime wiring (ADR-000/ADR-003) — `Dockerfile`,
   adapter-selection config, Cloud Run service config.

For each checkpoint: Codex Builder implements strictly that checkpoint's
slice of §12's surface; Codex Reviewer performs a focused adversarial review
of that checkpoint's diff and tests against the relevant subset of §3, §8
(invariants that checkpoint touches), §10 (its failure-behavior row(s)), and
§13 — not a full Phase 3 re-review each time; and only a passing checkpoint
unblocks the next. The order above is the default; Codex Builder may reorder
for a genuine discovered dependency (e.g. needing the secrets adapter's
credential-fetch shape settled before finishing the persistence adapter's
connection wiring) but must not skip a checkpoint's own review, and must not
merge two checkpoints' reviews into one pass.

After all seven checkpoints individually pass their focused review, Codex
Reviewer performs one additional **final cross-adapter review** — required,
and distinct from any single checkpoint's review — covering what no
single-checkpoint pass would catch:

- Interactions between adapters (e.g. a persistence-layer error type
  surfacing correctly through `Worker` into the queue's retry behavior; the
  secrets adapter being genuinely exercised by both the persistence and
  Gmail adapters' credential paths, not just its own isolated test).
- The full regression suite (PHASE-02's existing tests plus every checkpoint
  added in this phase) run together, with all real adapters wired in via
  configuration, not just each adapter's own isolated contract tests.
- Every invariant in §8 re-checked against the complete set of real
  adapters together, not one at a time — the same discipline
  `docs/phases/PHASE-02/REVIEW.md` §16 applied when it re-scanned all 15
  invariants after fixes, not just the ones previously flagged.
- A scan for any accumulated scope drift across the seven checkpoints
  against §12/§13 as a whole, and confirmation that no checkpoint recorded
  an unresolved `ARCHITECTURE ESCALATION REQUIRED` per §2/§13/§14 criterion
  14.

Only after the final cross-adapter review passes does Claude perform the
architecture-compliance review (as in PHASE-02), and only then is the phase
presented for human approval. Phase 3 must not be marked `PASS` on the
strength of seven individually-passing checkpoint reviews alone — the final
cross-adapter review is a required, separate gate, and its result must be
recorded in `docs/phases/PHASE-03/REVIEW.md` alongside each checkpoint's own
review record.

## 19. Implementation authorization

SPEC.md v3 is **human-approved in full**, 2026-08-18, including ADR-013
(Docker Compose as local test infrastructure, with its five binding
constraints). §18's seven-checkpoint delivery/review process governs
implementation.

Codex Builder's authorization is scoped **per checkpoint**, not blanket, per
the human's standing instruction: no checkpoint beyond the one explicitly
authorized may begin, even though the SPEC as a whole is approved. The
authoritative record of which checkpoint(s) are currently authorized lives in
`docs/phases/PHASE-03/STATUS.md` ("Agent authorization"), not in this file —
STATUS.md is updated at each checkpoint boundary as Codex Reviewer's focused
review passes and the human authorizes the next checkpoint. As of this
revision, STATUS.md reflects the phase as `READY_FOR_IMPLEMENTATION` with the
specific first-authorized checkpoint recorded there once its scope is
confirmed with the human.

Codex Reviewer performs a focused review after each checkpoint and the
required final cross-adapter review after all seven pass; Claude performs
the final architecture-compliance review only after that cross-adapter
review passes. Claude does not implement this phase directly, per the
project's agent workflow (`docs/agents/CLAUDE.md`, `docs/PROMPT.md`).

## 20. Spec self-review (Claude, 2026-08-18)

### v3 round (Docker Compose / ADR-013)

Performed before presenting this v3 revision:

- **ADR-013 traces correctly**: every one of ADR-013's five numbered
  constraints appears at least once in this SPEC, not just in the ADR file —
  constraint 1/2 in §4/§13/§17; constraint 3 (no production secrets in
  Compose config) in §11, §13, and §14 criterion 15; constraint 4 (no
  Docker-specific leakage into domain/workflow/interfaces) in §6, §13, and
  §14 criterion 16. Confirmed by re-reading each cited section after
  editing, not by assuming the cross-references were placed correctly on
  first pass.
- **No conflict with the ORM-isolation rule**: constraint 4's "must not leak
  Docker-specific assumptions into domain/workflow contracts" and the v2
  ORM-isolation rule ("no sqlalchemy import outside
  `src/persistence/postgres/`") are two instances of the same underlying
  principle — the persistence checkpoint's boundary must absorb both the ORM
  and the local-test mechanism. Checked they're stated as complementary
  (§14 criteria 12 and 16 sit adjacent, both enforced by the same checkpoint
  1 review) rather than as competing or redundant requirements.
- **§17 fully resolved**: both engineering questions v1 left open (Postgres/
  migrations tooling; contract-test infrastructure) are now marked RESOLVED
  with a dated human decision and a citation (ADR-013 for the second); no
  open engineering question remains in §17 beyond the standing instruction
  to escalate anything genuinely new.
- **Implementation-authorization language now correctly reflects per-
  checkpoint gating**: reworded §19 so it no longer implies "SPEC approved
  ⇒ Codex Builder starts checkpoint 1" — the human's authorization is
  explicitly per-checkpoint and lives in STATUS.md, matching the instruction
  that accompanied this approval round ("authorize Codex Builder for
  Checkpoint 3A only. Do not authorize later checkpoints until 3A has passed
  its required Codex Reviewer gate").
- **Flagged, not resolved silently**: §18 defines seven checkpoints numbered
  1-7 with no lettered sub-splits. The human's authorization instruction
  names "Checkpoint 3A," which doesn't map unambiguously onto that list —
  this self-review does not guess and silently pick an interpretation for a
  decision that scopes what Codex Builder is about to be told to build;
  it's raised back to the human directly rather than resolved here.

### v2 round (SQLAlchemy/Alembic, checkpoints, escalation rule)

Performed before presenting the v2 revision, rather than assuming the edits
composed cleanly:

- **Internal consistency**: re-read the full document end-to-end after
  editing. §3's persistence/schema bullets, §6's ADR-to-module table, §12's
  allowed surface, and §18's checkpoint 1 all now agree on SQLAlchemy 2.x +
  Alembic and the `src/persistence/postgres/` isolation boundary — none
  still references the v1 "psycopg + hand-written SQL migrations" default.
  §6's table's `ADR-001` row (`src/persistence/postgres/`) required no
  change since it was already framework-agnostic.
- **No architecture drift introduced by the ORM choice**: confirmed the
  SQLAlchemy decision is additive to §12's surface, not a change to any
  Protocol in `src/persistence/interfaces.py`, any domain dataclass in
  `src/domain/models.py`, or the compare-and-swap contract ADR-001 already
  specifies — the new ORM-isolation requirement (§3, §13, §14 criterion 12)
  is a constraint on *how* the adapter is built, not a change to *what* it
  must satisfy.
- **Checkpoint list matches scope**: verified the seven checkpoints in new
  §18 are exactly the seven bulleted work items in §3 (persistence,
  queue/dispatch, secrets, PDF, Gmail/idempotency, schema-mapping loader,
  containerization) — no checkpoint was invented that lacks a corresponding
  §3 scope item, and no §3 scope item was left without a checkpoint.
- **Escalation rule is load-bearing, not decorative**: checked that the new
  §2 escalation rule is actually referenced from the places that need to
  enforce it — §13 (prohibited changes), §14 (acceptance criteria 14), and
  §18 (checkpoint review must confirm no unresolved escalation) — rather
  than stated once and never checked against.
- **GIT_RULES.md alignment**: §18's "own focused commit(s) per checkpoint"
  language matches GIT_RULES.md §5's commit-size guidance and §10's Codex
  Builder commit authority; nothing in this revision asks Codex Builder or
  Codex Reviewer to push without the authorization GIT_RULES.md already
  requires (§17-19) — this SPEC revision does not change either agent's git
  authority, already addressed separately in `docs/agents/CODEX_BUILDER.md`
  and `docs/agents/CODEX_REVIEWER.md`.
- **No unauthorized scope change**: diffed this revision against v1 mentally
  section by section — every change traces to one of the four human
  decisions in the 2026-08-18 approval message; nothing else in v1's scope,
  invariants, failure-behavior table, or security requirements was altered.
- **Residual open item, surfaced rather than resolved silently**: the
  docker-compose contract-test-infrastructure default (§17) remains a
  proposal, not a decision the human explicitly addressed this round — it is
  still part of what's being presented for approval, not something this
  self-review upgraded to "resolved" on its own authority.
