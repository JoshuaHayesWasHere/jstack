# deeper-home-step

## Intent

Task: section 3 of the /deeper design: a step in the home skill's brief writing, not a separate file, that runs on its own for research, perf, analysis and outcome briefs, with its own copy of the four questions
Done when:
- `skills/home/SKILL.md`, where a home writes a brief or a scout request, has the step: for a research, perf, analysis or outcome brief (named how the home tells them, for example by its playbook: investigation, perf-issue, and the like), the home answers the four questions, its own copy of them in the step (not a call to `/deeper`, which stays manual), and puts answer 2 (the rawest material) in the scout's `Read:` or the request's sources, answer 3 (methods and tools) in the brief for the crew, and answer 4 in `Proves it:`
- a mechanical fix, a docs change and a bug fix with a known cause skip the step, as the principle's boundary says
- the skill's tests that pin its text (grep `tests/` for the home skill) cover the step: it is there, it names the four questions, and it maps 2, 3 and 4
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the skill text tests, and one brief this repo's home writes after the merge carrying the four answers in Read, the crew's lines and Proves it (the home checks it; the Result says how it was checked before the merge)
Where: `skills/home/SKILL.md`, `templates/scout-request.md` if the sources line lives there, the tests of the home skill
Do not touch: `skills/deeper/`, the principle, `templates/brief.md` and the parser
Decisions: the user, 2026-10-15 01:33 ET, word 57fb24bc8b71, from Sous Chef's Grok Bot chat: "Yes, build it in jstack", approving the /deeper design by Poteto Stalker (saved at ~/.local/state/home/jstack/scouts/deeper-design.md), with his decisions of 01:32 ET in it: the principle is named depth-over-breadth; the home's brief step carries its own copy of the four questions and `/deeper` stays manual (`disable-model-invocation`); Altitude outcome briefs and a Range step are out. The split into three briefs is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/deeper-design.md, section 3

Scope of this review. It overrides anything above that reads wider.
Review only the lines this pull request changes: its diff against its base branch.
Report a finding only when it is about a changed line, or about something a changed line breaks. Give every finding the file and line of the changed line, and when the damage is elsewhere, say where in the text.
For a finding about a removed line, give the line that now sits just before or just after where it was. For a finding about what the change as a whole lacks (a "Done when" line it does not meet, a test it does not have), give no file and say so.
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

### 1. [Warning] `Instruments:` is a brief line that nothing else knows about, and the new text contradicts the brief template
**Location**: skills/home/SKILL.md:530 and :537 (the damage is in templates/brief.md:17 and skills/scout/SKILL.md:125)
**Finding**: The step sends answer 3 to "A brief's Instruments: line". It also says a home-written brief "has a `Read:` line with answer 2 and an `Instruments:` line with answer 3, though the home wrote it."
- `templates/brief.md` has no `Instruments:` line. Its line 17 says that apart from a light scout's answer, "any other brief the home writes leaves all five out", and `Read:` is one of those five.
- The scout skill (skills/scout/SKILL.md:125) tells a scout to fill "the five lines the template keeps for a scout, `Read:` to `Ruled out:`". It never mentions `Instruments:`.
- `grep -rn Instruments` finds the field only in this diff and in evals/deeper. No skill, template or parser defines or reads it.
**Evidence**: A home following this step writes a line the template forbids for its briefs, plus a field no one defines. A scout following its own skill drops answer 3. The only way answer 3 reaches the scout's brief is that the home remembers to write it into the request's "Deliver" line.
**Suggestion**: Name an existing destination for answer 3, such as `Change:`, the Done-when list, or the line a playbook row asks for. Alternatively, the field must be added to `templates/brief.md` and the scout skill. That file is under "Do not touch", so if that is the remedy, note it as a follow-up rather than leaving the contradiction in this PR.

### A2

### 2. [Warning] The case statement judges the playbook, not the kind of work, so outcome work and bug fixes with an unknown cause are always skipped
**Location**: skills/home/SKILL.md:520–533
**Finding**: The kind of work (`research | perf | analysis | outcome`) is only looked at when the playbook is `none`. Whenever a playbook is picked, its name alone decides.
- `bug-fix` always skips. Its row is "reproduce, root-cause and fix with runtime evidence", which covers bugs whose cause is not yet known. The task's boundary, and the skip message itself, exempt only "a bug fix with a known cause".
- Outcome work always skips when it carries `feature` or `autonomous-run` (a task "driven to its Done when"), because neither is in the arm.
**Evidence**: Run the block with `picked='bug-fix'`. It prints `skip: bug-fix is not research, perf, analysis or outcome work: ... a bug fix with a known cause ...`, even for a bug whose cause is unknown. The intent asks for the step on outcome briefs, but the only way an outcome brief gets it is with no playbook at all.
**Suggestion**: Make the kind of work the input in every case: `kind='research|perf|analysis|outcome|other'`. The playbook can be a default for the kind, but should not replace it. That turns the ten-name list into the four kinds and lets a known-cause or unknown-cause bug fix be classed correctly.

