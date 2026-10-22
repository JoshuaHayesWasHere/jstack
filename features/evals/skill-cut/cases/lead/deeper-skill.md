# deeper-skill

## Intent

Task: sections 1, 2, 5 and 6 of the /deeper design, built on Felix Rieseberg's "four types of ambition" (Depth): a skill that returns the four answers and a rewritten prompt, a principle, a blind eval required before merge, and the credit
Done when:
- `skills/deeper/SKILL.md`, manual only (`disable-model-invocation: true` in its front matter): given a task or a draft brief, it answers the four questions of the design's quote (what a top professional would do that is not asked; the rawest material; the methods and tools; what outside the agent shows the result is right) and gives a rewritten prompt. Run by a home, it does not block: the home takes the rewrite as the default and pipes a `jbus gate` with two options, keep the original or use the rewrite. The skill is installed by `install.sh` as the others are and is listed where skills are listed
- `principles/depth-over-breadth.md` (the repo names principle files without a `principle-` prefix: follow that, the user's name is depth-over-breadth), the 25th, in the shape of the other 24: choose depth over extra scope in research, perf, analysis and outcome work (raw data over summaries, an expert's instruments over their words, an outside judge over self-assessment); its boundary (not for mechanical fixes); paired with prove-it-works, explain-the-number, build-the-lever, attack-the-premise. `jdrift` lists it as a jstack source, not a missing upstream, and its test passes; every count of principles (docs, the explained page, tests) says 25
- `THIRD_PARTY.md` credits Felix Rieseberg, "How to be more ambitious: A tutorial for humans with models" (2026-10-13, the URL in the design), and ties it to the planned pstack /sharpen and /in-your-own-words port
- `evals/deeper/`: about 10 past briefs from `~/.local/state/home/jstack/tasks/` (research, perf, analysis or outcome ones, named in the eval), each run through brief writing with and without /deeper; the pairs scored blind (the scorer does not know which is which, and is not the agent that wrote them: a script over the brief text, or a reader that sees only shuffled, unlabelled pairs) on three things: raw sources used, instruments named, and whether the proof is outside the agent; then, for each brief whose pull request merged, how it turned out. The eval is rerunnable by one command, its results are committed, and the Result says whether /deeper won. If it did not, say so: that is a finding, not a reason to tune the eval
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the blind scores in `evals/deeper/` (a scorer that is not the writing agent), and the jdrift test
Where: `skills/deeper/`, `principles/depth-over-breadth.md`, `src/jdrift/` (its source map), the docs and tests that count or list principles and skills, `install.sh` if it lists skills, `THIRD_PARTY.md`, `evals/deeper/`
Do not touch: `skills/home/` (deeper-home-step's); `templates/brief.md` and the parser (deeper-proves-it's); the other principles' text
Decisions: the user, 2026-10-15 01:33 ET, word 57fb24bc8b71, from Sous Chef's Grok Bot chat: "Yes, build it in jstack", approving the /deeper design by Poteto Stalker (saved at ~/.local/state/home/jstack/scouts/deeper-design.md), with his decisions of 01:32 ET in it: the principle is named depth-over-breadth; the home's brief step carries its own copy of the four questions and `/deeper` stays manual (`disable-model-invocation`); Altitude outcome briefs and a Range step are out. The split into three briefs is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/deeper-design.md, sections 1, 2, 5 and 6

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

### 1. [warning] The "outside" measure counts any backtick span as an outside judge
**Location**: evals/deeper/score.py:5914 in the prompt's diff (`OUTSIDE = re.compile(r"\`[^\`]+\`" ...`), the first branch of `OUTSIDE`
**Finding**: Any proof line with inline code counts as "names a judge outside the agent". So does a line that only names a path, such as "- \`skills/x/SKILL.md\` says Y". This is a proxy that rewards formatting, not a check for a judge.
**Evidence**: I rescored the committed run-2 briefs (`runs/` + `key.json`) with `outside()` once as written and once without the backtick branch:
- plain: 60/106 proof lines count as outside as written, 36/106 (0.34) without the branch.
- deeper: 110/155 as written, 51/155 (0.33) without the branch.

The whole plain-to-deeper rise in "outside" (0.57 to 0.75 in run 2) comes from backticks. With the other patterns alone, the two arms are level. The README's Result says "no effect shown", which still holds. But the 8/2 split and the README's suggestion that the planned `Proves it:` line is "aimed at that gap" both rest on a measure that reads code formatting. Deeper briefs use far more backticks because the skill tells them to name things by path and command.
**Suggestion**: Make a backtick span count only when it holds a command that is run (`make`, `pytest`, `uv run`, `hyperfine` and so on), or drop that branch. Then say in the README that the current measure counts inline code.

### A2

