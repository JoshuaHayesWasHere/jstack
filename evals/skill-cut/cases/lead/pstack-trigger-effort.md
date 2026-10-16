# pstack-trigger-effort

## Intent

Task: the audit's P7, optional items, in his approval of "every other upstream update"
Done when:
- the merge-result question is answered from the code, with a test: does jmerge's "fails over today's main" check run the checks on the merge result? If yes, THIRD_PARTY.md says so; if no, it is made to when main changed a caller or a dependency of the files the PR touches (or a lockfile), with a test
- the effort question: whether a T3 launch (`modelSelection`) takes an effort setting, read from T3's own tool schema. jroles may only keep effort at medium or lower (the user's rule: never set or ask for an effort above medium), so the decision is written in THIRD_PARTY.md either way, and nothing raises it
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the test of the merge-result check, and the T3 schema quoted in the Result
Size: S
Where: `src/jmerge/`, `src/jbus/` (the "main changed" trigger), `src/jroles/` only if it gains a lower-effort field, `THIRD_PARTY.md` (the decision lines), the tests
Do not touch: the effort defaults in `~/.claude/settings.json`; nothing above medium anywhere
Decisions: the user, 2026-10-15 09:44 ET, word 79eb162adcb3, from Sous Chef's Grok Bot chat: "Yes, send it", approving the pstack catch-up (bring jstack up to current pstack, the #633 principle rewrite and every other upstream update it is missing), in the audit's priority order. Upstream is cursor/plugins `pstack/` at e5136d8; read it from a fresh clone in a temporary directory (`git clone --filter=blob:none`), never from memory. Keep jstack's local form where the audit says so. The split is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/pstack-drift-2026-10-15.md, "#613 in detail" and P7

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

