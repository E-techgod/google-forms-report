# ADR-004: LLM provider/model selection

Status: PROPOSED (partial — see below) — pending human approval and BUSINESS
INPUT REQUIRED (docs/phases/PHASE-01)

## Context

Which LLM provider/model Quirón may contractually use for applicant health/
personal data is BR-9 in `SPEC.md` §16 — a business/compliance decision (data-
processing terms, existing vendor contracts) that must not be invented by Claude
or Codex. The `LLMProvider` interface itself (`SPEC.md` §6.9) is provider-
agnostic regardless of which vendor is eventually selected.

## Decision

This ADR does **not** name a vendor. What it does resolve, as pure engineering
scope (not business content):

- v1 is built against exactly one concrete `LLMProvider` adapter — no multi-
  provider fallback (this also resolves AQ-3: no secondary provider for v1;
  revisit only after a real outage incident or an explicit multi-provider
  contractual requirement).
- Development/tests run against a fake/`NullLLMProvider` implementing the same
  interface; it is excluded from selection whenever `ENV=production`
  (`SPEC.md` §6.13).
- If Quirón's compliance posture turns out to forbid sending any applicant data
  to a third-party LLM at all (the BR-9 caveat in `SPEC.md` §16.2), the same
  interface accommodates a deterministic template-only narrative generator as the
  "provider" instead — a new adapter, not an architecture change.

The concrete production adapter (which vendor, which model, how credentials are
obtained) is the one piece of this ADR that stays open pending BR-9.

## Alternatives considered

Not applicable to vendor selection (business decision, out of scope for this
document). For the *shape* of the fallback path: always requiring a live LLM call
even without a confirmed provider was rejected, since it would force inventing a
placeholder vendor relationship rather than genuinely deferring.

## Consequences

Narrative-stage code (context building, schema validation, semantic validation —
`SPEC.md` §6.6–§6.8) can be fully written and tested now against the interface
and a fake. Only the production adapter implementation and its credentials wait
on BR-9.

## Dependencies / open items

`BUSINESS INPUT REQUIRED` — BR-9 (provider/model + contractual/compliance
clearance) before the production adapter can be implemented or selected.
