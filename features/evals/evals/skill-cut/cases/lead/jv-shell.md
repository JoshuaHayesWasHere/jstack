# jv-shell

## Intent

Task: the user: "there is no header or sidebars, navbars or helpers ... in general the UI / UX feels subpar"
Done when:
- a header with the name, where you are, and the time of the last read
- a sidebar with "All" first, then every project with its waits count and a health dot; under 900 px it becomes a row of chips
- Room, jbus and Runners are drawn once, as the machine's, and never inside a project; project facts are never in the machine row
- the Bus card no longer wraps one letter per line at 1440; there is no sideways scroll at 1440, 900 and 390 wide, which the browser tests check
- empty lanes do not take a row each: only the steps that hold a task are drawn, with the rest folded
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Where: `src/jbus/view/page.html`, `src/jbus/view/panels/` (pulse, room, checks, bus), `tests/test_jbus_view_page.py`
Do not touch: the `jbus-view` unit, port 4388 and the tailnet setup, port 3773; the CSP in `src/jbus/view/__init__.py`; no npm, no CDN, no build step, no framework (vanilla JS and plain CSS in the one page and its panels); what jbus decides or writes (the view only reads, but for `POST /answer`)
Decisions: the user, on the grill page reports/jview-buildout.html (sent before 22:47 ET 2026-10-14; the page session ended by him), every card answered as recommended: a bare link opens an overview (the machine row once, one waits band, a row per project); hash routes with one hashchange handler; a header and a sidebar, chips on a phone; one /stack.json; one vanilla file ("keep it vanilla and as fast as possible"); six pull requests, the bare link first; a word cap of 250 for the overview and 150 for a project; noticed kept out of the count and labelled "not counted"; Linear-style keys. His steers there: retired projects are not shown (a link to one says there is no such project); hovering any shape or mark shows its tip; a Threads band per project so scouts and crewmates can be followed. The scout report is scouts/jview-buildout.md and the mockups are reports/jview-buildout/ (mockup-b is the base). A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/reports/jview-buildout/mockup-b.html, with a's Runners machine card grafted in, as the report says

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

### 1. [warning] The sidebar stays empty for up to 15 s on a link to a project that does not exist
**Location**: src/jbus/view/page.html:1002 (`poll`, the `/stack.json` request on a project page)
**Finding**: The project page asks for `/stack.json` with `if (mine === turnOf) { STACK = st; if (S) render(); }`. On a link to a project that is not there, `/state.json` returns 404 and sets `S = null` (line 1005). If that 404 arrives before the `/stack.json` answer (a likely order), the 404 path renders while `STACK` is still null, so the project list is empty. When `STACK` then arrives, `if (S)` is false and nothing is drawn again. The sidebar shows nothing until the next poll's 404 calls `render()`, up to `POLL` (15 s) later. The same guard skips a render whenever `S` is null.
**Evidence**: `renderSide` builds `ps` from `STACK.projects`, and the only `render()` after the stack arrives is behind `if (S)`. No test covers a fresh load of a no-such route followed by a look at `seen["side"]["items"]`.
**Suggestion**: Call `render()` without the `S` guard, since `put` already skips parts that did not change. Add a test that loads `#/nope` and checks the sidebar items at the first poll.

### A2

### 2. [warning] The sidebar's health dot and the overview row disagree on what "unwell" means
**Location**: src/jbus/view/page.html:670 (`troubles`)
**Finding**: `troubles(p)` is a second copy of the health-to-amber mapping that `projectRow`'s chips already contain (lines 716–723), and the two do not match. `projectRow` marks `Blind N` amber when `h.blind > 0`. `troubles` ignores `h.blind`, and it treats `threads == null` as trouble while the row only marks that chip. A project with blind spots and nothing else wrong gets an amber "Blind 6" chip on its row but a green dot in the sidebar.
**Evidence**: Compare `chip(h.blind ? "op" : "ok", ...)` with the four `said.push` branches in `troubles`, none of which reads `blind`.
**Suggestion**: Use one function that returns a `[state, inner, tip]` list per health fact. The row's chips and the sidebar's dot/tip both read from it, with the dot amber if any entry is `op`. That removes the duplicated mapping.

### A3

### 3. [warning] "The time of the last read" shows the current time while the server is gone
**Location**: src/jbus/view/page.html:752
**Finding**: The header now says `"read " + hm(NOW, true)` with the title "The time of the last read of the server". But after `MISS` failed polls, `lost()` sets `NOW = Date.now()` (line 992) and calls `render()`. `jb()` still returns `S.jbus` from the old read, so the header shows "read <now>" and moves forward on every failed poll. That is exactly the case where the last-read time matters. Before this change the same value had a neutral label; the new wording makes it a claim that is wrong.
**Evidence**: `lost` → `NOW = Date.now()` → `render` → the `J` branch → line 752.
**Suggestion**: Keep the time of the last answer as its own value (for example, set it in `took`/`tookStack`) and show that, not `NOW`.