### 2. [warning] "Raw sources" has no control for copying the skill's own list, but the README says it does
**Location**: evals/deeper/README.md:246 in the diff ("not only by copying the skill's own examples"); evals/deeper/score.py:5865 (`RAW`)
**Finding**: `beyond` takes out the instruments the skill names. Nothing does the same for raw material. Yet `skills/deeper/SKILL.md` question 2 lists "logs, transcripts, traces, a profile, the database, the CI run's own log, the counters of the machine". Those match the `RAW` keys `logs`, `transcripts`, `traces`, `profiles`, `database`, `ci_runs` and `machine_counters` almost word for word.
**Evidence**: A deeper-arm writer that repeats the skill's list scores 6 to 7 on raw. That explains most of the 0.65 to 3.90 gap. The README's "What holds" line says it holds "on every case of both runs, and not only by copying the skill's own examples". That claim is backed only for instruments, not for raw sources.
**Suggestion**: Add a `beyond` for raw that leaves out the categories the skill names, or narrow the "What holds" sentence to instruments.

### A3

### 3. [warning] `write()` deletes the committed runs before any model call, with no recovery if a run fails partway
**Location**: evals/deeper/eval.py:1480-1482 in the diff (`shutil.rmtree(HERE / name ...)` in `write`)
**Finding**: `runs/` and `deeper/` are wiped first. Then 60 `claude -p` calls run through `pool.map`. Any single `RuntimeError` (a non-zero exit, empty output, or a missing block quote in `rewritten()`) or a 900 s timeout ends the run. That leaves:
- a partial `runs/`,
- `deeper/` files that do not match it,
- the old `key.json`, which now names deleted files.
**Evidence**: `key.json` is written only after the loop ends. `report` then refuses because the key and the scores do not match, and the committed results can be restored only from git. This is the "crashed halfway" case the review asks about. The step is advertised as rerunnable by one command.
**Suggestion**: Write into a temporary directory and swap it in after the key is written. Or write the key one entry at a time and skip jobs that already have output.

### A4

### 4. [nit] The "Not held" column counts a phrase, and the README treats it as a per-brief fact
**Location**: evals/deeper/eval.py:1434 in the diff (`not_held=len(re.findall(r"does not hold", text))`)
**Finding**: It counts every "does not hold" anywhere in the brief, including the Review and repeats. It misses "did not hold" and "doesn't hold". The README's "Seven of the ten had a Done when line their Result said did not hold" is read off this count.
**Suggestion**: Limit the search to the Result section and match the tense variants, or present the column as a phrase count.

### A5

### 5. [nit] Importing the eval leaves `evals/deeper` and `src` on `sys.path` for the whole test session
**Location**: evals/deeper/eval.py:1318 in the diff (`sys.path[:0] = [...]`); tests/test_eval_deeper.py:6691-6704 in the diff
**Finding**: `load()` in the test removes `EVAL` from `sys.path` in its `finally`. But `exec_module` of `eval.py` adds `HERE` and `src` again for good, and registers a top-level module named `score`, separate from `deeper_score`. Every later test in the same worker then sees a bare `score` module and `evals/deeper` on its import path.
**Suggestion**: In `eval.py`, import `score` with a path-scoped import (as the test does). Or have the test restore `sys.path` and `sys.modules` after loading.

### B1

### 1. [warning] The eval's verdict came from a re-run of a skill change that only altered the output format
**Location**: `evals/deeper/README.md:61-73`, and `evals/deeper/results.md:69`
**Finding**: Run 1 did not win under the rule (proof outside lost, 4 cases up and 6 down). The only change before run 2 was the output form of the rewritten prompt: a fence became a block quote (`git diff fbb2892 7a0815c -- skills/deeper/SKILL.md`). The four questions and the instructions stayed the same. Run 2 then won with outside at 8 up and 2 down. The README calls run 2 "the skill as it merges" and puts "won" in its Result.
**Evidence**: For eight of the ten cases the outside measure changed sign between two runs of what is in effect the same skill (README table). Under the rule, "lost on none" depends on that measure, so the outcome of the whole eval turned on run-to-run noise. The README says "Only what the two runs agree on is a finding", but the two runs disagree on outside, and it still states the verdict as "won". Running again after a "did not win" is the move the task warned against ("that is a finding, not a reason to tune the eval"). Here it was the skill that changed rather than the eval, but the effect on the verdict is the same.
**Suggestion**: Give the Result as "won on raw and instruments in both runs; proof outside not shown; the rule's no-loss condition passed in one run of two". Or apply the rule to both runs pooled. Do not call the eval won on run 2 alone.

### B2

### 2. [warning] The `raw` measure largely counts the skill's own example list, and no check catches that
**Location**: `evals/deeper/score.py:28-41` (`RAW`), and the claim at `evals/deeper/README.md:72`
**Finding**: Answer 2 of `skills/deeper/SKILL.md` lists "logs, transcripts, traces, a profile, the database, the CI run's own log, the counters of the machine". Seven of the twelve `RAW` kinds match those words directly: `logs`, `transcripts`, `traces`, `profiles`, `database`, `ci_runs` (`run logs?`) and `machine_counters` (`\bcounters?\b`).
**Evidence**: Instruments got a `beyond` count without the skill's examples. Raw got nothing like it. Even so, the README says under "What holds" that `/deeper` makes a brief name its raw material "and not only by copying the skill's own examples". The evidence supports that only for instruments. The raw gap (0.65 to 3.90) could be mostly the skill's list showing up again in the brief.
**Suggestion**: Add a raw `beyond` count without the skill's listed kinds, as `SKILL_EXAMPLES` does for instruments. Then re-score the committed briefs, which needs no new model calls, or limit the README claim to instruments.

