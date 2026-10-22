# exec-removal-jstack

## Intent

Task: the user, 2026-10-15 13:16 ET and 13:43 ET (word ac1e4e21fef1), relayed by Sous Chef: eliminate the exec home ("they can completely go we are moving from this pattern"). Sous Chef is the one orchestrator; jbus's webhook carries escalations to it, and his word comes down by `jbus word`. The experts (Poteto, Theo, Jez) are retired with Exec. This is step 4 of the removal plan in `scouts/exec-home-removal.md` in this home's state folder (sections 1 and 5c list every place and the proposed wording).
Done when:
- `skills/new-home/SKILL.md`: step 6 "One message to Exec" and its block are gone; the description, `card:` and "The end" no longer name it
- `skills/home/SKILL.md`: no text names Exec. The user's word comes "most often from Sous Chef" by `jbus word`; "ask for no second confirmation, here, to Sous Chef or by a gate"; the party example is an expert's; the "Exec is reached with nothing but what jbus carries" paragraph is gone. One line under the start says: escalations reach the user through jbus's webhook, and a home keeps no registry of homes: jbus is it
- `skills/handoff/SKILL.md`: the party handoff no longer has an `exec` role or case; the `_exec/direct.md` pair-telling block of step 4 is gone
- `src/jroles`: role `exec` gone, `docs/jroles.md` too; `src/jbus/queue.py` no longer names a run from `_exec` "Exec"; `src/jbus/word.py` and `src/jbus/cli.py` text and the retired `exec-webhook` streak cleanup no longer name Exec (keep any behaviour a test still needs, renamed)
- `docs/jbus.md`, `docs/configuration.md`, `README.md`, `docs/jstack-explained.html` no longer describe Exec; where they said Exec gets events they say the webhook (Sous Chef)
- the tests that pinned Exec (`test_new_home_skill.py`, `test_party_handoff.py`, `test_handoff_next.py`, `test_handoff_mail.py`, `test_roles.py`, `test_jbus_approval.py`, `test_jbus_approve_by_rule.py`, `test_jbus_word.py`, `test_jbus_one_wake.py`, `test_jbus_digest.py`, `test_settings.py`, `test_home_gauge.py`, `test_jbus_view_page.py`, `test_readme_current.py`) pin the new text instead
- `rg -i '\bexec\b|_exec|exeggutor' skills src docs templates tests README.md` finds only the shell builtin `exec` and Hyprland `exec-once`
- `make check` exits 0
Proves it: `make check`, and the `rg` command above returning only shell `exec` hits
Size: M
Where: `skills/new-home/SKILL.md`, `skills/home/SKILL.md`, `skills/handoff/SKILL.md`, `src/jroles/`, `src/jbus/queue.py`, `src/jbus/word.py`, `src/jbus/cli.py`, `docs/`, `README.md`, the tests listed
Do not touch: the homes' state folders (the home scrubs its own files), `~/.config/`, T3 projects and threads, `skills/expert/` beyond removing an Exec mention, `skills/home/SKILL.md` text this brief does not name
Decisions: the user's words under Task. Wording is the scout's section 5c unless it reads wrong in place. A question only he can answer is a gate through `jbus gate`, with the default taken; ask him nothing in this thread.
Design: none, the scout's report is the design and the Done when list pins the outcome

