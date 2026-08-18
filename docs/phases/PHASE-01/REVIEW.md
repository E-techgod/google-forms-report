# PHASE-01 — Review

## 1. Review target

- Phase number: 01
- Spec version reviewed: SPEC.md v3 (v2's §6.13 fail-closed config design and §16
  business-item reclassification, plus §17 now indexing 13 PROPOSED ADRs under
  `docs/architecture/`)
- Implementation commit/diff reviewed: N/A — no implementation exists in this
  phase.
- Reviewer role: Claude, adversarial self-review of its own proposed architecture
  (no Codex Reviewer activity — not authorized for this phase).

## 2. Spec compliance

Not applicable in the usual sense (there is no implementation to check against the
spec). Instead this section checks SPEC.md against the requirements in
`docs/PROMPT.md`:

| PROMPT.md requirement | Status |
|---|---|
| Domain boundaries (pure vs. infra) | Satisfied — §6.1 |
| System invariants | Satisfied — §8 maps all 15 |
| Data lifecycle | Satisfied — §6.3 |
| Processing state machine | Satisfied — §9 |
| Idempotency | Satisfied — see §10 rows, plus AF-3 below (residual gap identified) |
| Persistence | Satisfied — §6.3 entity list, deliberately non-specific on DDL |
| Async execution | Satisfied — §6.2 diagram + narrative |
| Failure analysis | Satisfied — §10 covers all 17 listed cases |
| Classification engine | Satisfied — §6.5, rule content correctly deferred as BR-1 |
| LLM boundary | Satisfied — §6.6, §6.8 |
| Information boundaries | Satisfied — §6.7 |
| Provider strategy | Satisfied — §6.9, single-provider v1 recommendation made explicitly |
| Versioning | Satisfied — §6.10 |
| Observability | Satisfied — §6.11 |
| Test architecture | Satisfied — §15 |
| ADR list | Partially satisfied in SPEC (AQs named); explicit ADR backlog is below in this file |
| Repository structure | Satisfied — §6.12 |

## 3. Invariant review

Walking `docs/INVARIANTS.md` individually against the architecture in SPEC.md:

1. **At most once logically** — Held, via stage-level compare-and-swap claims
   (§9/§10). Caveat: "logically" is doing real work here — see AF-3 (email
   send is at-least-once at the network layer; logical dedup is best-effort, not
   guaranteed, for that one specific case).
2. **Retry never duplicates delivery** — Held for all stages except the exact
   crash window described in AF-2/AF-3. Flagged, not silently assumed solved.
3. **LLM never decides/modifies classification** — Held structurally (§6.6): no
   code path writes LLM output into `Assessment`. This is the strongest invariant
   in the design because it doesn't depend on the model behaving — it depends on a
   function signature that doesn't exist.
4. **Client reports exclude internal metadata** — Held via allow-list construction
   (§6.7). Risk: BR-4 (which fields count as "internal-only") isn't answered yet,
   so the boundary's *shape* is right but its *content* is unverified until Quirón
   confirms.
5. **Internal reports may include client-facing info** — Trivially held (superset
   by construction).
6. **Classification explainable by triggered rules** — Held by `Assessment`
   contract (§7.3) — but only as strongly as rule implementations are actually pure
   and complete. Nothing in the architecture *forces* every rule to populate
   `reason`; that's a code-review-time check for the eventual implementation phase,
   not something this architecture can guarantee on its own. Documented as a gap,
   not silently assumed.
7. **Raw submissions immutable** — Held (§6.3, no update path defined).
8. **Rule changes require new version** — Held as a contract requirement; *enforcement*
   (CI check) is named as ADR-010 but not designed in detail — acceptable for this
   phase, must not be forgotten in implementation.
9. **Model/provider changes can't alter classification** — Held for the same
   structural reason as #3.
10. **No facts absent from source/rules** — Partially held. Schema validation is
    solid; the semantic grounding check (§6.8) is explicitly a deny-list
    heuristic, not a proof. This is the weakest invariant enforcement in the whole
    design and is called out below as AF-1.
11. **External failure ≠ data loss** — Held, provided `RawFormSubmission` is
    durably persisted before the HTTP response is returned (§6.2) — this ordering
    is load-bearing and must not be weakened during implementation (e.g. by
    someone "optimizing" the webhook to enqueue before persisting, for latency).