### B3

### 3. [warning] Running the eval's one command on a machine without `claude` deletes the committed briefs
**Location**: `evals/deeper/eval.py:202-205` (`write`), reached from `main([])`
**Finding**: The default `uv run python evals/deeper/eval.py` runs `cases`, then `write`. On a machine with no `tasks/`, `cases` keeps the committed cases. `write` then calls `shutil.rmtree` on `runs/` and `deeper/` before the first `claude` call. With no `claude` (or with any failed call), `subprocess.run` raises, and the committed briefs are already gone from the working tree.
**Evidence**: Any failure partway through has the same effect, because `key.json` is written only at the end. `runs/` is left with a partial set, `key.json` and `scores.json` are stale, and nothing can resume: all 60 calls start over. The README offers `score report` for a machine without the tools, but the one documented command is the one that wipes the data.
**Suggestion**: Write into a temporary directory and swap it in only when the run completes. Or check `shutil.which("claude")` before deleting anything.

### B4

### 4. [warning] Text written by the eval goes unredacted when `XDG_CONFIG_HOME` is set
**Location**: `evals/deeper/eval.py:119-123` (`_private`)
**Finding**: `_private` loads the patterns from `jleak.path(Path.home() / ".config")`. It ignores `XDG_CONFIG_HOME`, which `jleak`'s own CLI respects (`src/jleak/cli.py:56`). When the file is not at `~/.config`, `jleak.Missing` is caught and `()` is returned without a word. Cases, briefs and `/deeper` outputs are then written to a repo meant to be public, with no redaction.
**Evidence**: The README says private patterns are taken out of every request and every model output. That holds only when the patterns load, and a failure to load is swallowed.
**Suggestion**: Resolve the config path the way `jleak.cli` does. In `cases` and `write`, fail when the patterns are missing instead of falling back to "no patterns".

### B5

### 5. [nit] `SELF` counts any proof line that mentions a review as self-assessment, which distorts the case about reviews
**Location**: `evals/deeper/score.py:85-89` (`SELF`)
**Finding**: `\breview(?:ed|er|ers)?\b` disqualifies any `Done when:` line containing "reviews", even one whose judge is clearly outside the agent. One example is "three reviews run at once, counted from the event log by `jq`".
**Evidence**: `rs-parallel-reviews` is about running reviews in parallel. It scores 0.27 (plain) and 0.44 (deeper) on outside, and the shipped brief scores 0.143, the lowest in the tables. The regex is matching the subject of the task, not who judges the result.
**Suggestion**: Disqualify only phrasings where a review is the judge ("the reviewer agrees", "a review confirms"), not the bare word.

### B6

### 6. [nit] The principle card says two playbooks rely on the principle, and neither mentions it
**Location**: `principles/depth-over-breadth.md:20` (the `<!-- card: ... -->` leans), shown on `docs/jstack-explained.html:735`
**Finding**: The leans field lists `` `deeper`; `perf-issue`; `investigation` ``. A search for `depth-over-breadth` across `playbooks/` and `skills/` finds only `skills/deeper/SKILL.md`.
**Evidence**: Leans on the other principles' cards match real references. For example, `explain-the-number` is listed on `perf-issue`, and `playbooks/perf-issue.md` links to it. This card claims usage that does not exist.
**Suggestion**: List only `deeper` until the playbooks link to the principle. Changing the playbooks is outside the "Where" line, so that part is for later.

### B7

### 7. [nit] The gate's `Context:` placeholder invites four lines, and jbus keeps only the first
**Location**: `skills/deeper/SKILL.md:67`
**Finding**: The placeholder reads `Context: <the four answers of /deeper, in one line each>`. A home that writes one line per answer produces four lines. `mirror.field(lines, "Context")` (`src/jbus/mirror.py:59`) returns only the `Context:` line, so answers 2 to 4 are silently dropped from the gate's record.
**Evidence**: The test fills in one line joined with semicolons (`tests/test_deeper_skill.py`), so it never covers the reading the wording suggests.
**Suggestion**: Change the placeholder to "the four answers of /deeper, on this one line, separated by semicolons".

### B8

### 8. [nit] `Pinned.own` has a default nothing uses
**Location**: `src/jdrift/__init__.py:30`
**Finding**: `own: tuple[str, ...] = ()` defaults the field, but `read_section` is the only place `Pinned` is built (`grep -rn 'Pinned(' src tests`), and it always passes `own`.
**Suggestion**: Drop the `= ()` so the field is required like the others.
