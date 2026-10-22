# brief-size-and-playbook-checked

## Intent

Task: the feature playbook's step 4 (size) has never fired: 0 briefs carry a size; and a brief named `Playbook: fix` or `Playbook: feature.` launched with no playbook (~/.local/state/home/jstack/scouts/principles-in-practice.md)
Done when:
- `Size: S|M|L|XL` is a line in `templates/brief.md` and the plan-entry template
- `src/jbriefs/parse.py` and `src/jbus/dispatch.py` refuse a brief with no size or with a playbook name that is not a file in `playbooks/` (or `none`), each with one line; rows approved before the merge are grandfathered
- parser tests for `fix`, `feature.`, no size, and a good brief
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the parser tests above, and the live queue run through the check, with no approved row stranded
Size: S
Where: `templates/brief.md`, the plan-entry template, `src/jbriefs/parse.py`, `src/jbus/dispatch.py`, the tests, the home skill's brief lines
Do not touch: the `Design:` and `Proves it:` rules
Decisions: the user, on the principles-in-practice page (2026-10-15, session 5bbaa418991bcb43, ended by him), every pick left as recommended, no notes: the five entries in this order, cite-orphan-principles after deeper-skill; and his go in the jstack home thread. The scout's report is ~/.local/state/home/jstack/scouts/principles-in-practice.md. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/principles-in-practice.md, Plan entries, brief-size-and-playbook-checked

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

### 1. [Warning] The grandfather cutoff is set to a time before the merge, so rows approved before the merge can still be gated
**Location**: src/jbus/dispatch.py:60 (`SHAPED_SINCE = "2026-10-15 11:15 ET"`), used at src/jbus/dispatch.py:180
**Finding**: The task says rows approved before the merge keep their old rules. The code instead uses a fixed time that is earlier than the PR's own commit (bbe24b2, 2026-10-15 11:22 -0400) and so earlier than any merge. If a row is approved between 11:15 ET and the merge, its brief was written under the old home skill and template, with no `Size:` line. The new `short_of` will then gate it with "brief has no Size: line". The same happens to any brief written before the merge but approved after 11:15.
**Evidence**: The remedy the gate implies is to add a `Size:` line. That changes the brief's sha, so `_ready` then gates the row again with "brief changed after approval" until the user gives a new approval. That is a stranded row, which "no approved row stranded" rules out. Today the live queue's latest approvals were at 11:06 ET (`~/.local/state/jbus/*/queue.json`), so nothing is caught yet. The window stays open until the merge, though, and homes keep approving rows during that time.
**Suggestion**: Set the cutoff when the merge actually happens, or to a time safely after it. Another option is to grandfather a row whose brief has no `Size:` line at all when its approval is older than the merge. Either way, add a test for a row approved just after the constant but before the merge.

### A2

### 2. [Warning] The cutoff check compares text in the user's configured time zone with a hard-coded "ET" string
**Location**: src/jbus/dispatch.py:180 (`at >= SHAPED_SINCE`)
**Finding**: `ran_at` comes from `user.stamp(clock())`, which writes the time in whatever zone and label jsettings is configured with (src/jsettings/__init__.py:60). The constant is fixed text in ET. The comparison only gives the right answer when the config says `America/New_York` with label `ET`. That holds for the user's config and the test conftest, but it is nowhere enforced.
**Evidence**: With no `timezone` key, the machine's zone is used. If `timezone_label` is unset the stamp ends in `EDT`, and `"… 11:15 EDT" < "… 11:15 ET"`. If the zone is not New York, the cutoff moves by hours. The docstring calls this "the one shape `queue` writes", but that shape depends on the config. The check is a stand-in for the real time, not the time itself.
**Suggestion**: Keep the cutoff as an aware `datetime` in UTC. Read `ran_at` back into a datetime with the same settings and compare instants, not strings.

### A3

### 3. [Warning] Briefs written by a scout reach launch with the template's Size placeholder, so they are always gated
**Location**: skills/home/SKILL.md:498 (the new `Size:` paragraph); the step that skips it is at skills/home/SKILL.md:494
**Finding**: Step 1 says "A brief a scout wrote is already there: check that its `Home:` line ..., and go to step 2." That path skips the new `Size:` paragraph. The scout skill (skills/scout/SKILL.md:125) writes briefs from `$T/brief.md` and lists the lines it must fill, but `Size:` is not among them. Its brief therefore keeps `Size: S | M | L | XL`, and `parse.sized` rejects that as "the template's own text".
**Evidence**: Every scout-written brief approved after the cutoff gates on "no size". Fixing it means editing the brief, which needs a new approval (same chain as finding 1).
**Suggestion**: In the home skill's step 1, have the home check and set `Size:` from the plan entry on a scout's brief, as it already does for `Home:`. The matching change to the scout skill is outside the "Where" line, so it is noted for later.

### A4