12. **Secrets never committed/logged** — Held as a requirement (§11); nothing in
    this phase creates secrets, so nothing to verify yet beyond the requirement
    itself.
13. **Sensitive form data never logged** — Held as a requirement (§11, §6.11 event
    list contains no payload fields).
14. **No email before artifact exists** — Held structurally: the state machine
    (§9.2) has no transition from `NARRATIVE_READY`/earlier directly into a
    delivery outcome; `REPORTS_READY` is a hard prerequisite.
15. **Reconstructable from stored metadata** — Held via append-only entities +
    version fields (§6.3, §6.10).

**Conclusion: no invariant is violated by the architecture as specified.** Two
(6 and 10) are enforced only as strongly as the eventual rule/validator
*implementation* honors them — the architecture provides the structure but not a
proof. This is flagged, not hidden.

## 4. Architecture compliance

N/A — no implementation exists to check for boundary violations, dependency
direction violations, or scope creep. Will apply starting with the first phase that
includes code.

## 5. Edge-case review

Cases probed beyond the required failure matrix:

- **Two workers race to claim the same failed-stage job.** SPEC.md §9/§10 assumes
  an atomic conditional update (`UPDATE ... WHERE status = X`), not read-then-write.
  This must be enforced by the actual persistence technology chosen (AQ-2); if the
  eventual datastore doesn't support atomic conditional writes cleanly, the claim
  mechanism as designed doesn't hold. Flagged as a hard requirement on ADR-001, not
  an assumption.
- **Google Form is edited mid-flight** (a field is renamed while a submission is
  queued). Covered by §10's "changed Google Form fields" row — normalization fails
  loud rather than guessing. Verified this doesn't silently corrupt any earlier
  submission, since `form_schema_version` is captured at receipt time, not at
  processing time.
- **A submission has zero required narrative-eligible fields** (all optional fields
  the applicant skipped). The architecture doesn't currently define a floor — does
  narrative generation proceed with an almost-empty context, or is there a minimum
  viable context below which it doesn't make sense to call the LLM at all? Not
  addressed in SPEC.md. Recorded as a new architectural question, AQ-9.
- **Rule engine produces zero triggered rules.** SPEC.md's `Assessment` contract
  doesn't state whether "no rules triggered" is itself a valid, expected
  qualification outcome or an error condition. This is really BR-1's territory
  (rule content), but the *contract* should say whether an empty
  `rules_triggered[]` is valid. Recommend SPEC.md be read as: yes, valid, and
  `qualification` for the empty-trigger case is itself part of the versioned
  triggered→qualification mapping — no separate special case needed. Worth
  confirming explicitly when rule content (BR-1) arrives.

## 6. Failure-path review

The §10 failure matrix in SPEC.md was built directly against the required list in
`docs/PROMPT.md` step 8 and cross-checked line by line — all 17 required cases are
present. Adversarial additions beyond the required list surfaced two real gaps,
documented as Adversarial Findings AF-1 and AF-2/AF-3 below, rather than smoothed
over.

## 7. Test review

N/A — no tests exist in this phase. §15 of SPEC.md specifies what future phases
must satisfy; nothing to execute or verify yet.

## 8. Diff review

N/A — no code diff. Repository housekeeping performed as part of this phase: a
malformed, empty `docs/phases/ PHASE-01/` directory (leading-space typo, likely a
prior mis-scaffold) was removed and replaced with the correctly named
`docs/phases/PHASE-01/`. No application files were touched; `main.py` is unchanged.

## 9. Adversarial findings