Playbook: refactoring, the steps the crewmate worked by.
The principles it cites, and when each applies:
- test-behavior-not-implementation: Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change.
- model-the-domain: Apply when writing stateful logic, or when code branches a lot or repeats a shape assumption across files.
- foundational-thinking: Apply before writing logic: choosing core types and data structures, sequencing scaffold-vs-feature work, asking what concurrent actors share. Get the data structures right so downstream code becomes obvious.
- redesign-from-first-principles: Apply when integrating a new requirement into an existing design.
- subtract-before-you-add: Apply when sequencing an addition, refactor, or rewrite. Remove dead code, redundant validators, and stub references first, then build on the simpler base.
- laziness-protocol: Apply when refactoring, evaluating diff size, or tempted to add abstractions, layers, or signal threading. Bias toward deletion and the smallest change that solves the problem.
- migrate-callers-then-delete-legacy-apis: Apply when introducing a new internal API while old callers still exist. Migrate callers and delete the old API in the same wave instead of preserving compatibility layers.
- prove-it-works: Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'
- minimize-reader-load: Apply when reviewing or shaping code that's hard to trace. Count layers between question and answer, and hidden state in the reader's head; collapse one-caller wrappers and shrink mutable scope.
- sequence-verifiable-units: Apply to multi-step work (sweeps, migrations, runs of similar edits) and to how you order commits and pull requests. Break work into small units that each end in a verifiable state, check each before the next, and order delivery so the sequence proves itself to a reviewer.

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

### 1. [warning] An old `[exec]` table now loads without a warning, and its webhook URL and key are no longer redacted
**Location**: src/jbus/__init__.py:42 (`IGNORED = ("loud",)`) and :178 (`_ignored`). `_unread` and `Config.unread` were removed near :79 and :122.
**Finding**: Before this change, a config with a top-level `[exec]` table, or with `exec_watch` on a project, loaded, and every pass said "ignored: … remove them". The `webhook_url` and `webhook_key` of that `[exec]` table also went into `Config.secrets()` through `hooks()`. Now `tomllib` still reads the table, but nothing names it and `hooks()` returns only `[*self.projects, self.webhook]`.
**Evidence**: On a machine whose `config.toml` still has `[exec] webhook_url = "...", webhook_key = "..."`, the URL and key are no longer in `secrets()`. Gate text, digest lines or `jbus events` output that quotes them now prints them in clear. The deleted test `test_the_url_and_key_of_an_exec_table_nobody_reads_are_still_taken_out` covered exactly this case, and the digest test dropped its `exec_key` plant. The brief said "keep any behaviour a test still needs, renamed"; this behaviour was deleted, not renamed. The user's own config has no exec keys, so this machine is not hit, but jstack is installable elsewhere. `docs/configuration.md:95` now documents only `loud`, so the user is never told to remove the stale secret.
**Suggestion**: Keep the retired-table handling and rename it, for example `IGNORED = {"top": ("exec",), …}` becoming a neutral "retired" set. Or keep `_unread` under a non-Exec name and keep its test. (principle: migrate-callers-then-delete-legacy-apis)

### A2

### 2. [warning] The retired `exec-webhook` streak cleanup was deleted, though the brief said to rename it
**Location**: src/jbus/cli.py:451 (just after the removed `alert.retire(config.state_dir, RETIRED)` and the `exec-sent.json` unlink loop)
**Finding**: The Done-when line says the cleanup "no longer name[s] Exec (keep any behaviour a test still needs, renamed)". The PR deleted the behaviour and also deleted the test that needed it, `test_the_copy_to_exec_leaves_no_streak_and_no_file_behind`.
**Evidence**: On a machine where `streaks.json` still holds an alerted `exec-webhook` streak, nothing ends that streak any more, so it stays in `jbus status` streaks for good. Any `exec-sent.json` left in a project state directory also stays. This machine has no such leftovers, which makes the deletion safe here. It is still a departure from the brief that the PR does not record.
**Suggestion**: Keep it as `alert.retire(state_dir, "exec-webhook")` under a neutral constant name, or record in the PR that the reconciliation was dropped on purpose and why. (principle: migrate-callers-then-delete-legacy-apis)

### A3

