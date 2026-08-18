# Git Commit & Push Rules

## Purpose

These rules govern how Claude, Codex Builder, Codex Reviewer, and any future
implementation agents interact with Git.

The goals are to:

- preserve a clean and auditable history;
- prevent accidental scope creep;
- prevent broken code from being pushed;
- make every change easy to review and reverse;
- ensure agents do not bypass phase or checkpoint approval gates;
- preserve human control over important project milestones;
- ensure reviewed checkpoint work is backed up remotely without requiring
  repeated manual push authorization.

These rules apply to all project phases unless an approved phase specification
explicitly states otherwise.

---

# 1. Core Git Principle

Git history must reflect logical units of work.

Agents must prefer:

`small + focused + reviewable commits`

over:

`large + mixed + difficult-to-review commits`

A commit must answer one clear question:

**What single logical change does this commit introduce?**

A push should normally represent a reviewed checkpoint or other explicitly
authorized project milestone.

---

# 2. Read Project State Before Git Actions

Before creating a commit or push, an agent must read:

- `docs/PROMPT.md`
- `docs/INVARIANTS.md`
- `docs/GIT_RULES.md`
- `CURRENT_PHASE.md`
- the current phase `SPEC.md`
- the current phase `STATUS.md`
- relevant agent-role instructions
- relevant ADRs when applicable

The agent must verify that the work and Git action are authorized by the
current phase/checkpoint.

---

# 3. Never Commit Unauthorized Work

An agent must not commit:

- work outside the current phase or checkpoint;
- architecture changes that have not been approved;
- invented business rules;
- unrelated refactors;
- experimental files outside approved scope;
- secrets;
- credentials;
- API keys;
- access tokens;
- `.env` files containing real secrets;
- generated temporary files;
- local IDE configuration unless explicitly required;
- sensitive client data;
- production data;
- debug dumps containing sensitive information.

If unauthorized changes exist in the working tree, they must not be silently
included in the commit.

---

# 4. Inspect the Diff Before Every Commit

Before committing, inspect:

`git status`

`git diff`

and, when applicable:

`git diff --staged`

Verify:

- every changed file is expected;
- every changed line belongs to the current task;
- no secrets are present;
- no debug code was accidentally left behind;
- no unrelated file was modified;
- no architecture boundary was violated.

Do not blindly use:

`git add .`

unless the full working tree has first been reviewed and every change is
intentionally part of the same commit.

Prefer staging specific files or logical groups of files.

---

# 5. Commit Size

Commits should be small enough that another engineer or reviewing agent can
understand the change without reconstructing an entire phase.

Good:

- add submission domain model;
- implement boolean normalization;
- add duplicate-submission tests;
- fix retry state transition;
- add Gmail adapter interface;
- address reviewer finding for idempotency;
- harden concurrent duplicate-insert test.

Bad:

- implement backend;
- finish phase;
- updates;
- fixes;
- miscellaneous changes;
- complete app.

One commit should normally represent one logical change.

Multiple focused commits may belong to the same checkpoint.

---

# 6. Commit Message Format

Use:

`<type>(<scope>): <short description>`

Recommended types:

- `feat` — new functionality
- `fix` — bug fix
- `test` — tests only
- `refactor` — internal restructuring without behavior change
- `docs` — documentation
- `chore` — tooling/configuration/maintenance
- `perf` — performance improvement
- `security` — security-specific improvement

Examples:

`feat(normalization): add canonical boolean conversion`

`test(classification): add duplicate flag edge cases`

`fix(workflow): prevent repeated client email delivery`

`docs(phase-01): record approved architecture`

`refactor(persistence): isolate repository interface`

`security(logging): remove sensitive payload fields`

`fix(persistence): make raw submission insert atomic`

Commit messages must describe what actually changed.

Do not use vague messages such as:

`update`

`changes`

`stuff`

`fix code`

`done`

---

# 7. Phase and Checkpoint Reference

When useful, include the phase and checkpoint in the commit body.

Example:

