# PHASE-02 — Technical Skeleton

## Feature

Implement the architecture from Phase 1 as a complete technical skeleton using fake/in-memory adapters and no real business content.

---

## Goal

Create working application structure, domain models, interfaces, workflow logic, configuration boundaries, and tests so later phases can replace fake adapters with real infrastructure without redesigning the core system.

---

## Scope

Implement:

* repository/package structure;
* typed domain models;
* normalization boundary;
* `RuleEngine` interface;
* `NarrativeContext` builder;
* client/internal report-context builders;
* semantic-validator interface;
* state-transition validator;
* configuration models;
* per-stage `ReadinessGate`;
* repository interfaces;
* queue interface;
* `LLMProvider` interface;
* `ReportRenderer` interface;
* `EmailSender` interface;
* `SecretProvider` interface;
* fake/in-memory implementations;
* webhook receiver;
* resumable worker;
* thin `main.py`;
* unit, contract, readiness, and workflow tests.

The complete workflow must be runnable locally using synthetic data and fake adapters only.

---

## Do Not Change

Do not introduce:

* real Quirón classification rules;
* real Form mapping content;
* final report/narrative content;
* real recipients;
* real retention policy;
* real LLM provider;
* real infrastructure credentials;
* real Cloud SQL calls;
* real Cloud Tasks calls;
* real Gmail calls;
* real Secret Manager calls;
* tests requiring external network access.

Do not change the architecture established in Phase 1.

---

## Requirements

### Models

Implement typed representations for:

* `RawFormSubmission`;
* `NormalizedApplication`;
* `Assessment`;
* `NarrativeContext`;
* `Narrative`;
* `Report`;
* `Delivery`;
* `SubmissionState`.

### Business boundaries

`RuleEngine` must support deterministic versioned rules but contain no real business rules yet.

Missing real rule configuration must fail closed rather than invent a classification.

### Context boundaries

Narrative and client-report context builders must use explicit allow-lists.

Default client-facing configuration must under-share rather than accidentally expose internal data.

### State machine

Implement the Phase 1 lifecycle and transition validator as the single authority for valid transitions.

### Configuration

Provide schemas/config points for:

* rules;
* Form mapping;
* narrative/report templates;
* client allow-list;
* recipients;
* alerts;
* retention;
* retry policy;
* LLM provider configuration.

Required production configuration must fail closed when missing or unapproved.

Raw submission ingestion must continue even when downstream configuration is absent.

### Adapters

Every external dependency must have an interface and a fake/in-memory implementation sufficient for testing.

### Workflow

The worker must:

1. read persisted state;
2. determine the next stage;
3. claim work safely;
4. execute one stage;
5. persist the result;
6. support safe retry/resume.

---

## Edge Cases

Tests must cover at minimum:

* duplicate submission;
* invalid state transition;
* missing rule configuration;
* missing schema configuration;
* missing provider configuration;
* missing recipient configuration;
* unapproved prompt/template configuration;
* duplicate/concurrent stage claim;
* simulated LLM failure;
* simulated PDF failure;
* simulated email failure;
* simulated persistence/workflow interruption;
* crash after one stage commits but before the next begins;
* retry/resume without repeating completed work;
* client-context leakage;
* sensitive data appearing in logs.

All test data must be synthetic.

---

## Acceptance

Phase 2 is complete when:

* all required models and interfaces exist;
* domain code runs without network access or credentials;
* fake/in-memory adapters satisfy their contracts;
* missing configuration fails closed correctly;
* ingestion still works when downstream configuration is absent;
* a synthetic submission completes the entire pipeline using fakes;
* duplicate submissions do not repeat processing;
* concurrent claims cannot execute the same logical stage twice;
* crash-and-resume continues from persisted state;
* client context does not expose internal fields;
* sensitive synthetic values do not appear in logs;
* completed artifacts remain reconstructable from stored metadata;
* the complete test suite passes.

---

## Open Decisions

No new architectural decision should be required for this phase.

Business values remain intentionally deferred:

* classification rules;
* actual Form mapping;
* narrative/report content;
* client allow-list;
* recipients;
* retention;
* final retry/SLA policy;
* alert destination;
* LLM provider/model;
* production-volume assumptions.

If implementation reveals that the approved architecture cannot support one of these requirements cleanly, stop that specific work and surface the architecture conflict instead of silently redesigning the system.
