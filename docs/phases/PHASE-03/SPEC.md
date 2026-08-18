# PHASE-03 — Real Infrastructure Adapters

## Feature

Replace Phase 2's fake infrastructure adapters with production-facing implementations while preserving the existing domain, workflow, state-machine, and interface contracts.

---

## Goal

Connect the existing technical skeleton to real infrastructure technologies without redesigning the application core.

Real adapters must remain interchangeable with their Phase 2 fakes.

This phase implements infrastructure-facing code and local contract testing. It does not provision production cloud resources.

---

## Scope

Implement:

### Persistence

PostgreSQL persistence using:

* SQLAlchemy 2.x;
* Alembic migrations;
* existing repository interfaces;
* append-only historical entities;
* mutable `SubmissionState`;
* atomic compare-and-set stage claims.

SQLAlchemy must remain isolated inside the Postgres persistence implementation.

### Queue

Implement:

* Cloud Tasks producer;
* HTTP worker push endpoint;
* OIDC verification before processing;
* one task delivery = one worker stage attempt.

### Secrets

Implement the existing `SecretProvider` against Google Secret Manager.

### PDF

Implement `ReportRenderer` using Jinja2 + WeasyPrint.

### Gmail

Implement `EmailSender` using the Gmail API.

Delivery idempotency must use:

`X-Submission-Delivery-Id: <submission_id>:<report_type>:<recipient>`

Before retrying a send:

1. search for an existing message with the delivery ID;
2. send only when no previous message is found;
3. if reconciliation/search fails, do not blindly send again.

### Form schema

Implement loading of versioned `FormSchemaMapping` files.

Real Form mapping content remains outside this phase.

### Adapter selection

Real vs. fake adapters must be selected through configuration, not code modification.

### Packaging

Add:

* application `Dockerfile`;
* Cloud Run deployment configuration;
* Docker Compose for local development/integration/contract testing.

Docker Compose is local/test infrastructure only and must not become an application or production architecture dependency.

---

## Do Not Change

Do not change:

* domain models;
* existing adapter Protocol signatures;
* workflow contracts;
* state-machine transitions;
* classification behavior;
* retry taxonomy;
* business rules;
* client/internal report boundaries.

Do not:

* implement the real LLM provider;
* add real business content;
* provision live cloud infrastructure;
* perform automated tests against live GCP/Gmail resources;
* expose SQLAlchemy outside the Postgres adapter;
* place production secrets in source, Docker, Compose, test fixtures, or configuration;
* introduce Docker/Compose-specific assumptions into domain or workflow code.

If a real service cannot satisfy an existing interface without a material architecture change, surface the conflict instead of silently changing the interface.

---

## Requirements

### Persistence

The real database must preserve the same contract as the fake repositories.

Concurrency protection must be proven against actual concurrent Postgres connections, not only Python-level mocks.

Historical entities remain append-only.

### Queue security

Every Cloud Tasks worker request must validate its OIDC token before persistence or business processing occurs.

Invalid or missing authentication is rejected.

### Failure handling

Real adapter failures must map to the existing retry/failure model rather than introduce a second workflow system.

### Gmail idempotency

Retries must never blindly resend when delivery status is uncertain.

Search/reconciliation failure must fail safe.

### Security

Credentials come from Secret Manager.

Do not log:

* raw Form answers;
* narrative context;
* LLM bodies;
* report contents;
* email bodies;
* plaintext recipient information beyond approved correlation metadata;
* secrets.

### Local test infrastructure

Docker Compose may provide local infrastructure such as PostgreSQL for contract tests.

It must:

* use synthetic/local credentials only;
* remain replaceable;
* not change production architecture;
* not leak into domain/workflow contracts.

---

## Edge Cases

Cover at minimum:

* concurrent Postgres stage claims;
* Postgres timeout/disconnection;
* append-only mutation attempt;
* Cloud Tasks retry/redelivery;
* missing OIDC token;
* invalid OIDC token;
* Secret Manager failure;
* WeasyPrint rendering failure;
* malformed template/context;
* Gmail transient failure;
* Gmail quota/rate limit;
* Gmail send succeeded but acknowledgement was lost;
* Gmail reconciliation/search failure;
* duplicate email retry;
* worker restart;
* adapter configuration mismatch;
* missing credentials;
* Docker/local environment configuration differences;
* regression from fake-backed behavior.

Transient infrastructure failures may retry through the existing bounded retry system.

Authentication, unsafe reconciliation, and invalid configuration failures must fail closed rather than retry blindly.

---

## Acceptance

Phase 3 is complete when:

* every real adapter implements its existing interface without signature drift;
* real/fake selection is configuration-driven;
* Postgres passes the existing repository contracts;
* real concurrent Postgres claims prove at-most-once stage ownership;
* append-only semantics are preserved;
* SQLAlchemy remains isolated to the persistence adapter;
* Cloud Tasks requests are authenticated before processing;
* Secret Manager values are never exposed in logs;
* WeasyPrint produces valid PDFs for client and internal contexts;
* Gmail idempotency and search-before-send behavior are proven by contract tests;
* a synthetic workflow completes using real/local adapters wherever live credentials are unnecessary;
* the Phase 2 fake-backed suite continues to pass;
* automated tests require no live GCP or Gmail credentials;
* the Docker image builds and starts locally;
* Docker Compose remains local/test-only infrastructure;
* no existing domain, workflow, state-machine, or invariant contract was weakened to accommodate an adapter.

---

## Open Decisions

Still outside this phase:

* final LLM provider/model and contractual approval;
* real Google Form mapping content;
* production business rules/content;
* production recipients;
* production alert destination;
* production retention policy;
* final production retry/SLA values;
* actual GCP resource provisioning;
* Gmail Workspace service-account/domain-wide-delegation provisioning;
* staging/live infrastructure validation.

Already decided for this phase:

* PostgreSQL;
* SQLAlchemy 2.x;
* Alembic;
* Cloud Tasks;
* Google Secret Manager;
* Jinja2 + WeasyPrint;
* Gmail API;
* Cloud Run production direction;
* Docker Compose for local integration/contract testing only.
