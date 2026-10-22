# deeper-proves-it

## Intent

Task: section 4 of the /deeper design: "a new brief field: `Proves it:` in `templates/brief.md`, right after `Done when:`. The brief parser requires it to name something outside the agent: a test, metric, dataset, external judge or the user. It rejects \"reviewed by crewmate\", \"reviewed by reviewer\", and empty or self-referential answers."
Done when:
- `templates/brief.md` has a `Proves it:` line right after the `Done when:` list, with its one-line guide in the template's own style
- the brief parser (`src/jbriefs/parse.py`, and the brief checks jbus runs before a launch, beside `dispatch.designed`) reads `Proves it:` and accepts it only when it names something outside the agent: a test (a test path or name, or a command), a metric, a dataset, an external judge, or the user. It refuses an empty line, the template's own text, and a proof by the crew, the crewmate, the reviewer, the agent, "self", "the model" or a review alone, with one line saying why
- a brief with no `Proves it:` line is handled as the Design line was introduced: say in the Result whether existing queued briefs are refused or grandfathered, and pick the one that does not strand an approved row (a gate if it needs the user)
- tests: each accepted kind, each refused kind, the empty line and the template line
- the home skill's brief section and `docs/` that list a brief's lines name the new one
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the parser tests above, and one real queued brief run through the launch check, with the line printed
Where: `templates/brief.md`, `src/jbriefs/parse.py`, `src/jbus/dispatch.py`, `skills/home/SKILL.md` (the brief lines only), `docs/`, the tests
Do not touch: the other brief lines and their rules; `skills/deeper/` and the principle (deeper-skill's)
Decisions: the user, 2026-10-15 01:33 ET, word 57fb24bc8b71, from Sous Chef's Grok Bot chat: "Yes, build it in jstack", approving the /deeper design by Poteto Stalker (saved at ~/.local/state/home/jstack/scouts/deeper-design.md), with his decisions of 01:32 ET in it: the principle is named depth-over-breadth; the home's brief step carries its own copy of the four questions and `/deeper` stays manual (`disable-model-invocation`); Altitude outcome briefs and a Range step are out. The split into three briefs is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/deeper-design.md, section 4

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

### 1. [Warning] The `_OUTSIDE` patterns accept self-referential lines because they are checked before `_SELF`
**Location**: src/jbriefs/parse.py:31-36 (patterns), used at parse.py:126-128 in `proof()`
**Finding**: `proof()` returns success as soon as any `_OUTSIDE` pattern matches anywhere in the line, and only then looks at `_SELF`. Several of those patterns match ordinary words, so lines that name only the agent pass:
- `\bmake \w` matches "make sure the reviewer is happy", which passes as "a test".
- `\btests?\b` matches "self-test", because the hyphen counts as a word boundary. It passes as "a test", yet the task says self-referential answers are refused.
- `` `[^`]+` `` matches any text in backticks, so "`the crewmate` checks it" passes as "a test".
- `\bhis (word\|pick\|eye)\b` matches "the reviewer gives his word", which passes as "the user".
- `\bevals?\b`, `\bbenchmarks?\b` and `\bgithub\b` let "the agent's own eval" and "reviewed by the crewmate on github" through.
**Evidence**: The Done-when line says the parser "refuses ... a proof by the crew, the crewmate, the reviewer, the agent, 'self', 'the model' or a review alone". The docstring rule "a test the crewmate runs is still a test" is right for "the crewmate runs tests/test_x.py". But the patterns are loose enough that the gate can be passed without meaning to, using phrases a home would write normally. None of the tests covers a near-miss like this. Every REFUSED case is a short phrase with no outside keyword in it.
**Suggestion**: Tighten the "a test" pattern so it needs a path (`tests?/\S+`, `test_\w+`, `\w+_test\.py`) or a command. That means backticks holding a known tool such as `make`, `uv`, `pytest` or `jbus`, not any backticked text. Drop `make \w` unless it is followed by a target and is not "make sure". Drop "his word"/"his pick"/"his eye" or tie them to "the user"/"the operator". Add REFUSED cases for "self-test", "make sure the reviewer is happy", "`the crewmate` checks it" and "the reviewer gives his word".

### A2

### 2. [Warning] A brief without the line is let through for good, not only briefs queued before this change
**Location**: src/jbus/dispatch.py:157-164 (`proven`), parse.py:135-141 (`proves_it` returns None), docs/jbus.md:85
**Finding**: The Done-when line asks for briefs that were *already queued* to be grandfathered. What the code does is let any brief with no `Proves it:` line launch, including briefs written after this change. A home that leaves the line out gets no gate. The new requirement then holds only through the prose in skills/home/SKILL.md, which is the "rule in prose" case question 4 warns about.
**Evidence**: `proven()` returns `""` whenever `parse.proves_it` returns None. Nothing ties the exemption to when the row was approved or to the brief's sha. The docs line "A brief with no `Proves it:` line was written before the line was asked for" is something the code assumes but never checks.
**Suggestion**: Grandfather by something the queue already records. For example, exempt rows whose `approved` time (or `brief_sha`) is from before a cut-off, and gate missing lines on anything approved later. Approved rows are then not stranded, and leaving the line out stops being a way around the gate.

### A3

### 3. [Warning] A brief that fails both the design and proof checks causes two gates and two re-approvals
**Location**: src/jbus/dispatch.py:332-334
**Finding**: `proven()` runs only when `designed()` returns nothing. If a brief has no `Design:` line and also a refused `Proves it:` line, the first gate reports only the design problem. the user fixes it and re-approves (new sha). Only then does the next pass raise the proof gate, which needs another edit and another approval.
**Evidence**: `short, kind = designed(brief), "no design"; if not short: short, kind = proven(brief), "no proof"`. Every approval is the user's, so each extra round costs him.
**Suggestion**: Gather both reasons and send one gate. For example, `faults = [f for f in (designed(brief), proven(brief)) if f]`, joined with `; ` and keyed by the brief sha. This also removes the `kind` pair juggling.

### A4

### 4. [Nit] The head-scanning loop is now written twice, in two packages
**Location**: src/jbriefs/parse.py:135-141 (`proves_it`) and src/jbus/dispatch.py:139-154 (`designed`, not changed)
**Finding**: `proves_it` repeats `designed`'s loop line for line: stop at `## `, take the first line that starts with a label, strip the label. The two also detect the template text by the same `startswith("<")` test (parse.py:124). `dispatch.proven` is a pass-through, `found.why if found else ""`.
**Suggestion**: Add one `head_line(text, label) -> str | None` to `jbriefs.parse`, and have both checks return `why`. Moving `designed` there is a change to existing code, so note it for later. In this PR, `proven` could be removed by having `proves_it` return `Proof` with an empty `why` when the line is missing.

