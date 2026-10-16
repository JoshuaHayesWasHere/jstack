# brief-lint-approval-binding

## Intent

Task: the user, 2026-10-15 22:31 ET (word ff14298b8b7b), relayed by Sous Chef: "run the Size/Playbook/Proves-it and required-field checks before a brief is queued for the user, not after; and bind approval to the brief's content so cosmetic or wording-only edits keep the approval, while scope/risk changes still re-ask. Done when: an approved brief with a wording-only edit stays approved in a test, and an incomplete brief can't be queued." Merged in: topic #3 of his 13:06 list (word e79623bff60c), "Verifiable approvals: an approval record holding the user's message id plus the brief's content hash, so other bots can check it and the user isn't asked again. Also cover re-approvals when a brief's sha changes." Refined the same evening (word 0eb12af8334d): "tie the user's approval to what a brief says, not its exact wording. ... Approval should survive harmless edits (typos, formatting, reordering) while still catching real changes to intent or scope. Propose how to hash or fingerprint brief meaning so a reworded-but-equivalent brief keeps its go." Today the checks (`jbriefs` parse: Proves it, Size, Playbook) run at launch in `src/jbus/dispatch.py`, so a bad brief is queued, approved, then gated; and an approval is bound to `brief_sha`, the sha256 of the whole body (`src/jbus/queue.py:284-310`), so any edit voids it.
Done when:
- `jbus queue add` runs every check a launch runs (Proves it, Size, Playbook a real crewmate playbook, and the required fields of `templates/brief.md`: Task, Done when, Proves it, Size, Where, Pull request, Review, Playbook) and refuses an incomplete brief with one line per fault; nothing is queued. The launch keeps its checks as a backstop
- an approval binds to a meaning fingerprint, deterministic and with no model: over the fields that carry scope and risk (Done when, Proves it, Size, Where, Do not touch, Pull request, Review, Playbook, Stack), each line reduced to its content (lowercased, punctuation, whitespace and markdown dropped, a small fixed list of filler words dropped, the remaining words sorted), the lines of a list field sorted, and the fields in a fixed order. Kept exact, and so always a change: every path or code span in backticks, every number, every URL, and the values of Size, Playbook, Review, Pull request and Stack. A typo fix keeps the go: a word of five or more letters that is within two edits of the approved word counts as the same word when the fingerprints are compared. So typos, formatting, reordering lines or fields, and edits only to the title, Task, Decisions, Design, Read, Change, Rests on, Sources or Ruled out keep the go; an added, removed or changed Done-when line, path, number or value re-asks
- the PR description and `docs/jbus.md` state the fingerprint method above, its normalisation steps, and its known limit: a real reword that swaps a content word ("must" for "may") re-asks, by design, since a deterministic check cannot judge meaning beyond that
- the approval record holds both the scope fingerprint and the full `brief_sha` at the time of the go, plus the basis that already names the user's word id or message; `jbus queue show --json` (or a `jbus queue verify <slug>`) prints them so another bot can check that the brief it holds is the one he approved
- rows approved before this change keep working: an old full-text sha is read as before
- tests: an approved brief with a wording-only edit to Task stays approved and launches; one whose Done-when lines are reordered, re-wrapped and re-punctuated stays approved; an edit that adds a Done-when line or changes Size re-asks; a brief missing Size, Playbook or Proves it is refused by `queue add`; the verify output matches the record
- `docs/jbus.md` and the home skill's "Handing a task to a crewmate" say a brief is checked at `queue add`
- `make check` exits 0
Proves it: `make check` runs the tests above
Size: M
Where: `src/jbus/queue.py`, `src/jbus/dispatch.py`, `src/jbriefs/`, `src/jbus/cli.py`, `skills/home/SKILL.md` (Handing a task to a crewmate), `docs/jbus.md`, the tests
Do not touch: the rows already in any project's `queue.json` by hand; `~/.config/`
Decisions: the user's words under Task. Which fields count as scope is the home's call above; a question only he can answer is a gate through `jbus gate`, with the default taken; ask him nothing in this thread.
Design: none, the Done when list pins the checks, the fingerprint and the record

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

### 1. [Warning] `queue add` accepts template text that was never filled in for Task, Done when, Pull request and Review
**Location**: src/jbriefs/parse.py:355 (`_filled`)
**Finding**: `_filled` treats a field as the template's own text only when it starts with `<`. The template's own lines for four required fields do not start that way:
- `Task: "<the request, in the user's words>"` starts with `"`.
- `Done when:` followed by `- <a check>` starts with `-`.
- `Pull request: open one when done | ask first` has no `<`.
- `Review: review | none` has no `<`.

