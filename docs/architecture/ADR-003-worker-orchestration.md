# ADR-003: Worker / orchestration approach

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

`docs/phases/PHASE-01/REVIEW.md` (finding AF-4) already reasoned through this
during the adversarial pass on SPEC.md v1: an earlier draft considered one queue
task per stage transition plus a full workflow-orchestration engine, and rejected
both as unjustified for a linear six-state pipeline. This ADR formalizes that
conclusion rather than leaving it only as a review note.

## Decision

A single resumable worker type, re-entrant per submission, driven entirely by
persisted `SubmissionState` (`SPEC.md` §9). Each worker invocation (one Cloud
Tasks delivery = one attempt) reads current state, executes exactly the next
stage, and returns — it never assumes it owns or must complete the whole pipeline
run in one invocation.

## Alternatives considered

- **Temporal / Cloud Workflows**: durable execution and built-in state
  visibility "for free," at the cost of operating another stateful system
  (Temporal) or committing to a DSL (Cloud Workflows) — unjustified for a linear
  6-state pipeline at expected v1 volume.
- **One Cloud Function/service per stage**: clean separation of concerns, but
  multiplies deployable units, IAM surface, and cold-start overhead for what is
  architecturally one linear flow, not an independently-scaling fan-out.

## Consequences

All resumability logic (the `ReadinessGate` check plus the compare-and-swap
claim) lives in application code, not infrastructure — more application code to
test, less infrastructure to operate. Consistent with the project's stated
preference for simple abstractions over clever ones.

## Dependencies / open items

ADR-001 (claim mechanism requires the persistence layer's conditional-write
support), ADR-002 (delivery mechanism).
