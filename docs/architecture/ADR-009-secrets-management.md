# ADR-009: Secrets management approach

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

LLM API credentials, Cloud SQL credentials, and the Gmail service-account key
must never be committed or logged (INVARIANT 12).

## Decision

Google Secret Manager, referenced by Cloud Run service configuration (mounted as
environment variables or accessed via the client library at startup), with
IAM-scoped access per individual secret.

## Alternatives considered

- **Encrypted config files committed to the repo**: rejected outright regardless
  of encryption — it directly conflicts with INVARIANT 12, since the decryption
  key itself becomes the new secret-management problem, unsolved.
- **A third-party secrets vault (e.g. HashiCorp Vault)**: adds an operational
  component to run and secure, with no advantage over the platform-native option
  given ADR-000 (GCP hosting).

## Consequences

None beyond standard secret-rotation practice, which is an operational runbook
concern, not an architectural one.

## Dependencies / open items

ADR-000 (GCP hosting).