All four pass, so a brief copied straight from `templates/brief.md` gets past `queue add` on those fields. `parse._template` (line 227) already catches the `|` case and is used by `sized` and `playbook`, but `_filled` does not use it.
**Evidence**: The new test `test_queue_add_says_every_fault_one_line_each` writes `Task: <the request>` without the template's quotes, so the gap is never tested. The task says `queue add` must refuse "an incomplete brief". `docs/jbus.md` (new paragraph at diff line 91) and the home skill both say each field must be "not the template's own text", and that is not true here.
**Suggestion**: In `_filled`, treat a field as the template's text when, after stripping quotes and list markers, it starts with `<`, or when `_template()` is true. Add a test that runs `queue add` on the unedited `templates/brief.md` and expects every required field to fault. (principle: prove-it-works)

### A2

### 2. [Warning] The home skill throws away the new "its go does not hold" line
**Location**: skills/home/SKILL.md:632
**Finding**: The launch block now captures `jbus queue add ... 2>&1` into `$said`, but it prints `$said` only when the command fails. When it succeeds it prints only `added: the row <slug>`. The PR adds `, its go does not hold for it: approve it again` (`queue.GO_VOID`, printed by `asks.py:107`) on a successful add, so the home never sees it. Changing a brief's scope then looks to the home like a plain success, and the user is only asked again when a later pass gates `brief changed after approval`.
**Evidence**: `asks._queue` returns 0 after printing the GO line and the table. The skill's `if` branch drops all of that output.
**Suggestion**: On success, print `$said` whenever it contains `its go does not hold`, and add a sentence to the skill saying the home then puts the brief to the user again. (principle: prove-it-works)

### A3

### 3. [Warning] Some flips of meaning keep the go, and the stated limit leaves them out
**Location**: src/jbriefs/meaning.py:94 (apostrophe stripping), :72 (`FILLER`), :157 (`_near`)
**Finding**: Three effects in the normalisation reverse a line's meaning and still pass `same`:
- **Contractions:** line 94 turns `shouldn't` into `shouldnt`, which is within two edits of `should`, and both words have five or more letters. So "`queue add` shouldn't queue X" pairs with "should queue X". The same holds for `wouldn't` and `would`, and for `couldn't` and `could`.
- **Near words with opposite meanings:** `include` and `exclude`, `import` and `export`, and `never` and `every` are each two edits apart.
- **Fillers plus sorting:** `from`, `to`, `by` and `with` are dropped and the remaining words are sorted. So "move `a.py` to `b.py`" and "move `b.py` to `a.py`" give the same fingerprint.

All of these sit in fields that carry scope (Done when, Do not touch).
**Evidence**: The task asks for "catching real changes to intent or scope" and says the PR and the docs must state the known limit. The docs (diff line 131), the PR body and the module docstring name only `must`/`may` re-asking and `files`/`fixes` merging. None of them says that negation by contraction, near words with opposite meanings, or swapped direction keep the go. The near-word and sorting rules are in the spec. Stripping the apostrophe is the author's choice.
**Suggestion**: Turn `n't` into a separate `not` token instead of deleting the apostrophe. At the least, state these cases in the docs' and the PR's limit section. (principle: prove-it-works)

### A4

### 4. [Warning] The add check and the launch check are two separate lists that can drift apart
**Location**: src/jbus/dispatch.py:184-185; src/jbriefs/parse.py:360 (`faults`)
**Finding**: The launch checks with `CHECKS = (("no design", parse.designed), ("no proof", proven))` plus `ASKED`. `queue add` checks with a separate hand-written body in `faults`, which calls `proof`, `sized`, `playbook` and `designed` itself. "`queue add` makes the same checks" is promised only in prose (dispatch docstring, queue docstring, docs). A check added to `CHECKS` or `ASKED` later will not reach `queue add`, and nothing would fail.
**Suggestion**: Keep one tuple of check functions in `jbriefs.parse`. `faults` would run it, after the required-field checks. `dispatch` would build `CHECKS` and `ASKED` from it and keep only the grandfathering: no `Proves it:` line, and the `shaped_since` time. (principle: model-the-domain)

### A5