`feat(persistence): add postgres repository adapter`

Commit body:

`Phase: PHASE-03`

`Checkpoint: 1 — Persistence`

`Implements the repository contract defined in docs/phases/PHASE-03/SPEC.md.`

This is strongly recommended for architecture-sensitive work.

---

# 8. Tests Before Commit

For implementation commits, the agent must run the relevant tests before
committing.

At minimum:

- tests directly related to the changed component;
- existing tests likely to be affected by the change.

When reasonable, run the complete applicable regression suite before declaring
a checkpoint implementation complete.

A commit must not knowingly contain failing tests unless:

1. the phase explicitly permits an intermediate failing state;
2. the failure is documented;
3. the commit remains local;
4. the checkpoint is not represented as reviewed or complete.

A knowingly failing intermediate commit is never automatically eligible for
push.

---

# 9. Formatting, Linting, and Type Checks

When the project defines formatting, linting, type-checking, or security tools,
the implementing agent must run the relevant checks before declaring a
checkpoint complete.

Examples may include:

- formatter;
- linter;
- type checker;
- test suite;
- security scanner.

Use the tooling already defined by the project.

Do not introduce unnecessary tooling merely to satisfy this rule.

---

# 10. Codex Builder Commit Authority

Codex Builder may commit implementation work when:

- the current phase/checkpoint authorizes implementation;
- changes remain inside approved scope;
- relevant tests pass;
- the diff has been reviewed;
- no architecture escalation is active.

Codex Builder may create multiple focused local commits during implementation
and fix rounds.

Codex Builder may not approve its own implementation.

Commit authority does not by itself mean a checkpoint has passed review.

---

# 11. Codex Reviewer Rules

Codex Reviewer reviews the actual commits and diff produced by Codex Builder.

The reviewer must inspect:

- changed files;
- relevant tests;
- commit boundaries;
- unauthorized changes;
- invariant violations;
- scope creep;
- suspicious dependencies;
- hidden architecture changes;
- whether claimed tests were actually executed;
- whether concurrency/failure tests genuinely prove the required behavior.

The reviewer should normally not rewrite commit history merely for cosmetic
reasons.

If corrections are required, they should normally be returned to Codex Builder.

Corrections should result in focused additional commits such as:

`fix(workflow): address duplicate delivery review finding`

or:

`test(persistence): harden concurrent duplicate insert proof`

Codex Reviewer normally does not commit implementation fixes.

Codex Reviewer normally does not push.

Reviewer push authority exists only when an approved phase workflow explicitly
authorizes it and all pre-push requirements are satisfied.

Codex Reviewer must never push directly to `main` and must never force-push.

---

# 12. Claude Git Role

Claude acts as architect, orchestrator, and architecture-compliance reviewer.

Claude may inspect:

- `git status`
- `git diff`
- `git diff --staged`
- `git log`
- individual commits;
- branch state;
- test results.

Claude must not approve a checkpoint or phase based only on Codex Builder's
written summary.

Claude must inspect the actual implementation changes relevant to architecture.

Claude may request corrections before allowing the checkpoint or phase to
advance.

When Codex cannot perform a Git action because of a structural sandbox/tool
limitation, Claude may perform the Git action only after independently
verifying:

- the diff;
- test state;
- approved scope;
- commit contents;
- the applicable Git rules.

The reason for Claude performing the action must be recorded.

---

# 13. Architecture Changes

If implementation reveals that an approved architecture must change:

**DO NOT COMMIT AN ARCHITECTURAL WORKAROUND AS NORMAL IMPLEMENTATION.**

Instead:

1. stop the affected implementation;
2. document the issue in `REVIEW.md`;
3. set the checkpoint/phase state to `BLOCKED_ARCHITECTURE`;
4. escalate to Claude;
5. update the relevant architecture/specification if approved;
6. obtain required human approval;
7. resume implementation afterward.

Architecture must not drift through implementation commits.

No checkpoint containing an unresolved architecture escalation may be pushed as
a completed/reviewed checkpoint.

