# ADR-006: Gmail sending mechanism

Status: PROPOSED — pending human approval and an operational dependency
(docs/phases/PHASE-01)

## Context

`docs/PROMPT.md` and `docs/INVARIANTS.md` both name Gmail specifically (not
"email" generically) as the delivery channel — treated here as a given
constraint, not an open choice. What remains open is only the sending/auth
mechanism.

## Decision

Gmail API via a Google Workspace service account with domain-wide delegation,
impersonating a dedicated sending mailbox (a service address, not a named
individual's inbox).

## Alternatives considered

- **OAuth token tied to a human's personal mailbox**: fragile — token/consent
  lifecycle tied to an individual employee's account, and sending automated mail
  "as a person" is a poor operational fit for a production pipeline.
- **A transactional email API (SendGrid/SES) instead of Gmail directly**:
  contradicts the explicit "Gmail" requirement in the source documents; would
  also require reconciling with `docs/INVARIANTS.md`, which was not raised as a
  live option.

## Consequences

Requires Quirón's Workspace administrator to provision the service account and
grant domain-wide delegation before the adapter can send anything — an
operational/IT dependency, not a coding task, and not something this document can
resolve on its own.

## Dependencies / open items

Quirón IT provisioning (operational; flagged, not invented). Which mailbox/
domain sends, and who else is cc'd, is part of BR-5 (`SPEC.md` §16.2).
