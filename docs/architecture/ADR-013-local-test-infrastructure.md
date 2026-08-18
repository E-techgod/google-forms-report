# ADR-013: Local development/test infrastructure mechanism

Status: APPROVED — human approval 2026-08-18 (`docs/phases/PHASE-03`)

## Context

PHASE-03 SPEC.md §17 needed a concrete mechanism for exercising the real
persistence adapter (ADR-001, SQLAlchemy 2.x + Alembic per this phase's
2026-08-18 decision) against something genuinely Postgres-wire-compatible,
without requiring a live Cloud SQL instance or any GCP credential for
automated tests to run (PHASE-03 SPEC.md §4, §14 acceptance criterion 9).
The same need extends to any later phase that tests a real adapter locally.

## Decision

Docker Compose is the default local development/integration/contract-test
infrastructure mechanism for PHASE-03 and, unless a later ADR says otherwise,
for later phases with the same real-adapter contract-testing need. A
`docker-compose.yml` (plus any companion test-only env file) provisions a
local Postgres instance that PHASE-03's persistence contract tests (and
local development via `main.py`) run against.

This decision carries five binding constraints, all part of the approval:

1. Compose is development/test infrastructure only, not production
   orchestration. It has no role in how the application is actually deployed
   or run in production.
2. Production architecture remains governed by the approved Cloud Run/GCP
   ADRs (ADR-000 hosting, ADR-001 persistence, ADR-002 queue, ADR-003
   worker orchestration, ADR-009 secrets) — unchanged and unaffected by this
   decision.
3. Compose-based tests must run without live GCP credentials — consistent
   with PHASE-03 SPEC.md §4's existing requirement that no automated test in
   this phase depends on a real cloud service.
4. No production secret or sensitive value may be committed into Compose
   configuration (`docker-compose.yml` or any associated env file) — only
   synthetic/local-only test credentials for the Compose-provisioned
   Postgres instance may appear, same discipline ADR-009 already applies to
   real secrets, extended here to local test config.
5. Local test infrastructure must remain replaceable and must not leak
   Docker-specific assumptions into domain/workflow contracts. Nothing under
   `src/domain/`, `src/workflows/`, or any Protocol in
   `src/persistence/interfaces.py` may assume Compose's network naming,
   Compose's env-file mechanism, or any other Compose-specific detail — the
   persistence adapter receives its connection configuration the same way
   any other environment configuration is injected (`AppConfig`/
   `SecretProvider`), so that swapping Compose for a different local-test
   mechanism later requires no change above the adapter boundary.

## Alternatives considered

- **A Python-only embedded/in-memory Postgres-compatible engine**: avoids a
  Docker dependency entirely, but is not genuinely wire-compatible enough to
  validate the actual Cloud SQL Postgres behavior ADR-001 depends on
  (e.g. real transactional `UPDATE ... WHERE` semantics for the
  compare-and-swap claim) — rejected as testing a different database in
  spirit, not the one being shipped against.
- **`testcontainers` library-managed containers with no committed Compose
  file**: a viable, closely related approach — and not excluded as an
  implementation detail Codex Builder may use *underneath* Compose-defined
  images if convenient. What this ADR decides is that the checked-in,
  documented, human-legible mechanism is Compose, not that every container
  lifecycle call must go through the `docker compose` CLI specifically.

## Consequences

Contributors and CI need Docker available locally to run persistence
contract tests; PHASE-03 SPEC.md §17 already flagged this as something to
surface early (during checkpoint 1) if this project's actual CI pipeline
cannot run Docker. No production deployment artifact or process depends on
Compose. The five constraints above are treated as acceptance-relevant for
any checkpoint that touches Compose configuration, not merely aspirational.

## Dependencies / open items

ADR-001 (persistence technology — Cloud SQL Postgres, the property Compose's
local Postgres instance is standing in for), ADR-009 (secrets management —
the discipline constraint 4 extends to local test config). None blocking.