### A5

### 5. [Nit] `Brief.proof` and `Proof.said` are only used by tests
**Location**: src/jbriefs/parse.py:166-168, and the `said` field at about parse.py:105
**Finding**: Nothing in `src/` reads `Brief.proof`. jbus calls `parse.proves_it` directly, and the jbriefs page does not show the field. Only tests/test_briefs.py reads it. `Proof.said` is the same: only read in test assertions.
**Suggestion**: Remove the property, or show it on the jbriefs page if that was the plan. As it stands it is surface area with no consumer.

### A6

### 6. [Nit] The template text is detected by a leading "<"
**Location**: src/jbriefs/parse.py:124
**Finding**: The line counts as "the template's own text" only if it starts with `<`. If a home deletes the angle brackets but keeps the guide text ("what outside the agent shows it holds: a test or a command, ... the user ..."), the line is accepted as "a test", because `\btest\b` matches the template's own wording.
**Suggestion**: Compare against the template's actual `Proves it:` text with the brackets stripped, or refuse any line that contains `<` or `>`.

### A7

### 7. [Nit, no file] Two Done-when items cannot be checked from the diff
**Finding**: Two parts of the Done-when list leave no trace in the code. First, "say in the Result whether existing queued briefs are refused or grandfathered". Second, the "Proves it: ... one real queued brief run through the launch check, with the line printed". Grandfathering is stated in the dispatch.py docstring and in docs/jbus.md, but the Result and the printed run against a real queued brief must be checked in the brief's Result.

### B1

