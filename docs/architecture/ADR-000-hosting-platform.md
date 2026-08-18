# ADR-000: Hosting platform

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

`docs/PROMPT.md`'s required failure matrix explicitly names "Cloud Run restart"
and "deployment during processing" as cases the architecture must handle — a
strong signal that Google Cloud Run was already assumed by whoever wrote that
document, though it has never been formally confirmed (SPEC.md AQ-1). The system
also already depends on two other Google products (Google Forms as source, Gmail
as delivery channel), which weighs toward a Google-centric stack.

## Decision

Recommend Google Cloud Run as the compute host for v1: one Cloud Run service
receiving the Google Forms webhook, one Cloud Run service (or a second entrypoint
on the same image) acting as the Cloud Tasks push-target worker (see ADR-002).

## Alternatives considered

- **AWS Lambda/Fargate + SQS**: technically viable, but mixing clouds when the
  source (Forms) and delivery channel (Gmail) are both Google products adds a
  second IAM system, a second secrets store, and cross-cloud networking for no
  corresponding benefit.
- **A single long-lived VM/VPS**: conceptually simpler, but reintroduces "handle
  process restart / redeploy without losing in-flight work" as something the
  application must solve entirely itself, without Cloud Run's managed
  restart/redeploy semantics or autoscaling.

## Consequences

Persistence, queue, and secrets choices (ADR-001, ADR-002, ADR-009) default to
GCP-native services unless a specific reason argues otherwise.

## Dependencies / open items

None blocking. Foundational for ADR-001, ADR-002, ADR-006, ADR-009. Worth a direct
confirmation with whoever specified "Cloud Run" in the original requirements,
since it may already be a settled decision outside this document.