### 4. [Warning] Any file in `playbooks/` passes the check, including playbooks a crewmate never runs
**Location**: src/jbriefs/parse.py:218
**Finding**: `playbook()` accepts any `playbooks/<name>.md`. That includes playbooks for the home (`orchestrate`, `autopilot-full`, …), scouts (`investigation`, `trace-forensics`), experts (`expert-*`), and `opening-a-pr`, which says "never picked for a brief".
**Evidence**: When the crew skill's step 3 (skills/crew/SKILL.md:30–56) meets one of these, it prints `not a crewmate's` and the crewmate works with no playbook. That is the failure the task set out to stop: a brief that "launched with no playbook". The "Done when" wording ("a file in `playbooks/`") is met, but what the user wanted is not fully met.
**Suggestion**: Read the playbook's first `Run by:` line and refuse any brief whose playbook is not `a crewmate`, using the same rule the crew block uses. This is one more `elif` in `playbook()`.

### A5

### 5. [Nit] The new `_head` duplicates the loop in `proves_it` just above it
**Location**: src/jbriefs/parse.py:170
**Finding**: `_head(text, label)` is the same walk over the brief's head that `proves_it` (line 160) does inline. Two copies of "the head ends at `## `" now sit side by side in one file.
**Suggestion**: Make `proves_it` call `_head(text, "Proves it:")` and remove its own loop. `dispatch.designed` repeats the same walk too, but it is unchanged here, so that is noted for later.

### A6

### 6. [Nit] `_SIZES` is typed out by hand alongside `SIZES`
**Location**: src/jbriefs/parse.py:61
**Finding**: `"(S, M, L or XL)"` repeats the `SIZES` tuple by hand. If a size is added or renamed, the two can drift apart, and the tests also hard-code the same string.
**Suggestion**: Build `_SIZES` from `SIZES`, for example `f"({', '.join(SIZES[:-1])} or {SIZES[-1]})"`.

### B1

### 1. [warning] The grandfather cutoff is already in the past, so rows approved before the merge can still be stranded
**Location**: src/jbus/dispatch.py:60 (`SHAPED_SINCE = "2026-10-15 11:15 ET"`), used by `shaped_since` at dispatch.py:183-190
**Finding**: Whether a row is grandfathered depends on a fixed wall-clock time. It does not depend on when this rule actually reaches the dispatcher. The cutoff is 11:15 ET today. It is now about 11:25 ET, and the PR is not merged. Between 11:15 and the merge, homes keep writing briefs from the old `templates/brief.md`, which has no `Size:` line, because `$T` is the main checkout. Any such brief approved in that window will be gated as "no size" once this merges. That breaks the Done-when "no approved row stranded" and the docstring at dispatch.py:29-31 ("was approved before the two were asked for").
**Evidence**: I read the live queues (`~/.local/state/jbus/{jstack,infra,lavish-axi}/queue.json`). The latest `ran_at` is `2026-10-15 11:06 ET`, so nothing is stranded yet. Every approval from now until the merge falls into the gap, though. The stated proof, "the live queue run through the check", only shows the state at the moment the check ran.
**Suggestion**: Base the cutoff on the change actually landing, not on a guessed time. For example, set `SHAPED_SINCE` when the PR merges, or grandfather any row whose approval record predates the first launch pass that ran the new code. At minimum, move the constant to a time after the merge and say so in the PR.

### B2

### 2. [warning] The cutoff compares time strings as text and depends on the zone label in the stamp
**Location**: src/jbus/dispatch.py:60 and :189 (`return bool(at) and at >= SHAPED_SINCE`)
**Finding**: `queue.ran_at` returns `jsettings.Settings.stamp(...)`: `"%Y-%m-%d %H:%M <word>"`, written in the user's configured zone, and the word is either the configured label or `tzname()`. `SHAPED_SINCE` hard-codes ET local time plus the word "ET". The comparison is only right for a config whose zone is America/New_York. For any other zone it is off by the zone offset. With the zone unset, the machine's zone is used. If the label is unset, the word is "EDT" or "EST", and an exact-minute tie then resolves by comparing "EDT" with "ET". The cutoff also silently depends on the stamp format inside `jsettings`. That is a proxy check, a string, standing in for the real moment.
**Evidence**: `src/jsettings/__init__.py:60-61` is `stamp` and `:53-55` is `word`. The docstring at dispatch.py:186 ("in the one shape `queue` writes, so the two compare as text") is a prose rule that keeps this correct.
**Suggestion**: Make `SHAPED_SINCE` an aware `datetime`. Parse the approval's `ran_at` the way `digest.py:149` already does, `datetime.fromisoformat(made.ran_at[:16])` localized through the config's zone, and compare datetimes.

### B3

### 3. [nit] The gate test takes its expected messages from the functions it is testing
**Location**: tests/test_gate_skills.py:362-364
**Finding**: The expected `why` values are `parse.sized("")` and `parse.playbook("Playbook: fix\n")`, which are the same functions dispatch calls. The `startswith` check at :375 pins only the prefix. If the message wording changes or breaks, the gate test still passes.
**Suggestion**: Write out the literal gate lines, as `test_briefs.py` does with `PLAYBOOK_ASKED`.

### B4

### 4. [nit] The new `_head` helper sits beside the identical loop it could replace
**Location**: src/jbriefs/parse.py:170-177 (`_head`), directly after `proves_it` at :160-167
**Finding**: `_head` repeats the head-scan loop that `proves_it` uses just above it. `proves_it` could become `said = _head(text, "Proves it:"); return proof(said) if said is not None else None`, which leaves one place that defines "a brief's head". `dispatch.designed` (dispatch.py:153-160) has the same loop again. That function is not in this diff and would be a later cleanup, not something for this PR.
**Suggestion**: Make `proves_it` call `_head` in this PR, since `_head` is new here.