### 1. [critical] The words that count as "outside" are loose enough to accept the agent's own word, and they are checked first
**Location**: src/jbriefs/parse.py:133-142 (`_OUTSIDE`), used at :190-192 in `proof()`
**Finding**: `proof()` returns success on the first `_OUTSIDE` match and never reads `_SELF` afterwards. Several of the `_OUTSIDE` patterns match ordinary words that say nothing about a test, metric, dataset or judge. Lines that only name the crew, the reviewer or the model are accepted:
- `` `[^`]+` `` treats any backticked text as "a test". So ``the `reviewer` says so`` or `` `self` `` is accepted.
- `\bmake \w` matches "make sure". So "the crewmate will make sure it works" is accepted as "a test".
- `\d\s*%` matches any percentage. So "the reviewer is 100% sure" is accepted as "a metric".
- `\bjudge\b` matches "the model is the judge", which is accepted as "an external judge". "the model judges it" is refused only because "judges" misses the `\b`.
- `\bevals?\b` and `\bthe user\b` match "the reviewer evals it" and "the crewmate, as the user asked".

**Evidence**: The task says to refuse "a proof by the crew, the crewmate, the reviewer, the agent, 'self', 'the model' or a review alone". This gate is the only thing standing between such a line and a launch: `dispatch._ready` launches whenever `proven()` returns "". The docstring's reason for checking `_OUTSIDE` first ("a test the crewmate runs is still a test") only holds when the outside match really is a test. Here a bare keyword is enough.
**Suggestion**: Make the `_OUTSIDE` patterns specific: a backticked span only when it looks like a command or path, `make <target>` only for a known form like `make check`, and `%` only when a metric word is near it. Or require that what is left after removing the `_SELF` matches still names something outside. Either way, add refused cases to `REFUSED` for each example above.

### B2

### 2. [warning] The tests only exercise the cases the regexes were written for
**Location**: tests/test_briefs.py:299-329 (`PROOFS` / `REFUSED`)
**Finding**: Only one case mixes a self word with an outside word: "the crewmate runs tests/test_briefs.py", and it is meant to pass. No case checks that a self-referential line refuses when it contains one of the broad trigger tokens (a backticked word, "make sure", a percentage, "judge").
**Evidence**: Every example in finding 1 passes the current suite. The precedence rule is the riskiest part of the change, and the tests pin only its happy side.
**Suggestion**: Add `REFUSED` entries that execute `parse.proof` on lines like the ones in finding 1.

### B3

### 3. [warning] A second hand-written loop over the brief's head lines, and a check split across two layers
**Location**: src/jbriefs/parse.py:199-206 (`proves_it`), src/jbus/dispatch.py:157-164 (`proven`)
**Finding**: `proves_it` repeats the loop in `dispatch.designed`: walk the lines, stop at `## `, match a label prefix. So the two launch checks now live in different modules with different shapes. `designed` returns a string in dispatch; `proven` is a two-line wrapper over a `Proof` object in jbriefs. The `_ready` change adds `short, kind = designed(...), "no design"; if not short: short, kind = proven(...), "no proof"`. Each further brief check will need another branch like it.
**Evidence**: The two loops are the same except for the label. A third check means a third loop and another branch in `_ready`.
**Suggestion**: Write one `head_line(text, label) -> str | None` helper in `jbriefs.parse`. Have both checks use it, and make `_ready` iterate over a tuple of `(kind, check)` pairs. Moving `designed` into parse is outside this task's "Where" (and its rules are "do not touch"), so note that part for later.

### B4

### 4. [nit] `Brief.proof` has no caller outside the tests
**Location**: src/jbriefs/parse.py:166-168
**Finding**: Nothing in `src/` reads `Brief.proof`. The jbriefs page and CLI never show it, and jbus calls `parse.proves_it` on the raw text. The property only gives the tests a second way to reach the same function.
**Evidence**: Searching `src` for `.proof` and `proves_it` finds only the `dispatch.py:163` call.
**Suggestion**: Drop the property, or use it in jbriefs where it would be shown.

### B5

### 5. [nit] Detecting the template's text by a leading `<` is a guess about the input
**Location**: src/jbriefs/parse.py:188-189
**Finding**: Any line that starts with `<` is refused as "the template's own text", including a real one like `<= 50 ms p95 from jgauge`. A template line with its first character changed is no longer recognised.
**Evidence**: The template's text is known, since `templates/brief.md` is the one copy. Comparing against it, or against the `<...>` placeholder pattern as a whole, would be exact.
**Suggestion**: Match `^<[^>]*>$`, or compare with the template's line.

### B6

### 6. [nit, no file] Two "Done when" items cannot be seen in the diff
**Finding**: The "Done when" asks for the grandfather-or-refuse decision to be stated in the Result, and for one real queued brief to be run through the launch check with the line printed. The diff shows the grandfathering in docs and code (docs/jbus.md:85, the dispatch.py docstring), but not the Result or the run. Check the Result.
