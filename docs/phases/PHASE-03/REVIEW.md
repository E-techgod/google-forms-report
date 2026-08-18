# PHASE-03 — Review

## 1. Review target

- Phase number: 03
- Spec version reviewed: `docs/phases/PHASE-03/SPEC.md` v3
- This file records review evidence per checkpoint, per SPEC.md §18. Only
  Checkpoint 1 (Persistence adapter) has been implemented and reviewed so
  far. Checkpoints 2-7 are not yet authorized.

## 2. Checkpoint 1 (Persistence adapter) — build cycle

### 2.1 Implementation

Codex Builder implemented SPEC.md §18 checkpoint 1 in full: a SQLAlchemy
2.x-backed adapter for every Protocol in `src/persistence/interfaces.py`
under `src/persistence/postgres/`, Alembic migrations (`alembic/`,
`alembic.ini`), Docker Compose local test infrastructure (`docker-compose.yml`,
per ADR-013), and `tests/contract/` (repository contract tests, the
compare-and-swap concurrency test, an ORM-import-boundary test, and a
Compose-secret-scan test).

### 2.2 Sandbox limitations discovered (operational, not architectural)

Codex Builder's own execution sandbox on this machine cannot reach the
Docker daemon socket (`permission denied`) even when the daemon is running
and reachable from Claude's own shell, and separately cannot write to
`.git` (`index.lock`: `Operation not permitted`). Both are structural
sandbox restrictions specific to how the Codex CLI subprocess is sandboxed
here, not an architecture or scope issue. Practical consequence for this and
future checkpoints: Codex Builder can write and reason about code but cannot
independently execute Postgres-backed tests or create commits in its own
sandbox; Claude verified against a live `docker compose`-provisioned
Postgres instance and performed the `git add`/`git commit` step directly
after independently confirming the work was correct and complete — the
commit content is entirely Codex Builder's authored work, verified before
being committed, not Claude-authored implementation.

### 2.3 Bugs found only by testing against real Postgres

Two genuine bugs were invisible to code review and to Codex Builder's own
(DB-less) test runs, and were only caught once Claude ran the suite against
a real, live Postgres instance:

1. `serialize_stage_error()` embedded a raw `datetime` in a dict written to
   a JSONB column — `TypeError: Object of type datetime is not JSON
   serializable`. Fixed: serialize `occurred_at` via `.isoformat()`.
2. `compare_and_set()`'s `last_error IS NULL` WHERE-clause condition never
   matched, because `create()` stored Python `None` as the **JSON scalar
   `null`** inside the JSONB column (via psycopg's default `Jsonb(None)`
   binding), not **SQL NULL** — confirmed directly via `psql`
   (`last_error IS NULL` returned `false` for a row with no error). This
   silently broke every claim attempt on a submission with no prior error,
   which is why the first concurrency-test run showed *both* racing threads
   losing (`assert 0 == 1`) rather than a genuine 1-winner race outcome.
   Fixed: `SubmissionStateRow.last_error` column type changed to
   `JSONB(none_as_null=True)` so "no error" round-trips as true SQL NULL
   everywhere, migration amended to match.