---

# 14. Business Logic Changes

Agents may not silently change business rules.

Examples include:

- qualification criteria;
- risk classifications;
- scoring;
- thresholds;
- customer-facing decisions;
- advisor recommendations;
- eligibility logic;
- business priorities.

If a business rule must change, it must be explicitly approved and versioned
according to project rules before implementation.

---

# 15. Branch Rules

Development work should occur on a branch associated with the current phase or
task.

Recommended phase branch format:

`phase/<number>-<short-name>`

Examples:

`phase/01-architecture`

`phase/03-infrastructure`

`phase/06-persistence`

For small isolated tasks, task branches may be used when useful:

`fix/duplicate-email-idempotency`

`test/classification-edge-cases`

Agents must not create unnecessary branches for trivial edits.

A checkpoint does not require its own branch unless the phase SPEC or human
project owner explicitly requires one.

---

# 16. Main Branch Protection

`main` represents the latest human-approved project state.

Agents must not directly push implementation work to `main` unless the human
project owner explicitly authorizes that workflow.

Preferred flow:

`phase branch`

→ checkpoint implementation

→ checkpoint review

→ automatic checkpoint push

→ remaining checkpoints

→ final phase review

→ Claude architecture review

→ human phase approval

→ merge into `main`

Automatic checkpoint push authority does **not** authorize merge or push to
`main`.

---

# 17. Commit and Push Are Different Permissions

A commit and a push remain separate Git actions.

Implementation agents may create local commits while work is in progress.

However, once a checkpoint satisfies the automatic push conditions defined
below, the reviewed checkpoint branch should be pushed without requiring a
separate human message asking for the push.

This automatic authority applies only to the current non-`main` phase/task
branch.

---

# 18. Automatic Push After a Checkpoint Passes Review

A completed checkpoint is automatically authorized for push when **all** of the
following are true:

1. The checkpoint was explicitly authorized for implementation.
2. Codex Builder has completed the checkpoint's approved scope.
3. Relevant checkpoint tests pass.
4. Required regression tests pass.
5. Required formatting/lint/type checks pass when applicable.
6. Codex Reviewer has completed the checkpoint's required focused review.
7. The review result is:
   - `PASS`, or
   - `PASS WITH APPROVED DEFERMENTS`.
8. All blocking findings from previous review rounds are resolved.
9. No unresolved invariant violation exists.
10. No unresolved architecture escalation exists.
11. No unresolved security issue exists.
12. The pre-push checklist in §30 passes.
13. The destination is the current authorized non-`main` phase/task branch.

When all conditions are true:

**Codex Builder should push the current reviewed checkpoint commits to the
configured remote branch automatically.**

A separate human "push now" instruction is not required.

After pushing, report:

- remote name;
- branch name;
- pushed commit SHA(s);
- checkpoint represented by the push;
- whether the working tree remains clean or contains intentionally uncommitted
  work.

---

# 19. Failed or In-Review Checkpoints Must Not Auto-Push

Automatic checkpoint push is forbidden when the current review result is:

- `FAIL`;
- `NEEDS_ATTENTION`;
- `BLOCKED`;
- `BLOCKED_ARCHITECTURE`;
- `BLOCKED_BUSINESS_INPUT`;
- unresolved/ambiguous.

If Codex Reviewer finds a blocking issue:

1. keep the existing implementation commits local unless they were previously
   pushed as an earlier approved checkpoint state;
2. return findings to Codex Builder;
3. create focused fix commits;
4. re-run required verification;
5. perform another Codex Reviewer pass;
6. push only after the checkpoint reaches an allowed passing state.

A Builder claim that "tests pass" never replaces the Reviewer gate.

---

# 20. Fix Rounds and Automatic Push

Fix rounds remain part of the same checkpoint.

During a fix round:

- Codex Builder may create additional focused local commits;
- those commits remain local while review is unresolved;
- Reviewer re-checks the corrected checkpoint;
- when the checkpoint finally reaches `PASS` or
  `PASS WITH APPROVED DEFERMENTS`, all unpushed reviewed commits belonging to
  that checkpoint become eligible for automatic push together.

