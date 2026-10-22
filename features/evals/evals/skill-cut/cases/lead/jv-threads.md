# jv-threads

## Intent

Task: the user, on the grill page: "we need to make threads more obvious per project, also i want to be able to track the work of scouts and crewmates as well"
Done when:
- each project's row and page has a Threads band, by role (crewmates, scouts, reviewers, home), out first with liveness and last write, ended today dimmed, the rest folded, from `pass.json` `projects[name].threads` (`state.py:769`)
- `#/<project>/thread/<role>/<slug>` opens a drawer of what the thread works on: a task's step, or a scout's request; a task's drawer lists its threads
- the server reads one new read-only source, each scout request's `## Report` and `Status:` line under the home's `scouts/`, to say researching, reported or blocked
- a project whose last pass left no list of threads says so as a blind spot, never as none
- tests of the band, the drawer and the scout status, from small made-up fixtures
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Where: `src/jbus/view/state.py` (`_threads`, a scout status reader), `src/jbus/view/__init__.py` if a route or the read-only config needs it, `src/jbus/view/panels/threads/`, `src/jbus/view/page.html`, the tests
Do not touch: the `jbus-view` unit, port 4388 and the tailnet setup, port 3773; the CSP in `src/jbus/view/__init__.py`; no npm, no CDN, no build step, no framework (vanilla JS and plain CSS in the one page and its panels); what jbus decides or writes (the view only reads, but for `POST /answer`)
Decisions: the user, on the grill page reports/jview-buildout.html (sent before 22:47 ET 2026-10-14; the page session ended by him), every card answered as recommended: a bare link opens an overview (the machine row once, one waits band, a row per project); hash routes with one hashchange handler; a header and a sidebar, chips on a phone; one /stack.json; one vanilla file ("keep it vanilla and as fast as possible"); six pull requests, the bare link first; a word cap of 250 for the overview and 150 for a project; noticed kept out of the count and labelled "not counted"; Linear-style keys. His steers there: retired projects are not shown (a link to one says there is no such project); hovering any shape or mark shows its tip; a Threads band per project so scouts and crewmates can be followed. The scout report is scouts/jview-buildout.md and the mockups are reports/jview-buildout/ (mockup-b is the base). A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/reports/jview-buildout/mockup-b.html, its Threads band and thread drawer

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

### 1. [Warning] A scout that ended without a Report still says "researching"
**Location**: src/jbus/view/page.html:560 (`threadChip`, `word`); src/jbus/view/state.py:715-736 (`request`)
**Finding**: `request()` decides the state from the file alone. When there is no `## Report`, the state is always `researching`. `threadChip` then shows `q.state` ahead of the thread's liveness. Take a scout thread with `live: "ended"` whose request has no Report, because the thread crashed, was interrupted or was settled early. Its chip reads "researching 2h00", dimmed. The drawer (thread/panel.js `works`) says "researching: Its request has no Report yet" right under a heading of "ended".
**Evidence**: The task asks for the band to tell the user what scouts are doing. A scout that stopped without reporting needs his attention, and this is exactly the case where the page says it is still working. No test covers a scout that ended with no Report. In `a_day_of_threads` the researching scout is `waiting` and the ended scout has a Report.
**Suggestion**: Only say `researching` while `t.out`. For an ended scout with no Report, show a distinct word such as "ended, no report" with the amber/gap chip, and add a test for it.

### A2

### 2. [Warning] `Status: not done` is shown as a green "reported"
**Location**: src/jbus/view/state.py:734
**Finding**: Any Status other than `blocked` becomes `reported`. The panel's `REQ` table draws that with chip class `ok` and the text "Its Report is written". The scout template (`templates/scout-report.md`) allows `done | not done | blocked`. The scout skill's own settle check (`skills/scout/SKILL.md:196-200`) treats anything but `done` as "stay: the Report does not say Status: done".
**Evidence**: A scout that reports "not done" shows the same green state as a finished one, while jbus still treats it as unfinished. The `rye-tin` fixture in `test_each_scouts_request_says_researching_reported_or_blocked` writes `not done` and then appends a later `done`. So the case where the last Report is `not done` is never checked on its own.
**Suggestion**: Map `done` to `reported`, `blocked` to `blocked`, and anything else to a separate not-done state, or at least to a non-`ok` chip. Test a last Report whose Status is `not done`.

### A3

### 3. [Warning] The same thread row is written twice, and the role names are kept in two tables
**Location**: src/jbus/view/panels/thread/panel.js:8 (`about`); src/jbus/view/panels/threads/panel.js:8 (`threadRow`); src/jbus/view/page.html:547 (`ROLE`); src/jbus/view/panels/threads/panel.js:3 (`ROLES`)
**Finding**:
- `about(t)` copies `threadRow(t)` line for line: the queued, pending and page notes, the started and last-wrote text, and the liveness chip. The only difference is the title, which is a `<code>` in one and an `openBtn` in the other.
- The PR adds a second role table, `ROLE` in page.html, with shape, singular, plural and description, beside the existing `ROLES` in the threads panel with key, plural and singular.
- `band()` walks `ROLES.slice(0, 4)` only to index into `ROLE[r[0]][2]`. Both tables are positional arrays, so the field meanings are a convention to remember: `r[0]`/`r[1]`/`r[2]`/`r[3]` mean different things in each table.