This is direct evidence for why SPEC.md required the persistence checkpoint
to be verified against real Postgres (via ADR-013's Compose infrastructure)
rather than accepted on code-reading or fakes-only testing alone — both bugs
would have shipped invisibly otherwise.

### 2.4 Independent verification (Claude, before committing)

Performed directly against a live `docker compose`-provisioned Postgres
instance (fresh volume, migrations applied from scratch), not taken from
Codex Builder's self-report:

- `uv run pytest tests/contract -q` → **11 passed** (9 Postgres-backed
  repository contract tests + 2 boundary/infra tests).
- `uv run pytest tests/unit tests/workflow tests/contract -q` → **55
  passed**, 2 warnings (pre-existing PHASE-02 `datetime.utcnow()` deprecation
  warnings, unrelated) — full regression suite plus new tests, together.
- `test_compare_and_set_allows_only_one_real_database_claim` repeated 10x in
  a row: passed every time — not flaky, a genuine single-winner race.
- `information_schema.triggers` inspected directly via `psql`: confirmed a
  real `*_append_only_guard` trigger blocking both `UPDATE` and `DELETE` on
  all six append-only tables (`assessments`, `deliveries`, `narratives`,
  `normalized_applications`, `raw_form_submissions`, `reports`), and
  confirmed no such trigger exists on `submission_states` (the one mutable
  entity) — SPEC.md §14 acceptance criterion 3 satisfied at the database
  level, not just by application code.
- `docker-compose.yml` reviewed directly: only synthetic local credentials
  (`local_test_user`/`local_test_password`), no production secret pattern.
- `tests/contract/test_boundaries_and_infra.py` (import-boundary + Compose
  secret scan) passed as part of the above runs.

### 2.5 Commit

`b543b92` — `feat(persistence): add SQLAlchemy/Postgres repository adapter`.
Staged precisely: `pyproject.toml`, `uv.lock` (automatic companion),
`alembic.ini`, `alembic/`, `docker-compose.yml`,
`src/persistence/postgres/`, `tests/contract/`. Confirmed via `git status`
that no pre-existing unrelated uncommitted file (PHASE-02 `src/`/`tests/`,
`docs/`, `CURRENT_PHASE.md`, `.gitignore`, `main.py`) was included. Not
pushed.

## 3. Checkpoint 1 — Codex Reviewer focused review

Performed via the Codex CLI's `adversarial-review` command, scoped to
exactly the diff introduced by commit `b543b92` (`--base HEAD~1 --scope
branch`), with explicit focus text pointing at SPEC.md §§3, 8, 12-15, 18 and
ADR-001/ADR-013, per `docs/agents/CODEX_REVIEWER.md`'s adversarial mandate.
Not a rubber stamp: instructed to try to break the implementation and not
approve based on a summary.

**Verdict: `needs-attention`** (Codex Reviewer's classification; treated
here as **FAIL for Checkpoint 1**, since the finding is a real, in-scope
correctness defect, not a style note).

### Finding (verified independently by Claude, not taken on the reviewer's word alone)

| Severity | Title | Location |
|---|---|---|
| High (confidence 0.98) | Raw-submission dedup is race-prone and can raise instead of cleanly rejecting duplicates | `src/persistence/postgres/repositories.py:46-69` |

`PostgresRawFormSubmissionRepository.insert()` performs two read-before-write
checks (`session.get(...)`, then a `SELECT ... WHERE form_id/response_id`)
and only then `session.add(...)`. Two concurrent requests carrying the same
`(form_id, response_id)` can both observe "no existing row," then race to
insert; the `uq_raw_form_response` unique constraint rejects the loser at
flush/commit time, which means the method can raise `IntegrityError` instead
of returning `False`. The existing webhook contract (`src/api/webhook.py`,
PHASE-02) expects a boolean duplicate signal, not a database exception on
this path — the likely production behavior is a 500 during duplicate/retry
traffic rather than the deterministic `REJECTED_DUPLICATE` PHASE-01 SPEC.md
§10 specifies. This bears directly on INVARIANT 1 (at-most-once processing)
and PHASE-03 SPEC.md §14 acceptance criterion 2 (the real adapter must
satisfy the fake's declared contract, which returns `False`, not an
exception, for a duplicate).

Claude's independent read of `repositories.py:46-69` confirms the race
window exists exactly as described: both preflight checks and the `add()`
happen inside one session/transaction per caller, which does not prevent a
second, independent session from racing the first.

### Recommended correction (from Codex Reviewer, endorsed by Claude)

Make duplicate rejection atomic at the database boundary — e.g. an
`INSERT ... ON CONFLICT DO NOTHING` with a rowcount check (covering both the
primary key and the `uq_raw_form_response` unique constraint), or catch and
translate the specific `IntegrityError` to `False` — and add a genuine
concurrent duplicate-insert test (two real threads/connections racing the
same `(form_id, response_id)`) so this class of regression cannot hide
behind sequential-only repository tests, the same way the compare_and_set
bug in §2.3 was only caught by real concurrent execution.

## 4. Required corrections (Checkpoint 1)

| Severity | Description | Required correction | Responsible agent | Status |
|---|---|---|---|---|
| High | `PostgresRawFormSubmissionRepository.insert()` can raise `IntegrityError` on a concurrent duplicate instead of returning `False` | Atomic conflict handling (`ON CONFLICT DO NOTHING` + rowcount check, or caught/translated `IntegrityError`) plus a real concurrent duplicate-insert test | Codex Builder | Open — not yet authorized for a fix round; awaiting human direction per the instruction to stop and report after this review |

## 5. Deferred issues

None evaluated yet — Checkpoint 1 has one open Required Correction, so no
deferment decision is being made in this pass.

## 6. Architecture conflicts

None. This finding is a concrete implementation bug in new Checkpoint 1
code, fixable within the already-approved interfaces and SPEC — no
`ARCHITECTURE ESCALATION REQUIRED`.

## 7. Checkpoint 1 result (first review round)

**FAIL — one high-severity correction required.**

Everything else examined (ORM isolation, append-only enforcement including
at the database trigger level, the compare-and-swap concurrency test,
Compose secret hygiene, scope discipline against checkpoints 2-7) passed
both Codex Reviewer's pass and Claude's independent verification. The one
open item is the raw-submission duplicate-insert race in
`PostgresRawFormSubmissionRepository.insert()`. Per the human's explicit
instruction accompanying Checkpoint 1's authorization, work stopped here and
this result was reported before any fix round or Checkpoint 2 was
authorized.

## 8. Checkpoint 1 — fix round (human-authorized, scoped)

The human authorized a fix round strictly scoped to the §3/§4 finding, with
explicit required behavior (atomic DB-layer duplicate detection via
`INSERT ... ON CONFLICT DO NOTHING`, losing call returns `False` without
leaking `IntegrityError`, no change to any approved interface/contract) and
explicit required verification (a real Postgres-backed concurrent
duplicate-insert test, full contract + regression suites, repeated runs to
catch flakiness).

### 8.1 First attempt — genuine but incomplete fix

Codex Builder's first attempt correctly switched to
`INSERT ... ON CONFLICT DO NOTHING` (no explicit conflict target, so it
covers both the `submission_id` primary key and the `uq_raw_form_response`
unique constraint) but determined success via `result.rowcount == 1`.
Claude's independent verification against real Postgres found this made
**every** insert return `False`, including non-duplicate ones — 3 failed,
10 passed on `tests/contract`. Root cause, confirmed via direct diagnostic
scripts against the live database: `result.rowcount` reports `-1` for this
exact statement shape with SQLAlchemy + psycopg3 in this environment,
regardless of whether the row was actually inserted (confirmed the row
existed in the database via a separate `SELECT` even when `rowcount == -1`).
This was sent back to Codex Builder with the precise diagnosis and a
confirmed-working alternative (`.returning(...)` + `result.first() is not
None`, verified directly against both the success and conflict cases before
being handed over).

### 8.2 Second attempt — verified correct

Codex Builder replaced the rowcount check with `.returning(RawFormSubmissionRow.submission_id)`
and `result.first() is not None`. Claude's independent verification against
a live Postgres instance:

- `uv run pytest tests/contract -q` → **13 passed** (11 prior + 2 new:
  duplicate-response concurrency test, duplicate-submission-id test).
- `uv run pytest tests/unit tests/workflow tests/contract -q` → **57
  passed**, 2 warnings (pre-existing, unrelated).
- New duplicate-insert concurrency test repeated 15x: 15/15 pass, no
  flakiness.
- Existing `compare_and_set` concurrency test repeated 10x (regression
  check): 10/10 pass, no flakiness.
- `git status` confirmed only `src/persistence/postgres/repositories.py`
  and `tests/contract/test_postgres_repositories.py` changed — no scope
  creep.

Committed as `28de6cb` —
`fix(persistence): make raw-submission dedup atomic at the database layer`.
Staged precisely (only those two files), not pushed. As with the first
commit, Claude performed the `git add`/`git commit` step directly after
independent verification, because Codex Builder's sandbox cannot write to
`.git` (§2.2) — the committed content is entirely Codex Builder's authored
fix.

### 8.3 Codex Reviewer re-review

Focused re-review via `adversarial-review --base HEAD~1 --scope branch`
against commit `28de6cb`. **Verdict: `needs-attention`** — one high-severity
finding (confidence 0.97):

> The new duplicate-response concurrency test only synchronizes the two
> threads at method entry (via `Barrier(2)`); it does not force overlap
> *inside* the database critical section. In a schedule where one thread's
> full round trip (SELECT/INSERT/commit) completes before the other begins,
> the *old* buggy implementation would also often produce a clean one-True/
> one-False result (the loser's preflight `SELECT` would see the already-
> committed row and return `False` without ever reaching a conflicting
> `INSERT`). The test therefore doesn't prove the original `IntegrityError`
> regression is actually gone under real contention.

This is a legitimate category of concern (concurrency tests can pass "by
luck" on scheduling rather than by proving the property under test), raised
adversarially exactly as `docs/agents/CODEX_REVIEWER.md` asks. It was not
accepted or rejected on the reviewer's word alone.

### 8.4 Claude's empirical verification of the reviewer's finding

Rather than take the finding — or dismiss it — on reasoning alone, Claude
reconstructed the *old* (pre-fix) read-before-write `insert()` logic in an
isolated diagnostic script and ran it through the **exact same**
`Barrier(2)`/two-thread/two-real-connection pattern the new test uses,
against the live Postgres instance, 30 times.

**Result: 30/30 trials raised an exception (`IntegrityError`) against the
old buggy implementation.** Zero trials produced a "clean" one-True/one-False
result that would have let the regression hide. This directly contradicts
the reviewer's theorized failure mode for *this specific environment*: the
barrier-synchronized pattern reliably forces real overlap here (both
threads' round trips to the local Docker Postgres instance are slow enough
relative to Python thread-start latency that the race window is
consistently hit), and reliably would have failed against the old code —
it is not a test that merely "usually" catches the bug.

This does not mean the reviewer's underlying concern is baseless in
principle (a `Barrier`-synced-at-entry test is not a *mathematical*
guarantee of overlap in every possible environment/scheduling condition,
only an empirically strong one in this one) — but it means the specific,
concrete claim ("the old implementation would also usually produce exactly
one True and one False") is not supported by direct measurement in this
codebase's actual test environment. Claude is not overriding the finding
silently; it is recorded here in full alongside the counter-evidence, for
the human to weigh — see STATUS.md's Next required action.

## 9a. Checkpoint 1 — test-hardening round (human-authorized, scoped)

Per the human's decision after §9, a test-hardening round was authorized:
production fix `28de6cb` accepted as correct and not to be changed; scope
limited to strengthening the concurrency test to force overlap at the
database critical section, plus a regression fixture proving the hardened
test deterministically fails against the old implementation.

### 9a.1 First hardening attempt

Codex Builder implemented a "blocker holds an uncommitted conflicting
INSERT, releases only after a `before_cursor_execute` listener confirms the
contender's real INSERT statement is about to execute" harness, shared by a
hardened production test and a new regression fixture reconstructing the
pre-`28de6cb` logic. Claude verified the mechanism itself in isolation
(confirmed genuine DB-level blocking and correct `IntegrityError` on
release) but found the regression fixture failed in the real suite for an
unrelated reason: both new tests used hard-coded IDs and depend on the
non-truncating `postgres_dsn` fixture, so the first test's committed winner
row leaked into the second test, causing the old logic's preflight check to
short-circuit before ever reaching the INSERT the harness was built to
intercept. Sent back with the precise root cause; Codex Builder fixed it by
giving each test a distinct `label`-derived ID namespace. Claude re-verified:
58/58 full suite, both hardened tests 10/10 stable. Committed as `62aaf14` —
`test(persistence): force deterministic overlap in duplicate-insert race test`.

### 9a.2 Codex Reviewer re-review — second finding

Focused re-review of `62aaf14` (`--base HEAD~1 --scope branch`). **Verdict:
`needs-attention`** (confidence 0.97): the `before_cursor_execute` hook
fires client-side, before the driver physically sends the statement to
Postgres — in principle the main thread could commit the blocker in the
narrow gap between the hook firing and the contender's `cursor.execute()`
actually reaching the server, meaning genuine overlap at the database level
is still not strictly guaranteed by construction.

### 9a.3 Claude's analysis and empirical test of both sub-cases

Rather than accept or dismiss this on reasoning alone, Claude directly
constructed the degenerate case the finding describes — the blocker fully
committed *before* the contender's insert is attempted at all (the
worst-case zero-overlap scenario) — and ran both the current and old logic
through it:

- **Current (fixed) code, zero overlap**: `insert()` still returns `False`,
  exactly one row persisted — identical to the genuine-overlap case. Postgres's
  unique-index conflict detection is airtight regardless of arrival timing
  for `ON CONFLICT DO NOTHING`, so **the production test's validity is
  unaffected by this finding** — its assertions hold under either timing
  sub-case.
- **Old (buggy) code, zero overlap**: returned `False` **without raising** —
  because the old code's preflight `SELECT` cleanly sees the already-
  committed row and short-circuits before ever reaching the conflicting
  `INSERT`. This means if the client-side race window the reviewer
  describes is ever actually hit, **the regression fixture's own
  `IntegrityError` assertion would fail** (not silently pass with a false
  claim, but a genuine, narrow source of flakiness) — which falls short of
  the human's explicit requirement that this fixture *deterministically*
  fail against the old behavior, not merely reliably do so.

Conclusion: the finding is **valid and worth closing for the regression
fixture specifically**, even though the production test needs no further
change. The reviewer's own suggested remedy (a server-side synchronization
point — e.g. polling `pg_locks`/`pg_stat_activity` for the contender's
backend to be observably waiting on the conflicting lock before releasing
the blocker, instead of relying on the client-side `before_cursor_execute`
hook) directly closes this gap. Sent to Codex Builder as a further scoped
round rather than decided unilaterally, consistent with stopping at each
Codex Reviewer gate.

## 9b. Checkpoint 1 — final test-hardening round (human-authorized, scoped)

Per the human's decision after §9a, a further scoped round was authorized:
production code (`28de6cb`) and the prior hardening commit (`62aaf14`)
remain accepted as correct; scope limited to replacing the regression
fixture's client-side `before_cursor_execute` synchronization with a
server-observable one, per the reviewer's own suggested remedy.

### 9b.1 Implementation

Codex Builder replaced the client-side hook with: a uniquely
`application_name`-tagged contender connection (`contender-{label}`), and a
bounded, `monotonic()`-deadline poll of
`pg_locks JOIN pg_stat_activity ... WHERE application_name = :tag AND
granted = false` on the blocker's connection — only committing the blocker
once Postgres itself reports the contender's tagged backend is actively
waiting on an ungranted lock. Both duplicate-response tests (hardened
production test and old-logic regression fixture) now share this mechanism.

Claude's independent verification against a live Postgres instance:
58/58 full suite; both hardened tests repeated 15x each, no flakiness;
explicitly confirmed the bounded-timeout guarantee by forcing a
non-conflicting insert through the harness and observing a clean
`AssertionError` at ~1.6s against a 1.5s timeout (not a hang). Committed as
`1e14dfc` — `test(persistence): use server-observable synchronization for
the duplicate-insert race harness`. Only `tests/contract/test_postgres_repositories.py`
changed.

### 9b.2 Codex Reviewer final review — third finding

Focused re-review of `1e14dfc`. **Verdict: `needs-attention`**, but
**severity `medium`** (confidence 0.93) — lower than the two prior `high`
findings. Finding: `contender_tag` is a fixed string per test label
(`contender-current-insert`, `contender-old-insert`), not bound to the
specific contender backend's PID. `_wait_for_lock_wait()` matches *any*
`pg_locks` row with that `application_name` and `granted = false` — so in
principle a stale/leaked connection from an interrupted prior run, or (if
this suite were ever run under parallel workers) a different worker's
connection sharing the same tag and blocked on an unrelated lock, could
satisfy the poll early, releasing the blocker before the real contender has
reached its conflicting INSERT — reintroducing the same class of ambiguity
this round exists to close, in that narrow circumstance. Recommended fix:
capture the contender connection's `pg_backend_pid()` and bind the wait
query to that exact PID (optionally also the specific lock target), rather
than relying on the tag alone.

### 9b.3 Claude's assessment

Confirmed the finding is technically valid: `_wait_for_lock_wait`'s query
(`tests/contract/test_postgres_repositories.py` around `_wait_for_lock_wait`)
indeed filters only by `application_name` + `granted = false`, with no PID
binding. Assessed practical risk as lower than the two prior findings in
this checkpoint: this test suite currently runs sequentially, not under
parallel workers, and each test's contender connection is disposed in the
helper's `finally` block, so a same-run collision is not currently possible
in practice — the exposure is specifically to *external* factors (an
interrupted prior run's leaked connection, or a future parallel-execution
change) rather than anything present in this suite's current, actual
execution model. Unlike the two prior findings, this one does not currently
threaten either test's correctness under this suite's real conditions as
run — but the reviewer's proposed fix (PID binding) is cheap, precise, and
would close the gap completely regardless of future execution changes.
Reported to the human for a decision rather than proceeding unilaterally,
consistent with stopping at each Codex Reviewer gate, and because the
human's authorization for this round used explicit "final" framing.

## 9c. Checkpoint 1 — second final-round hardening (human-authorized, scoped)

Per the human's decision after §9b, one more narrowly scoped round was
authorized: bind the wait query to the contender's exact `pg_backend_pid()`,
per the reviewer's own suggested fix, removing sole reliance on the
`application_name` tag. The human also set an explicit stopping rule for
this round's review: hypothetical harness-only concerns requiring
conditions outside this suite's actual supported execution model, absent
any real production defect/invariant violation/nondeterministic regression
escape/false-positive path, are to be recorded as non-blocking observations
rather than reopening Checkpoint 1.

### 9c.1 Implementation

Codex Builder built the contender's engine with `pool_size=1,
max_overflow=0`, captured `pg_backend_pid()` from a short-lived connection
on that same engine before starting the contender thread, and rebound
`_wait_for_lock_wait()` to filter `pg_locks` directly on that exact PID
(`WHERE pid = :contender_pid AND granted = false`) instead of
`application_name`. Claude verified the mechanism is structurally correct:
with exactly one physical connection ever created for that engine, the
connection the contender's real operation later checks out is provably the
same backend whose PID was captured.

Claude's independent verification against a live Postgres instance: 58/58
full suite; both hardened tests repeated 15x each, no flakiness;
bounded-timeout behavior re-confirmed via the same forced non-conflicting
scenario as before (~1.6s against a 1.5s timeout). Committed as `002104b` —
`test(persistence): bind duplicate-insert race harness to exact contender
PID`. Only `tests/contract/test_postgres_repositories.py` changed.

### 9c.2 Codex Reviewer final review

Focused review of `002104b`, explicitly instructed to apply the human's
stopping rule. **Verdict: `approve`.** Zero findings.
Summary: "Ship it. I could not support a material blocking finding in
commit 002104b: the harness is now scoped to the exact contender backend
PID, the forced-overlap proofs still match their claims, bounded timeout
behavior remains intact, and the diff stays within the authorized test-only
surface." Next step recorded by the reviewer: "Record this pass as approved
under the explicit PHASE-03 Checkpoint 1 stopping rule."

## 10. Checkpoint 1 final result

**PASS.**

Across four Codex Reviewer passes and three scoped correction/hardening
rounds (§3-4 the original duplicate-insert race; §8 the atomic-fix round,
which itself required a follow-up correction after Claude's independent
verification caught a `rowcount`-always -1 regression before it was ever
committed; §9a-9c three successive rounds hardening the concurrency test's
synchronization mechanism from `Barrier`-at-entry, to a client-side SQL
event hook, to server-observable `pg_locks`/`pg_stat_activity`, to finally
PID-bound `pg_locks`), every finding was either fixed and independently
re-verified against real Postgres, or — in one case (§9b) — assessed by
Claude as not currently exploitable and then closed anyway per further
human instruction, rather than left unresolved.

Checkpoint 1 (Persistence adapter, SPEC.md §18 item 1) is complete: all of
SPEC.md §14's checkpoint-1-relevant acceptance criteria are satisfied and
independently verified (SQLAlchemy 2.x adapter implementing every
`src/persistence/interfaces.py` Protocol; ORM isolation with a passing
import-boundary test; Alembic migrations; append-only enforcement at the
database trigger level for all six required tables, confirmed directly via
`information_schema.triggers`; the compare-and-swap claim as a genuine
SQLAlchemy Core `UPDATE ... WHERE` with a correctness check tightened to
full-state equality; Docker Compose local test infrastructure per ADR-013
with no secrets in its config; the raw-submission duplicate-insert path now
atomic at the database layer with a PID-bound, server-observable,
bounded-timeout concurrency test proving both the current implementation's
correctness and the old implementation's deterministic failure). Final
commit for this checkpoint: `002104b` (on top of `1e14dfc`, `62aaf14`,
`28de6cb`, `b543b92`).

Per SPEC.md §18, this PASS covers Checkpoint 1 only. It does not by itself
authorize Checkpoint 2 (Queue/dispatch adapter) or any later checkpoint —
each requires its own explicit human authorization — and it is not the
required final cross-adapter review or Claude's architecture-compliance
review, both of which happen only after all seven checkpoints individually
pass.

## 9. Checkpoint 1 result (fix-round review)

**Evaluated, not resolved unilaterally.** The original high-severity finding
(§3-4) is fixed and independently verified (§8.2). The re-review's finding
(§8.3) is a test-robustness concern, not a correctness defect in the fix
itself — Codex Reviewer did not dispute that `insert()` now correctly
returns `False` for both duplicate classes, only that the *proof* of
race-safety could in principle be stronger. Claude's empirical check (§8.4)
found the existing proof already reliable in this environment (30/30), but
did not unilaterally decide this is sufficient to close the checkpoint,
given the human's standing instruction to stop and report after each Codex
Reviewer pass. Reported to the human for a decision: accept as-is with the
empirical evidence on record, or authorize hardening the test further (e.g.
forcing overlap inside the transaction rather than relying on `Barrier`-at-
entry timing, per the reviewer's suggested alternatives).
