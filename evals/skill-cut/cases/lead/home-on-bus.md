# home-on-bus

## Intent

Task: the user, 2026-10-15 11:24 ET, word 27e8df9c6c34, relayed by Sous Chef from Grok Bot chat: "We need to add this project to jbus and ensure any new home we create is added to the bus". Winnifred had a home (thread the user) and was no jbus project until the jstack home added it at 11:25 ET. `/new-home` already runs `jbus project add` (skills/new-home/SKILL.md:80-99), but a home started by `/home` in a repo, or one made before that step, never registers; firstmate and LittleRamPantries have a `home-id` today and are no jbus project
Done when:
- the home skill's start ("When a home starts") registers its repo when jbus's config has no table for it: it finds the repo's T3 project id (from T3 Code, by the checkout path), runs `jbus project add <repo folder> --checkout <path> --project-id <id>` the way new-home's step 3 does, and reads its lines the same way (`added`, `already`, `needs you`). `jbus project add` stays the only writer of the config; the skill never opens or prints it
- a home that merges its own pull requests (one whose rules say so, or one the user says merges by itself) writes its id to `home-thread` before the project is added, so jbus's `jmerge` does not race it (`src/jbus/merge.py:1-5`, `home_thread`); a home that lets jbus merge leaves `home-thread` empty, as now. The start says which it did
- jbus itself finds what slipped past: each pass (or the daily sweep) lists every folder under the homes' state root with a `home-id` and no project in the config, and says so as one quiet line and in `jbus status` ("homes not on the bus: firstmate, LittleRamPantries"), and the view's machine row shows the count. A party's folder (`_<name>`) and an expert's are not homes and are not listed
- `jbus project add`'s refusal lines and new-home's step 3 are unchanged; new-home and the home skill share one block (or one helper) for the registration, so the two cannot drift
- tests: the start's block in a temporary home root and config adds a missing project and leaves a present one alone; a home that merges writes `home-thread` before the add; the pass lists a `home-id` folder with no project and not a `_party`
- `docs/jbus.md` ("Add a project") says a home's start registers its repo, and when `home-thread` is written
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the tests above, and `jbus status` on this machine after the merge naming exactly the homes then missing from the config (firstmate and LittleRamPantries today, unless the user has them added first)
Size: M
Where: `skills/home/SKILL.md` ("When a home starts"), `skills/new-home/SKILL.md` (step 3, to share the block), `src/jbus/` (the pass or sweep that lists unregistered homes, `cli.py` status), `src/jbus/view/` (the machine row's count), `docs/jbus.md`, the tests
Do not touch: `~/.config/jbus/config.toml` by hand (only `jbus project add` writes it); the other homes' folders; adding firstmate, LittleRamPantries or any other repo to the config (the user's word covered Winnifred and the rule, not those: the status line names them for him)
Decisions: the user's words under Task. Registering at the home's start, a `home-thread` for a home that merges itself, and a status line rather than adding the missing ones are the home's calls. A question only he can answer is a gate: take the default, pipe it to `jbus gate home-on-bus` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: none, the Done when list pins where the registration runs, the merge switch and the check

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

### 1. [warning] A home that merges by itself now gets a "stale id" warning at every later start
**Location**: skills/home/SKILL.md:74, and the switch write it allows in skills/new-home/SKILL.md:155. The damage is at skills/home/SKILL.md:171-178 (unchanged).
**Finding**: The `home-thread` row now lets a home write its own thread id into the switch. Step 3 of every later start does two things:
- it prints `jbus does not merge here: $H/home-thread holds <id>. Nothing empties it but the user, by hand.`
- it tells the home to explain that "a home that started before the id moved to `home-id` left its own there".

The row itself still opens with "The merge switch, and not this home's id".
**Evidence**: After one handoff, the next home finds the earlier home's id in `home-thread`. It then tells the user, at once, that an old home left a stray id there. That is false, because the switch was set on purpose by "On the bus". So a correct setup now looks like leftover state from a migration, at every start.
**Suggestion**: Change the wording at line 178 (and the "not this home's id" clause) so that an id written by "On the bus" reads as the switch being on by choice. Or have the block write a fixed marker instead of a thread id, since `merge.home_thread` only checks that the file is not empty.

