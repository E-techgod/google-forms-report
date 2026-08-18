# ADR-001: Persistence technology

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

The architecture requires: (a) atomic conditional writes for the stage-level
compare-and-swap claim mechanism (`SPEC.md` §9/§10 — `UPDATE ... WHERE status =
expected`), (b) a relational structure across seven append-only entity types
linked by `submission_id` (`SPEC.md` §6.3), and (c) audit/reconstruction queries
that must remain possible indefinitely (INVARIANT 15).

## Decision

Cloud SQL for PostgreSQL.

`UPDATE submission_state SET status = $new WHERE submission_id = $id AND status =
$expected` (checking rows-affected = 1) is a well-understood, transactional claim
primitive. The seven entities' foreign-key relationships (all keyed off
`submission_id`) map directly onto relational tables, and reconstructing a
historical report (INVARIANT 15) is a straightforward join, not a
denormalization exercise.

## Alternatives considered

- **Firestore**: serverless, no connection-pooling/VPC-connector overhead, native
  fit for Cloud Run. Its transaction model (optimistic concurrency, retry-on-
  contention) works but is a less direct fit for the blocking compare-and-swap
  pattern this design already assumes, and modeling seven relationally-linked
  append-only entity types fights a document store more than it helps.
- **Cloud Spanner**: strictly more capable (global consistency, horizontal scale)
  but unjustified cost/operational complexity for expected v1 volume; nothing in
  the requirements points to multi-region or very-high-write-throughput needs.

## Consequences

Cloud Run workloads need a Cloud SQL Auth Proxy sidecar (or the Cloud SQL
connector library) and, if using a private IP, a VPC connector — a real but
well-documented operational cost, not a novel one.

## Dependencies / open items

ADR-000 (GCP hosting).