Example history:

`feat(persistence): add postgres repositories`

`fix(persistence): make raw submission insert atomic`

`test(persistence): harden concurrent duplicate insert test`

Once Checkpoint 1 passes review, all three may be pushed to the Phase 3 branch
together.

Do not squash away useful implementation/finding/fix history unless the human
project owner explicitly requests history cleanup.

---

# 21. Automatic Push Does Not Authorize the Next Checkpoint

Pushing a passing checkpoint does not authorize implementation of the next
checkpoint.

After push:

- the completed checkpoint remains complete;
- the next checkpoint remains `NOT AUTHORIZED` unless the phase workflow or
  human project owner explicitly authorizes it.

The Git push gate and the checkpoint implementation-authorization gate are
independent.

---

# 22. Automatic Push Does Not Mean Phase Approval

A phase containing multiple checkpoints may accumulate several automatically
pushed checkpoint commits on its phase branch.

This is expected.

For example:

`Checkpoint 1 PASS → push`

`Checkpoint 2 PASS → push`

`Checkpoint 3 PASS → push`

...

The phase still requires:

- all required checkpoints;
- final cross-checkpoint/cross-adapter review when specified;
- Claude architecture-compliance review;
- human approval.

Only then may the phase be marked `APPROVED` and become eligible for merge into
`main`.

---

# 23. Manual Push Authorization

A human may explicitly authorize a push before the normal checkpoint-auto-push
gate when there is a valid reason, such as:

- remote backup;
- external review;
- CI execution requiring a remote branch;
- collaboration across machines.

Such a push must still:

- use a non-`main` branch unless explicitly authorized otherwise;
- pass the pre-push checklist;
- clearly report that the checkpoint is still in progress or under review.

An early backup push must never be represented as checkpoint approval.

---

# 24. Never Force Push Without Explicit Approval

Agents must not use:

`git push --force`

or:

`git push --force-with-lease`

unless explicitly authorized by the human project owner for that specific
situation.

Rewriting shared remote history is considered a high-impact action.

Automatic checkpoint push authority never includes force-push authority.

---

# 25. Never Delete Remote Branches Without Approval

Agents must not delete remote branches unless explicitly authorized.

This includes commands equivalent to:

`git push origin --delete <branch>`

Automatic checkpoint push authority does not include branch deletion.

---

# 26. Never Destroy Work to Fix Git State

Agents must not use destructive Git operations merely to make the repository
look clean.

High-risk commands such as:

`git reset --hard`

`git clean -fd`

must not be used when they could destroy uncommitted work unless:

- the human project owner explicitly authorizes the action; or
- the agent can prove the affected files are disposable generated artifacts.

When uncertain:

**STOP AND ASK.**

---

# 27. Phase Merge Rules

A phase is normally eligible for merge into `main` only when:

- `SPEC.md` acceptance criteria are satisfied;
- all required checkpoints are complete;
- all required checkpoint reviews pass;
- final cross-checkpoint review passes when required;
- relevant tests pass;
- Claude has completed architecture-compliance review;
- no unresolved architecture escalation exists;
- required business decisions are resolved or explicitly deferred;
- human approval has been granted.

Only then may the phase be marked:

`APPROVED`

and merged according to the repository workflow.

Checkpoint auto-push authority never bypasses these requirements.

---

# 28. Phase Completion Commit

When a phase is formally approved, documentation changes may be committed
separately.

Example:

`docs(phase-03): record approved infrastructure phase`

This commit may include:

- final `STATUS.md`;
- final `REVIEW.md`;
- updated `CURRENT_PHASE.md`;
- approved ADR changes;
- architecture documentation updates.

Do not mix large implementation changes into this administrative commit.

This phase-completion commit may be pushed to the phase branch once the human
approval it records actually exists.

---

# 29. Dependency Changes

Adding, removing, or significantly upgrading dependencies must be intentional.