### 1. [warning] The effort shape is not proven by the T3 schema, and no test would catch a wrong shape
**Location**: src/jroles/__init__.py:340 (`given["options"] = [{"id": "effort", "value": self.effort}]`); THIRD_PARTY.md:63
**Finding**: The PR says T3 Code takes effort as `modelSelection.options`, written as a list of `{"id": "effort", "value": <level>}`. It also says a launch with no effort runs at `high`. Neither claim is in T3's tool schema as this repo has it. `tests/fixtures/t3/t3_thread_launch.json` types `options` as `{"anyOf": [{}, {"type": "null"}]}`, which accepts any value. So `test_what_it_prints_is_a_model_selection_the_launch_tool_takes` passes whatever shape jroles prints.
**Evidence**: The "Done when" line asks for the effort question to be "read from T3's own tool schema", and "Proves it" asks for that schema to be quoted. The schema does not hold this answer. If T3 actually wants another shape, for example `{"effort": "medium"}`, it may drop the option without an error. Every Claude role would then launch at the model's own default, which the PR itself says is `high`. That breaks the one rule this part of the task exists to keep, and nothing reports it.
**Suggestion**: Find the real source of the `options` shape (T3's model-options contract or its provider code) and cite it in THIRD_PARTY.md. Add a fixture or test that pins the shape and fails on a different one, or record the question as a gate.

### A2

### 2. [warning] Codex and Grok lines are not checked against the "never above medium" rule, yet the PR says the rule holds for every named role
**Location**: src/jroles/__init__.py:363-366; THIRD_PARTY.md:63; src/jroles/__init__.py:308
**Finding**: A Codex or Grok line sends no effort, so it launches at whatever that provider defaults to. THIRD_PARTY.md still says the rule "holds for every role the map names", and the module docstring says the same. Nobody checked what T3 does for Codex or Grok when no effort is sent.
**Evidence**: The PR's own reason for always sending `medium` on Claude is that T3's default is above medium. It does not show that Codex or Grok differ. A `crew: codex gpt-5-codex` line could launch above medium.
**Suggestion**: Either find out each provider's default and effort option and cap them, or narrow the THIRD_PARTY.md and docstring wording to Claude lines and gate the Codex/Grok question.

### A3

### 3. [warning] The new check skips the "main changed a dependency" direction when the head cannot be read
**Location**: src/jmerge/cli.py:169-171 (`related`, `ours = {... _text(self.main, "git", "show", f"{one.head}:{path}") or "" ...}`)
**Finding**: If `git show <head>:<path>` fails in the main checkout, each of the PR's own files is read as empty. `uses(own, "", path)` can then never find an import or a named path, so a dependency that main changed is never flagged. The check stays green when it should not.
**Evidence**: `moved` runs `git fetch -q origin`, which fetches branches only. Elsewhere in `cli.py` (about lines 1078-1080), code that needs a pull request's head fetches `refs/pull/<n>/head` when `cat-file -e` fails. `related` does neither. It also treats "head not here" the same as "file deleted by the PR". In jmerge, every other git failure blocks the merge; this one lets it through. No test covers a head that is missing from the main checkout.
**Suggestion**: Check `cat-file -e {head}^{commit}` first, fetching `refs/pull/<n>/head` if needed. If the head still cannot be read, treat the check as stale or return a reason. Add a test for that case.

### A4

### 4. [warning] Bare-name imports between test files are missed, and this repo relies on them
**Location**: src/jmerge/ready.py:210-223 (`modules`)
**Finding**: `modules` names a file only by its dotted path, plus the path without `src/` for files under `src/`. A test that imports a sibling test by bare name, as pytest's rootdir/`tests` sys.path insertion allows, is never matched.
**Evidence**: The PR's own test does this: `tests/test_jmerge_callers.py` has `from test_jmerge_fresh import BEFORE, STALE, Kitchen, git, url, write`. Other tests do too, such as `tests/test_settings.py` with `from test_jbus_kitchen import ...`. `modules("tests/test_jmerge_fresh.py")` gives only `("tests.test_jmerge_fresh",)`. So if main changes the shared `Kitchen` fixture while a PR changes `test_jmerge_callers.py`, the check is still called fresh. That is exactly the "main changed a dependency" case the task targets, in this repo.
**Suggestion**: Also name a file under a pytest `testpaths` directory (`tests/`) by its bare module name, and add a test for a sibling test import.

### A5

### 5. [nit] A path match is a plain substring, and the conftest rule matches by suffix
**Location**: src/jmerge/ready.py:265-269 (`uses`)
**Finding**: `other in text` matches `src/pkg/core.py` inside `src/pkg/core.pyc` or `xsrc/pkg/core.py`. `other.endswith("conftest.py")` also matches a file named `myconftest.py`, and then treats its directory prefix (`tests/my`) as the conftest scope.
**Evidence**: Each wrong match makes a PR wait for a fresh check, or for a guarded PR, a rebase. It fails closed but adds noise.
**Suggestion**: Check the basename with `os.path.basename(other) == "conftest.py"`, and require a word or path boundary around the named path.

### A6

### 6. [nit] One `git show` subprocess per file, for every ready PR, on every run
**Location**: src/jmerge/cli.py:169-176 (`related`)
**Finding**: Whenever `stale_paths` is empty, `related` starts one `git show` per PR file and one per path main changed since the check started. That is repeated for every ready PR, on every run.
**Evidence**: Main can change hundreds of paths in a day, and a jbus pass stops jmerge after 300 s.
**Suggestion**: Read all the blobs at once with a single `git cat-file --batch`.

### A7

### 7. [nit] Three files changed outside the "Where" line
**Location**: docs/configuration.md:76, docs/jmerge.md:89/96/105, docs/jroles.md:118-123
**Finding**: The "Where" line lists `src/jmerge/`, `src/jbus/`, `src/jroles/`, `THIRD_PARTY.md` and the tests. These three doc files are outside it.
**Evidence**: The review brief counts each such file as a finding. Each edit does describe the new behaviour, so keeping them may be right, but whoever set the "Where" line should make that call.

### B1

### 1. [warning] A pull request that renames or moves a module misses callers main added under the old name
**Location**: src/jmerge/cli.py:645 and 659-667 (`related`)
**Finding**: `stale_paths` gets `left`, the paths the pull request's own renames left behind. `self.related(one, tip, paths)` does not. `related` builds `ours` from `one.files` only, and GitHub lists only the new path of a rename (that is why `self.left(one)` exists). So `modules(<old path>)` is never compared with the imports of the files main changed.
**Evidence**: Take the case #613 is mainly about. The patch moves `src/pkg/core.py` to `src/pkg/engine.py`, and after the patch's check started, main adds `src/pkg/caller.py` with `from pkg import core`. `stale_paths` returns nothing because caller.py is not one of the patch's paths. `related` compares caller.py's imports (`pkg`, `pkg.core`) with `modules("src/pkg/engine.py")` and finds no match. The check stands and the pull request merges onto a main that now has a broken import. The new test only covers renaming a function inside a file that keeps its path (`RENAMED`), so it does not exercise this.
**Suggestion**: Pass `left` into `related` and add each left path to `ours` with empty text, as `related` already does for any file it cannot read. Add a Kitchen test where the patch does a `git mv` and main adds a caller of the old module.

### B2

### 2. [warning] Imports of sibling modules by bare name are missed, and this repo's own tests import that way
**Location**: src/jmerge/ready.py:868-880 (`modules`), used by `uses` at 919
**Finding**: `modules` gives a file two possible import names: its full dotted path, and that path without the leading `src`. With `testpaths = ["tests"]` and pytest's default rootdir import mode, the files in `tests/` import each other by bare name, for example `from test_jmerge_fresh import ...` and `from test_tool_calls import LAUNCHES`. At least ten test files do this, including the new `tests/test_jmerge_callers.py`. `modules("tests/test_jmerge_fresh.py")` returns only `("tests.test_jmerge_fresh",)`, so neither direction ever matches.
**Evidence**: Suppose a pull request changes `tests/test_jmerge_callers.py` and main later changes `Kitchen` in `tests/test_jmerge_fresh.py`. That is a dependency change, but `callers_and_dependencies` returns nothing and the stale green stands. The heuristic is tuned to the `src/` layout and silently gives no answer for any other import root.
**Suggestion**: Also count the bare name (the last part) of a file that sits next to the importing file, or of any file in a pytest import root. At the least, add a test for the `tests/` sibling case.

### B3

### 3. [warning] Naming a path anywhere in any file counts as a dependency, so pull requests that only change docs are made stale
**Location**: src/jmerge/ready.py:926 (`if "/" in other and other in text`), applied both ways at 941
**Finding**: A file counts as related if its raw text contains the other file's path, whatever kind of file it is. Because `callers_and_dependencies` also checks `uses(own, ours[own], path)`, a pull request that edits `THIRD_PARTY.md` or `docs/jmerge.md` is made stale every time main touches any path those docs mention. These docs mention `src/jmerge/cli.py`, `src/jmerge/ready.py`, `src/jmerge/ci-paths.txt`, `tests/test_jmerge_callers.py` and more. This pull request itself would be such a case.
**Evidence**: A prose mention is neither a caller nor a dependency of what the check tests. The check is a proxy for the relationship (a substring in the text) rather than the relationship itself. It fails closed, but the cost is real. A guarded pull request with no `fresh-check` gets `it needs a rebase` (cli.py:651-653). Where `fresh-check` exists, the whole `make check` runs again only because a markdown line mentions a file.
**Suggestion**: Limit the path match to files the check can actually execute or load (code, Makefile, CI config). Do not let a pull request's own non-code files pull in main's changes to the paths they mention.

### B4

### 4. [warning] Nothing confirms that T3 accepts the effort option in this shape, so a wrong shape would silently launch at `high`
**Location**: src/jroles/__init__.py:52; tests/test_roles.py:137 and 154; THIRD_PARTY.md:28
**Finding**: THIRD_PARTY.md says `modelSelection.options` is "a list of `{"id": "effort", "value": <level>}`". The repo's copy of T3's schema (`tests/fixtures/t3/t3_thread_launch.json`) declares `"options": {"anyOf": [{}, {"type": "null"}]}`, which accepts any value. So `test_what_it_prints_is_a_model_selection_the_launch_tool_takes` passes whatever `options` contains, and the new parametrized tests only check jroles' own output. "Proves it" asks for the T3 schema to be quoted, but the schema in the repo does not show this shape.
**Evidence**: If T3 expects another shape (for example `{"effort": "medium"}`) or ignores unknown ids, the launch either fails or falls back to the model's default, which is `high` by the PR's own account. That breaks the rule the change exists to enforce, and no test or runtime check would notice.
**Suggestion**: Record the source of the shape in the fixture: either a schema that actually spells out the `options` item shape, or a captured T3 launch that accepted it. Then validate the jroles output against that, not against an `{}` schema.

### B5

### 5. [nit] Each import tree is parsed once per pair of files
**Location**: src/jmerge/ready.py:941
**Finding**: `any(uses(path, text, own) or uses(own, ours[own], path) for own in ours)` calls `imports()`, which runs `ast.parse`, on `theirs[path]` once for every `own`, and on `ours[own]` once for every `path`. That is O(|ours| x |theirs|) parses. `related` also starts one `git show` subprocess per file each time `stale` runs, and `stale` runs for every ready pull request on every pass. The jbus pass has a 300-second limit.
**Suggestion**: Parse each file once: build `imports` and `modules` per file up front, then intersect the sets.
