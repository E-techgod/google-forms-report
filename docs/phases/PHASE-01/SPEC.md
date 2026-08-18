# PHASE-01 — Architecture Foundation

## Feature

Define the production-safe architecture for the Google Forms → insurance report pipeline before implementation begins.

---

## Goal

Establish the minimum architecture needed for the system to be:

* reliable;
* deterministic where business decisions are involved;
* resumable after failures;
* idempotent;
* auditable;
* secure with sensitive applicant data;
* testable without external services;
* easy to extend without changing core domain logic.

No application code is implemented in this phase.

---

## Scope

Define:

* domain boundaries;
* submission → report → delivery data lifecycle;
* processing state machine;
* persistence boundaries;
* idempotency strategy;
* async webhook/worker architecture;
* deterministic classification boundary;
* LLM boundary;
* internal vs. client report boundary;
* adapter interfaces;
* configuration/readiness boundaries;
* versioning;
* observability;
* test strategy;
* repository structure.

Core lifecycle:

`RawFormSubmission → NormalizedApplication → Assessment → Narrative → Report → Delivery`

Processing flow:

`Google Form → Webhook → Persist → Enqueue → Worker → Normalize → Classify → Narrative → PDF → Deliver`

The webhook must persist the submission and return quickly. Downstream work is asynchronous, resumable, and driven from persisted state.

---

## Do Not Change

The architecture must preserve these boundaries:

* Business classification is deterministic and never decided by an LLM.
* The LLM generates narrative only.
* Raw submissions are immutable.
* Completed stage outputs are not silently overwritten.
* Client-facing data is built from an explicit allow-list.
* External failures must not cause submission loss.
* Retries must not create duplicate processing, reports, or deliveries.
* Sensitive form answers, prompts, reports, and credentials must not appear in logs.
* Domain logic must not depend on network services, credentials, infrastructure SDKs, or adapters.
* Business rules must not be invented by engineering.

---

## Requirements

### Domain

Pure domain logic includes:

* normalization;
* deterministic classification;
* state-transition validation;
* narrative-context construction;
* report-context construction;
* semantic validation.

Infrastructure is accessed only through adapters.

### State

Primary successful lifecycle:

`RECEIVED → NORMALIZED → CLASSIFIED → NARRATIVE_READY → REPORTS_READY → COMPLETED`

Failures must preserve the last durable successful state and support bounded retry when appropriate.

Terminal states include:

* `COMPLETED`;
* `REJECTED_DUPLICATE`;
* `REJECTED_INVALID`;
* `FAILED_PERMANENT`.

### Idempotency

The architecture must prevent duplicate effects from:

* duplicate Form events;
* queue redelivery;
* worker retry;
* LLM retry;
* PDF retry;
* email retry.

Delivery is tracked independently per recipient.

### LLM

The LLM may receive only an explicit `NarrativeContext`.

It must not:

* create or modify classification;
* create or remove deterministic flags;
* infer unsupported medical facts;
* make underwriting decisions.

LLM output must pass schema validation and semantic grounding checks before use.

### Reports

`ClientReportContext` and `InternalReportContext` are constructed separately.

The client context is allow-list based and must never expose internal rule metadata, provider metadata, or other internal-only fields.

### Configuration

Business-controlled values must be explicit, versioned configuration rather than hardcoded assumptions.

Production stages fail closed when required approved configuration is missing.

Missing downstream configuration must never prevent the raw submission from being accepted and persisted.

### Versioning

Track independently:

* form schema version;
* rule version;
* prompt version;
* template version;
* application release version.

---

## Edge Cases

The architecture must safely handle:

* duplicate submissions;
* malformed payloads;
* missing required fields;
* missing optional fields;
* Google Form schema changes;
* missing/unapproved configuration;
* LLM timeout;
* malformed LLM output;
* unsupported/hallucinated narrative claims;
* provider outage;
* PDF failure;
* Gmail failure;
* Gmail quota/rate limits;
* partial delivery;
* worker/process restart;
* deployment during processing;
* queue redelivery;
* persistence failure.

General rule:

> Retry transient failures without repeating already-completed side effects. Fail closed on invalid configuration, invalid input, security failures, or untrusted output.

---

## Acceptance

Phase 1 is complete when:

* domain and infrastructure boundaries are clearly defined;
* the data lifecycle and state machine are defined;
* retry/idempotency behavior is defined;
* LLM classification isolation is structurally defined;
* client/internal information boundaries are defined;
* important failure cases have defined behavior;
* sensitive-data boundaries are defined;
* business-controlled values have explicit configuration points;
* repository boundaries are defined;
* no unresolved engineering decision is being silently assumed;
* no application implementation code has been introduced.

---

## Open Decisions

These do not block the architecture but must be resolved before the affected production behavior is enabled:

* Quirón classification/rule content;
* real Google Form field mapping and required fields;
* final narrative/report copy and disclaimers;
* final client-report field allow-list;
* delivery recipients/routing;
* data-retention policy;
* production retry/SLA targets;
* human-alert destination;
* LLM provider/model and contractual/privacy approval;
* expected production volume/capacity requirements.

If the real Google Form requires binary/file uploads or legal/privacy requirements prohibit sending applicant data to a third-party LLM, revisit the affected architecture before implementation.