Before committing a new dependency, verify:

- why it is necessary;
- whether the standard library or existing dependencies already solve the
  problem;
- whether it affects deployment;
- whether it affects security/privacy;
- whether it expands architecture beyond approved scope.

Unexpected dependency additions must be surfaced during review.

---

# 30. Required Pre-Push Checklist

Before every push — including an automatic checkpoint push — verify:

1. Correct remote.
2. Correct branch.
3. Destination is not `main` unless explicitly human-authorized.
4. `git status` is understood.
5. All commits being pushed are understood.
6. Diff since the remote branch is reviewed.
7. No unrelated changes are included.
8. No secrets or sensitive data are included.
9. Relevant checkpoint tests pass.
10. Required regression tests pass.
11. Required lint/type/security checks pass when applicable.
12. Codex Reviewer gate has passed if this is a normal checkpoint-completion
    push.
13. No unresolved blocking review finding exists.
14. No unresolved invariant violation exists.
15. No unresolved architecture escalation exists.
16. Current phase/checkpoint permits the push.
17. Push is not a force-push.
18. The remote branch history will not be destructively rewritten.

If any required item fails:

**DO NOT PUSH.**

---

# 31. Generated Files

Generated files should only be committed when intentionally part of the
repository.

Do not automatically commit:

- caches;
- test artifacts;
- temporary PDFs;
- local databases;
- logs;
- coverage output;
- build output;
- downloaded models;
- local secrets;
- IDE metadata;
- Python cache directories.

Use `.gitignore` appropriately.

---

# 32. Sensitive Information

Before every commit and push, verify that no sensitive information is present.

Never commit or push:

- API keys;
- OAuth tokens;
- refresh tokens;
- passwords;
- private keys;
- service-account credentials;
- `.env` production values;
- customer medical or personal information;
- confidential production payloads.

If a secret is accidentally committed:

**STOP.**

Do not simply delete it in a later commit and assume the problem is solved.

Report the incident so the credential can be rotated and Git history can be
handled appropriately.

Do not push the affected history until the incident response is resolved.

---

# 33. Human Approval

Only the human project owner may grant final human approval of:

- material architecture changes;
- business decisions requiring human approval;
- phase completion;
- merge into `main`;
- force-push;
- destructive history rewrite;
- remote branch deletion.

Agents may write:

`READY_FOR_HUMAN_APPROVAL`

Agents may not write:

`HUMAN APPROVED`

unless the human has explicitly provided that approval.

Checkpoint automatic push is operational authorization and does not constitute
human approval of the overall phase.

---

# 34. Push Reporting

After every successful push, the responsible agent must report:

- remote;
- branch;
- latest pushed commit SHA;
- checkpoint or purpose of the push;
- whether it was:
  - automatic post-review checkpoint push;
  - human-authorized early/backup push;
  - phase-completion push;
- whether anything remains uncommitted locally.

Do not merely say:

`pushed`

The resulting remote state should be auditable.

---

# 35. Failure to Push

If a checkpoint has passed and automatic push is authorized but the push cannot
be completed because of:

- sandbox restrictions;
- missing Git credentials;
- repository permissions;
- unavailable remote;
- network restrictions;
- branch protection;

the agent must:

1. not pretend the push succeeded;
2. report the exact limitation;
3. preserve the reviewed local commits unchanged;
4. provide the remote, branch, and commit SHA that should be pushed;
5. allow Claude or the human project owner to perform the push if authorized.

A tooling limitation is not a reason to weaken Git rules.

---

# 36. Golden Rule

When there is a choice between:

**moving quickly**

and:

**preserving a clean, understandable, reviewed, recoverable project state**

choose the clean and recoverable project state.

Agents should make progress aggressively inside approved boundaries.

Local commits are implementation checkpoints.

Passing reviewer gates authorize safe remote backup of completed checkpoints.

Human approval continues to control architecture, phase completion, and `main`.

No agent may trade away auditability, architecture integrity, review quality,
or human control merely to finish faster.   