### A3

### 3. [Warning] For a scout's request, the step is decided by the scout's playbook, not by the task the brief is for
**Location**: skills/home/SKILL.md:430 (with the case arm at :526)
**Finding**: Step 1 for a durable scout runs the deeper block with the request's playbook. Only two playbooks are run by a scout: `investigation` and `trace-forensics`. Both are in the deeper arm.
**Evidence**: Every scout request that has a playbook gets the four questions. That includes a request whose "Deliver" asks for a brief for a refactoring, a docs change or a bug fix with a known cause. The step then has the home push answers 3 and 4 onto that brief through the Deliver line. The principle's boundary says such work skips the step, so this breaks the second "Done when" line for scout-written briefs.
**Suggestion**: For a request, run the step with the kind of the task being briefed (as in finding 2), not with the scout's playbook.

### A4

### 4. [Warning] The list of playbook names is kept in the skill text, and the test cannot notice when it falls behind
**Location**: skills/home/SKILL.md:526; tests/test_home_deeper.py:136–140
**Finding**: The arm lists ten names by hand: `investigation | trace-forensics | runtime-forensics | perf-issue | hillclimb | eval | ...`. Each playbook's own `Run by:` row is where its kind of work is described. The test only checks that each listed name is a file in `playbooks/`.
**Evidence**: Suppose someone adds a new research-type playbook with `authoring-a-playbook`. The step skips it silently, and every test still passes. Nothing ties the list to the playbooks it is meant to cover. A rule kept in prose like this drifts.
**Suggestion**: Put a marker in each playbook's front matter or `Run by:` row and have the block read it, the same way the playbook-row block already reads `Run by:`. That would change files under `playbooks/`, which is outside "Where", so it is noted for later. Within this PR, the test could at least assert the reverse direction: that every playbook not in the list is one the boundary allows to skip.

### A5

### 5. [Nit] For a request whose "Deliver" asks for no brief, answers 3 and 4 have nowhere to go
**Location**: skills/home/SKILL.md:537
**Finding**: "where its Deliver list asks for the crewmate's brief, name them on that line". The text says nothing about a request that delivers a report or a visual page.
**Evidence**: In that case the home works out answers 3 and 4 and then drops them, with no instruction to do so. The "Done when" line says answer 4 goes in `Proves it:`, and here it goes nowhere.
**Suggestion**: Say what happens in that case. Either the step is skipped for such requests, or 3 and 4 go into the request's questions.

### A6

### 6. [Nit] The tests only run the block; nothing checks the instructions that tell the home where to write the answers
**Location**: tests/test_home_deeper.py:155–160
**Finding**: `test_the_answers_go_to_read_to_the_crew_and_to_proves_it` runs the block and checks the four lines it echoes. The rules for the request path (SKILL.md:430 and the "Deliver" sentence at :537) are not covered. Neither is whether `Read:` and `Instruments:` exist in any template.
**Evidence**: Finding 1's contradiction gets through because no test compares the lines the step names against `templates/brief.md` or `templates/scout-request.md`.
**Suggestion**: Add a test that takes each brief line the echoed questions name (`Read:`, `Instruments:`, `Proves it:`) and asserts it appears in `templates/brief.md`.

### B1

### 1. [warning] The step asks the home to write a `Read:` line, which `templates/brief.md` tells it to leave out, and an `Instruments:` line that nothing defines
**Location**: skills/home/SKILL.md:537 (and the echo lines at 529-530)
**Finding**: The step says "A brief the step ran on has a `Read:` line with answer 2 and an `Instruments:` line with answer 3, though the home wrote it." Two things contradict this:
- `templates/brief.md`, which the home is told to "read it first", says of `Read:`/`Change:`/`Rests on:`/`Sources:`/`Ruled out:`: "any other brief the home writes leaves all five out." A home that reads the template gets the opposite instruction to the step.
- `Instruments:` appears nowhere in the repo outside this diff. It is not in `templates/brief.md`, `skills/crew/SKILL.md`, `skills/scout/` or `src/jbriefs/parse.py`.

**Evidence**: Running `grep -rn Instruments skills templates src playbooks` finds only SKILL.md:530 and :537. The brief template is on the "Do not touch" list, so the PR keeps the conflict in place on purpose and does not settle which rule wins. The words "though the home wrote it" admit the clash without resolving it. So the crew's brief shape, and the scout writing the brief from a request, never learn about the `Instruments:` line. The only place it is named is the home's prose.
**Suggestion**: Reuse lines the template already has. Put answer 3 in the "Done when" list or the `Proves it:` line, or keep it as a plain sentence in the task body, and say so. If not, record in the Result that `templates/brief.md` and the scout's brief shape need a follow-up for `Read:` on home briefs and a new `Instruments:` line. Both files are outside "Where", so that would be noted for later.

