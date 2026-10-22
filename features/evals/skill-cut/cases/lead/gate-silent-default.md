# gate-silent-default

## Intent

Task: the user, 2026-10-15 22:31 ET (word ff14298b8b7b), relayed by Sous Chef: "every gate in every home must carry a default action, and if the user hasn't answered in 2 hours the home takes the recommended default. Exceptions that still wait: deletes data, spends money, touches prod or real users, or can't be undone." Refined the same evening (word 8197e02cd7e4): "every gate gets a safe default of act-unless-stopped instead of wait-unless-started. No more silent defaults that leave work parked. BUT: anything irreversible or slow to revert must have a fail-safe, e.g. a confirmation step, a dry-run, or a hold that requires the user before it proceeds. Define what counts as irreversible in the brief and propose the fail-safe per case. Don't ship the default-change without the fail-safe design alongside it." Today `jbus gate` refuses a gate with no `Default:` (`src/jbus/questions.py` around line 94); a thread takes the default and carries on, but a question stays open, and an action that needs his answer parks.
Irreversible or slow to revert means: undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. The cases and their fail-safes:
| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for the user |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for the user |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for the user |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for the user |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for the user (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for the user |
Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch.
Done when:
- a gate is act-unless-stopped: the thread acts on its default at once, the question is shown to the user as already acted on, and an answer that differs is carried back as today; no question parks work while it waits
- a gate whose default is one of the cases above must say so with one line, `Holds: <deletes data | rewrites history | spends money | touches prod or real users | changes access or secrets | publishes>`, and must name its fail-safe on a `Fail-safe:` line; `jbus gate` refuses a `Holds:` gate with no fail-safe, and an unknown case. A `Holds:` gate does not act: it waits for the user's answer, with the dry-run, plan or bundle attached, and is never closed by silence
- `jbus gate` refuses a gate with no filled `Default:` line (kept) and one whose recommended option is not the default
- a pass closes an open question with no `Holds:` line once it has been open 2 hours, as answered by its default and by silence (a basis that says it is not his word); a later differing answer is still taken
- `skills/home/SKILL.md` ("Gates", "Ask one"), the crew and scout skills where they gate, and `templates/gates.md` state the rule, the definition and the table above; `docs/jbus.md` says it. The default change and the fail-safe rules ship in this one pull request
- tests with a fake clock: a gate with no default is refused; a `Holds: deletes data` gate with no `Fail-safe:` is refused; a `Holds:` gate stays open at 48 hours; a plain gate closes at 2 hours and not at 1:59; a later differing answer is taken
- `make check` exits 0
Proves it: `make check` runs the fake-clock tests above; after the merge `jbus queue show` on this machine lists no open question older than 2 hours that has no `Holds:` line
Size: M
Where: `src/jbus/questions.py`, the pass that ages questions (`src/jbus/waiting.py` or `cli.py`), `skills/home/SKILL.md` (Gates), `skills/crew/SKILL.md` and `skills/scout/SKILL.md` where they gate, `templates/gates.md`, `docs/jbus.md`, the tests
Do not touch: open questions already in any project's `questions.json` by hand (the new pass handles them; old gates with no `Waits:` line close at 2 hours, which is the user's rule); `~/.config/`
Decisions: the user's words under Task. "The recommended default" is read as: the default must be the recommended option. The definition and table above are the home's proposal, which the user asked for in the brief. A question only he can answer is a gate through `jbus gate`, with the default taken; ask him nothing in this thread.
Design: none, the Done when list pins the line, the clock and the exceptions

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

