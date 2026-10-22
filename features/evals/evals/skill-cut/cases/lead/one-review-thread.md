# one-review-thread

## Intent

Task: the user, 2026-10-15 22:34 ET (word ad710449692a), voice call relayed by Sous Chef: "replace the two pr-review reviewer threads (A/B) per PR with one scoped review thread that reviews only the PR's diff, posts one combined review, and archives itself when the PR merges or closes. Done when a new PR gets exactly one review thread and it auto-archives on merge. Must still satisfy jmerge's review-at-head requirement." Today the pr-review skill (`skills/pr-review/SKILL.md`, "The review", step 3 around line 349) starts two `Agent` subagents, "pr-review reviewer A" and "B", inside the reviewer thread; T3 shows each as a thread under it. The reviewer settles itself at its end (line 533), and jbus's `threads.settle` (`src/jbus/threads.py:322`) settles a finished slug's threads and their subagent threads, but archives none.
Done when:
- the reviewer thread reads the diff itself (`gh pr diff`), with the same intent, `SCOPE` text and seven questions, and starts no reviewer subagent: no "reviewer A" or "B" thread exists for a new pull request. The blast-radius proof stays, run in the same thread. The `## Review` section keeps every line jmerge and jbus read (`Head:`, `Patch-id:`, `Verdict:`, `Findings:`, the `Finding:` lines the crewmate answers), with `Reviewers: 1`
- the reviewer sends the crewmate one combined review, and writes one `## Review` section
- jmerge's ready rule still passes on that section: a review of the head, its findings answered, as `src/jmerge/ready.py` reads it today, with no change to `ready.py` unless a test shows one is needed
- when a pull request merges or closes, jbus archives (not only settles) its review thread on the next pass; a review thread of an open pull request is never archived
- the interrogate skill and any other skill or doc that tells pr-review to start two reviewers says one; `skills/pr-review/SKILL.md`'s description and card say one review thread
- tests: the skill text names no reviewer A/B subagent call; a jbus pass with a merged pull request archives its `review:` thread and leaves one of an open pull request alone; a `## Review` section in the new shape is read as ready by jmerge
- `make check` exits 0
Proves it: `make check` runs the tests above; after the merge, the next pull request on this machine has exactly one review thread in `t3_thread_list`, and it is archived after jbus merges it
Size: M
Where: `skills/pr-review/SKILL.md`, `skills/interrogate/SKILL.md` (only where it is pr-review's caller), `templates/review.md` if it names two reviewers, `src/jbus/threads.py`, `docs/jbus.md`, the tests
Do not touch: `src/jmerge/ready.py` unless a test proves the new section fails it; reviews already written in briefs; `~/.config/`
Decisions: the user's words under Task. A question only he can answer is a gate through `jbus gate`, with the default taken; ask him nothing in this thread.
Design: none, the Done when list pins the one thread, the section shape and the archive

Playbook: authoring-a-skill, the steps the crewmate worked by.
The principles it cites, and when each applies:
- encode-lessons-in-structure: Apply when you catch yourself writing the same instruction a second time, or notice a recurring correction. Encode the rule as a lint, metadata flag, runtime check, or script instead of more text.
- prove-it-works: Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'
- test-behavior-not-implementation: Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change.

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

### 1. [warning] The jmerge "new shape" test never puts a finding in the section, so it doesn't test what it claims
**Location**: tests/test_pr_review_skill.py:1512-1534 (`test_jmerge_reads_a_review_written_from_the_template_by_one_reader_as_ready`)
**Finding**: The template line is `Findings:` with nothing after the colon (`cat -A templates/review.md` shows `Findings:$`). It does not contain `": "`, so the generator copies it through unchanged.
- `filled["Findings"]` (`"\n- warning a.txt:1 it is wrong ..."`) is never used.
- `.replace("Findings: \n", "Findings:\n")` changes nothing.
- The template's `- <severity> ...` line is filtered out by `not line.startswith("- ")`.

So the brief jmerge reads has `Verdict: findings`, an empty `Findings:` list, and one `Finding: not fixed` line. `ready.py` (lines 298-303) counts `said.found` only from `- ` lines under `Findings:`, so `found == 0` here. The "every finding it lists has its `Finding:` line" rule is never tested against a real listed finding.
**Evidence**: The Done when line asks for "a `## Review` section in the new shape is read as ready by jmerge", meaning a review of the head with its findings answered. As written, the test would still pass if the findings/answers matching broke.
**Suggestion**: Write the `Findings:` line and its `- warning a.txt:1 ...` item into the section explicitly, or fill keys on a `:` split rather than `": "`. Then add a negative case: the same section with no `Finding:` line must not be `ready`. (principle: test-behavior-not-implementation)

### A2

### 2. [warning] "Closed" is inferred from absence in a 100-item open list, and the result is an archive
**Location**: src/jbus/threads.py:164-174 (`shut`)
**Finding**: `shut` treats a slug as closed when its last Result's `Branch:` URL is not among `world.open`'s URLs. `world.open` comes from `pulls(run, "open", ..., "--limit", "100")` (watch.py:210). Nobody reads the pull request's actual state.
**Evidence**: Any open pull request that falls outside that list gets its `review:` thread settled and archived:
- the 101st open PR;
- a PR keyed differently;
- a Result whose URL differs in form from GitHub's `url`.

The Done when line says "a review thread of an open pull request is never archived". The `tests/test_work.py:243` change shows the behaviour change in practice: a review thread of a PR missing from `open.json` is now archived, where before it was left alone. Before this change, the absence inference only kept a crew thread out of `tasks`. Now it drives a destructive action that jbus never undoes.
**Suggestion**: Confirm "closed" from the real state, for example with `_named(run, url)` / `gh pr view --json state`, cached the way `merged.json` caches merges. At minimum, restrict the archive to `world.merged` plus a PR whose state GitHub reports as `CLOSED`. (principle: none)

### A3

### 3. [warning] `docs/flow.html` still says the reviewer runs two reviewers and settles itself (no file: a gap in the change)
**Location**: no file (the stale text is in docs/flow.html:214, which this change does not touch)
**Finding**: The page still reads "Two reviewers, one lead, one proof ... Two reviewers who do not see each other read the diff ... then settles itself". The Done when line requires that "any other skill or doc that tells pr-review to start two reviewers says one". The change updated `docs/flow.md`, `README.md` and `docs/jgauge.md` but missed this hand-written page.
**Evidence**: `grep -rn "two reviewers" docs` finds it. `docs/jstack-explained.html` is built from the card by `jdrift.explained` in the docs sweep, so that one is exempt. `flow.html` is not built. `tests/test_flow_doc.py` only checks that names exist, so nothing catches it. (principle: encode-lessons-in-structure)

### A4

### 4. [warning] `finished()` adds a non-prefix "archive" key to a map keyed by title prefix
**Location**: src/jbus/threads.py:203-208 and 363-364, 384-385, 394
**Finding**: The map `{"crew: ", "review: ", "scout: "}` is keyed by title prefix, and `"archive"` is now a mode flag inside it. To use it, `settle` needs three extra pieces:
- the `prefix == "review: " and slug in over["archive"]` special case;
- a second `shelve` set copied down to subagents;
- a nested action loop with `break`.

**Evidence**: The rule is simply "a `review:` thread whose slug is in `shut(...)` is also archived". `slug_of` already gives each thread's slug, subagents included. So the action list can be computed at the call site: `("settle", "archive") if role_of(title) is review and slug_of[at] in ended else ("settle",)`. That removes the dict key and the `shelve` propagation. The `ended` set can be returned or computed once.
**Suggestion**: Keep `finished` as a prefix map. Compute `ended = shut(world, briefs)` in `settle` and derive the archive decision from it, or return it as a separate value. (principle: none)

### A5

### 5. [info] A merged PR's review threads are never archived when the brief's last Review is `not run`
**Location**: src/jbus/threads.py:197-201, 207
**Finding**: `archive` is `reviewed & ended`, and `reviewed` requires the brief's *last* `## Review` verdict to be `clean` or `findings`. Suppose a later scoped pass writes `Verdict: not run`. Then no `review:` thread of that slug is archived after the merge, including the first reviewer, which already finished cleanly.
**Evidence**: The Done when line says "when a pull request merges or closes, jbus archives ... its review thread on the next pass". "One that stopped early stays" made sense while the PR was open. After a merge, the thread waits on nothing.
**Suggestion**: For slugs in `ended`, archive non-busy review threads regardless of verdict, or say in `docs/jbus.md` that these are kept on purpose. (principle: none)

### A6

### 6. [info] Step 4's claim about what the reading was not given is false in a single thread
**Location**: skills/pr-review/SKILL.md:232
**Finding**: "Judge it against what the reading was not given: the brief's decisions, and the repo..." No longer holds:
- The reading is this same thread, which read the whole brief in Start step 1.
- The intent the reading is given runs from `Task:` through `Decisions:`.
- Step 3 tells the reading to open the code around the diff.

**Evidence**: The text survives from the two-subagent design, where the lead really had context the readers lacked. In one thread it tells the reviewer it has an independent check that it doesn't have.
**Suggestion**: Say what the lead step actually adds now: re-checking each claim against the repo and the brief. (principle: none)

### A7

### 7. [info] Files outside the brief's `Where` line
**Location**: README.md:98, docs/flow.md:17, docs/jgauge.md:22, src/jbus/t3.py:7 and 282-288
**Finding**: The brief's `Where` does not list `README.md`, `docs/flow.md`, `docs/jgauge.md` or `src/jbus/t3.py`. The three docs are covered by the Done when line about "any other skill or doc". `t3.py` is needed, because `_held` refused `archive`. Each is still outside `Where`.
**Evidence**: The diff stat lists them, and none appears on the `Where:` line. (principle: none)

### A8

### 8. [nit] The new `docs/jbus.md` sentence about settling closed PRs is hard to parse
**Location**: docs/jbus.md:108
**Finding**: "...only when the brief's last Review has the verdict `clean` or `findings`, and then also when the pull request closed unmerged" reads as if closing unmerged were a second verdict condition. What the code does (`(tasks | ended)` at threads.py:197): a reviewer is over when its task is over *or* its pull request closed, and in both cases the last verdict must be `clean`/`findings`.
**Suggestion**: Rephrase it to say that. (principle: none)

### B1

### 1. [warning] `shut()` adds a second rule for "closed" that disagrees with `watch.pull`
**Location**: `src/jbus/threads.py:164` (`shut`)

**Finding**: `src/jbus/watch.py` already decides whether a slug's pull request is closed, in `pull()` (around line 368). It returns `Pull.CLOSED` when the slug has no open or merged pull request and its `Branch:` line ends on an address. The new `shut()` decides the same thing a different way: it checks whether the Result's address string appears among the open pull requests' URLs, then removes the slugs in `world.open`.

**Evidence**:
- The two rules can give different answers. The new test shows one case: `eta` names `pull/8`, which is open under the slug `delta`. `watch.pull` says `eta` is closed, and `shut()` says it is not. So the work view and the archive rule now disagree about the same brief.
- `shut()` matches raw URL strings. An address that differs only in form (a renamed or transferred repo, or `http` vs `https`) is never found among the open URLs. If that pull request's branch is also not named after the slug, the review thread of a still-open pull request gets archived. The task says that must never happen.

**Suggestion**: Drop `shut()` and use the existing rule, along the lines of `{slug for slug, text in briefs.items() if pull(world, slug, mirror.last_result(text), "") in (work.Pull.MERGED, work.Pull.CLOSED)}`. Then "merged or closed" is defined in one place. (principle: none)

### B2

### 2. [info] Step 4 says the reading was not given the brief's decisions, but it was
**Location**: `skills/pr-review/SKILL.md:232`

**Finding**: Step 4 now says "Judge it against what the reading was not given: the brief's decisions". That is no longer true.
- Step 1 of "Start" has this same thread read `$H/tasks/<slug>.md`.
- The intent built in steps 1 and 2 copies the brief "from `Task:` to the end of `Decisions:`".

**Evidence**: The old version was true because the two `Explore` reviewers really did not see the brief beyond the intent. With one thread, the lead is judging its own list, so the outside check the sentence promises does not exist. A reader could think there is still an independent cross-check when there is none.

**Suggestion**: Say plainly that the reading and the judgment are the same thread. Point the judgment at what does add something: checking each claim against the repo, and the dismissal discipline. (principle: none)

### B3

### 3. [info] The test fakes keep archived threads in the list and never archive the subagents under them
**Location**: `tests/test_jbus_kitchen.py:269`, and `src/jbus/threads.py:372`

**Finding**:
- The fake `t3_thread_organize` sets `archived` and keeps listing the thread. Real T3 Code may stop listing an archived thread. The test therefore never checks what happens after an archive in a world where archived threads disappear.
- `settle()` collects the threads under a review thread with `settled=False` only. A reviewer A/B subagent that was already settled before this change is never archived, even when its parent is.

**Evidence**: The test asserts the archive calls and the `archived` flag on the fake, not what T3 Code would show afterwards. Reviews started under the old skill with A/B subagents leave settled, unarchived subagents behind.

**Suggestion**: Have the fake drop archived threads from `t3_thread_list`, and add a case with a settled subagent under a shelved parent. (principle: test-behavior-not-implementation)

### B4

### 4. [info] Files changed outside the brief's `Where` line
**Location**: `README.md:98`, `docs/flow.md:17`, `docs/jgauge.md:22`, `src/jbus/t3.py:282`

**Finding**: None of these four files is on the `Where` line.
- **`README.md`, `docs/flow.md`, `docs/jgauge.md`**: these are covered by the `Done when` line "any other skill or doc that tells pr-review to start two reviewers says one".
- **`src/jbus/t3.py`**: the archive cannot work without it, because `_held` refused every `archive` call before this change.

**Evidence**: Each changed line traces to the task, so there is no harm. They are still outside `Where`, and the brief should have listed `src/jbus/t3.py`. (principle: none)
