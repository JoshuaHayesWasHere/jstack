### Intent
> Task: the feature playbook's step 4 (size) has never fired, because 0 briefs carry a size. Also, a brief naming `Playbook: fix` or `Playbook: feature.` launched with no playbook. The change adds `Size: S|M|L|XL` to `templates/brief.md` and the plan-entry template. `parse.py` and `dispatch.py` then refuse a brief with no size, or one whose playbook is not a file in `playbooks/` (or `none`), each with a one-line reason. Rows approved before the merge are grandfathered. There are parser tests for `fix`, `feature.`, no size, and a good brief. `make check` and `jgauge test-slot -- make check` pass, and no approved row is stranded.

### Reviewers
- Reviewer A: 6 findings
- Reviewer B: 4 findings
- Both reviewers answered the review questions. They agree on the two main dispatch issues and on the `_head` duplication.

### Act On

**1. The grandfather cutoff is a guessed time from before the merge (A1, B1, merged)**
`SHAPED_SINCE = "2026-10-15 11:15 ET"` (`src/jbus/dispatch.py:60`) is earlier than the PR's own commit (11:22). Any brief written from the old template and approved between 11:15 and the merge gets gated with "no Size: line". Adding the line changes the brief's sha, which re-gates it with "brief changed after approval". That leaves the row stranded, which the "no approved row stranded" requirement rules out.
- Both reviewers traced this concrete path through `_ready`.
- The live-queue proof only shows the state when the check ran (latest approval 11:06). It is now 2026-10-16, so the window has been open for a day, and the live queue should be re-checked before merge.
- Fix: set the cutoff at or after the actual merge. Add a test for a row approved after the constant but before the cutoff takes effect.

**2. The cutoff is compared as text, so it depends on the zone and label in `stamp` (A2, B2, merged)**
`at >= SHAPED_SINCE` (`dispatch.py:180/189`) is only correct when jsettings uses `America/New_York` with label `ET`. Another zone shifts the cutoff by hours. An unset label gives `EDT`, and the string comparison is then wrong at the boundary.
- The only thing keeping this correct is the docstring: a rule written in prose, and a proxy instead of the real instant.
- It sits on the same line as fix 1, so fixing both together costs almost nothing.
- Fix: make the cutoff an aware UTC `datetime`. Parse `ran_at` back through the configured zone the way `digest.py:149` already does, and compare instants.

**3. Scout-written briefs reach launch still carrying the template's `Size:` placeholder (A3)**
- Home skill step 1 (`skills/home/SKILL.md:494`) sends a scout's brief straight to step 2, skipping the new `Size:` paragraph at :498.
- The scout skill does not fill `Size:`, so `parse.sized` rejects every such brief as "the template's own text".
- The result is a concrete path to a stranded row for every scout-written brief approved after the cutoff. Only one reviewer raised it, but the path is real and in scope.
- Fix: in home step 1, have the home set `Size:` from the plan entry on a scout's brief, alongside the existing `Home:` check. That file is in **Where**.
- The matching scout-skill change is outside **Where**, so it is noted for later.

### Consider

**4. Any file in `playbooks/` passes, including ones a crewmate never runs (A4)**
- Briefs naming `orchestrate`, `expert-*`, `opening-a-pr`, and similar playbooks pass the check. At launch the crew block prints `not a crewmate's` and the crewmate runs with no playbook, which is the failure this task set out to stop.
- The "Done when" line is met as worded. Meeting the intent behind it costs one `elif` in `playbook()` that reads `Run by:`.
- I lean toward doing it, but the rule the user approved was literally "a file in `playbooks/`".

**5. `_head` duplicates the loop in `proves_it` (A5, B4)**
- `_head` is new in this PR and sits right beside an identical loop.
- Having `proves_it` call `_head` is a two-line change that leaves one definition of "a brief's head".
- It is cheap and both reviewers raised it, but it is not a blocker.
- `dispatch.designed` has the same loop, but it is unchanged here, so that is noted for later.

### Noted
- **A6**: `_SIZES` repeats `SIZES` by hand. It is real drift risk but small, and the tests pin the string anyway.
- **B3**: the gate test takes its expected `why` values from `parse.sized` and `parse.playbook`. The test still executes dispatch, and `test_briefs.py` pins the parser wording literally, so the wording is covered, just in another file. Writing out literals would make it stricter, but that is optional.

### Dismissed
- None. Every finding was grounded in a changed line, and none was a pure preference.

### Agreement Map
- The reviewers agreed independently on the two cutoff problems (1, 2) and on the `_head` duplication. Both cutoff problems are on the same line and share one fix, which makes them the clearest blocker.
- They diverged in coverage:
  - A went further into intent: the scout path (3) and non-crewmate playbooks (4). Those are the findings showing that the task's own failure mode can still happen through paths the "Done when" wording did not name.
  - B looked at test quality (B3).
- The pattern suggests the parser logic is sound and the weaknesses sit at the edges: when the rule takes effect, and which producers of briefs are covered. That is where the rework should go.

BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Consider
A5: Consider
A6: Noted
B1: Act on
B2: Act on
B3: Noted
B4: Consider
