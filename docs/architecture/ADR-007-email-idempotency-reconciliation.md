# ADR-007: Email idempotency / reconciliation strategy

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

`docs/phases/PHASE-01/REVIEW.md` finding AF-2: Gmail's API has no native
idempotency-key mechanism. A crash between "Gmail accepted the send" and "we
recorded the `Delivery` row as sent" risks a duplicate send on naive retry — a
direct violation of INVARIANT 2.

## Decision

Before sending, set a deterministic custom header on the outgoing message (e.g.
`X-Submission-Delivery-Id: <submission_id>:<report_type>:<recipient>`). On any
retry of a `DELIVERY_FAILED` or ambiguous-crash case, search the sending mailbox
via the Gmail API for a message carrying that header before calling send again;
only send if no match is found.

## Alternatives considered

- **Blind retry, accept the rare duplicate-send risk**: simplest, but is a
  direct, avoidable violation of an explicit invariant in a real (if narrow)
  crash window — rejected because INVARIANT 2 leaves no room for "usually fine."
- **Two-phase commit with Gmail**: not offered by the Gmail API; not actually
  available as an option.

## Consequences

Adds one extra Gmail API read (search) per *retry* attempt only — the first send
attempt for a given recipient incurs no extra call. Negligible cost relative to
the correctness guarantee gained.

## Dependencies / open items

ADR-006 (Gmail sending mechanism).