### 3. [warning] The party handoff machinery is kept, but no real party uses it any more
**Location**: skills/handoff/SKILL.md:62 and :288 (`jroles expert`); tests/test_party_handoff.py (whole file renamed `exec` to `desk`)
**Finding**: With Exec gone, the non-expert parties are all retired. The live state root holds only `_exec` (retired) and three experts that have a `CHARTER.md`, and `party_home` never handles a folder with a `CHARTER.md`. That leaves `party_home`, the "A party's home" close block, "The thread a party's handoff started", and the `expert` role used for non-expert parties without a real caller. The tests keep the path alive by inventing a `desk` party. The role choice is also odd: the handoff asks for the `expert` role only for parties that are, by construction, never experts. `skills/expert/SKILL.md` does not call `jroles`.
**Evidence**: The brief made the change "they can completely go; we are moving from this pattern". The PR renamed Exec's fixtures instead of asking whether the pattern itself still has a user.
**Suggestion**: Remove the party-handoff section, its blocks and the test file. This is a larger cut, so note it for a follow-up if it goes beyond this PR's scope. (principle: subtract-before-you-add)

### A4

### 4. [warning] Files changed outside the "Where" line
**Location**:
- src/jbus/__init__.py:42
- src/jbus/project.py:26
- tests/fixtures/t3/README.md:10
- tests/test_home_on_bus.py:155
- tests/test_jbus_view.py:1089

**Finding**: "Where" lists `src/jbus/queue.py`, `word.py` and `cli.py` under `src/jbus`, plus `src/jroles/`, the docs, the README and a named list of tests. Each file above is outside that list. The `__init__.py` change is the one with behavioural effect (finding 1). The others are text renames needed for the `rg` Done-when line.
**Evidence**: Review rule 7, where each such file is a finding. (principle: none)

### A5

### 5. [nit] The new home line adds a rule the brief did not ask for
**Location**: skills/home/SKILL.md:98
**Finding**: The brief asked for one line: "escalations reach the user through jbus's webhook, and a home keeps no registry of homes: jbus is it". The added sentence also says "A home sends no other thread a status". That is a new standing rule. It also sits awkwardly beside the home messaging its own crewmates and scouts.
**Suggestion**: Use the brief's wording without the extra clause. (principle: laziness-protocol)

### A6

### 6. [nit] The new roles test mostly restates the constant
**Location**: tests/test_roles.py:53
**Finding**: `assert ROLES == ("crew", "scout", "review", "home", "expert")` pins the tuple literal, which is an implementation detail. The behavioural assertions already in the test cover what matters: a `bad line` for an unknown role, and `SystemExit` for `main(["orchestrator"])`. The unknown role in them is `orchestrator`, not `exec`, so nothing checks that the removed role in particular is refused.
**Suggestion**: Drop the tuple assertion and use `exec: …` as the refused line and the argv. (principle: test-behavior-not-implementation)

### A7

### 7. [nit] A leftover pair-telling message in the gauge fixture
**Location**: tests/test_home_gauge.py:330
**Finding**: The `t3_thread_send` entry still carries `"the home of demo is another now"`. That is the wording of the pair-telling send this PR removed from the handoff. The handoff's remaining sends are the mail pass-on and the sender notice.
**Suggestion**: Change it to the pass-on message's shape. (principle: none)

### B1

### 1. [warning] A leftover `[exec]` table now loads silently, and its webhook URL and key are no longer redacted
**Location**: src/jbus/__init__.py:42 (`IGNORED = ("loud",)`). The `Config.unread` field is removed, `hooks()` is at line 122 (now `[*self.projects, self.webhook]`), and `_ignored`/`_unread` are at about line 178. This file is outside the "Where" line.
**Finding**: Before this change, a config with a top-level `[exec]` table or a project `exec_watch` key still loaded. Each pass printed `ignored: … still has [exec], exec_watch of project …: … remove them`. The `[exec]` table's `webhook_url` and `webhook_key` were added to `Config.secrets()` through `unread`, so `jbus.redact` took them out of journal lines, gate text and the digest. After this change `load()` accepts `raw["exec"]` without complaint because tomllib keeps unknown keys. Nothing tells the user to remove it, and its URL and key are no longer in `secrets()`. The tests that pinned this were deleted rather than renamed: `test_the_url_and_key_of_an_exec_table_nobody_reads_are_still_taken_out`, the `exec_key` entry in `test_jbus_digest`, and the `[exec]` and `watch` cases in `test_jbus_one_wake`.
**Evidence**: The brief asks for text that no longer names Exec, and to "keep any behaviour a test still needs, renamed". It does not ask to drop the secret handling for a retired table. Removing the `"exec"` name from these keys is enough to pass `rg`. The redaction and the "remove it" notice are behaviour, not Exec wording. The live `~/.config/jbus/config.toml` has no `[exec]` or `exec_watch` today, so this machine is not exposed now. A restored or older config would leak its URL and key into logs without any warning.
**Suggestion**: Keep a generic "retired top-level table" entry, for example `IGNORED = {"top": ("retired_desk",) …}`. Or, more simply, have `_ignored` flag any unknown top-level table and redact any `webhook_url`/`webhook_key` found in an unread table. If not, record in the PR that dropping this was deliberate. (principle: subtract-before-you-add)

