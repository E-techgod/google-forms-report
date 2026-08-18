# ADR-008: Form schema mapping representation & drift detection

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

BR-2 (`SPEC.md` §16.2) needs a concrete representation for `FormSchemaMapping`.
`SPEC.md` §10 already requires normalization to fail closed and loudly on schema
drift; the remaining question is the mapping's representation format and whether
drift detection should be proactive or purely reactive.

## Decision

Represent each `FormSchemaMapping` as a versioned, declarative config file (one
per `form_schema_version`) under `config/`, mapping Google Form field IDs to
`NormalizedApplication` attributes with an explicit required/optional flag per
field — never embedded directly in code. For v1, drift detection is **reactive
only**: a live submission's normalization failing closed on a missing required
field (`SPEC.md` §10) *is* the detection mechanism.

## Alternatives considered

- **Proactive polling of the Google Forms API** to diff live field definitions
  against the active mapping on a schedule, alerting before any submission is
  affected: strictly better user experience, but adds a new integration (a Forms
  API read scope, a scheduled job, its own failure handling). Judged unjustified
  complexity for v1 given that reactive failure is already *safe* (no data loss,
  no silent misclassification, `RawFormSubmission` preserved either way) even
  though it's less proactive. Recommend revisiting as a fast-follow once the
  system has real production traffic to justify the extra integration.

## Consequences

A Form field rename is discovered only when it actually breaks a live
submission's normalization — acceptable because the failure mode is safe
(fails closed, alerts per BR-8, submission durably preserved), not silent or
data-losing.

## Dependencies / open items

None blocking. Real mapping content still requires BR-2.
