# ADR-011: Retry budget and backoff defaults

Status: PROPOSED — pending human approval and BUSINESS INPUT (BR-7)
(docs/phases/PHASE-01)

## Context

AQ-9/AQ-7 in `SPEC.md`: §9.4 already proposes a placeholder retry budget (5
attempts) pending BR-7 (the real SLA). This ADR fixes the v1 default and its
shape so the skeleton has something concrete to run against.

## Decision

Confirm the placeholder as the v1 default: 5 attempts per stage, exponential
backoff (approximately 30s, 2m, 10m, 30m, 2h, capped), after which the
submission transitions to `FAILED_PERMANENT` and alerts fire (BR-8). Gmail-
specific rate-limit failures use a distinct, longer, quota-aware backoff schedule
rather than the generic one (`SPEC.md` §10, "Gmail quota/rate limit" row) — a
transient-timeout schedule retried against a quota error just re-triggers the
same quota error.

## Alternatives considered

- **Unbounded retry**: rejected — a stuck submission must eventually surface to
  a human (BR-8), not retry invisibly forever; unbounded retry defeats that.
- **A single shared backoff schedule for every failure type**: simpler, but
  conflates "transient blip, retry soon" with "quota exhausted, retrying soon is
  pointless" — rejected as imprecise and wasteful of retry budget.

## Consequences

These exact numbers are an engineering placeholder, explicitly not a business
SLA commitment, until BR-7 is confirmed.

## Dependencies / open items

`BUSINESS INPUT REQUIRED` — BR-7 (confirm or replace these numbers before
claiming any SLA in production; not required before building/testing against the
placeholder).