### A2

### 2. [warning] Two of the three branches in the "On the bus" block can never run
**Location**: skills/home/SKILL.md:308-315 (the new block), with the trigger at :303.
**Finding**: Step 5 runs "On the bus" only where step 4 printed `no project:`. The block that reads jbus sets that `WHY` only when `jbus` is on PATH and `$P` is empty (line ~707-709). So when the block runs:
- the `on the bus` branch (`[ -n "$P" ]`) cannot be taken;
- the `jbus is not installed` branch cannot be taken;
- the prose that handles both lines (line 321) is dead too.

The only thing the block really adds is `C`, the main checkout.
**Evidence**: Under the `no jbus:` case, step 4 prints that line instead, and step 5 never calls "On the bus". The new test only gets `on the bus` by calling `machine.start()` directly, outside the step-5 trigger, so it checks a route a real start never takes.
**Suggestion**: Drop the block and its three-way prose. Step 1 of "On the bus" can name the checkout as `$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")`, or the step 4 `no project:` line can print it. This removes one guarded block (test_scoped_home.py's count can go back to 7) and a branch table.

### A3

### 3. [warning] A self-merging home can turn off jbus's merging for a project someone else just added
**Location**: skills/new-home/SKILL.md:155-163
**Finding**: The switch is written before `jbus project add`, and it is kept when the add answers `already`. Say another thread (`/new-home`, or a second home or scope of the same repo) adds the project with jbus merging, between this start's step 4 and this block. The block still writes `home-thread`. The add then says `already`, and the repo silently becomes "home merges".
**Evidence**: The new paragraph at line 170 accepts a switch left behind after a refused add, because "jbus runs no jmerge for a repo with no project anyway". That reasoning does not hold for `already`: the project exists, and the switch now stops its `jmerge`. Nothing reconciles this or tells the user.
**Suggestion**: On `already` with `ME` set, when the block itself wrote the switch, empty it again, or at least print a line saying the switch was turned on for an existing project.

### A4

### 4. [nit] An empty folder name would put `home-thread` at the root of the homes' state
**Location**: skills/new-home/SKILL.md:150
**Finding**: `S=$HOME/.local/state/home/${C##*/}/home-thread`. If the checkout is filled in by hand with a trailing slash, `${C##*/}` is empty. With `ME` set, the block then writes `~/.local/state/home/home-thread` before `jbus project add` refuses the empty name.
**Evidence**: The home's own block derives `C` with `dirname`, so it never ends in a slash. The new-home block is now shared and filled in by hand, though, and the write runs before any check on the name.
**Suggestion**: Strip a trailing `/` from `C` before using it, or treat an empty `${C##*/}` as "not filled in".

### A5

### 5. [nit] The `status()` docstring says the opposite of what the code does
**Location**: src/jbus/cli.py:192-193
**Finding**: The docstring says the homes not on the bus are something "which no pass leaves". But `poll` writes `status(...)` to `status.json`. The view reads the list from that file (`KEPT_BY_JBUS`, pulse's `homes_off_bus`), and `poll` compares against `last["homes_off_bus"]` from it.
**Suggestion**: Say instead that it is the list as this pass found it, written into the status file.

### A6

### 6. [nit] The new paragraphs split the `jbus project add` command from its argument list
**Location**: docs/jbus.md:190-192
**Finding**: Two paragraphs are inserted between the line that gives `jbus project add <name> --checkout <path> --project-id <id>` and the bullet list that explains `<name>`, `--checkout` and `--project-id`. The bullets now read as if they belong to the "homes not on the bus" paragraph.
**Suggestion**: Move the two new paragraphs below the bullet list.

### B1

### 1. [warning] Step 3 of the home's start still says an id in `home-thread` is an old home's leftover, which now contradicts the new deliberate write
**Location**: skills/home/SKILL.md:303-327 ("On the bus" step 2-3). The damage is at skills/home/SKILL.md:171-178 (step 3 of "When a home starts"), which the diff left unchanged.
**Finding**: A home that merges by itself now writes its own id into `$H/home-thread`. On every later start, step 3's block prints `jbus does not merge here: $H/home-thread holds <id>. Nothing empties it but the user, by hand.` The prose there tells the home to say "a home that started before the id moved to `home-id` left its own there."
**Evidence**: After this change, that explanation is wrong for every repo that took the merge-by-itself path. Each later home will tell the user that a stale, legacy id is blocking jbus's merges, when the switch was set on purpose. The user may then empty it, and jbus and the home's rules would both start merging, which is the race the task was meant to prevent.
**Suggestion**: Reword step 3's `jbus does not merge here` prose so it allows an id that a merge-by-itself home wrote at registration ("On the bus").

### B2

### 2. [warning] Unchanged lines in new-home and the docs still say only the user writes `home-thread`
**Location**: skills/new-home/SKILL.md:75 (the step 3 intro) and :112 (the new paragraph). The contradicting lines are skills/new-home/SKILL.md:171 (`home-thread holds $holds (..., written by hand)`) and :175 (`fresh-check, off, merge-off and home-thread are the user's four switches ... this skill writes none of them`). Outside the "Where" line, noted for later: skills/handoff/SKILL.md:199 ("it is set by hand"), docs/state.md:18 ("You write it by hand") and docs/configuration.md:151 ("Nothing writes this file but you").
**Finding**: The change makes new-home's step 3 block a writer of `home-thread`, and updated only the home skill's state table to match. Step 4 of the same new-home skill still says the skill writes none of the four switches.
**Evidence**: The same file now holds two opposite rules about the merge switch. An agent reading step 4 or `docs/configuration.md` gets the old rule.
**Suggestion**: Change new-home:171/175 in this PR. Note the handoff and docs lines for a follow-up.

### B3

### 3. [warning] The third placeholder invites a literal "nothing", which would silently turn jbus merging off
**Location**: skills/new-home/SKILL.md:80-91 (`ME='<the id of a home that merges by itself, or nothing>'`, then `[ -n "$ME" ]` and the `printf ... > "$S"` write)
**Finding**: The placeholder text itself says "or nothing", and the only check is that `<` and `>` are gone. If a model fills in `ME='nothing'` (or `none` or `empty`), the block writes that word to `home-thread`. It then prints `3 home-thread: done, ... holds nothing: the home merges here`, and jbus never runs `jmerge` for the repo (`merge.py:home_thread` only checks that the file is non-empty).
**Evidence**: The block treats any non-empty value as a thread id and does not check its shape. The fill-in rule exists only in prose ("nothing in place of the third"). This is the "rule in prose" case: a runtime check would make the mistake impossible.
**Suggestion**: Reject a value that does not look like a T3 thread id (for example, require `mcp:*` or the uuid form), and print `not filled in` instead. Or split the merge-by-itself case into its own explicit flag, so the default path has no third value to fill in.

### B4

### 4. [nit] The "On the bus" block has two branches the start never reaches
**Location**: skills/home/SKILL.md:303 (the trigger) and :308-314 (the block)
**Finding**: Step 5 runs "On the bus" only when step 4 printed `no project:`. The block that reads jbus sets that `WHY` only when `jbus` is on PATH and `$P` is empty. So the `on the bus` branch and the `jbus is not installed` branch never run from the start flow; only the tests use them.
**Suggestion**: Either run the block on every start, so it is the check itself and does not depend on matching a line of step 4, or drop the dead branches.

### B5

### 5. [nit] Loop-variable renames in `poll` and `alarm` are churn
**Location**: src/jbus/cli.py:459-461, 532-542
**Finding**: Renaming `project` to `one` is needed in `status()`, which now calls the `project` module. `poll`'s cleanup loop and `alarm` never use the module, and the ruff rules (`E,F,W,I,B,UP`) do not flag shadowing. Meanwhile, `poll`'s nested `first(project: jbus.Project)` still shadows the module, so the renames don't even make the file consistent.
**Suggestion**: Limit the rename to `status()`, or apply it to `first` too, so the module name is never shadowed.