### 1. [critical] A silence-closed question tells a thread that re-pipes it to act, even when its gate now holds
**Location**: src/jbus/questions.py:416 and :388-389 (`ask`, the new `holds`/`fail_safe` fields), with `silent` at :481. The damage is at the unchanged line :394 (`again = one if one.answer else replace(one, **said)`) and at :734 (`already answered`).
**Finding**: `ask` treats any record with an answer as settled. Since this change, that includes an answer of `closed_by: silence`. Suppose a thread re-pipes the same question (same slug, same words) after the 2-hour close: the module docstring says threads do park the same gate again at a later head. That thread now gets `already answered: question N: closed with its default by jbus …`. Any new `Holds:`/`Fail-safe:` lines are thrown away, because answered records are never replaced. `skills/crew/SKILL.md` (line ~154) and the scout skill tell the thread "Go by it." So a thread that sends a plain gate and later finds the default deletes data or force-pushes, then re-pipes with `Holds: deletes data`, is told the question was answered and goes ahead. Nobody ever said yes.
**Evidence**: the diff added `_open()` (":505 open, or closed by silence alone") and used it only in `closed_in_files`, not in `ask`. No test re-pipes a silence-closed question. The test at :768 even asserts the `already answered` reply after silence.
**Suggestion**: in `ask`, treat a silence-closed record as open (`again = replace(one, **said) if _open(one) else one`). If the re-pipe adds `holds`, clear the silence answer. Add a fake-clock test: plain gate, close at 2h, re-pipe with `Holds:`, then expect the question to be open again with `holds` set.
(principle: model-the-domain)

### A2

### 2. [warning] Silence closes the link-conflict questions that ask the home, so the stack parks
**Location**: src/jbus/questions.py:505-513 (`silent`/`_quiet`) and :536 (the new step). The damage is in skills/home/SKILL.md:757-759 and :812-822.
**Finding**: `_quiet` closes every open record with no `holds`. That includes the `<slug>: <url> has a conflict, and it is a link of a stack` questions. The home's own table (skills/home/SKILL.md:663) says these ask the home and not the user. The home's reader picks them out with `select(.answer == null)` into `$LINKS`. Two hours after the question is asked, `silent` closes it, it drops out of `$LINKS`, and the home never sends the rebase line. The conflicted link then sits. That is the opposite of "no question parks work".
**Evidence**: the jq filter in the home block is `.answer == null`, and `silent` sets `answer`. Nothing in `_quiet` exempts these questions, and no test covers them.
**Suggestion**: exempt the questions that ask the home from `_quiet`. The better fix is to stop keeping them as user gates at all, so their conflict line is still sent.
(principle: model-the-domain)

### A3

### 3. [warning] The "Your words" page shows a close by silence as the user's own answer
**Location**: src/jbus/questions.py:488 (`given = Answer("default", SOURCE, at, UNANSWERED, True, closed_by=SILENCE)`). The damage is in src/jbus/view/panels/words/panel.py:137 and :75-90, and panel.js:17-21.
**Finding**: the words panel lists every record with an `answer` as "questions you answered". It renders anything that is not `closed_by == HOME` as `Your answer "default"`, with "the default stands", "by jbus", "in no answer in 2 hours". The task says a close by silence must carry a basis saying it is not the user's word. `basis()` refuses it as the basis for an approval, but the user's own record of what he said still claims it was his.
**Evidence**: `_answer` only special-cases `questions.HOME`, and `build` keeps every answered record.
**Suggestion**: give `closed_by == SILENCE` its own branch, as `home` has, or leave it out of the words list. The panel files are outside the "Where" line, so this is noted for later. The cause is in `questions.py`.
(principle: model-the-domain)

### A4

### 4. [warning] Nothing the user reads shows "already acted on" or the fail-safe
**Location**: src/jbus/questions.py:526-528 (`item` adds `acted`, `holds`, `fail_safe`). This is also a gap in the change as a whole.
**Finding**: two "Done when" lines need the question shown to the user as already acted on, and a `Holds:` gate shown with its dry-run, plan or bundle attached. The new fields only reach `waiting-on-user.json`:
- The item's `line` is still `question N: …`, unchanged.
- The page's `you` panel drops the new keys. Its `_WAITS` SHAPE and `_waiting` copy only a fixed set of keys.
- The home's "block that reads jbus" (skills/home/SKILL.md:752, in the "Where" line) pulls only `number, slug, question, default, built_on, undo`.
So in the home, and on the page, the user sees a holding gate with no fail-safe and a plain gate with no sign that it was acted on.
**Evidence**: `grep acted|fail_safe` finds them only in `questions.py`. The test at :714 checks the raw JSON file, not anything rendered.
**Suggestion**: put the state in `line`, for example `question N (acted): …` or `question N (holds: deletes data; fail-safe: …): …`. Also add `.holds, .fail_safe` to the home's jq and its "Show the open ones" printf. The page panel is outside the "Where" line, so it is noted for later.
(principle: prove-it-works)

