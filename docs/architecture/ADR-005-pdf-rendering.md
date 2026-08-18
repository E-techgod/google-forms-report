# ADR-005: PDF rendering approach

Status: PROPOSED — pending human approval (docs/phases/PHASE-01)

## Context

Report templates are versioned independently of code (`SPEC.md` §6.10,
`template_version`), which favors authoring templates in a markup format over a
purely programmatic PDF-drawing API — Quirón-approved copy (BR-3) will change on
its own schedule, separate from application releases. The project's toolchain is
already Python (`pyproject.toml`, `uv.lock`).

## Decision

HTML/CSS templates (Jinja2) rendered to PDF via WeasyPrint: pure-Python, no
external browser binary dependency, and sufficient CSS support for a document-
style insurance report (not a pixel-perfect design surface).

## Alternatives considered

- **Headless-Chrome printing (Playwright/Puppeteer)**: meaningfully better CSS/
  layout fidelity, but adds a browser binary to the container image and a
  heavier runtime — unjustified unless approved template content (BR-3) turns
  out to need CSS features WeasyPrint doesn't support.
- **ReportLab**: full programmatic control, no HTML/CSS layer — but template
  changes become code changes, working against BR-3's need for report content to
  be revisable independently of the pipeline.

## Consequences

Report templates become versioned, independently reviewable assets, consistent
with how prompt templates are already treated (`SPEC.md` §6.10).

## Dependencies / open items

None blocking. Revisit only if WeasyPrint proves insufficient once real template
content (BR-3) exists.