### A4

### 4. [warning] Moving the header and sidebar out of the word count loosens the user's 150/250 caps, and the new SHELL cap only works at three projects
**Location**: tests/fixtures/jbus-view/probe.js:104, tests/test_jbus_view_page.py:100
**Finding**: `words` now counts only `<main>`, and the header plus sidebar go into a separate `shell` total. The machine cards were inside `<main>` on the overview, so they used to count toward the 250. Now they count toward neither cap, and the first screen can carry about 26 more words than the user's limit. `SHELL = 30` is a fixed number, but the module docstring says the shell "grows by one name and one count for each project". Today's three projects already come to about 26 words, so a fifth project fails the test even though nothing is wrong with the page.
**Evidence**: The docstring at test lines 4–6 and `SHELL = 30`. Only three-project scenes are tested.
**Suggestion**: Either count the shell inside the caps the user set, or make the shell's limit a function of the project count (a base plus 2 × projects) and test it with more projects than today.

### A5

### 5. [warning] page.html goes from 979 to 1067 lines
**Location**: src/jbus/view/page.html
**Finding**: This change pushes the file past 1,000 lines. The new shell code (`machineOf`, `mitem`, `machineRow`, `troubles`, `renderSide`, `renderHeader`) is a separate concern and could live on its own the way the panels do. the user asked for "one vanilla file", so this may be intended. If so, the PR should say so; otherwise the split is noted for later, since a new file would sit outside the "Where" line.

### A6

### 6. [nit] The sidebar's sticky offset assumes the header is 50 px tall
**Location**: src/jbus/view/page.html:50
**Finding**: `.side { position: sticky; top: 50px; max-height: calc(100vh - 50px) }` hard-codes the header's height. The header has `flex-wrap: wrap` and is sticky down to 640 px. When it wraps (a long project name in the crumbs at 900–1100 px), it grows past 50 px and the sticky sidebar slides under it (header `z-index: 5`). Nothing ties the 50 to the header's real size.
**Suggestion**: Use a CSS variable shared by `.hdr` and `.side`, or make the header and the shell one grid so the sidebar does not need a fixed offset.

### A7

### 7. [nit] The machine row disappears where the page has no project read
**Location**: src/jbus/view/page.html:644 (`machineOf`)
**Finding**: `return STACK && !PROJECT ? STACK.machine : null` means that on a project route with no `S` (the first load, or a project that does not exist), the machine is not drawn, even when `STACK.machine` is already there. The new test docstring says the machine is "drawn once, on every view".
**Suggestion**: Fall back to `STACK.machine` (without drawers) whenever there is no `S`.

### A8

### 8. [nit] The theme control changed from three buttons to a cycle button, without a test
**Location**: src/jbus/view/page.html:1047 (`show`), 411
**Finding**: The Auto/Light/Dark group became one button that cycles. The task did not ask for that; only its position in the header did. The new `NEXT`/`NAME` cycling and its aria-label are not tested: the only theme test drives `#theme=` from the address bar.
**Suggestion**: Keep the three-button group in the header, or add a test that clicks `#theme` and checks the order auto → light → dark → auto and the stored value.

### B1

### 1. [warning] The page's word caps are loosened by counting the header and sidebar separately
**Location**: tests/fixtures/jbus-view/probe.js:103-104; tests/test_jbus_view_page.py:100 (`SHELL = 30`)
**Finding**: `words` used to count the whole `document.body`. Now it counts only `main`, and the header and sidebar go into a separate `shell` count capped at 30. The machine row used to sit inside `main` and was counted (on the overview it was `#machine` inside `#stack`). Now it is in the sidebar and falls outside the cap. The header's title, read time and theme control were counted too, and now are not.
**Evidence**: the user's decision was "a word cap of 250 for the overview and 150 for a project", meaning what the first screen shows. The tests now allow up to 280 and 180 words on that screen. The new content was not made to fit the cap; it was moved out of what the cap measures. That is a proxy check.
**Suggestion**: Keep `words` over the whole visible first screen (main + header + side) and hold that total to `WORDS` / `EVERY`. A separate shell count can stay as a diagnostic if wanted.

### B2

### 2. [warning] `SHELL = 30` only fits the fixture's three projects
**Location**: tests/test_jbus_view_page.py:100, and the docstring added at lines 4-6
**Finding**: The docstring says the shell "grows by one name and one count for each project", yet the cap on it is a fixed 30.
**Evidence**: An estimate with the fixture: header about 7 words, sidebar (All plus 3 projects) 8, "This machine" 2, machine items about 9, so about 26. Two more projects pass 30. The cap describes the test data, not a design limit. It will fail on growth that is expected, or someone will raise it without thinking.
**Suggestion**: Make the cap a function of the project count (base + 2 per project), or fold it into finding 1's single total.