### A5

### 5. [warning] `recommended` is now always the same as `default`, but both marks and both fields remain
**Location**: src/jbus/questions.py:355-366 (the new `_proposed` branches) and :315-319 (FORM).
**Finding**: after this change, a gate is valid only when the one `(default)` option is also the one `(recommended)` option. So `Option.recommended == Option.default` on every new record. Even so:
- Every thread must still spell both marks.
- `_proposed` has two more refusal branches whose only job is to enforce that the marks match.
- The record, the page (`"marks": ["taken as default", "the thread recommends"]`) and the docs carry two fields that never differ.
- A thread on an older skill that writes `tea (default)` is now refused outright.
**Evidence**: about 12 test fixtures were rewritten only to add `, recommended`, which shows how much ceremony the redundant mark costs.
**Suggestion**: read `(default)` as also being the pick, accept `(default, recommended)` as a synonym, and refuse `(recommended)` on any other option. Those two new branches and the extra doc sentences then go away. The `Option.recommended` field can be derived from `default` for new records.
(principle: redesign-from-first-principles)

### A6

### 6. [nit] The home skill still says only the user's name closes a question
**Location**: skills/home/SKILL.md:694-697 (the changed "Gates" paragraph). The stale text is at :822, "only their name closes a question".
**Finding**: the changed paragraph removed "and nothing else does either", because silence now closes questions. The "handled" instruction in the same section still says "only their name closes a question", which a pass now contradicts after 2 hours.
**Suggestion**: reword :822 to match the new rule.
(principle: none)

### B1

### 1. [critical] A held gate answered "--default" never tells its thread to go ahead, so the held action stays parked
**Location**: src/jbus/questions.py:526 (`"acted": not one.holds`), together with how `ask`/`_held` change what a `Holds:` gate means. The damage is in `tell` (src/jbus/questions.py:622), `_answer` (around line 759) and the view's answer path (src/jbus/view/__init__.py, around line 470).

**Finding**: Before this change, a gate's default had always been carried out already. That is why `tell` skips any answer with `keeps` set, `_answer` prints "nothing is sent", and the page says "closed … with its default, and nothing was sent". This PR adds `Holds:` gates, whose thread does **not** act on the default and waits for the user's answer. Nothing in that send path was updated for them.

**Evidence**: Walk one through.
- A crewmate gates `Holds: deletes data` with `Fail-safe: dry-run …`. It does not act, as SKILL.md tells it: "the action waits for the user's answer".
- the user agrees with the default and runs `jbus answer 1 --default`, or ticks the default on the page.
- `answer()` stores `keeps=True`. `tell` then hits `given.keeps` → `continue`.
- The thread never hears anything, so the held action is never done. The same happens on the page path, where `keeps` → `(False, "", "")` and no carry.

So a held gate can only lead to action when the user's answer *differs* from the default. Saying "yes" to the recommended default does nothing. This breaks the Done when line "A `Holds:` gate … waits for the user's answer". docs/jbus.md:132 also still says "After `--default`, jbus sends the thread nothing, because the thread already did what you chose", which is false for a gate that holds. No test answers a `Holds:` gate at all.

**Suggestion**: In `tell` (and `View._carry`), carry a `keeps` answer when `one.holds` is set, with a "go ahead with the default" message. Make `_answer` and the page say so. Fix the sentence in docs/jbus.md. Add a fake-clock test: a `Holds:` gate answered `--default` sends one message to its thread.
(principle: model-the-domain)

### B2

### 2. [warning] "Shown to the user as already acted on" exists only as a JSON field that nothing displays
**Location**: src/jbus/questions.py:526-528 (`item`)

**Finding**: `acted`, `holds` and `fail_safe` are written into `waiting-on-user.json`, and nothing else uses them:
- `grep` finds no reader in src/jbus/view (page.html, panels/you/panel.js, state.py).
- `waiting._blocks` (src/jbus/waiting.py:447) keeps a fixed key list that drops all three fields.

