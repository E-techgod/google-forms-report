# ADR-010: Rule-version enforcement mechanism

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

INVARIANT 8 requires any rule-logic change to bump `rule_version`, but nothing in
the architecture as specified in `SPEC.md` v1 stops a developer from editing rule
content without bumping the version. This is the same category of risk as
`docs/phases/PHASE-01/REVIEW.md` finding AF-6 (the `approved_for_production` flag
relying on review discipline rather than a mechanical check).

## Decision

A CI check computes a content hash of each registered ruleset's logic/config and
compares it against a hash committed alongside that ruleset's declared
`rule_version`; a mismatch (content changed, version didn't) fails the build. The
same mechanism applies to `prompt_version` and `template_version`
(`SPEC.md` §6.10), and is the concrete answer to AF-6's open question of how the
`approved_for_production` flag gets review-process backing: flipping that flag on
a version whose content hash doesn't match its last-approved hash also fails CI.

## Alternatives considered

- **Manual code-review discipline only**: relies on a human remembering every
  time — precisely the failure mode INVARIANT 8 exists to prevent. Rejected as
  the *sole* mechanism, though review remains valuable in addition to, not
  instead of, the automated check.

## Consequences

Adds a CI step. Ruleset/prompt/template authors must understand that any content
edit requires an explicit version bump or the build fails — this friction is the
intended behavior, not a defect.

## Dependencies / open items

None blocking. Must exist before the first real rule/prompt/template content
(BR-1/BR-3) is committed, not necessarily before the skeleton itself.
