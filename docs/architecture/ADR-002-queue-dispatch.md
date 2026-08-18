# ADR-002: Queue / dispatch technology

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

The system needs a point-to-point work queue — one producer (the webhook), one
consumer type (the worker) — with per-task retry/backoff, not a fan-out/multi-
subscriber pattern.

## Decision

Cloud Tasks, HTTP push to the worker's Cloud Run endpoint (OIDC-authenticated),
with per-queue retry/backoff configuration aligned to the `RetryPolicy` config
point (`SPEC.md` §16.2, BR-7 / ADR-011).

## Alternatives considered

- **Pub/Sub**: built for fan-out to multiple independent subscribers. This system
  has exactly one consumer type per submission; Pub/Sub's additional concepts
  (subscriptions, ack deadlines, separately configured dead-letter topics) add
  complexity with no corresponding benefit here.
- **DB-polling worker with no managed queue**: removes a moving part, but
  reimplements retry/backoff/visibility-timeout logic Cloud Tasks already
  provides, and loses built-in rate-limiting — useful for absorbing the Gmail
  quota failure case (`SPEC.md` §10) without a bespoke limiter.

## Consequences

The worker Cloud Run service must accept authenticated push requests from Cloud
Tasks rather than independently polling for work.

## Dependencies / open items

ADR-000 (GCP hosting).