### B3

### 3. [warning] On a project page, the jbus item takes `unwell` from a `/stack.json` up to a minute old, or from nothing
**Location**: src/jbus/view/page.html:645 (`machineOf`)
**Finding**: Everything else in the project-page machine row comes from that project's fresh `/state.json` (`S.jbus`, `S.room`, `S.checks.runners`). `unwell` alone comes from `STACK.machine.unwell`, which is refreshed every fourth poll (line 1002). When the stack request has failed, `STACK` is null, `unwell` becomes `[]`, and the jbus item shows `ok`/"passing" with no machine source named.
**Evidence**: The `/stack.json` failure handler is a silent `function () {}` (line 1002). So a machine source being unreadable (e.g. `status.json`, the timer, `runner units`) can disappear from the jbus item while the rest of that row is current. The old pulse card computed this from `S.sources`, which the page still has. The sources are declared `machine=True` in the panel `.py` files.
**Suggestion**: Derive `unwell` from the project's own read: `S.sources` filtered to machine sources not `ok` and not `by: "session"`. If `S.sources` lacks a `machine` flag, have the server add it. That server change is outside the "Where" line, so it is noted for later. Either way, one read feeds the whole row.

### B4

### 4. [warning] page.html grows from 979 to 1067 lines with no split
**Location**: src/jbus/view/page.html (the new shell block at about lines 637-711, plus the CSS at lines 44-67)
**Finding**: The change pushes the one page past 1,000 lines. About 90 of the added lines are a self-contained unit: `machineOf`, `mitem`, `machineRow`, `troubles`, `renderSide`, `renderHeader`, and the shell CSS.
**Evidence**: `src/jbus/view/panels/` already exists to break the page into per-part scripts that are inlined server-side, so no build step is needed. A small `shell` script in that pattern would keep the page under 1,000 lines and still be one served file. Rubric question 5 asks for this.
**Suggestion**: Move the shell renderers into their own inlined script, using the mechanism the panels use. If that needs a change in `__init__.py`/`state.py`, it is outside the "Where" line and is noted for later.

### B5

### 5. [warning] Project health is now judged by two separate rule sets
**Location**: src/jbus/view/page.html:670-678 (`troubles`) versus the existing row chips at line 720
**Finding**: `troubles(p)` rewrites the rule "bus is bad if `failed_wakes || last_error`" and the checks error/failed rule, which the overview row chips already apply (line 720). The sidebar dot and the row chips can now disagree as soon as either one is edited.
**Evidence**: The two places already differ. `troubles` makes the dot amber when `threads == null` or any source is unwell, and the row chips have their own logic. Line 673 also prints "0 failed wakes, last error: X" when only `last_error` is set, because `plural(b.failed_wakes, …)` runs even when `failed_wakes` is 0. The row chip at line 720 guards against that case.
**Suggestion**: Give each health part one helper that returns `{e, say}`, and use it for both the row chips and the sidebar dot and tooltip.

### B6

### 6. [nit] The "no such project" page drops the machine row
**Location**: src/jbus/view/page.html:644-647 (`machineOf`)
**Finding**: With `NOSUCH` set, `PROJECT` is truthy and `S` is null, so `machineOf` returns null. The machine row and its "This machine" heading are hidden, even though `STACK` has been fetched (line 1002 fetches it when `!STACK`).
**Evidence**: The new test docstring says the machine is "drawn once, on every view". The not-found view is a view.
**Suggestion**: Fall back to `STACK.machine` whenever there is no project read.

### B7

### 7. [nit] A comment now contradicts the new poll code
**Location**: src/jbus/view/page.html:994 (just before the changed lines 995-1002)
**Finding**: "One request a poll, for the view in front." A project page now also asks `/stack.json` on its first poll and every fourth poll after that.
**Suggestion**: Update the comment, as was done for the header comment at line 443.

### B8

### 8. [nit] The sidebar's sticky offset is hard-coded to the header's height
**Location**: src/jbus/view/page.html:50 (`top: 50px; max-height: calc(100vh - 50px)`)
**Finding**: The header is `flex-wrap: wrap`, so its height depends on content: long crumbs, or "asking the server" in the read slot. If it wraps between 900 and 1100 px wide, the sticky sidebar slides under it.
**Suggestion**: Set a CSS custom property for the header height and use it in both places, or give the header a fixed `height` / `nowrap`.

### B9

### 9. [nit] The theme control was redesigned beyond what the task asked
**Location**: src/jbus/view/page.html:1046-1060, and the `.theme` CSS at lines 66-67
**Finding**: The three-button Auto/Light/Dark group is now one button that cycles through them. The task asked for a header; it did not ask to change how the theme is picked. You now need up to two taps to reach a look, and the control's state is only in its label.
**Suggestion**: If space in the header forced this, say so in the PR. Otherwise keep the three-button group inside the header.