**Evidence**: Done when says "the question is shown to the user as already acted on" and "A `Holds:` gate … waits … with the dry-run, plan or bundle attached". the user sees the same gate card as before: no "acted" marker and no fail-safe to answer on. The only test, `test_a_waiting_question_says_whether_it_was_acted_on_or_holds`, reads the JSON file, which is a stand-in for what the user actually sees.

**Suggestion**: Render `acted` and `fail_safe` on the gate card, and pass them through `_blocks`. That touches files outside the "Where" line, so it can be noted for later. Otherwise this Done when line is not met.
(principle: prove-it-works)

### B3

### 3. [warning] The new rule makes an expert's findings disappear after 2 hours
**Location**: tests/test_expert_skill.py:52 (`Option: leave it (default, recommended)`). The damage is in skills/expert/SKILL.md:283.

**Finding**: An expert sends a finding that "something should change" as a gate whose default is "nothing was changed". Now the default must also be the recommended option. To pass, the test marks "leave it" as recommended, so the expert has to recommend *against* its own finding. Then `silent` closes it after 2 hours as "default", and it leaves the user's list. An expert's findings now dismiss themselves by silence, and each one claims the expert recommends doing nothing.

**Evidence**: the user asked that silence not leave work parked. He did not ask for advice that recommends a change to be thrown away. The expert skill was not updated for the new rule: there is no mention of `(default, recommended)`, act-unless-stopped, or `Holds:`. Only the test fixture was edited to make the suite pass.

**Suggestion**: Decide how expert findings should behave. One option is `Holds:`-like waiting or a separate kind. Another is an expert default that is the recommended change, held for the user. skills/expert/SKILL.md is outside the "Where" line, so note it for later and do not paper over it in the test.
(principle: redesign-from-first-principles)

### B4

### 4. [warning] After silence closes a question, the page no longer lets the user answer it, though the docs say he still can
**Location**: src/jbus/questions.py:503-505 (`_open`) and line 444 (`answer`). The docs line is docs/jbus.md:115.

**Finding**: `answer()` accepts a reply that replaces a close by silence. However, `waiting.py:211` lists only `one.answer is None`, so the question drops off "what waits on you", and the page offers answers only for listed gates. After 2 hours the only way left is `jbus answer` typed by hand, and the only notice is a quiet `note` event. docs/jbus.md says "You can still answer it later … one that differs goes to the thread as any other". The page says "A gate that jbus holds is answered here", so this is a path the user can no longer find in the UI.

**Suggestion**: Keep silence-closed questions answerable in the view, for example a "closed by silence" state, or say plainly in the docs that only the CLI takes a later answer.
(principle: none)

### B5

### 5. [nit] The two marks are now redundant, and `_proposed`'s new branches enforce that redundancy
**Location**: src/jbus/questions.py:355-366

**Finding**: Since the default must also be the recommended option, `(recommended)` and `Option.recommended` add no information. They always equal `default`. The PR still makes every thread write both marks, adds two refusal branches to check that they match (one using a walrus on a dataclass's truthiness), and rewrites about 10 test fixtures and the FORM text.

**Suggestion**: The Done when line ("refuses one whose recommended option is not the default") is met just as well by refusing a `(recommended)` mark on any option other than the default and treating `(default)` as both. Keeping `(default, recommended)` accepted would remove the `not picked` branch and avoid churn for any thread that pipes old-style `(default)` gates.
(principle: subtract-before-you-add)

### B6

### 6. [nit] `_held` re-implements `mirror.field` line scanning
**Location**: src/jbus/questions.py:371-381

**Finding**: The dict comprehension repeats `mirror.field`'s `startswith(f"{name}:")` / slice / strip logic so that it can count repeated lines. If the field rules change, for example to strip leading whitespace as `mirror.options` does, the two parsers will drift apart.

**Suggestion**: Add a `mirror.fields(body, name) -> list[str]` and use it for both. That is a change to src/jbus/mirror.py, which is outside the "Where" line, so it is noted for later.
(principle: boundary-discipline)