- **AF-1 (architectural weakness, INVARIANT 10 enforcement is soft).** The
  semantic-grounding check in §6.8 is a deny-list heuristic (block known dangerous
  categories) rather than a proof that every claim in the narrative is grounded.
  A sufficiently generic hallucinated sentence ("Your application reflects a
  thorough and consistent history") could pass validation while still being an
  LLM-invented characterization not literally present in `NarrativeContext`. Full
  general-purpose grounding verification is a hard, open problem and is
  deliberately not attempted in v1 — but this must be understood as a known,
  accepted residual risk, not a solved problem, when human approval is given.
- **AF-2 (architectural weakness, delivery dual-write problem).** Gmail's API has
  no native idempotency-key mechanism. If the process crashes *after* Gmail
  accepts a send but *before* the `Delivery` row is marked `sent`, a naive retry
  would send twice — directly violating INVARIANT 2. SPEC.md's per-recipient claim
  (§10) narrows the blast radius (only that one recipient, not the whole
  submission) but does not close the window.
- **AF-3 (recommended mitigation for AF-2, not yet a decision).** Before resending
  in the "ambiguous crash during send" case, reconcile against Gmail rather than
  blindly retrying: set a deterministic custom `Message-ID` (or a custom header
  carrying `submission_id` + `recipient`) at send time, and on resume/retry, search
  Gmail for that identifier before calling send again. This turns an unsafe blind
  retry into a safe check-then-send. This is a recommendation for ADR-007, not a
  final decision — it has operational cost (an extra API call per retry) that
  should be weighed against how often this crash window is actually expected to be
  hit in practice (likely rare).
- **AF-4 (overengineering risk avoided, noted for the record).** An earlier draft
  of this design considered one queue task per stage transition (10 fine-grained
  states) and a full workflow-orchestration engine (e.g. Temporal/Cloud Workflows).
  Both were rejected in favor of: a single resumable worker path driven by
  persisted `SubmissionState`, and a coarser 6-state model with attempt counters
  instead of per-attempt states (§9.1). For expected v1 volume, a custom
  orchestration engine is unjustified complexity; the state-machine-in-a-row
  pattern with atomic claims is sufficient and considerably easier to test and
  operate. This should be revisited only if submission volume or stage-fan-out
  complexity grows materially beyond what a single worker type can handle.
- **AF-5 (overengineering risk avoided, provider abstraction).** Confirmed the
  multi-provider LLM fallback path is correctly scoped out of v1 (§6.9) rather than
  built "because the interface allows it." Recommend this stays deferred until an
  actual outage incident or a contractual multi-provider requirement (AQ-3)
  materializes.

### 9.1 Adversarial pass on the v2 addition (§6.13, §16)

- **Checked**: does any placeholder default silently produce production-looking
  output? No — every deferred config point either fails the stage closed
  (`*_NOT_CONFIGURED` reason codes) or, where a placeholder is usable in dev
  (prompt/template/rule versions), it is named so it cannot be mistaken for
  approved content (`DRAFT-UNAPPROVED`, `unconfigured-dev-only`).
- **Checked**: does fail-closed anywhere block durable ingestion of a raw
  submission? No — §6.13 explicitly scopes `ReadinessGate` to per-stage
  processing, not to the webhook/`RECEIVED` path, specifically to avoid violating
  INVARIANT 11. This was verified against every deferred item in §16.2; none of
  them gate ingestion.
- **Checked**: is the retention placeholder (§16.2 BR-6, "no automatic deletion")
  itself a business decision being smuggled in as a default? Judged acceptable:
  the *direction* (favor retention over premature deletion when uncertain) is an
  engineering safety choice forced by INVARIANT 15, not a business retention
  *period* — no number is assumed, and the item is still marked
  production-launch-blocking for the real period.
- **AF-6 (new, minor — process risk, not architecture risk).** The
  `approved_for_production` flag pattern (§6.13) is only as strong as the review
  discipline behind setting it — nothing in the architecture stops someone from
  flipping it to `true` on unapproved content by mistake. This is a governance/CI
  concern for implementation (e.g. require the flag change to go through the same
  review as a rule-version bump, ADR-010), not an architectural gap; recorded so
  it isn't lost by the time implementation starts.
- **Conclusion**: no item reclassified as implementation-safe-to-defer required
  assuming business behavior to design its placeholder. No item was found to be
  architecture-blocking. This matches the instruction to only stop the project for
  a genuine fundamental-architecture conflict — none exists on current information.

## 10. Required corrections

No blocking corrections — there is no implementation to correct. The items in §9
(AF-1 through AF-3) are residual architectural risks that must be explicitly
accepted (or resolved further) by the human owner before implementation begins;
they are not defects in this document, they are honest limits of the design being
surfaced rather than hidden.

| Item | Severity | Required action | Responsible | Status |
|---|---|---|---|---|
| AF-1 semantic grounding is heuristic, not proof | Medium | Explicit human acceptance of residual hallucination risk, or a scoped follow-up phase to strengthen validation | Human owner (accept) / Claude (design follow-up if rejected) | Open |
| AF-2/AF-3 Gmail dual-write window | Medium | Decide ADR-007 (reconciliation-before-resend vs. accept rare-duplicate risk) before implementation | Human owner + Claude | Open |

## 11. Deferred issues

- AQ-9 (minimum viable `NarrativeContext` — see §5) — deferred to the same
  decision point as BR-1/BR-3, since it depends on knowing what fields the form
  actually collects. Impact: low until real form data is available. Approved to
  defer by virtue of being genuinely blocked on business input, not a choice to
  skip rigor.
- AF-6 (`approved_for_production` flag needs review-process backing, §9.1) —
  deferred to implementation-phase CI/process design. Impact: low now (nothing to
  misconfigure yet, since no config points exist in code); must be picked up
  before the first item in §16.2 is actually approved for production.

## 12. Architecture conflicts

None. This is the first architecture proposed for this project — there is no prior
approved architecture to conflict with.

## 13. ADR backlog — now resolved to PROPOSED recommendations

Every item originally listed here has been written up as a full ADR under
`docs/architecture/`, each PROPOSED (recommendation + alternatives + tradeoffs),
none implemented, none silently decided:

- `docs/architecture/ADR-000-hosting-platform.md` — Google Cloud Run.
- `docs/architecture/ADR-001-persistence.md` — Cloud SQL for PostgreSQL (must
  support atomic conditional writes — see Edge-case review).
- `docs/architecture/ADR-002-queue-dispatch.md` — Cloud Tasks.
- `docs/architecture/ADR-003-worker-orchestration.md` — single resumable worker
  over persisted state, no external orchestration engine (formalizes AF-4).
- `docs/architecture/ADR-004-llm-provider-selection.md` — interface/fallback
  strategy resolved (single provider, no v1 fallback); vendor selection itself
  remains `BUSINESS INPUT REQUIRED` (BR-9), correctly left open.
- `docs/architecture/ADR-005-pdf-rendering.md` — Jinja2 + WeasyPrint.
- `docs/architecture/ADR-006-gmail-sending-mechanism.md` — service-account
  domain-wide delegation (carries a Quirón IT provisioning dependency).
- `docs/architecture/ADR-007-email-idempotency-reconciliation.md` — deterministic
  header + search-before-resend (formalizes AF-2/AF-3 mitigation).
- `docs/architecture/ADR-008-form-schema-mapping.md` — declarative versioned
  config, reactive-only drift detection for v1.
- `docs/architecture/ADR-009-secrets-management.md` — Google Secret Manager.
- `docs/architecture/ADR-010-rule-version-enforcement.md` — CI content-hash check
  (also answers AF-6).
- `docs/architecture/ADR-011-retry-backoff-defaults.md` — 5 attempts, exponential
  backoff (placeholder pending BR-7).
- `docs/architecture/ADR-012-minimum-narrative-context-floor.md` — configurable
  threshold + deterministic fallback narrative (addresses the thin-context
  hallucination risk raised in §5 edge-case review).

Two ADRs (ADR-006, ADR-004) each carry one residual open item that is not an
engineering choice — Quirón IT provisioning and BR-9's vendor/compliance
clearance, respectively — correctly left unresolved rather than invented.

## 14. Final review result

**PASS WITH APPROVED DEFERMENTS — pending human review.**

The architecture in SPEC.md (v3) satisfies every requirement in `docs/PROMPT.md`
and does not violate any invariant in `docs/INVARIANTS.md`. All ten business items
were re-tested against "does this change the fundamental architecture" and none
did — nine are implementation-safe-to-defer with a concrete config/placeholder/
fail-closed design each, one (BR-10) is production-launch-blocking with no code
impact. Three residual risks are carried forward, all non-blocking to continued
design/skeleton work: AF-1 (semantic grounding is heuristic), AF-2/AF-3 (Gmail
send dual-write window), AF-6 (production-approval flag needs process backing at
implementation time). This review is Claude's own adversarial pass; it does not
substitute for the human architecture approval required by `docs/PROMPT.md`'s
phase gate rules, which is still pending (see STATUS.md).
