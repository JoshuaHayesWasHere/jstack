# pstack-rebase-cap

## Intent

Task: the audit's P6
Done when:
- `skills/crew/SKILL.md` "A conflict": once a crewmate has written `fixed and green`, a third rebase forced by main is not made: it writes one stop line in its Result and pipes a gate, and jbus surfaces it as waiting
- the count is kept where jbus or jmerge can read it (the brief's Result or a jmerge counter), and a test in the suite drives three rebases and finds the stop on the third
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the test that drives three rebases
Size: S
Where: `skills/crew/SKILL.md` ("A conflict"), `src/jmerge/` or `src/jbus/` where the count is read, the tests
Do not touch: how a rebase is pushed (`--force-with-lease` pinned, as now)
Decisions: the user, 2026-10-15 09:44 ET, word 79eb162adcb3, from Sous Chef's Grok Bot chat: "Yes, send it", approving the pstack catch-up (bring jstack up to current pstack, the #633 principle rewrite and every other upstream update it is missing), in the audit's priority order. Upstream is cursor/plugins `pstack/` at e5136d8; read it from a fresh clone in a temporary directory (`git clone --filter=blob:none`), never from memory. Keep jstack's local form where the audit says so. The split is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/pstack-drift-2026-10-15.md, "#613 in detail" and P6

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

### 1. [warning] The held pull request shows as waiting on its crewmate, not on the user
**Location**: src/jbus/merge.py:97 (`held a third rebase` is added to the `"rebase"` rule). The test pins this at tests/test_jbus_merge.py:288 (`"REBASE_HELD": "rebase"`).
**Finding**: `merge.step` puts the reason `REBASE_HELD` on the `rebase` step. In src/jbus/work.py:287 that step is `Pattern("rebase", "Rebase", "crew", "its crewmate", ...)`, so jbus shows the row as waiting on its crewmate. That contradicts the reason's own words ("its gate asks the user") and the skill text added at SKILL.md:118 ("jbus lists the gate as waiting on the user").
**Evidence**: An open gate outranks this (work.py:203, the `asking` pattern), so the row is right only while the gate is open. Once the gate is answered with the default ("it waits and the home sequences the colliding work"), or if the crew never parks the gate, nothing is left to outrank the step. The row then reads "Rebase, its crewmate" for good. But the crew has nothing to do: it may not rebase again until a `Rebase hold lifted:` line is written. The repo already maps wait reasons that only the user can clear to the `hold` step ("Needs you"), as with `NOT_UPHELD` and `UNRULED_DROPS`.
**Suggestion**: Move `held a third rebase` to a `("hold", ...)` rule and change the mapping in test_jbus_merge.py to `"REBASE_HELD": "hold"`.

### A2

### 2. [warning] The cap starts counting at the `Fixed:` line, not at "fixed and green"
**Location**: skills/crew/SKILL.md:62 (prose) and the block's counting awk at SKILL.md:72 (`/^Fixed: / {fixed = 1}`).
**Finding**: The first "Done when" line says the cap applies "once a crewmate has written `fixed and green`". The block counts every rebase made after any `Fixed:` line. Per SKILL.md:807-815, `Fixed:` is written before the head is green: `Fixed: none needed` comes after a clean review whatever CI says, and `Fixed: <commit>` comes right after the push.
**Evidence**: Take a pull request that has its `Fixed:` line and whose check is red, for example `<command> fails on <head> over today's main`. Each rebase that message asks for uses up the cap, even though the pull request was never green. Two such rebases, then one more conflict, and it is held before it was ever "fixed and green". The PR explains its choice (the `fixed and green` line is sent only to a home, not written), but the condition it actually checks is a stand-in for the one the task names.
**Suggestion**: Count from a mark written to the brief when the head turns green after `Fixed:`. If that is not possible, state in the PR that this deviation from the "Done when" line is deliberate.

### A3

### 3. [warning] Running the block again on a held head tells the crew to park a second gate
**Location**: skills/crew/SKILL.md:86-87 (the branch where the brief already has the hold line) and SKILL.md:118 ("On `hold` ... park a gate").
**Finding**: The block writes the hold line only once for a head, but it prints a line starting `hold:` on every run, and the prose says to park a gate whenever it sees `hold`. Nothing tells the first run apart from later ones.
**Evidence**: While held, the crew can be woken again for the same head. For example, src/jbus/mainmoved.py sends one message per main commit to every red pull request, and a held pull request is often red. Each wake runs the block, gets `hold: ... the brief has the line ...` again, and parks a new gate with the same question. The state left by the first run decides nothing about what the crew does next.
**Suggestion**: Print a different word when the line was already there (for example `held:`), and in the prose park the gate only on the first `hold:`.

### A4

### 4. [nit] The hold is recorded at the local HEAD, but jmerge compares it with GitHub's head
**Location**: SKILL.md:84 (`head=$(git rev-parse HEAD)`); the line is read at src/jmerge/ready.py:194 against `one.head` (cli.py:703).
**Finding**: If the local head differs from the one at GitHub, `rebase_held` does not match and jmerge does not wait on the hold.
**Evidence**: After the second rebase, the push can be refused ("the push was refused", SKILL.md:582). If main then moves again, the block writes `Rebase hold: at <unpushed head>`. jmerge's `one.head` is the old pushed head, so it reports some other reason instead of the hold.
**Suggestion**: Use the `pushed` head the block already has from `gh pr view`.

### A5

### 5. [nit] The test does not go through jmerge's own path for the hold
**Location**: tests/test_crew_skill.py:256, 268-272.
**Finding**: The test runs the shell block for real, which is good, but it checks jmerge only by calling `ready.rebase_held` directly. The change in src/jmerge/cli.py:703 is never exercised: the check placed after `ready.held` and before `short_of`, and the early return that skips the stale and range-diff checks. Moving or dropping that line would not fail any test.
**Suggestion**: Add an assertion that goes through `waits`, or through jmerge's printed `wait` line and `merge.step`, for a brief that has the hold line at the head.

### A6

### 6. [nit] The test's `home` argument also switches the slug
**Location**: tests/test_crew_skill.py:209-212.
**Finding**: `run(about, home)` replaces `<slug>` with the hard-coded `"alpha"` only when `home` is given. That ties two separate things to one argument, so any later caller that passes `home` with a different brief name gets the wrong path without any error.
**Suggestion**: Pass the slug explicitly (`run(about, home=None, slug="alpha")`), or work it out from the brief's file name.

### B1

### 1. [warning] jbus shows the held pull request as waiting on its crewmate, but it is waiting on the user
**Location**: src/jbus/merge.py:97 (`"held a third rebase"` added to the `rebase` rule); tests/test_jbus_merge.py:288 (`"REBASE_HELD": "rebase"`)
**Finding**: jmerge's `REBASE_HELD` reason maps to the `rebase` step. In src/jbus/work.py:287 that step is drawn as `"Rebase"`, owned by `"crew"`, `"its crewmate"`, and src/jbus/view/state.py:182 describes it as "main moved under it, or a rebase dropped lines". But once the hold is written, the crewmate has nothing left to do. The SKILL text says the user answers the gate, and only then is the pull request rebased. The step that fits is `hold` ("Needs you", "user", "your word").
**Evidence**: `merge.step()` returns the first rule whose pattern matches the reason, and `watch.py:373` turns that into `work.Pull`. So the board puts the pull request under Rebase / its crewmate. The done-when line asks that "jbus surfaces it as waiting". The row says it waits on the wrong party, and only the separate gate tells the user. The test table at tests/test_jbus_merge.py:288 locks the wrong mapping in place.
**Suggestion**: Map `held a third rebase` to the `hold` step, or emit it as a jmerge `hold` and not a `wait`, and change the test table to match.

### B2

### 2. [warning] The count reads the whole brief, but every block is meant to read only the last Result
**Location**: skills/crew/SKILL.md:396-399 (the `read -r fixed rebased lifted` awk)
**Finding**: The awk matches `^Fixed: `, `^Rebased after fixed: ` and `^Rebase hold lifted: ` anywhere in the file. SKILL.md:159 says a later round appends `## Result, follow-up (...)` and that "the home and every block read the last result".
**Evidence**: Suppose a pull request was rebased twice after its first `Fixed:` line. Then a steer from the user starts a follow-up round, the crewmate pushes new fixes and writes a new `Fixed:` line. The old `Rebased after fixed:` lines still count as 2, so the first conflict of the new round is held at once. The cap is supposed to cover rebases after this round's fixed-and-green state, not every rebase in the brief's history.
**Suggestion**: Start counting at the last `## Result` heading (reset the counters on `/^## Result/`), or count only `Rebased after fixed:` lines that come after the last `Fixed:` line.

### B3

### 3. [warning] A `Fixed:` line stands in for "fixed and green"
**Location**: skills/crew/SKILL.md:379 and 397
**Finding**: The done-when line starts the cap "once a crewmate has written `fixed and green`". The block starts it at the `Fixed:` line instead. That line is written right after the fix is pushed (SKILL.md:807), before any check has passed, and `Fixed: none needed` starts it too.
**Evidence**: Main can force rebases while CI on the fix is still running or red. Those rebases use up the two allowed ones before the pull request was ever green, so the third, held one can come earlier than the task intends. This is the "proxy" case in question 4: the block reads a nearby marker, not the green state itself.
**Suggestion**: Start counting at a marker written when the pull request turns green: the `fixed and green` step, or a line the crewmate writes when it sends it or whoever merges. Otherwise, state the deviation from the done-when line explicitly.

### B4

### 4. [warning] The test skips the stopped-rebase path and never runs jmerge's `waits()`
**Location**: tests/test_crew_skill.py:231-274
**Finding**: The new test does run the shell block, which is good. But each move of main (`second.txt`, `third.txt`, `fourth.txt`) touches a file the branch does not change, so every rebase succeeds. Two things go unexecuted:
- The prose says a rebase "that stops on a conflict" also counts. That is the `counted` call in the `elif` branch at SKILL.md:443.
- The cli.py:703 change, where `rebase_held` comes before `short_of` inside `waits()`. The test only calls `ready.rebase_held` directly.

**Evidence**: If the second `counted` call were deleted, or the `rebase_held` call removed from `waits()`, this test would still pass.
**Suggestion**:
- Add a run where main changes the branch's own file, so the rebase stops, and assert that a `Rebased after fixed:` line is written.
- Add a `waits()` or jmerge-level assertion that a pull request at the held head reports `REBASE_HELD`.

### B5

### 5. [nit] "Once for a head" checks for any hold line ever written at that head, not the current hold
**Location**: skills/crew/SKILL.md:426 (`grep -q "^Rebase hold: at $head,"`)
**Finding**: Two checks disagree on what counts as the current hold:
- The block's de-dup accepts any earlier `Rebase hold: at <head>` line anywhere in the brief.
- `ready.rebase_held` holds only when the last hold-or-lift line is a hold at that head.

**Evidence**: Example: the hold at X is lifted, the next rebase stops (it is counted), and the branch ends up back at X, for instance after a manual `git rebase --abort`. The block then finds the old line, prints `hold:` and writes nothing. The last matching line is now `Rebase hold lifted:`, so jmerge reports no hold, even though the crewmate has parked a gate.
**Suggestion**: De-dup only against the last `Rebase hold`/`Rebase hold lifted` line, the same rule `rebase_held` applies.
