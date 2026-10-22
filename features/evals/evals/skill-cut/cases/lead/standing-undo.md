# standing-undo

## Intent

Task: the user, 2026-10-15 22:31 ET (word e79623bff60c), relayed by Sous Chef: "re-home these 14 topics ... develop each into a brief". Topic 10: "A way to undo a bad merge into standing.md".
Done when:
- the home skill (where a home writes a standing rule, and `skills/home/scoped-homes.md:7`) and the handoff skill run `jbus snapshot` right after any edit to `$H/standing.md`, so each edit is a commit of its own in `~/.local/state/home` and is pushed; the twice-daily timer stays
- `jbus snapshot` takes an optional `--why <text>`, which goes in the commit message after the time (for example `snapshot 2026-10-15 22:40 ET: jstack standing rule 28 added`)
- `docs/state.md` has a short section "Undo an edit to standing.md": find it with `git -C ~/.local/state/home log -p -- <repo>/standing.md`, restore with `git -C ~/.local/state/home show <commit>^:<repo>/standing.md > ...`, then snapshot again with `--why`
- tests that execute: in a temporary state tree with a bare remote, an edit plus `jbus snapshot --why x` makes one commit whose message ends in `x` and touches that file; the restore command from the docs brings back the earlier text
- `make check` exits 0
Proves it: `make check` runs the tests above; after the merge, the next edit to `jstack/standing.md` shows as its own commit in `git -C ~/.local/state/home log -- jstack/standing.md`
Size: S
Where: `src/jbus/snapshot.py`, `skills/home/SKILL.md`, `skills/home/scoped-homes.md`, `skills/handoff/SKILL.md`, `docs/state.md`, `tests/test_jbus_snapshot.py`
Do not touch: any live `standing.md`; `~/.local/state/home` itself; the snapshot timer's times
Decisions: the user's words under Task. A question only the user can answer is a gate through `jbus gate`, with the default taken; ask him nothing in this thread.
Design: none, one flag and one step

Playbook: feature, the steps the crewmate worked by.
The principles it cites, and when each applies:
- model-the-domain: Apply when writing stateful logic, or when code branches a lot or repeats a shape assumption across files.
- foundational-thinking: Apply before writing logic: choosing core types and data structures, sequencing scaffold-vs-feature work, asking what concurrent actors share. Get the data structures right so downstream code becomes obvious.
- redesign-from-first-principles: Apply when integrating a new requirement into an existing design.
- exhaust-the-design-space: Apply when facing a novel UI interaction or architectural decision with no precedent in the codebase. Build 2-3 competing prototypes and compare side by side before committing.
- never-block-on-the-human: Apply when tempted to ask 'should I do X?' on reversible work.
- test-behavior-not-implementation: Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change.
- sequence-verifiable-units: Apply to multi-step work (sweeps, migrations, runs of similar edits) and to how you order commits and pull requests. Break work into small units that each end in a verifiable state, check each before the next, and order delivery so the sequence proves itself to a reviewer.
- subtract-before-you-add: Apply when sequencing an addition, refactor, or rewrite. Remove dead code, redundant validators, and stub references first, then build on the simpler base.
- boundary-discipline: Apply when wiring validation, error handling, or framework adapters. Concentrate guards at system boundaries (CLI, config, network, external APIs); trust internal types and keep business logic in pure functions.
- migrate-callers-then-delete-legacy-apis: Apply when introducing a new internal API while old callers still exist. Migrate callers and delete the old API in the same wave instead of preserving compatibility layers.
- prove-it-works: Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'

Scope of this review. It overrides anything above that reads wider.
Review only the lines this pull request changes: its diff against its base branch.
Report a finding only when it is about a changed line, or about something a changed line breaks. Give every finding the file and line of the changed line, and when the damage is elsewhere, say where in the text.
For a finding about a removed line, give the line that now sits just before or just after where it was. For a finding about what the change as a whole lacks (a "Done when" line it does not meet, a test it does not have), give no file and say so.
End every finding with the principle it breaks, `(principle: <name>)`, a name from the principles listed above, or `(principle: none)` when it breaks none of them or none is listed.
Do not report and do not fix a bug or weakness in code this pull request did not change, however real: those are handled elsewhere.
Do not ask for work beyond what the task above needed.
Read the changed code the way a tech lead would, and answer these about it:
1. Does it meet the task and every "Done when" line above? Name each line it does not meet.
2. Is it tested properly? A test must execute something. A new or changed test that only matches wording and executes nothing is a warning, and the remedy to name is a test that executes (one that runs the shell, parses the block and checks it, or runs the script), not deleting the test.
3. Does it do what the user wanted, not only what the words of the task say?
4. Is it correct? Look for these too, in the changed lines:
   - Run twice, or after a run that crashed halfway: if what happens depends on the state left behind, a reconciliation step is missing.
   - Shared state: where several actors can touch the same files, branches or data, is access kept in step by structure (a lock, sequential phases, one owner), or only by a convention that will not hold?
   - A rule in prose: a comment or convention someone has to remember, where a type, a lint rule or a runtime check would make the wrong thing impossible.
   - An old path kept beside a new one: with no outside consumer, the callers move and the old path goes in the same change.
   - A proxy: a check that reads a file's age, a cached value or a self-report, and not the real value or the output itself.
   - A bug fix with no test for the bug.