### 5. [Nit] `scope` is stored and printed but nothing checks it
**Location**: src/jbus/queue.py:333 (`approved_text`), :346 (`verify`)
**Finding**:
- `approved_text` uses `kept.scope` only as a flag for "this record has a fingerprint". It compares `kept.meaning` and never checks that `scope == meaning.fingerprint(kept.meaning)`. An edited `meaning` in `queue.json` silently widens the go.
- `scope` equality and `holds` can disagree. After a typo fix, `verify` prints a different `scope` with `holds: true`. A bot that compares `scope` hashes, which is the use the docs give for it, would refuse a brief jbus launches.
- The record has no fingerprint version. Any later change to `FILLER` or to the regexes would compare new fingerprints against stored ones made the old way.

**Suggestion**:
- In `approved_text`, check `scope` against `meaning` before comparing.
- Say in the docs that `scope` equality is stricter than `holds`.
- Add a `method` or version field to the record. (principle: model-the-domain)

### A6

### 6. [Nit] The CLI decides what to print by matching the end of a string
**Location**: src/jbus/asks.py:107
**Finding**: `if said.endswith((queue.GO_HOLDS, queue.GO_VOID))` reads the return string to decide whether to print. Any change to the wording of either constant breaks this without an error.
**Suggestion**: Either have `queue.add` return a structured value, or always print the line it returns. (principle: boundary-discipline)

### A7

### 7. [Nit] Small redundancies in the new code
**Location**: src/jbriefs/parse.py:378; src/jbus/queue.py `fingerprint`
**Finding**:
- `faults` calls `designed(text)` twice.
- In `faults`, for `Size`, the `_filled` result is computed and then thrown away.
- `queue.fingerprint` runs `body()` to drop `Home:`/`Thread:`, and `meaning.meaning` then drops `ROUTING` again. (principle: none)

### A8

### 8. [Nit] The PR says the launch checks are unchanged, but they are not
**Location**: src/jbriefs/parse.py `playbook` (the new `crewmates` branch)
**Finding**: The PR's Scope section says "The launch's own checks are unchanged, apart from the gate key". `parse.playbook` now also refuses any playbook that is not a crewmate's (`autopilot-full`, `investigation`, `opening-a-pr`, ...). `dispatch.ASKED` calls `parse.playbook`, so a row approved since `shaped_since` with such a playbook, which used to launch, is now gated at launch. That change is intended by the task ("Playbook a real crewmate playbook"), but the PR description should state it. (principle: none)

### A9

### 9. [Nit] Changing an old row's priority now requires a complete brief, which costs its go
**Location**: src/jbus/queue.py `_do` Add, the `briefs.faults(body(verb.text))` check
**Finding**: `add` is the only way to change a row's `--priority` or `--depends`, and it now runs `faults` on re-adds too. To re-prioritise an approved row whose brief predates the required fields, someone has to rewrite the brief. That changes its sha, and the old-sha path then voids the go. The task says rows approved before this change should keep working. The four rows queued today all have every field, so this is theoretical for now. (principle: none)

### B1

### 1. [warning] `queue add` lets through the template's own text for Task, Done when, Pull request and Review
**Location**: src/jbriefs/parse.py:355 (`_filled`)
**Finding**: `_filled` only treats a value as template text when it starts with `<`. Four lines that `templates/brief.md` ships with pass that check unchanged:
- `Task: "<the request, in the user's words>"` begins with `"`.
- `Done when:` followed by `- <a check>` joins to `- <a check>`.
- `Pull request: open one when done | ask first` holds no `<` at all.
- `Review: review | none` holds no `<` at all.

So a brief copied from the template with these left alone has no fault for any of them, and it reaches the user for a go. That misses the "Done when" line requiring each field "filled in and not the template's own text". `parse._template` already checks for `<` and `|`, and `sized` uses it, but `_filled` does not. The test at tests/test_jbus_brief_meaning.py:157 writes `Task: <the request>` with no quotes, so the gap goes unseen.
**Evidence**: `said = " ".join(line.strip() for line in held[0]).strip()`, then `if said.startswith("<")`. Each of the four values above fails that test.
**Suggestion**: Strip quotes and a leading `- ` before the check, and use `_template`, so that `<` anywhere or `|` counts as template text. Add a test that queues `templates/brief.md` with only the slug and title filled in, and expects a fault for every required field. (principle: test-behavior-not-implementation)

### B2