**Evidence**: Adding a role, or a new "more" note on a thread, now means editing two places in two files.
**Suggestion**: Move `threadRow` to page.html next to `threadChip`, give it a parameter for the title, and use it in both panels. Fold `ROLES` into `ROLE`, as one ordered list of objects with named fields, and derive the filter and band order from it.

### A4

### 4. [Warning] A tag added to `health()` only so the row can remove that chip again
**Location**: src/jbus/view/page.html:720 and :768
**Finding**: A fourth element, `"threads"`, is added to one tuple of `health()`. `projectRow` then filters `x[3] !== "threads"` to drop it. The chip stays in `health()` only because `amber()` (line 724) still uses it for the sidebar dot. The doc comment had to be rewritten to explain the exception.
**Evidence**: This is a special case built into a shared helper. Any new caller of `health()` that draws chips has to know about the magic tag.
**Suggestion**: Take the threads chip out of `health()`. Let `amber()` add the "the last pass left no list of its threads" reason itself, or let the band supply it.

### A5

### 5. [Nit] A project page whose pass listed no threads has no band, though its row does
**Location**: src/jbus/view/page.html:805
**Finding**: `S.threads && !S.threads.length ? "" : band(...)` leaves the band out when the list is empty. The same project's row on the overview draws a calm "Threads 0 out" band.
**Evidence**: The first "Done when" line says "each project's row and page has a Threads band". The page and the row now differ for the same data, and the special case needs its own comment.
**Suggestion**: Draw the band on the page as well, the same calm band the row draws.

### A6

### 6. [Nit] `gates_inside=True` is applied and then undone
**Location**: src/jbus/view/state.py:727-732
**Finding**: `mirror.sections(..., gates_inside=True)` keeps a `## Gate` heading inside the Report's body. The next line, `re.split(r"^## ", ...)[0]`, cuts the body at that same heading again.
**Evidence**: Without `gates_inside`, the Report's body already ends at the gate, so `reports[-1]` would be the same text as `own`.
**Suggestion**: Call `mirror.sections(whole)` and delete the `re.split`, along with the docstring sentence that explains it.

### A7

### 7. [Nit] Default parameters on `_threads` that no caller uses
**Location**: src/jbus/view/state.py:738
**Finding**: `home: Path | None = None, day: str = ""` are optional, but the only caller, `Read.out`, always passes both. The defaults bring an extra `home is not None` branch and a `day and ...` guard with them.
**Suggestion**: Make both parameters required and drop the guards.

### A8

### 8. [Nit] A new panel folder outside the "Where" line, and a new `adds` key the panel docs don't mention
**Location**: src/jbus/view/panels/thread/panel.py:1, src/jbus/view/panels/thread/panel.js:1
**Finding**: The "Where" line names `src/jbus/view/panels/threads/`. This PR adds a second panel, `panels/thread/`. Its `panel.py` is an empty stub with `FIRST = True` and `build` returning `{}`. It also adds a new `adds.band` hook. The panels contract in `src/jbus/view/panels/__init__.py` documents only `adds.task` and `adds.you`. That file is outside "Where", so this is noted for later.
**Evidence**: The `thread/<role>/<slug>` route probably forces a separate folder. Even so, it is a file outside "Where", and the new hook goes undocumented.

### B1

### 1. [warning] The `scouts/` source always reports "ok", even when there is nothing to read
**Location**: src/jbus/view/panels/threads/panel.py:17 (`Source(f"{SCOUTS}/", "server", lambda read: {"at": _mtime(read.home / SCOUTS)}, 145)`)
**Finding**: `seen` returns only `at`. It never passes `read` or `path` to `_source` (state.py ~858), so the defaults apply: `read=True` and `path=None`. The result is always `"ok"`, including when the home has no `scouts/` directory or cannot read it.
**Evidence**:
- `_source` returns "missing" only when it gets a `path` that does not exist, and "unreadable" only when `read` is false. This source can produce neither.
- The new stack test sets up `larder` and `pantry` with no `scouts/` directory, and they would still show `scouts/ ok`.
- `request()` makes it worse. It catches every `OSError` (state.py, `except (OSError, ValueError)`), so a permission error becomes `"missing"`. The thread drawer then says "No request `scouts/<slug>.md` in the home", which is wrong for a file that exists but cannot be read.
- `at` is the directory's mtime. Appending a `## Report` to an existing request does not change it, so `at` cannot show when a report was last written.
- The test (`test_each_scouts_request_says_researching_reported_or_blocked`) only covers the case where the directory exists.