5. Could it be done more simply or cheaply? Look for these too, in the changed lines:
   - Be ambitious about structural simplification. Do not stop at "this could be a bit cleaner." Look for reframings that make whole branches, helpers, modes, conditionals or layers disappear. Assume a "code judo" move is often available: one that uses the existing architecture more effectively and makes the change dramatically simpler. If you can delete complexity rather than rearrange it, push hard for that.
   - A file the change pushes from under 1,000 lines to over 1,000: should it be split first?
   - Ad-hoc conditionals, special cases or one-off branches put into an existing flow, where a helper or a module of its own would hold the logic.
   - A thin abstraction, identity wrapper or pass-through helper that adds indirection and no clarity.
   - Logic outside its canonical layer: feature logic in a shared path, or a one-off where an existing helper would do.
   When the remedy for one of these would change a file outside the "Where" line above, say so in the finding: it is noted for later, not asked for in this pull request.
6. Does it leave everything it did not mean to change unaffected? Look for these too, in the changed lines:
   - A changed line that does not trace to the task: adjacent code, comments or formatting "improved" in passing, or a refactor of something that was not broken. Every changed line should trace directly to the task above.
   - A removal the change did not earn: an import, variable or function that was already unused before this change is named in the finding, not deleted. What the change itself made unused goes in the same change, and one left behind is a finding too.
7. Does it change a file outside the "Where" line above? Each such file is a finding.

## Findings

### A1

### 1. [warning] Snapshots now run at any time from many homes, with no lock against each other or the timer
**Location**: skills/home/SKILL.md:79, skills/home/scoped-homes.md:7, skills/handoff/SKILL.md:92 (the damage is in `src/jbus/snapshot.py` `take` / `_commit`, lines 191–213 of the diff context)
**Finding**: Before this change, the only thing that ran `take` was `jbus-snapshot.timer`, twice a day. Now every home, scoped homes included, runs `git add -A` → `gitleaks` → `git reset -q` / `git commit` → `git push` on the same `~/.local/state/home` index whenever it edits a `standing.md`. Nothing keeps these runs in step: there is no lock and no single owner.
**Evidence**: Two concrete failures follow:
- A home's snapshot that overlaps the 08:30 or 17:30 run makes one of the two `git add` or `git commit` calls fail on `.git/index.lock`. `_must` raises `Failed`. If the timer's run is the loser, the unit fails, and `OnFailure` runs `jbus snapshot --alarm`, which alerts the desk and every project for a failure that is not real.
- Home A's `_commit` runs `git reset -q` (gitleaks found a secret, or gitleaks is missing) between home B's `git add -A` and B's `git diff --cached`. B then sees nothing staged, prints `nothing changed`, and B's standing.md edit gets no commit of its own. That is the guarantee the task asks for.
**Suggestion**: Wrap `take` in an exclusive `flock` on a file inside the tree's `.git`, so concurrent runs wait for each other instead of failing. This is a change inside the "Where" line (`snapshot.py`).
(principle: foundational-thinking)

### A2

### 2. [warning] The documented restore empties standing.md when the parent commit has no such file
**Location**: docs/state.md:108
**Finding**: `git -C ~/.local/state/home show <commit>^:<repo>/standing.md > ~/.local/state/home/<repo>/standing.md` has a problem: the shell truncates the target file before `git show` runs. Suppose `<commit>` is the one that created `standing.md` (the first rule a repo ever got), or the root commit, or a mistyped hash. Then `git show` fails ("path ... exists on disk, but not in '<commit>^'", or a bad revision), and the live `standing.md` is left as an empty file. The next start reads that empty file whole as "no standing rules", and the next snapshot (timer or home) commits the empty file.
**Evidence**: The test (`test_the_documented_undo_brings_back_the_text_before_a_bad_edit`) only covers a parent that contains the file, because the tree fixture's first commit is not the commit that created `standing.md`. So this path never runs.
**Suggestion**: Document a form that does not write until `git show` succeeds, for example `git -C ~/.local/state/home restore --source=<commit>^ -- <repo>/standing.md`. That form also reports the missing-path case without touching the file. Add a test for undoing the edit that created the file.
(principle: prove-it-works)