### B2

### 2. [warning] The retired `exec-webhook` streak cleanup was deleted, not renamed as the brief said
**Location**: src/jbus/cli.py:451 (just after the `ignored:` line, where `alert.retire(config.state_dir, RETIRED)` and the `exec-sent.json` unlink loop were). The test `test_the_copy_to_exec_leaves_no_streak_and_no_file_behind` was removed from tests/test_jbus_one_wake.py.
**Finding**: The "Done when" line says the cleanup should "no longer name Exec (keep any behaviour a test still needs, renamed)". Instead, the cleanup and its test are gone. On a machine that still has the streak in `streaks.json` or an `exec-sent.json` file, those are never cleared now.
**Evidence**: On this machine `~/.local/state/jbus/streaks.json` has no `exec-webhook` key and there is no `*/exec-sent.json`, so deleting the cleanup is safe here. That makes the deletion defensible, but it departs from what the brief said, and the PR does not record that it checked this.
**Suggestion**: State in the PR that the live state was checked and the cleanup is dead code, or keep the cleanup under a neutral name. (principle: prove-it-works)

### B3

### 3. [nit] Changed files outside the "Where" line
**Location**: src/jbus/__init__.py:42, src/jbus/project.py:25, tests/fixtures/t3/README.md:10, tests/test_jbus_view.py:1089, tests/test_home_on_bus.py:156
**Finding**: None of these files is in "Where" or in the list of tests. The edits to `project.py`, the fixture README, `test_jbus_view.py` and `test_home_on_bus.py` are wording changes that the `rg` "Done when" line needs, so they trace to the task. The change to `__init__.py` is behavioural (see finding 1). (principle: none)

### B4

### 4. [nit] A changed doc line and `who()` now label any session's approval as "the <directory> home", including approvals run by Sous Chef
**Location**: docs/jbus.md:279; src/jbus/queue.py:214
**Finding**: Exec was the one session `who()` named on its own. Now every session is `the <dir> home`. `docs/chef.md:51,85-88` says the Chef runs `jbus queue approve` itself. Since this PR makes Sous Chef the only orchestrator, its approvals will read as approvals by a home called after whatever folder it runs in. The audit trail for rule approvals ("run … by <who>") then cannot tell the orchestrator from a repo's home.
**Evidence**: Before this change the Chef's runs were also mislabelled, so the code behaviour is not new. What is new is that the changed doc line now states "`the <directory> home` for a session" as if it were true for every session.
**Suggestion**: Word the doc line as "the name of the directory it ran in", or leave it for a follow-up. (principle: model-the-domain)

### B5

### 5. [nit] The test of the gauge's handoff allow-list still uses the removed party-tell message as its example
**Location**: tests/test_home_gauge.py:844 (next to line 847)
**Finding**: `(T3_CODE + "t3_thread_send", {"threadId": "t", "message": "the home of demo is another now"})` is the text of the pair-telling step that this PR removed. `t3_thread_send` is still used by the handoff's mail pass-on, so the entry should stay. Its example should be a pass-on message, so the test describes the calls a handoff still makes. (principle: test-behavior-not-implementation)