### 2. [warning] The typo allowance keeps the go when a word is negated or flipped
**Location**: src/jbriefs/meaning.py:94 and :162
**Finding**: Line 94 removes the apostrophe inside a word, so `shouldn't` becomes `shouldnt`. Against `should` that is 2 edits, with both words 5 letters or more, so `_near` counts them as the same word. Likewise `couldn't`/`could` and `wouldn't`/`would`. A Done-when line "the gate should fire" changed to "the gate shouldn't fire" keeps the user's go. Some opposite words are also within 2 edits and keep it: `include`/`exclude`, `increase`/`decrease`, `import`/`export`, `maximum`/`minimum`.
**Evidence**: The two-edit rule is the task's own and is not in question. The point is how the code applies it:
- Joining contractions is the code's own choice. It is what makes a negation fall inside the allowance.
- docs/jbus.md and the module docstring give `files`/`fixes` as the only known limit, so "it keeps the go for an antonym or a negation" is undocumented.
- The task asked for a check "still catching real changes to intent".
**Suggestion**: Split a contraction into its own token (`n't` becoming `not`), so the count of words changes and the brief re-asks. Add the negation and opposite-word cases to the stated limit in docs/jbus.md and the PR description. Add a test showing that `should` changed to `shouldn't` re-asks. (principle: model-the-domain)

### B3

### 3. [warning] Keeping the launch's checks and `faults` in step is left to convention
**Location**: src/jbriefs/parse.py:360-380 (`faults`), src/jbus/dispatch.py:184 (`CHECKS`/`ASKED`)
**Finding**: Two lists say what a brief must have. dispatch keeps `CHECKS` + `ASKED` (designed, proven, sized, playbook), and `parse.faults` lists the same checks again by hand. It also rewrites `dispatch.proven` as `proof(_head(text, "Proves it:") or "").why`. A check added to dispatch's tuple would gate at launch and never refuse at `add`, which is the problem this task set out to fix. The only parity test, `test_queue_add_refuses_what_the_launch_would_gate`, checks the Design case alone. `faults` also runs `designed(text)` twice, and for Size it works out `_filled` and then throws it away.
**Suggestion**: Keep one tuple of `(kind, check)` in `jbriefs.parse`. Have `faults` loop over it after the required-field pass, and have `dispatch.short_of` take its checks from that same tuple. The launch is then a backstop by construction. (principle: redesign-from-first-principles)

### B4

### 4. [nit] `approve` does not run the checks, so a faulty row already queued is still put to the user
**Location**: src/jbus/queue.py:707 onward (`Approve` branch of `_do`)
**Finding**: `faults` runs only in `Add`. A row whose brief was queued before this change, and is incomplete, can still be approved, then gated at launch. That is the "queued, approved, then gated" order the task removes. The fix is one `briefs.faults(body(text))` check before `Approval(...)` is built. (principle: boundary-discipline)

### B5

### 5. [nit] The CLI decides whether to print `add`'s result by matching the end of its text
**Location**: src/jbus/asks.py:107
**Finding**: `if said.endswith((queue.GO_HOLDS, queue.GO_VOID))` reads back the wording of a string to learn whether the go was in question. Any change to the message breaks it silently. `queue.add` could return that state as data, or the CLI could print the `added …` line every time. (principle: model-the-domain)

### B6

### 6. [nit] Greedy pairing in `_pairs` can re-ask when a match exists
**Location**: src/jbriefs/meaning.py:166
**Finding**: After exact matches are removed, each approved line takes the first new line that is `alike`. If two approved lines both have typos and could each pair with the same new line, the first one takes it. The second then fails and the brief re-asks, though a valid pairing exists. This only errs toward asking again, so it is safe, but the docstring says "pairs with its own item". (principle: none)

### B7

### 7. [nit] A file outside the "Where" line was changed
**Location**: src/jbus/asks.py
**Finding**: The "Where" line names `src/jbus/cli.py`. The `verify` verb and the change to `add`'s output are in `src/jbus/asks.py` instead, where the queue verbs actually live, and cli.py is untouched. The Where line was probably just inaccurate, but this is a file the brief did not list. (principle: none)

### B8

### 8. [nit] Done-when gap: the PR description cannot be checked from this review
**Location**: none (the change as a whole)
**Finding**: The task requires the PR description to state the fingerprint method, its normalisation steps and its known limit. Only the diff was given, so that line is unconfirmed. docs/jbus.md does state all three. (principle: prove-it-works)