### A3

### 3. [warning] "A commit of its own" holds only if nothing else in the tree is dirty, and the `--why` message then mislabels the commit
**Location**: src/jbus/snapshot.py:195 (`_commit(tree, f"snapshot {user.stamp(now)}" + ...)`)
**Finding**: `take` still stages the whole tree with `git add -A`. A home's `--why "<repo> standing rule 3 added"` commit also sweeps in every other home's queue, briefs, `merge.log`, `home-id` and so on that changed since the last snapshot. The commit message then names only the standing.md edit.
**Evidence**: The test passes only because the fixture tree is otherwise clean (`show --name-only` == `demo/standing.md`). In the live tree, between 08:30 and 17:30, other files are almost always dirty. The path-limited `log -p` and `show <commit>^:<path>` in the doc still work, so the undo itself is not broken. But the history the user reads (`git log` with no path) carries messages that describe something other than what the commit contains.
**Suggestion**: When `why` is given, the cheap structural fix is to accept paths and commit only those, for example `jbus snapshot --why ... -- <repo>/standing.md`, and leave the rest for the timer. If that is out of scope, have the message say it is a whole-tree snapshot.
(principle: model-the-domain)

### A4

### 4. [warning] "Snapshot after any edit to standing.md" is a rule in prose, copied into three places
**Location**: skills/home/SKILL.md:79, skills/home/scoped-homes.md:7, skills/handoff/SKILL.md:92
**Finding**: The same instruction, including the `--why` message template, is written out in three skill files. Nothing makes it happen. A home that edits `standing.md` and forgets the call gets its edit folded into the next timer snapshot, mixed with everything else. That is exactly the case the undo section assumes cannot happen.
**Evidence**: The "Proves it" line ("the next edit ... shows as its own commit") depends wholly on a model remembering a sentence in a table cell. The three copies are already drifting: handoff hardcodes `added`, while the other two say `<added, changed or removed>`.
**Suggestion**: Keep one statement of the rule (the `standing.md` row in home/SKILL.md) and have the other two point to it. The durable fix is a verb that writes the line and snapshots in one step, such as `jbus standing add "<rule>"`. That would touch files outside the "Where" line, so it is noted for later and not asked for here.
(principle: none)

### A5

### 5. [warning] The handoff skill gains a new duty to write standing rules, which the task did not ask for
**Location**: skills/handoff/SKILL.md:92
**Finding**: The added text "One it did not write yet goes there now, as one dated line" brings in a new behaviour: at handoff, write any rule not yet recorded. The task asked only that handoff snapshot after an edit to `standing.md`. It also sits right after "the home wrote it to `standing.md` when it heard it", which it now partly contradicts.
**Evidence**: Before this change, handoff never edited `standing.md`. The crewmate invented an edit so there would be a place to put the snapshot step, and that added line does not trace to the task.
**Suggestion**: Either cut the new duty and leave only "after any edit to `$H/standing.md`, run `jbus snapshot --why ...`", or raise it through a gate.
(principle: none)

### A6

### 6. [nit] A file outside the "Where" line is changed
**Location**: docs/jbus.md:40, docs/jbus.md:200
**Finding**: `docs/jbus.md` is not among the files the task names. It gets a new table row and a rewritten step 3 of "Back up the homes' state". The change itself is reasonable, since the flag would otherwise be undocumented on the commands page, but it is outside the stated scope.
(principle: none)

### A7

### 7. [nit] The new `with_origin` helper sits beside the old inline copy it duplicates
**Location**: tests/test_jbus_snapshot.py:266
**Finding**: `with_origin` repeats the bare-repo-plus-`remote add` sequence already written inline at lines 96–98 and 117–118 of the same file. Those tests were left as they were, so the file now has two ways to do the same thing.
(principle: migrate-callers-then-delete-legacy-apis)

### B1