**Suggestion**: Return `{"at": ..., "read": (home/SCOUTS).is_dir(), "path": home/SCOUTS}`. Treat only `FileNotFoundError` as `missing` and anything else as unreadable. Add a test with no `scouts/` directory.

### B2

### 2. [warning] On a project's page, an empty thread list draws no band, so not every page has one
**Location**: src/jbus/view/page.html:163 (`put($("band"), S.threads && !S.threads.length ? "" : band(PROJECT, S.threads, false))`)
**Finding**: The "Done when" line says each project's row **and page** has a Threads band. On the page, a pass that listed zero threads draws no band. The same data on the overview row draws a calm "Threads 0 out" band, because `projectRow` calls `band(...)` unconditionally.
**Evidence**: The two places now disagree on the same input. The only reason given is a prose comment ("its threads card says 0 out"), and no test covers the empty-list case on either surface.
**Suggestion**: Draw the band in both places and let `band()`'s `calm` state handle zero. That removes the special case.

### B3

### 3. [warning] The thread drawer's `about()` is a near-copy of `threadRow()`, and the role tables are duplicated
**Location**: src/jbus/view/panels/thread/panel.js:180-187 (`about`); page.html:100-107 (`ROLE`)
**Finding**:
- `about(t)` repeats `threadRow(t)` in threads/panel.js line for line: the `more` list for queued, pending and page, the liveness chip, and the started/last-wrote line. Only the title cell differs.
- `ROLE` in page.html is a second role table (shape, singular, plural, description) next to the existing `ROLES` in threads/panel.js (key, plural, singular). The band reads both: it iterates `ROLES.slice(0, 4)` and labels each row with `ROLE[r[0]][2]`.
- `threadChip`, `threadAt`, `LIVESAY` and `ROLE` live in the page shell, although the threads panels are their only users.

**Evidence**: Two copies of the same row renderer will drift. Two role tables with different column orders and different words ("crews" in `ROLES`, "Crewmates" in `ROLE`) already disagree on what a role is called.
**Suggestion**: Keep one role table and one row renderer in threads/panel.js. Give `threadRow` a flag for the title link, and have the thread drawer call it. Move `threadChip`/`ROLE`/`LIVESAY` out of page.html into the threads panel.

### B4

### 4. [warning] Files changed outside the "Where" line
**Location**: src/jbus/view/panels/thread/panel.py:1, src/jbus/view/panels/thread/panel.js:1
**Finding**: The "Where" line names `src/jbus/view/panels/threads/`. This change adds a second panel directory, `panels/thread/`.
**Evidence**:
- `thread/panel.py` is a stub: `FIRST = True`, `SHAPE = {}`, and `build` returns `{}`. It exists only so that panel discovery registers a `thread` drawer kind for the `#/<project>/thread/...` route.
- `tests/fixtures/jbus-view/probe.js` is also changed. It counts as "the tests", so that is acceptable.

**Suggestion**: If the router needs a separate panel name, say so in the PR. Otherwise, register the drawer from the threads panel and drop the empty module.

### B5

### 5. [nit] `health()` marks the threads chip with a string in a fourth tuple slot, and only the row filters it out
**Location**: src/jbus/view/page.html:136 and :152
**Finding**: A fourth element `"threads"` was added to one tuple of `health()`, and `projectRow` filters it out with `x[3] !== "threads"`. The comment at :128-129 explains this in prose.
**Evidence**: Nothing ties the string to the filter. Renaming the string, or adding another band-drawn chip, would break the filter without any error. The other callers of `health()` (the sidebar dot) take the 4-tuple without the filter.
**Suggestion**: Give `health()` a parameter or a named flag such as `{band: true}`, or have the row build its chips without the threads fact.

### B6

### 6. [nit] The scout Report parse duplicates jbus's own rules, and the two disagree
**Location**: src/jbus/view/state.py:389-409 (`request`)
**Finding**: `request()` copies the parse in `jbus.threads._scouts`: `mirror.sections(..., gates_inside=True)`, filter on `REPORT`, take `reports[-1]`. It then adds its own rule for the Status line (the first `Status:` before the next `## `, with "blocked" as the first word). The scout skill's settle check reads `Status:` with awk, which keeps the last one in the Report region.
**Evidence**: There are now three readers of the same Status line with different rules. One example of the gap: a Report that says `Status: Blocked` (capital B) is shown as "reported".
**Suggestion**: Put the "last Report and its Status" helper in `jbus.threads` or `mirror`, and call it from both places. Note that this is outside the "Where" line, so it is for later.

### B7

### 7. [nit] A private helper is imported across modules
**Location**: src/jbus/view/panels/threads/panel.py:9 (`from jbus.view.state import ..., _mtime`)
**Finding**: The panel imports the underscore-private `_mtime` from state.py. Other sources build their `seen` inside state.py, for example `kept` and `_merges`.
**Suggestion**: Define the scouts `Source` in state.py next to `SCOUTS`, as is done for `PASS_FILE` and `MERGE_LOG`, and import the constant.
