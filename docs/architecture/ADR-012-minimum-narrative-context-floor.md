# ADR-012: Minimum viable NarrativeContext floor

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

`docs/phases/PHASE-01/REVIEW.md` §5 (edge-case review, AQ-9): a submission with
almost no narrative-eligible fields populated risks the LLM being asked to
narrate from a near-empty context — which raises hallucination risk (finding
AF-1) rather than lowering it, since a starved prompt gives the model more room
to fill gaps with plausible-sounding but ungrounded content.

## Decision

Add a configurable `MIN_NARRATIVE_CONTEXT_FIELDS` threshold. If the count of
populated (non-null) allow-listed fields in a built `NarrativeContext` falls
below the threshold, skip the LLM call entirely and use a deterministic, fixed
fallback narrative (referencing only `assessment.qualification`/`reasons`, no
LLM involved) instead of ever sending a starved prompt. Default threshold for
v1: **0** (mechanism present, but inert) until real form field composition
(BR-2) is known and a meaningful number can be set — this default does not
invent a business judgment about "how much is enough," it just wires the escape
hatch so one can be set later without a design change.

## Alternatives considered

- **Always call the LLM regardless of context size**: simplest, but directly
  worsens the exact hallucination risk AF-1 already flags as the weakest
  invariant enforcement in the design — rejected as compounding a known risk by
  policy rather than mitigating it.
- **Block the submission entirely on thin context**: too aggressive — a sparse
  but otherwise valid application shouldn't stall the whole pipeline over a
  narrative-quality concern; classification and delivery can still proceed with
  the deterministic fallback narrative.

## Consequences

The deterministic fallback narrative path must exist as code regardless of which
LLM provider is eventually selected (ADR-004) — effectively a second,
template-only narrative source used specifically for the below-threshold case.

## Dependencies / open items

Threshold value (what "enough" means) is pending BR-2 (real field set) — not a
new business item, an application of BR-2 once it exists.
