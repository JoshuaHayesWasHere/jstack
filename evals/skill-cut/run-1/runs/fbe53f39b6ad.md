### Intent
> The user wants threads to be more visible per project, and wants to follow what scouts and crewmates are doing. Each project's row and page gets a Threads band grouped by role. It shows threads that are out with liveness and last write, threads ended today dimmed, and the rest folded, all from `pass.json`. A `#/<project>/thread/<role>/<slug>` drawer shows what a thread is working on: a task's step, or a scout's request with its status (researching, reported, blocked) read from the home's `scouts/`. A project whose last pass left no thread list shows a blind spot, never "none". The view stays read-only and vanilla, and the work is tested from small fixtures.

### Reviewers
- Reviewer A: 8 findings
- Reviewer B: 7 findings
- Both answered the review skill's questions. They converged on three issues: the duplicated row and role tables, the empty band on the page, and the `thread/` folder outside "Where". Each also found a scout-status correctness gap the other missed.

### Act On

1. **An ended scout with no Report still says "researching"** (A1). `request()` decides the state from the file alone, and `threadChip` shows that state ahead of liveness. A scout that crashed or was settled early therefore reads "researching", under an "ended" heading. Following scouts was the user's reason for this band, and this is the one case that needs their attention. Say "researching" only while the thread is out. Show a distinct amber "ended, no report" otherwise, and test it.

2. **`Status: not done` is drawn as a green "reported"** (A2; B6's case-sensitivity point is folded in). Anything other than `blocked` maps to `ok`. The scout skill's own settle check treats anything other than `done` as unfinished, so the page contradicts jbus. The fix:
   - Map `done` to reported, `blocked` to blocked, and anything else to a non-`ok` not-done state.
   - Compare case-insensitively, since `Blocked` currently reads as reported.
   - Test a last Report whose Status is `not done`.

3. **The `scouts/` source always says "ok", and a read error says "No request"** (B1). `seen` never passes `path` or `read`, so a missing or unreadable `scouts/` cannot surface. `request()` also turns every `OSError` into "missing", so the drawer misstates a permission error as an absent file. A view whose job is to name blind spots should not hide its own. The fix:
   - Pass `path` and `read`.
   - Treat only `FileNotFoundError` as missing.
   - Test a home with no `scouts/`.

4. **The project page draws no band when the thread list is empty** (A5, B2). This misses the "Done when" line that the row **and page** have a band, and it disagrees with the row for the same data. Deleting the special case and letting `band()`'s calm state handle zero is both the fix and a simplification. This is distinct from the blind-spot case (no list at all), which must stay as it is.

5. **`about()` duplicates `threadRow()`, and roles live in two positional tables** (A3, B3). Both reviewers found this independently, and the drift has already started: "crews" in one table, "Crewmates" in the other. The fix:
   - Keep one row renderer, with a parameter for the title cell, and call it from both panels.
   - Keep one ordered role table with named fields, and derive the band and filter order from it.
   - Moving `threadChip`/`LIVESAY` out of the shell is welcome if it falls out naturally, but it is not required.

### Consider

- **The `"threads"` magic tag in `health()`, filtered back out by `projectRow`** (A4 as a warning, B5 as a nit). This special case in a shared helper is held together by a prose comment. The fix is small: let `amber()` add the reason itself, or have the row build its chips without that fact. It is worth doing if items 4 and 5 are already reworking this area.
- **The new `panels/thread/` folder outside "Where", and the undocumented `adds.band` hook** (A8, B4). The drawer is required by "Done when", and the panel discovery behind the route likely forces a separate name. Either say so in the PR, or register the drawer from `threads/` and drop the empty stub. Documenting `adds.band` in `panels/__init__.py` is outside "Where" and noted for later.
- **`gates_inside=True` followed by a `re.split` that undoes it** (A6). If the two really are equivalent, deleting the split and its docstring sentence is free. Confirm with the scout-status tests first, because the parse deliberately mirrors `jbus.threads._scouts`.
- **Importing private `_mtime` across modules** (B7). Define the scouts `Source` in `state.py` next to `SCOUTS`, the same way the `PASS_FILE` and `MERGE_LOG` sources are defined. This is cheap and inside "Where".

### Noted
- Unused defaults on `_threads` (A7). They are low impact, and tests may call `_threads` directly.
- One shared "last Report and its Status" helper across jbus, the view and the skill (B6). The helper belongs in `jbus.threads` or `mirror`, which is outside "Where", so it is for later. Only the in-scope part, the Status mapping, is folded into item 2.

### Dismissed
None. Every finding pointed at a concrete line and a concrete effect.

### Agreement Map
- **Agreement:** The reviewers overlapped on structure and scope: the duplication, the empty-band special case, the `health()` tag and the `thread/` folder. That consensus makes item 5 and the empty-band fix solid.
- **Divergence:** They split on correctness, and that split is the valuable part. A traced the scout state against liveness and against the skill's Status rules. B traced the source and read-error paths. Each found a way the page tells the user something false about a scout, which is the exact thing this PR exists to show.
- **Pattern:** The rendering is sound, but the scout-status reader's mapping from file to state is under-specified and under-tested. The three correctness items should be fixed together, with fixtures for an ended scout with no Report, a `not done` Report, and a home with no `scouts/`.

BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Consider
A5: Act on
A6: Consider
A7: Noted
A8: Consider
B1: Act on
B2: Act on
B3: Act on
B4: Consider
B5: Consider
B6: Noted
B7: Consider