### 1. [Warning] `--why` gives each standing.md edit its own commit only by convention; concurrent snapshots on the shared tree break it
**Location**: src/jbus/snapshot.py:195 (`take`, with `git add -A` at line 193). The rule is in prose at skills/home/SKILL.md:79 and skills/home/scoped-homes.md:7.
**Finding**: The change now runs `jbus snapshot` whenever a home edits a standing.md, as well as on the twice-daily timer. `take` still stages the whole tree with `git add -A` and has no lock. Every repo's homes, crewmates, scouts and jmerge write into `~/.local/state/home`, and several homes can snapshot at about the same time. Three things go wrong:
- **Mixed commits.** The commit labelled `--why "<repo> standing rule 3 added"` also carries other files that changed: briefs, `merge.log`, `merge-seen`, handoffs, and other repos' trees.
- **Two edits in one commit.** If the root home and a scoped home of the same repo both edit `<repo>/standing.md` before either snapshots, one commit holds both edits under one home's `--why`. Following the documented undo for "the bad one" then also reverts the other home's rule.
- **Lock failures.** Two snapshots at once (two homes, or a home and the timer) collide on `.git/index.lock`. One fails with `git add failed: ... index.lock: File exists` or `git commit failed`. The skills say nothing about retrying, so that edit lands in someone else's next commit.

**Evidence**: Done when asks that "each edit is a commit of its own". Nothing in the code enforces this: there is no lock, no path-scoped commit, and no check for a lock collision. It holds only if the homes happen not to overlap.
**Suggestion**: Hold an exclusive lock (`fcntl.flock` on a file in `.git`) across add, commit and push in `take`, so concurrent runs wait instead of failing. Also consider letting `--why` take the path it is about and commit only that path (`git commit -- <path>`), leaving everything else to the timer's snapshot. Then the message describes what the commit actually contains.
(principle: foundational-thinking)

### B2

### 2. [Warning] The documented restore command empties the live standing.md whenever `git show` fails
**Location**: docs/state.md:108
**Finding**: In `git -C ~/.local/state/home show <commit>^:<repo>/standing.md > ~/.local/state/home/<repo>/standing.md`, the shell truncates the target file before `git show` runs. If `git show` then fails, the live rules file is left empty. Three ordinary ways it fails:
- a mistyped or short-ambiguous `<commit>`;
- `<commit>` is the commit that first created `standing.md` (rule 1 added), so `<commit>^` has no such path;
- `<commit>` is the root commit, so it has no `^`.

The doc's next line then has the user snapshot that empty file, and the next home's start reads empty standing rules. The text says nothing about this.
**Evidence**: This is how shell redirection works. The test (tests/test_jbus_snapshot.py:309) covers only the case where the parent version exists.
**Suggestion**: Write to a temporary file and move it into place only on success: `git ... show <commit>^:<path> > <path>.tmp && mv <path>.tmp <path>`. Also say what to do when the edit created the file. Add a test where `<commit>` is the commit that created the file.
(principle: prove-it-works)

### B3

### 3. [Nit] The handoff skill gains a new duty to write standing rules, which the task did not ask for
**Location**: skills/handoff/SKILL.md:92
**Finding**: Before this change, the handoff skill never edited standing.md: "the home wrote it to `standing.md` when it heard it". The diff adds "One it did not write yet goes there now, as one dated line". That is a new place where rules are written, created so the snapshot step has something to attach to. It also contradicts the sentence just before it.
**Evidence**: The task asked the handoff skill to run `jbus snapshot` after any edit it makes to standing.md. It did not ask the handoff to start making such edits. `git show main:skills/handoff/SKILL.md` has no step that writes standing.md.
**Suggestion**: Keep only the snapshot instruction, worded generally ("after any edit to `$H/standing.md` in this skill, run `jbus snapshot --why ...`"), or tie it to an edit the handoff already makes. Don't add a rule-writing step.
(principle: none)

### B4

### 4. [Nit] A file outside the "Where" line is changed
**Location**: docs/jbus.md:40, docs/jbus.md:200
**Finding**: docs/jbus.md is not in the task's "Where" list but is edited, in its own commit (fc234ac). The content is accurate and useful: the command table and "Back up the homes' state" describe `--why`. It is still a change outside the stated scope, and the brief's Where line should have listed it.
**Evidence**: The Where line is `src/jbus/snapshot.py, skills/home/SKILL.md, skills/home/scoped-homes.md, skills/handoff/SKILL.md, docs/state.md, tests/test_jbus_snapshot.py`.
(principle: none)

### B5

### 5. [Nit] The test name says less than the test checks
**Location**: tests/test_jbus_snapshot.py:285
**Finding**: `test_a_snapshot_with_no_why_says_only_the_time` also checks the `why=` path of `snapshot.take` and its exact message, so the name describes only half of it. The no-why half is also already covered by `test_a_change_is_committed_as_a_snapshot_at_the_users_time` at line 77.
**Suggestion**: Drop the first half, which duplicates line 77, and rename the test for the `why=` message it actually checks.
(principle: test-behavior-not-implementation)