### B2

### 2. [warning] The `bug-fix` playbook always skips, but it is the playbook for bugs whose cause is not yet known
**Location**: skills/home/SKILL.md:533 (the `*)` arm), tests/test_home_deeper.py:163
**Finding**: Any playbook not in the hard-coded arm prints "skip: … a bug fix with a known cause go by the direct path". `playbooks/bug-fix.md` is "Run by: a crewmate, for a reported defect to reproduce, root-cause and fix with runtime evidence". That covers bugs whose cause is unknown. The principle's boundary (`principles/depth-over-breadth.md`) exempts only "a fix whose cause is already proven". The test `test_a_mechanical_fix_a_docs_change_and_a_known_bug_skip_it` pins `bug-fix` as a skip and labels it "known bug", which locks the mismatch in.
**Evidence**: The home picks `bug-fix` for an intermittent crash with no known cause. The block prints `skip: bug-fix is not research, perf, analysis or outcome work…`. Yet raw logs, a bisect and a failing-before test are exactly what such a task needs.
**Suggestion**: Decide from the kind of work, not from the playbook name. For example, run the case on the kind (`research|perf|analysis|outcome|known-cause-fix|mechanical|docs`), which the home can state for every task. The playbook name would then not decide anything.

### B3

### 3. [warning] The playbook list is a hard-coded copy, so new or reused playbooks get no deep step without warning
**Location**: skills/home/SKILL.md:526; tests/test_home_deeper.py:136-140
**Finding**: The arm lists `investigation | trace-forensics | runtime-forensics | perf-issue | hillclimb | eval` by hand. The kind of work is used only when the home picked `none`. A research or perf task given a general playbook, such as `swarm` ("a race of several workers"), `autonomous-run` or `arena`, falls to `skip`. A playbook added later for research or perf work also skips unless someone remembers to edit this arm. That is a rule held only in prose and memory.
**Evidence**: `test_every_playbook_the_step_names_is_a_file_in_playbooks` checks only one direction: every name in the arm is a file. It does not check that every research, perf, analysis or outcome playbook is in the arm. The playbooks' `Run by:` lines already say what kind of task each one is for, and the row block above already reads them. This arm duplicates that information by hand.
**Suggestion**: Same remedy as finding 2: key the step on the kind of work the home states, with no list of playbook names. The duplication then goes away. Another option is a marker in each playbook's `Run by:` line, read the way the row block reads `in a brief with`. That would change `playbooks/`, which is outside "Where", so it is noted for later.

### B4

### 4. [warning] For a scout's request, answers 3 and 4 are lost when the request asks for no brief, and the mapping to "that line" is unclear
**Location**: skills/home/SKILL.md:537
**Finding**: "A request has no brief to hold 3 and 4: where its 'Deliver' list asks for the crewmate's brief, name them on that line". The "Deliver" brief entry in `templates/scout-request.md` is a single bullet about a path. Packing the methods with their commands and the outside judge into that bullet is ad hoc. The task asked for answer 4 in `Proves it:` and answer 3 in the brief for the crew. When the Deliver list has no brief (a report-only request), answers 3 and 4 are worked out and then go nowhere. There is no line to put them on and no instruction to put them in the questions.
**Evidence**: The "Done when" line says answer 2 goes in "the request's sources", which the step maps to the questions' "where to start looking". It gives no place for answers 3 and 4 in a request without a brief.
**Suggestion**: In a request, write answers 3 and 4 as `Questions:` items too ("measure with X: `cmd`", "what would show it is right: Y"). The template already has those items, so no new home is needed for the answers.

### B5

### 5. [nit] Durable-scout step 1 points at "the block under it", which is in another section
**Location**: skills/home/SKILL.md:430
**Finding**: "Then run the block under it that asks for the deeper version". The "it" refers to the row-printing block about 90 lines further down, in "Handing a task to a crewmate". The reader has to work out which block is meant.
**Suggestion**: Name it directly: "the block in 'Handing a task to a crewmate' that asks for the deeper version".

### B6

### 6. [nit] The extra skip condition is prose only and the block does not reflect it
**Location**: skills/home/SKILL.md:537 ("Skip it too for a task whose 'Done when' already names its data, its instruments and its outside judge.")
**Finding**: The block prints `deeper` for these tasks, and the trailing sentence then overrides it. The home has to remember the override after it has already seen the four questions printed.
**Suggestion**: Make it part of the input, for example as one more kind of work, so the block prints the skip itself.

### B7

### 7. [nit] Not shown by the change: the "Done when" lines about `make check` and `jgauge test-slot`
**Location**: none (about the change as a whole)
**Finding**: Nothing in the diff or the commit shows that `make check` exited 0 or that `jgauge test-slot -- make check` passed. Per my instructions I ran nothing, so these two "Done when" lines are still unchecked.
