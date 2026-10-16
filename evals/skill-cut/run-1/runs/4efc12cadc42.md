### Intent
> The user found the view lacking: "there is no header or sidebars, navbars or helpers ... in general the UI / UX feels subpar". This PR should add the following, within `page.html`, its panels and the page tests, with no framework, build step or CSP change:
> - a header with the name, the current location and the time of the last read
> - a sidebar with "All" and then each project with its waits count and a health dot, which becomes chips under 900 px
> - the machine facts (Room, jbus, Runners) drawn once and never inside a project
> - no wrapped Bus card and no sideways scroll at 1440, 900 and 390 px
> - only the lanes that hold a task drawn, with empty lanes folded
> - the user's caps kept: 250 words for the overview and 150 for a project

### Reviewers
- Reviewer A: 8 findings (5 warnings, 3 nits)
- Reviewer B: 9 findings (6 warnings, 3 nits)
- They converged on most of the same ground. The review skill's questions were asked and answered by both.

### Act On

1. **The word caps were loosened by measuring less, not by fitting the content** (A4, B1, B2). `words` now counts only `<main>`. The header and sidebar go into a separate fixed `SHELL = 30`. On the overview the machine cards used to be inside the 250, and now they count toward neither cap. The user's cap was a decision about what the first screen carries. Moving content out of the measured region is a proxy check, so the test passes while the page grows past the limit. The fixed 30 also contradicts the PR's own docstring, which says the shell grows per project, so it will break at about five projects for no real reason.
   - Fix: count the whole first screen (main, header and side) against `WORDS` / `EVERY`. If the user's caps were meant to cover only the content area, make that case explicitly and scale the shell limit by project count.
   - Add a test with more projects than the fixture's three.

2. **The "read" time in the header shows the current time once the server is gone** (A3). After `MISS` failed polls, `lost()` sets `NOW = Date.now()` and re-renders. The header then says "read <now>" and ticks forward on every failure. That is the one moment the last-read time matters, and the new label turns it into a wrong claim. This is a direct "Done when" line.
   - Fix: keep the time of the last successful answer as its own value and display that.

3. **The sidebar dot and the overview row judge health by two diverging rule sets** (A2, B5). `troubles()` re-implements the chip logic and already disagrees with it:
   - It ignores `h.blind`, so a project gets an amber "Blind 6" chip next to a green dot.
   - It treats `threads == null` differently from the row.
   - It prints "0 failed wakes, last error: X" when only `last_error` is set.

   This is a concrete wrong output today, not a style point. Fix it with one helper per health fact that returns state and tip, read by both the chips and the dot.

4. **The no-project-read path draws an empty or partial shell** (A1, A7, B6). The paths are concrete:
   - On `#/nope`, the 404 usually lands before `/stack.json`. The `if (S) render()` guard then skips the redraw, and the sidebar stays empty for up to 15 s.
   - On the same path, `machineOf` returns null, so the machine row is missing on a view the PR's own docstring says has it.

   The user specifically steered that a retired project's link should say "no such project", so this page is meant to look right. All three are one fix: render when the stack arrives regardless of `S`, and fall back to `STACK.machine` when there is no project read. Add a test that loads `#/nope` and checks the side items and machine row at the first poll.

5. **On a project page, the jbus item can say "passing" with no source behind it** (B3). Everything else in that row comes from the fresh `S`. `unwell` alone comes from `STACK`, which is refreshed every fourth poll. The `/stack.json` failure handler is silent, so when `STACK` is null `unwell` becomes `[]` and the item shows ok. That is a false all-clear, the worst kind of status bug.
   - Minimum in scope: show the item as unknown, not ok, when `STACK` is absent.
   - Better: derive `unwell` from `S.sources` as the old pulse card did. If that needs a `machine` flag from the server, the server change is outside "Where" and noted for later.

### Consider

- **`page.html` passes 1,000 lines (979 → 1067)** (A5, B4). There is a real tension here. The user said "one vanilla file". However, `panels/` already inlines separate scripts server-side into one served page, so a `shell` panel would honour that and keep the page under 1,000 lines.
  - If the panel loader picks up a new file without touching `__init__.py`, this is cheap and in scope.
  - If not, it is noted for later, and the PR should say why it stayed inline.
- **The theme control was redesigned from three buttons to one cycling button** (A8, B9). The task asked to put the theme control in the header, not to change how it works. The new cycling is also untested. Either keep the three-button group in the header, or state that header space forced the change and add a test that clicks through auto → light → dark → auto and checks the stored value.
- **The sidebar's sticky offset is hard-coded at 50 px** (A6, B8). The header wraps, for example with long crumbs at 900 to 1100 px, and then the sidebar slides under it. A shared CSS variable fixes it at almost no cost. It is a visible glitch, but only at some widths with long names.

### Noted
- The comment "one request a poll" at `page.html:994` is now stale (B7). Fix it in passing while touching `poll` for item 4.

### Dismissed
- None. Neither reviewer padded with style preferences. Every finding traced to a changed line and a concrete effect. The nits are real but small.

### Agreement Map
The reviewers agreed independently on six issues:
- the word-cap loosening
- the duplicated health rules
- the 1,000-line crossing
- the missing machine row on the not-found view
- the hard-coded sticky offset
- the theme redesign

That consensus makes the cap and health-rule findings the strongest signals. Each reviewer also caught something the other missed, and both are correctness bugs in status display rather than taste:
- **A only:** the timing race that leaves the sidebar empty, and the "read" time that shows now.
- **B only:** the false "passing" from a missing `STACK`, and the stale comment.

The pattern is that the layout work largely meets the brief. The weak spots are the edges: what the page shows when a read is missing, stale or failed, and a test that was relaxed instead of satisfied.

BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Act on
A5: Consider
A6: Consider
A7: Act on
A8: Consider
B1: Act on
B2: Act on
B3: Act on
B4: Consider
B5: Act on
B6: Act on
B7: Noted
B8: Consider
B9: Consider
